"""
DART Open API로 국내 기업의 재무제표를 가져오는 수집기.

무료 API이며 개인 사용 규모에서는 호출 횟수가 충분함.
공식 문서: https://opendart.fss.or.kr/guide/main.do
"""
import io
import json
import time
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

import config

DART_BASE_URL = "https://opendart.fss.or.kr/api"
RATE_LIMIT_DELAY = 0.5  # API 과부하 방지용 호출 간격(초)

# 기업 고유번호 맵을 로컬에 캐싱해 매번 다운로드를 피함
CORP_CODE_CACHE_PATH = Path(".dart_cache/corp_codes.json")
CORP_CODE_CACHE_TTL = 7 * 24 * 3600  # 7일간 캐시 유지

# 분기 번호 → DART 보고서 코드 매핑
REPRT_CODE_MAP = {
    None: "11011",  # 사업보고서 (연간)
    4:    "11011",  # 사업보고서 (연간)
    1:    "11013",  # 1분기보고서
    2:    "11012",  # 반기보고서
    3:    "11014",  # 3분기보고서
}

# 손익계산서에서 추출할 계정명 키워드 (부분 일치로 검색)
# IFRS/K-GAAP, 연결/개별 차이로 계정명이 다를 수 있어 여러 후보를 둠
REVENUE_KEYWORDS       = ["매출액", "수익(매출액)", "영업수익"]
OPERATING_INC_KEYWORDS = ["영업이익"]
NET_INC_KEYWORDS       = ["당기순이익"]

# 모듈 내 메모리 캐시 (같은 프로세스 안에서 중복 다운로드 방지)
_corp_code_map = None


# ──────────────────────────────────────────────
#  기업 고유번호 맵 관련 함수
# ──────────────────────────────────────────────

def _fetch_corp_code_zip() -> bytes:
    """DART에서 전체 기업 고유번호 ZIP 파일을 다운로드."""
    config.require("dart")
    print("[dart] 기업 고유번호 목록(corpCode.xml) 다운로드 중...")
    try:
        resp = requests.get(
            f"{DART_BASE_URL}/corpCode.xml",
            params={"crtfc_key": config.DART_API_KEY},
            timeout=30,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"[dart] 기업 고유번호 ZIP 다운로드 실패: {e}") from e
    return resp.content


def _parse_corp_code_zip(zip_bytes: bytes) -> dict:
    """ZIP 바이트를 파싱해 {종목코드: 고유번호} 딕셔너리를 반환."""
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            # ZIP 안의 XML 파일명을 동적으로 찾음 (CORPCODE.xml 또는 유사명)
            xml_name = next(
                (n for n in zf.namelist() if n.lower().endswith(".xml")), None
            )
            if xml_name is None:
                raise ValueError("corpCode ZIP 안에 XML 파일이 없습니다.")
            with zf.open(xml_name) as f:
                root = ET.parse(f).getroot()
    except (zipfile.BadZipFile, ET.ParseError) as e:
        raise RuntimeError(f"[dart] 기업 고유번호 파일 파싱 실패: {e}") from e

    mapping = {}
    for item in root.findall("list"):
        stock_code = (item.findtext("stock_code") or "").strip()
        corp_code  = (item.findtext("corp_code")  or "").strip()
        # 상장 종목만 포함 (stock_code가 비어 있으면 비상장)
        if stock_code and corp_code:
            mapping[stock_code] = corp_code

    print(f"[dart] 기업 고유번호 맵 생성 완료: 상장 종목 {len(mapping)}개")
    return mapping


def get_corp_code_map(force_refresh: bool = False) -> dict:
    """
    종목코드(ticker) → DART 고유번호 딕셔너리를 반환.

    우선순위:
      1) 모듈 메모리 캐시 (같은 프로세스 내)
      2) 로컬 JSON 파일 캐시 (7일 이내)
      3) DART API에서 새로 다운로드
    """
    global _corp_code_map

    # 1) 메모리 캐시
    if _corp_code_map is not None and not force_refresh:
        return _corp_code_map

    # 2) 파일 캐시 (7일 이내면 재사용)
    if not force_refresh and CORP_CODE_CACHE_PATH.exists():
        age = time.time() - CORP_CODE_CACHE_PATH.stat().st_mtime
        if age < CORP_CODE_CACHE_TTL:
            try:
                with open(CORP_CODE_CACHE_PATH, encoding="utf-8") as f:
                    _corp_code_map = json.load(f)
                print(f"[dart] 기업 고유번호 맵을 파일 캐시에서 로드 ({len(_corp_code_map)}개)")
                return _corp_code_map
            except (OSError, json.JSONDecodeError) as e:
                print(f"[dart][warn] 파일 캐시 읽기 실패, 새로 다운로드: {e}")

    # 3) 새로 다운로드 후 파일에 저장
    zip_bytes = _fetch_corp_code_zip()
    _corp_code_map = _parse_corp_code_zip(zip_bytes)

    try:
        CORP_CODE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CORP_CODE_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(_corp_code_map, f, ensure_ascii=False)
        print(f"[dart] 기업 고유번호 맵을 파일에 저장: {CORP_CODE_CACHE_PATH}")
    except OSError as e:
        # 캐시 저장 실패는 치명적이지 않으므로 경고만
        print(f"[dart][warn] 파일 캐시 저장 실패(무시): {e}")

    return _corp_code_map


# ──────────────────────────────────────────────
#  재무제표 수집 함수
# ──────────────────────────────────────────────

def _parse_amount(amount_str):
    """'302,231,422,988,848' 같은 문자열을 float으로 변환. 파싱 불가면 None."""
    if not amount_str:
        return None
    cleaned = amount_str.replace(",", "").strip()
    if not cleaned or cleaned == "-":
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _match_keyword(account_nm: str, keywords: list) -> bool:
    """계정명이 키워드 목록 중 하나를 포함하는지 확인 (부분 일치)."""
    return any(kw in account_nm for kw in keywords)


def fetch_financial_statements(corp_code: str, year: int, quarter: int = None) -> dict:
    """
    단일 기업의 손익계산서에서 매출액/영업이익/당기순이익을 가져옴.

    연결재무제표(CFS)를 우선 시도하고, 데이터가 없으면 개별재무제표(OFS)로 대체.
    반환: {"revenue": ..., "operating_income": ..., "net_income": ...}
          값을 찾지 못한 항목은 None.
    """
    config.require("dart")
    reprt_code = REPRT_CODE_MAP.get(quarter, "11011")

    for fs_div in ("CFS", "OFS"):
        print(
            f"[dart] → POST fnlttSinglAcntAll.json  "
            f"corp_code={corp_code}  bsns_year={year}  "
            f"reprt_code={reprt_code}  fs_div={fs_div}"
        )
        try:
            resp = requests.get(
                f"{DART_BASE_URL}/fnlttSinglAcntAll.json",
                params={
                    "crtfc_key":  config.DART_API_KEY,
                    "corp_code":  corp_code,
                    "bsns_year":  str(year),
                    "reprt_code": reprt_code,
                    "fs_div":     fs_div,
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            print(f"[dart][error] API 호출 실패 (corp_code={corp_code}): {e}")
            return {"revenue": None, "operating_income": None, "net_income": None}

        status = data.get("status")

        if status == "000":
            # 손익계산서(IS) 항목만 추출
            is_items = [
                item for item in data.get("list", [])
                if item.get("sj_div") == "IS"
            ]

            result = {"revenue": None, "operating_income": None, "net_income": None}

            for item in is_items:
                account_nm = item.get("account_nm", "")
                # 당기금액을 우선 사용, 없으면 당기누적금액으로 대체
                amount = _parse_amount(
                    item.get("thstrm_amount") or item.get("thstrm_add_amount")
                )

                if result["revenue"] is None and _match_keyword(account_nm, REVENUE_KEYWORDS):
                    result["revenue"] = amount
                elif result["operating_income"] is None and _match_keyword(account_nm, OPERATING_INC_KEYWORDS):
                    result["operating_income"] = amount
                elif result["net_income"] is None and _match_keyword(account_nm, NET_INC_KEYWORDS):
                    result["net_income"] = amount

            # 하나라도 값이 있으면 이 재무제표 구분(CFS/OFS)으로 결정
            if any(v is not None for v in result.values()):
                return result

        elif status == "013":
            # 013: 해당 보고서가 아직 없음 — 다음 fs_div로 재시도
            print(f"[dart] {corp_code} {fs_div} {year}년 {quarter or '연간'} 보고서 없음, 다음 구분 시도")
        else:
            msg = data.get("message", "알 수 없는 오류")
            print(f"[dart][warn] API 응답 오류 (corp_code={corp_code}, status={status}): {msg}")
            break  # 재시도해도 같은 오류가 반복되므로 중단

    return {"revenue": None, "operating_income": None, "net_income": None}


def collect_financials(tickers: list, year: int, quarter: int = None) -> list:
    """
    여러 종목의 재무 데이터를 순차 수집.

    반환 항목: {"ticker", "corp_code", "fiscal_year", "fiscal_quarter",
                "revenue", "operating_income", "net_income"}
    """
    corp_map = get_corp_code_map()
    results = []

    for ticker in tickers:
        corp_code = corp_map.get(ticker)
        if not corp_code:
            print(f"[dart] {ticker}: 고유번호를 찾을 수 없음 (상장 종목 코드인지 확인), 건너뜀")
            continue

        label = f"{year}년 {quarter or '연간'}"
        print(f"[dart] {ticker} ({corp_code}) {label} 재무데이터 수집 중...")

        financials = fetch_financial_statements(corp_code, year, quarter)

        results.append({
            "ticker":         ticker,
            "corp_code":      corp_code,
            "fiscal_year":    year,
            "fiscal_quarter": quarter,
            **financials,
        })

        time.sleep(RATE_LIMIT_DELAY)

    return results
