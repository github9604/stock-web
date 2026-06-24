"""
환경변수 로딩 및 설정.

로컬 개발: .env 파일에서 읽음.
GitHub Actions: Secrets가 환경변수로 주입되므로 .env 파일 없이도 동작함.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ---------- API 키 ----------
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
DART_API_KEY = os.getenv("DART_API_KEY")
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")
FRED_API_KEY = os.getenv("FRED_API_KEY")

# KIS는 아직 키가 없음 — 나중에 발급받으면 .env / GitHub Secrets에 추가만 하면
# 아래 ENABLED_COLLECTORS["kis"]가 자동으로 True로 바뀌고 kis_collector.py가 동작함.
KIS_APP_KEY = os.getenv("KIS_APP_KEY")
KIS_APP_SECRET = os.getenv("KIS_APP_SECRET")
KIS_ACCOUNT_NO = os.getenv("KIS_ACCOUNT_NO")

# ---------- DB ----------
# Supabase 대시보드 > Project Settings > Database > Connection string (URI)
DATABASE_URL = os.getenv("DATABASE_URL")

# ---------- 수집기 활성화 여부 (해당 키가 있어야 켜짐) ----------
ENABLED_COLLECTORS = {
    "finnhub": bool(FINNHUB_API_KEY),
    "dart": bool(DART_API_KEY),
    "naver_news": bool(NAVER_CLIENT_ID and NAVER_CLIENT_SECRET),
    "fred": bool(FRED_API_KEY),
    "kis": bool(KIS_APP_KEY and KIS_APP_SECRET and KIS_ACCOUNT_NO),
}


def require(collector_name: str):
    """해당 수집기에 필요한 키가 없으면 명확한 에러 메시지로 알려줌."""
    if not ENABLED_COLLECTORS.get(collector_name):
        raise RuntimeError(
            f"[{collector_name}] 관련 API 키가 설정되지 않았습니다. "
            f".env 또는 GitHub Secrets에 키를 추가한 뒤 다시 실행하세요."
        )
