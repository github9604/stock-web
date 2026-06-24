"""
Finnhub API로 해외(미국) 종목의 시세를 가져오는 수집기.

무료 티어: 분당 60회 호출 제한.
RATE_LIMIT_DELAY로 호출 사이에 여유를 둬서 제한에 걸리지 않게 함.
"""
import time
from datetime import datetime, timezone

import requests

import config

FINNHUB_BASE_URL = "https://finnhub.io/api/v1"
RATE_LIMIT_DELAY = 1.1  # 분당 약 54회로, 60회 제한에 여유를 둠


def get_quote(ticker: str) -> dict:
    """
    단일 종목의 현재가 정보를 가져옴.
    응답 예시: {"c": 현재가, "pc": 전일종가, "h": 고가, "l": 저가, "o": 시가, "t": timestamp}
    """
    config.require("finnhub")
    resp = requests.get(
        f"{FINNHUB_BASE_URL}/quote",
        params={"symbol": ticker, "token": config.FINNHUB_API_KEY},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def get_company_name(ticker: str) -> str:
    """
    회사명을 가져옴 (stocks 테이블에 처음 등록할 때 사용).
    실패하면 ticker 자체를 이름으로 사용.
    """
    try:
        resp = requests.get(
            f"{FINNHUB_BASE_URL}/stock/profile2",
            params={"symbol": ticker, "token": config.FINNHUB_API_KEY},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("name") or ticker
    except Exception:
        return ticker


def collect_quotes(tickers: list) -> list:
    """
    여러 종목의 시세를 순차 수집.
    반환 항목: {"ticker", "name", "price", "change_pct", "captured_at"}
    """
    results = []
    for ticker in tickers:
        quote = get_quote(ticker)
        current_price = quote.get("c")
        prev_close = quote.get("pc")

        if not current_price or not prev_close:
            # 휴장일/잘못된 티커 등으로 데이터가 없는 경우
            print(f"[finnhub] {ticker}: 데이터 없음, 건너뜀")
            time.sleep(RATE_LIMIT_DELAY)
            continue

        change_pct = round((current_price - prev_close) / prev_close * 100, 2)

        results.append(
            {
                "ticker": ticker,
                "name": get_company_name(ticker),
                "price": current_price,
                "change_pct": change_pct,
                "captured_at": datetime.now(timezone.utc),
            }
        )
        time.sleep(RATE_LIMIT_DELAY)

    return results
