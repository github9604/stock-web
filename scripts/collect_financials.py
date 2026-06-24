"""
실행 진입점: 국내 관심종목의 재무제표를 DART에서 수집해 DB에 저장.

로컬 실행:
    python scripts/collect_financials.py               # 전년도 연간 보고서
    python scripts/collect_financials.py --year 2023   # 특정 연도 연간
    python scripts/collect_financials.py --year 2024 --quarter 2  # 특정 분기

GitHub Actions에서는 동일한 명령이 주기적으로 호출됨
(.github/workflows/collect-financials.yml 참고).
"""
import argparse
import os
import sys
from datetime import date

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.dart_collector import collect_financials
from db.client import get_connection, get_or_create_stock, insert_financial_statement

# TODO: watchlist 테이블이 채워지면 이 하드코딩 목록 대신
#       "SELECT ticker FROM watchlist JOIN stocks ..." 쿼리로 교체
SAMPLE_TICKERS = [
    "005930",  # 삼성전자
    "000660",  # SK하이닉스
    "035420",  # NAVER
    "005380",  # 현대차
    "051910",  # LG화학
]


def parse_args():
    today = date.today()
    # 사업보고서 제출 마감은 3월 말 ~ 4월 초.
    # 4월 이후 → 전년도(current_year-1) 보고서가 이미 공시된 시점
    # 1~3월   → 전년도 보고서가 아직 미공시일 수 있으므로 재전년도(current_year-2)를 기본으로
    if today.month >= 4:
        default_year = today.year - 1
    else:
        default_year = today.year - 2
    parser = argparse.ArgumentParser(description="DART 재무제표 수집기")
    parser.add_argument(
        "--year",
        type=int,
        default=default_year,
        help=f"수집 사업연도 (기본: {default_year})",
    )
    parser.add_argument(
        "--quarter",
        type=int,
        choices=[1, 2, 3, 4],
        default=None,
        help="분기 지정 (생략 시 연간 사업보고서)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    period_label = f"{args.year}년 {'연간' if args.quarter is None else f'{args.quarter}분기'}"
    print(f"[start] 재무데이터 수집 시작 — {period_label} / 대상 종목: {SAMPLE_TICKERS}")

    financials = collect_financials(
        tickers=SAMPLE_TICKERS,
        year=args.year,
        quarter=args.quarter,
    )

    if not financials:
        print("[warn] 수집된 재무데이터가 없습니다.")
        return

    saved_count = 0
    with get_connection() as conn:
        with conn.cursor() as cur:
            for f in financials:
                # 국내 종목: market='KR', currency='KRW'
                # 종목명은 DART 기업개황 API로 별도 수집 가능하나, 여기서는 ticker로 임시 등록
                stock_id = get_or_create_stock(
                    cur,
                    ticker=f["ticker"],
                    name=f["ticker"],
                    market="KR",
                    exchange="KOSPI",
                    currency="KRW",
                )
                insert_financial_statement(
                    cur,
                    stock_id=stock_id,
                    fiscal_year=f["fiscal_year"],
                    fiscal_quarter=f["fiscal_quarter"],
                    revenue=f["revenue"],
                    operating_income=f["operating_income"],
                    net_income=f["net_income"],
                )
                saved_count += 1
                print(
                    f"[saved] {f['ticker']}: "
                    f"매출={f['revenue']}, "
                    f"영업이익={f['operating_income']}, "
                    f"순이익={f['net_income']}"
                )

    print(f"[done] {period_label} 재무데이터 수집 완료 ({saved_count}건 저장)")


if __name__ == "__main__":
    main()
