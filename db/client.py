"""
Supabase(PostgreSQL) 연결 및 공용 쿼리 헬퍼.

db_schema.sql에서 만든 stocks / price_snapshots 테이블을 기준으로 작성됨.
"""
from contextlib import contextmanager

import psycopg2

import config


@contextmanager
def get_connection():
    """
    with get_connection() as conn: 형태로 사용.
    블록이 정상 종료되면 commit, 예외가 나면 rollback 후 다시 예외를 던짐.
    """
    if not config.DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL이 설정되지 않았습니다. .env 또는 GitHub Secrets를 확인하세요."
        )

    conn = psycopg2.connect(config.DATABASE_URL)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_or_create_stock(
    cur,
    ticker: str,
    name: str,
    market: str,
    exchange: str = None,
    currency: str = "USD",
) -> int:
    """
    stocks 테이블에서 ticker로 종목을 찾고, 없으면 새로 만든 뒤 id를 반환.
    섹터 매핑(sector_id)은 이후 별도의 섹터 배치 작업에서 채워질 예정이라
    여기서는 NULL로 둠.
    """
    cur.execute("SELECT id FROM stocks WHERE ticker = %s", (ticker,))
    row = cur.fetchone()
    if row:
        return row[0]

    cur.execute(
        """
        INSERT INTO stocks (ticker, name, market, exchange, currency)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
        """,
        (ticker, name, market, exchange, currency),
    )
    return cur.fetchone()[0]


def insert_price_snapshot(
    cur,
    stock_id: int,
    captured_at,
    price: float,
    change_pct: float = None,
    volume: int = None,
):
    """
    price_snapshots에 시세 한 건을 적재.
    (stock_id, captured_at) 조합이 이미 있으면 무시 (중복 적재 방지).
    """
    cur.execute(
        """
        INSERT INTO price_snapshots (stock_id, captured_at, price, change_pct, volume)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (stock_id, captured_at) DO NOTHING
        """,
        (stock_id, captured_at, price, change_pct, volume),
    )


def insert_financial_statement(
    cur,
    stock_id: int,
    fiscal_year: int,
    fiscal_quarter: int = None,
    revenue: float = None,
    operating_income: float = None,
    net_income: float = None,
):
    """
    financial_statements에 재무 데이터를 적재.
    이미 같은 (stock_id, fiscal_year, fiscal_quarter) 행이 있으면 UPDATE.

    fiscal_quarter=None(연간)일 때 PostgreSQL UNIQUE 제약에서 NULL != NULL로
    처리되어 ON CONFLICT가 작동하지 않으므로, SELECT로 존재 여부를 먼저 확인한다.
    """
    if fiscal_quarter is None:
        cur.execute(
            """
            SELECT id FROM financial_statements
             WHERE stock_id = %s AND fiscal_year = %s AND fiscal_quarter IS NULL
            """,
            (stock_id, fiscal_year),
        )
    else:
        cur.execute(
            """
            SELECT id FROM financial_statements
             WHERE stock_id = %s AND fiscal_year = %s AND fiscal_quarter = %s
            """,
            (stock_id, fiscal_year, fiscal_quarter),
        )

    row = cur.fetchone()
    if row:
        # 기존 행 갱신
        cur.execute(
            """
            UPDATE financial_statements
               SET revenue = %s, operating_income = %s, net_income = %s
             WHERE id = %s
            """,
            (revenue, operating_income, net_income, row[0]),
        )
    else:
        cur.execute(
            """
            INSERT INTO financial_statements
                (stock_id, fiscal_year, fiscal_quarter, revenue, operating_income, net_income)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (stock_id, fiscal_year, fiscal_quarter, revenue, operating_income, net_income),
        )


def insert_market_index(
    cur,
    index_code: str,
    captured_at,
    value: float,
    change_pct: float = None,
):
    """
    market_indices에 지수/지표 한 건을 적재.
    (index_code, captured_at) 조합이 이미 있으면 무시 (중복 적재 방지).
    """
    cur.execute(
        """
        INSERT INTO market_indices (index_code, captured_at, value, change_pct)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (index_code, captured_at) DO NOTHING
        """,
        (index_code, captured_at, value, change_pct),
    )


def insert_news(
    cur,
    title: str,
    published_at,
    source: str = None,
    url: str = None,
    region: str = "KR",
    category: str = None,
) -> int:
    """
    news 테이블에 뉴스 한 건을 삽입하고 생성된 id를 반환.
    URL이 같은 뉴스가 이미 있으면 기존 id를 반환 (중복 저장 방지).
    """
    # URL로 중복 확인 (URL이 없는 경우 제목+출처 조합으로 중복 방지 불가 — URL 기준이 현실적)
    if url:
        cur.execute("SELECT id FROM news WHERE url = %s", (url,))
        row = cur.fetchone()
        if row:
            return row[0]

    cur.execute(
        """
        INSERT INTO news (title, source, url, published_at, region, category)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (title, source, url, published_at, region, category),
    )
    return cur.fetchone()[0]


def link_news_to_stock(
    cur,
    news_id: int,
    stock_id: int,
    relation_layer: str = "stock_specific",
    relevance_score: float = None,
):
    """
    news_stock_relations에 뉴스↔종목 연결을 추가.
    같은 (news_id, stock_id, relation_layer) 조합이 이미 있으면 무시.
    relation_layer 허용값: 'macro' / 'sector' / 'peer' / 'supply_demand' / 'stock_specific'
    """
    cur.execute(
        """
        INSERT INTO news_stock_relations (news_id, stock_id, relation_layer, relevance_score)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT DO NOTHING
        """,
        (news_id, stock_id, relation_layer, relevance_score),
    )
