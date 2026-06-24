# 주식/경제 정보 웹 — 데이터 수집 백엔드

기획 전체 내용은 `project_summary.md`, DB 구조는 `db_schema.sql` / `db_erd.mermaid` 참고.

## 프로젝트 구조

```
stock-web/
├── config.py                  # 환경변수 로딩, 수집기 활성화 여부 판단
├── db/
│   └── client.py               # Supabase(PostgreSQL) 연결 + 공용 쿼리
├── collectors/
│   ├── finnhub_collector.py    # ✅ 구현완료 — 해외 시세
│   ├── dart_collector.py       # 🚧 스텁 — 국내 재무/공시
│   ├── naver_news_collector.py # 🚧 스텁 — 국내 뉴스
│   ├── fred_collector.py       # 🚧 스텁 — VIX 등 매크로
│   └── kis_collector.py        # ⏸ 보류 — 키 발급 전까지 비활성
└── scripts/
    └── collect_overseas_prices.py  # 실행 진입점 (해외 시세 수집)
```

## 로컬 실행 방법

1. 의존성 설치
   ```bash
   pip install -r requirements.txt
   ```

2. `.env.example`을 복사해서 `.env` 생성 후, 발급받은 키 값 채우기
   ```bash
   cp .env.example .env
   ```

3. 해외 시세 수집 실행
   ```bash
   python scripts/collect_overseas_prices.py
   ```

## DB 준비

Supabase 프로젝트에서 SQL Editor를 열고 `db_schema.sql` 내용을 그대로 실행하면
`stocks`, `price_snapshots` 등 필요한 테이블이 모두 생성됩니다.

## KIS(한국투자증권) 키를 나중에 추가할 때

1. `.env`에 `KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_ACCOUNT_NO` 값을 채워 넣으면
   `config.ENABLED_COLLECTORS["kis"]`가 자동으로 `True`가 됨
2. `collectors/kis_collector.py`의 `NotImplementedError` 부분을 실제 KIS REST API
   호출로 구현
3. IP 화이트리스트 정책 때문에 GitHub Actions 호스팅 러너에서는 동작하지 않을 수 있음
   → self-hosted runner 또는 고정 IP 서버에서 별도 워크플로로 분리 검토

## GitHub Actions 배포 시 주의사항

- 저장소를 **public**으로 두면 Actions 실행 분량이 무제한 무료 (private는 월 2,000분 제한)
- API 키는 코드에 직접 쓰지 말고 저장소 **Settings → Secrets and variables → Actions**에 등록
