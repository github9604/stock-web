"""
실행 진입점: 관심종목 이름으로 네이버 뉴스를 검색해 DB에 저장.

로컬 실행:
    python scripts/collect_news.py
    python scripts/collect_news.py --display 50   # 종목당 최대 50건

GitHub Actions에서는 동일한 명령이 주기적으로 호출됨
(.github/workflows/collect-news.yml 참고).
"""
import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.naver_news_collector import collect_news_for_stocks
from db.client import (
    get_connection,
    get_or_create_stock,
    insert_news,
    link_news_to_stock,
)

# TODO: watchlist 테이블이 채워지면 이 하드코딩 목록 대신
#       "SELECT ticker, name FROM watchlist JOIN stocks ..." 쿼리로 교체
SAMPLE_STOCKS = [
    {"ticker": "005930", "name": "삼성전자"},
    {"ticker": "000660", "name": "SK하이닉스"},
    {"ticker": "035420", "name": "NAVER"},
    {"ticker": "005380", "name": "현대차"},
]


def parse_args():
    parser = argparse.ArgumentParser(description="네이버 뉴스 수집기")
    parser.add_argument(
        "--display",
        type=int,
        default=20,
        help="종목당 수집할 뉴스 건수 (기본: 20, 최대: 100)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    tickers = [s["ticker"] for s in SAMPLE_STOCKS]
    print(f"[start] 뉴스 수집 시작 — 대상 종목: {tickers}  (종목당 최대 {args.display}건)")

    news_items = collect_news_for_stocks(SAMPLE_STOCKS, display=args.display)

    if not news_items:
        print("[warn] 수집된 뉴스가 없습니다.")
        return

    saved_count = 0
    skipped_count = 0

    with get_connection() as conn:
        with conn.cursor() as cur:
            for item in news_items:
                # 뉴스 저장 (URL 중복이면 기존 id 반환)
                news_id = insert_news(
                    cur,
                    title=item["title"],
                    published_at=item["published_at"],
                    source=item["source"],
                    url=item["url"],
                    region=item["region"],
                )

                # 종목과 연결
                ticker = item.get("ticker")
                if ticker:
                    stock_id = get_or_create_stock(
                        cur,
                        ticker=ticker,
                        name=ticker,   # 종목명은 watchlist 전환 시 실제 이름으로 교체
                        market="KR",
                        currency="KRW",
                    )
                    link_news_to_stock(
                        cur,
                        news_id=news_id,
                        stock_id=stock_id,
                        relation_layer="stock_specific",
                    )

                saved_count += 1
                print(f"[saved] [{ticker}] {item['title'][:50]}...")

    print(f"[done] 뉴스 수집 완료 ({saved_count}건 저장, {skipped_count}건 중복 건너뜀)")


if __name__ == "__main__":
    main()
