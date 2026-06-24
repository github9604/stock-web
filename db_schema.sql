-- ============================================================
-- 주식/경제 정보 웹 — DB 스키마 (PostgreSQL / Supabase 기준)
-- ============================================================
-- 설계 원칙:
--  1) 마스터 데이터(sectors, stocks)는 자주 안 바뀜 → 배치(월1회) 갱신
--  2) 시계열 데이터(price_snapshots, market_indices, supply_demand)는
--     날짜/시각 + 종목 조합으로 UNIQUE 제약 → 중복 적재 방지
--  3) news_stock_relations의 relation_layer가 "영향관계 4~5단계 구조"의
--     핵심 — 프론트엔드 배지/아코디언이 이 컬럼 기준으로 렌더링됨
-- ============================================================


-- ============================================================
-- 1. 마스터 데이터 (기준정보)
-- ============================================================

CREATE TABLE sectors (
    id              SERIAL PRIMARY KEY,
    sector_name     VARCHAR(100) NOT NULL,   -- 예: 반도체, 자동차, 금융
    industry_name   VARCHAR(100),            -- 세부 분류 (예: 메모리반도체)
    region          VARCHAR(10)  NOT NULL    -- 'KR' / 'US' (분류체계가 지역별로 다름)
);

CREATE TABLE stocks (
    id              SERIAL PRIMARY KEY,
    ticker          VARCHAR(20)  NOT NULL UNIQUE,  -- '005930', 'AAPL'
    name            VARCHAR(100) NOT NULL,
    market          VARCHAR(10)  NOT NULL,         -- 'KR' / 'US'
    exchange        VARCHAR(20),                   -- KOSPI/KOSDAQ/NASDAQ/NYSE
    sector_id       INTEGER REFERENCES sectors(id),
    currency        VARCHAR(5)   DEFAULT 'KRW',
    is_delisted     BOOLEAN      DEFAULT FALSE,
    created_at      TIMESTAMP    DEFAULT now()
);

CREATE INDEX idx_stocks_sector ON stocks(sector_id);


-- ============================================================
-- 2. 사용자 관심/보유 종목
-- ============================================================

CREATE TABLE watchlist (
    id              SERIAL PRIMARY KEY,
    stock_id        INTEGER REFERENCES stocks(id),
    list_type       VARCHAR(20)  NOT NULL,   -- 'portfolio' / 'watch'
    avg_price       NUMERIC(18,2),           -- 포트폴리오인 경우 평단가
    quantity        NUMERIC(18,4),
    added_at        TIMESTAMP    DEFAULT now()
);


-- ============================================================
-- 3. 시세 데이터
-- ============================================================

CREATE TABLE price_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    stock_id        INTEGER REFERENCES stocks(id),
    captured_at     TIMESTAMP    NOT NULL,
    price           NUMERIC(18,2) NOT NULL,
    change_pct      NUMERIC(6,2),
    volume          BIGINT,
    UNIQUE(stock_id, captured_at)
);

CREATE INDEX idx_price_stock_time ON price_snapshots(stock_id, captured_at DESC);

CREATE TABLE market_indices (
    id              BIGSERIAL PRIMARY KEY,
    index_code      VARCHAR(20)  NOT NULL,   -- 'KOSPI','NASDAQ','VIX','USDKRW','WTI'
    captured_at     TIMESTAMP    NOT NULL,
    value           NUMERIC(18,4) NOT NULL,
    change_pct      NUMERIC(6,2),
    UNIQUE(index_code, captured_at)
);


-- ============================================================
-- 4. 뉴스 & 영향관계 (인과구조의 핵심 테이블)
-- ============================================================

CREATE TABLE news (
    id              BIGSERIAL PRIMARY KEY,
    title           TEXT         NOT NULL,
    source          VARCHAR(100),
    url             TEXT,
    published_at    TIMESTAMP    NOT NULL,
    region          VARCHAR(10),             -- 'KR' / 'global'
    category        VARCHAR(50),             -- 정책/실적/매크로/산업 등
    sentiment       VARCHAR(10)              -- 'positive'/'negative'/'neutral' (선택, 확장기능)
);

CREATE INDEX idx_news_published ON news(published_at DESC);

-- 뉴스 1개가 여러 종목에, 여러 레이어로 연결될 수 있음 (N:M)
CREATE TABLE news_stock_relations (
    id              BIGSERIAL PRIMARY KEY,
    news_id         BIGINT  REFERENCES news(id),
    stock_id        INTEGER REFERENCES stocks(id),
    relation_layer  VARCHAR(20) NOT NULL,    -- 'macro' / 'sector' / 'peer' / 'supply_demand' / 'stock_specific'
    relevance_score NUMERIC(4,2)             -- 우선순위 산정용 (선택)
);

CREATE INDEX idx_news_rel_stock ON news_stock_relations(stock_id, relation_layer);


-- ============================================================
-- 5. 수급 데이터 (국내 종목 전용)
-- ============================================================

CREATE TABLE supply_demand (
    id              BIGSERIAL PRIMARY KEY,
    stock_id        INTEGER REFERENCES stocks(id),
    trade_date      DATE    NOT NULL,
    foreign_net     BIGINT,                  -- 외국인 순매수 (금액 기준, KRW)
    institution_net BIGINT,                  -- 기관 순매수
    individual_net  BIGINT,                  -- 개인 순매수
    UNIQUE(stock_id, trade_date)
);


-- ============================================================
-- 6. 재무 / 배당 / 밸류에이션 (스크리너용)
-- ============================================================

CREATE TABLE financial_statements (
    id                  BIGSERIAL PRIMARY KEY,
    stock_id            INTEGER REFERENCES stocks(id),
    fiscal_year         INTEGER NOT NULL,
    fiscal_quarter      INTEGER,             -- NULL이면 연간 데이터
    revenue             NUMERIC(20,2),
    operating_income    NUMERIC(20,2),
    net_income          NUMERIC(20,2),
    debt_ratio          NUMERIC(6,2),
    roe                 NUMERIC(6,2),
    UNIQUE(stock_id, fiscal_year, fiscal_quarter)
);

CREATE TABLE dividends (
    id                  BIGSERIAL PRIMARY KEY,
    stock_id            INTEGER REFERENCES stocks(id),
    fiscal_year         INTEGER NOT NULL,
    dividend_per_share  NUMERIC(10,2),
    dividend_yield      NUMERIC(6,2),
    payout_ratio        NUMERIC(6,2),        -- 배당성향
    consecutive_years   INTEGER,             -- 연속 배당/증액 연수
    UNIQUE(stock_id, fiscal_year)
);

CREATE TABLE valuation_snapshots (
    id                          BIGSERIAL PRIMARY KEY,
    stock_id                    INTEGER REFERENCES stocks(id),
    captured_at                 DATE    NOT NULL,
    per                         NUMERIC(8,2),
    pbr                         NUMERIC(8,2),
    shareholder_return_ratio    NUMERIC(6,2),  -- (배당+자사주매입)/순이익
    passes_good_company_filter  BOOLEAN,       -- 기본필터: PER<=10 & 환원율>=40%
    UNIQUE(stock_id, captured_at)
);

CREATE INDEX idx_valuation_filter ON valuation_snapshots(passes_good_company_filter, captured_at DESC);


-- ============================================================
-- 7. 미래 이벤트 & 선행지표
-- ============================================================

CREATE TABLE future_events (
    id                  SERIAL PRIMARY KEY,
    event_name          VARCHAR(200) NOT NULL,
    event_type          VARCHAR(30),         -- '정책','실적','매크로지표','산업'
    event_date          DATE    NOT NULL,
    related_stock_id    INTEGER REFERENCES stocks(id),  -- nullable (실적발표 등 종목 특정 이벤트)
    description         TEXT
);

CREATE INDEX idx_events_date ON future_events(event_date);

CREATE TABLE event_leading_indicators (
    id              SERIAL PRIMARY KEY,
    event_id        INTEGER REFERENCES future_events(id),
    indicator_name  VARCHAR(200) NOT NULL,   -- 예: 'CPI 발표', '고용지표'
    description     TEXT
);


-- ============================================================
-- 8. (선택) 변동성 신호 로그 — "왜 움직였나" 히스토리 보관용
-- ============================================================

CREATE TABLE volatility_alerts_log (
    id              BIGSERIAL PRIMARY KEY,
    stock_id        INTEGER REFERENCES stocks(id),
    alert_date      DATE    NOT NULL,
    change_pct      NUMERIC(6,2) NOT NULL,
    primary_cause_layer  VARCHAR(20),        -- 'macro'/'sector'/'peer'/'supply_demand'/'stock_specific'
    cause_summary   TEXT,                    -- LLM이 생성한 한 줄 요약 (배지에 쓰임)
    created_at      TIMESTAMP DEFAULT now()
);
