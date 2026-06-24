"""
네이버 뉴스 검색 API로 국내 뉴스를 가져오는 수집기.

무료, 하루 25,000회 호출 제한 (개인 규모에서는 여유로움).
공식 문서: https://developers.naver.com/docs/serviceapi/search/news/news.md
"""
import re
import time
from datetime import datetime, timezone

import requests

import config

NAVER_NEWS_URL = "https://openapi.naver.com/v1/search/news.json"
RATE_LIMIT_DELAY = 0.2  # 초당 5회 수준으로 여유 있게 제한
MAX_DISPLAY = 100       # 한 번에 가져올 최대 건수 (API 최대값)

# HTML 태그 제거용 정규식 (네이버 뉴스 응답에 <b>, </b> 등이 포함됨)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
# HTML 엔티티 치환 테이블 (네이버 응답에서 자주 등장하는 것만)
_HTML_ENTITIES = {
    "&amp;":  "&",
    "&lt;":   "<",
    "&gt;":   ">",
    "&quot;": '"',
    "&#039;": "'",
    "&apos;": "'",
}


def _clean_html(text: str) -> str:
    """HTML 태그와 엔티티를 제거해 순수 텍스트로 반환."""
    if not text:
        return ""
    text = _HTML_TAG_RE.sub("", text)
    for entity, char in _HTML_ENTITIES.items():
        text = text.replace(entity, char)
    return text.strip()


def _parse_pub_date(date_str: str):
    """
    네이버 뉴스 API의 pubDate 문자열을 UTC datetime으로 변환.
    형식 예시: "Mon, 23 Jun 2026 10:30:00 +0900"
    """
    if not date_str:
        return datetime.now(timezone.utc)
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(date_str).astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def search_news(query: str, display: int = 20, sort: str = "date") -> list:
    """
    네이버 뉴스 API로 키워드 검색.

    query:   검색어 (종목명, 키워드 등)
    display: 반환 건수 (최대 100)
    sort:    정렬 기준 — "date"(최신순) / "sim"(관련도순)

    반환 항목: {"title", "source", "url", "published_at", "region", "query"}
    """
    config.require("naver_news")
    display = min(display, MAX_DISPLAY)

    try:
        resp = requests.get(
            NAVER_NEWS_URL,
            headers={
                "X-Naver-Client-Id":     config.NAVER_CLIENT_ID,
                "X-Naver-Client-Secret": config.NAVER_CLIENT_SECRET,
            },
            params={
                "query":   query,
                "display": display,
                "sort":    sort,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"[naver_news][error] '{query}' 검색 실패: {e}")
        return []

    items = data.get("items", [])
    results = []
    for item in items:
        title = _clean_html(item.get("title", ""))
        url   = item.get("originallink") or item.get("link", "")
        source = item.get("description", "")  # 출처 필드가 없으면 빈 문자열
        # 출처: link에서 도메인 추출 (네이버 API는 출처 필드 미제공)
        try:
            from urllib.parse import urlparse
            source = urlparse(url).netloc.replace("www.", "")
        except Exception:
            source = ""

        results.append({
            "title":        title,
            "source":       source,
            "url":          url,
            "published_at": _parse_pub_date(item.get("pubDate")),
            "region":       "KR",
            "query":        query,  # 어떤 검색어로 찾았는지 (DB 저장 후 연결에 사용)
        })

    return results


def collect_news_for_stocks(stock_queries: list, display: int = 20) -> list:
    """
    여러 종목(또는 키워드)에 대해 순차 검색.

    stock_queries: [{"ticker": "005930", "name": "삼성전자"}, ...]
    반환: search_news() 결과 리스트에 ticker 필드 추가
    """
    all_news = []
    for sq in stock_queries:
        ticker = sq.get("ticker", "")
        name   = sq.get("name", ticker)
        print(f"[naver_news] '{name}' 뉴스 검색 중... (최대 {display}건)")
        items = search_news(query=name, display=display)
        for item in items:
            item["ticker"] = ticker  # 어떤 종목 검색에서 나왔는지
        all_news.extend(items)
        print(f"[naver_news] '{name}': {len(items)}건 수집")
        time.sleep(RATE_LIMIT_DELAY)

    return all_news
