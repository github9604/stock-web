"""
실행 진입점: 해외(미국) 관심종목의 시세를 수집해 DB에 저장.

로컬 실행:
    python scripts/collect_overseas_prices.py

GitHub Actions에서는 동일한 명령이 주기적으로 호출됨
(.github/workflows/collect-overseas-prices.yml 참고).
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.finnhub_collector import collect_quotes
from db.client import get_connection, get_or_create_stock, insert_price_snapshot

# TODO: watchlist 테이블이 채워지면 이 하드코딩 목록 대신
#       "SELECT ticker FROM watchlist JOIN stocks ..." 쿼리로 교체
SAMPLE_WATCHLIST_TICKERS = ["AAPL", "TSLA", "NVDA"]


def main():
    print(f"[start] 해외 시세 수집 시작 - 대상 종목: {SAMPLE_WATCHLIST_TICKERS}")

    quotes = collect_quotes(SAMPLE_WATCHLIST_TICKERS)

    if not quotes:
        print("[warn] 수집된 시세가 없습니다.")
        return

    with get_connection() as conn:
        with conn.cursor() as cur:
            for q in quotes:
                stock_id = get_or_create_stock(
                    cur,
                    ticker=q["ticker"],
                    name=q["name"],
                    market="US",
                    currency="USD",
                )
                insert_price_snapshot(
                    cur,
                    stock_id=stock_id,
                    captured_at=q["captured_at"],
                    price=q["price"],
                    change_pct=q["change_pct"],
                )
                print(f"[saved] {q['ticker']}: {q['price']} ({q['change_pct']}%)")

    print("[done] 해외 시세 수집 완료")


if __name__ == "__main__":
    main()
