"""
FRED API로 VIX 등 매크로 지표를 가져오는 수집기.

무료, 호출 제한 매우 넉넉 (하루 수만 건).
공식 문서: https://fred.stlouisfed.org/docs/api/fred/
"""
import time
from datetime import datetime, timezone

import requests

import config

FRED_BASE_URL = "https://api.stlouisfed.org/fred"
RATE_LIMIT_DELAY = 0.5  # API 과부하 방지용 호출 간격(초)

# 수집할 시리즈 목록: {series_id: index_code(market_indices.index_code)}
# 필요에 따라 추가 가능 (예: "T10YIE": "TIPS10Y")
DEFAULT_SERIES = {
    "VIXCLS": "VIX",  # CBOE 변동성 지수
}


def get_latest_observation(series_id: str) -> dict:
    """
    FRED 시리즈의 가장 최근 관측값 1건을 가져옴.
    반환: {"series_id", "index_code", "value", "date", "captured_at"}
    value가 없는 날(예: 주말·휴장일)은 "."으로 와서 None으로 처리.
    """
    config.require("fred")
    try:
        resp = requests.get(
            f"{FRED_BASE_URL}/series/observations",
            params={
                "series_id":      series_id,
                "api_key":        config.FRED_API_KEY,
                "file_type":      "json",
                "sort_order":     "desc",    # 최신순 정렬
                "limit":          5,         # 결측일(.)을 건너뛰기 위해 5건 가져옴
                "observation_start": "2000-01-01",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"[fred][error] {series_id} API 호출 실패: {e}")
        return None

    observations = data.get("observations", [])
    # "."은 데이터 없음 — 유효한 숫자가 나올 때까지 스캔
    for obs in observations:
        raw = obs.get("value", ".")
        if raw == ".":
            continue
        try:
            value = float(raw)
        except ValueError:
            continue

        return {
            "series_id":  series_id,
            "index_code": DEFAULT_SERIES.get(series_id, series_id),
            "value":      value,
            "obs_date":   obs["date"],       # "2025-06-20" 형태
            "captured_at": datetime.now(timezone.utc),
        }

    print(f"[fred][warn] {series_id}: 유효한 관측값이 없습니다.")
    return None


def collect_macro_indices(series_map: dict = None) -> list:
    """
    여러 FRED 시리즈를 순차 수집.
    series_map: {series_id: index_code} 딕셔너리. 생략 시 DEFAULT_SERIES 사용.
    반환 항목: {"series_id", "index_code", "value", "obs_date", "captured_at"}
    """
    if series_map is None:
        series_map = DEFAULT_SERIES

    results = []
    for series_id, index_code in series_map.items():
        print(f"[fred] {series_id}({index_code}) 최신값 수집 중...")
        obs = get_latest_observation(series_id)
        if obs is None:
            continue
        # DEFAULT_SERIES에 없는 series_id는 호출 시 전달된 index_code 사용
        obs["index_code"] = index_code
        results.append(obs)
        print(f"[fred] {index_code}: {obs['value']}  ({obs['obs_date']})")
        time.sleep(RATE_LIMIT_DELAY)

    return results
