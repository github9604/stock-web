"""
한국투자증권 KIS Developers API로 국내 실시간 시세를 가져오는 수집기.

상태: 키 미발급 (보류) — config.KIS_APP_KEY 등이 비어 있는 동안은
config.require("kis")에서 바로 에러를 던지도록 되어 있어 안전하게 막혀 있음.

나중에 할 일:
  1) .env / GitHub Secrets에 KIS_APP_KEY, KIS_APP_SECRET, KIS_ACCOUNT_NO 추가
     -> config.ENABLED_COLLECTORS["kis"]가 자동으로 True가 됨
  2) 아래 함수들을 실제 KIS REST API 호출로 구현
     (참고: https://github.com/koreainvestment/open-trading-api)
  3) GitHub Actions에서 이 모듈만 self-hosted runner(고정 IP)로 분리해서
     실행할지 결정 필요 (IP 화이트리스트 정책 때문 — project_summary.md 참고)
"""
import config


def get_access_token():
    config.require("kis")
    raise NotImplementedError("KIS 수집기는 키 발급 후 구현합니다.")


def get_quote(ticker: str):
    config.require("kis")
    raise NotImplementedError("KIS 수집기는 키 발급 후 구현합니다.")
