"""
실행 진입점: FRED API에서 VIX 등 매크로 지표를 수집해 DB에 저장.

로컬 실행:
    python scripts/collect_macro_indices.py

GitHub Actions에서는 동일한 명령이 주기적으로 호출됨
(.github/workflows/collect-macro-indices.yml 참고).
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.fred_collector import collect_macro_indices, DEFAULT_SERIES
from db.client import get_connection, insert_market_index


def main():
    print(f"[start] 매크로 지표 수집 시작 — 대상: {list(DEFAULT_SERIES.values())}")

    indices = collect_macro_indices()

    if not indices:
        print("[warn] 수집된 지표가 없습니다.")
        return

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx in indices:
                insert_market_index(
                    cur,
                    index_code=idx["index_code"],
                    captured_at=idx["captured_at"],
                    value=idx["value"],
                )
                print(f"[saved] {idx['index_code']}: {idx['value']}  ({idx['obs_date']})")

    print(f"[done] 매크로 지표 수집 완료 ({len(indices)}건 저장)")


if __name__ == "__main__":
    main()
