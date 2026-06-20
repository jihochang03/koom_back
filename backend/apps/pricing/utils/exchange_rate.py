"""
실시간 환율 조회.
무료 API (open.er-api.com) 우선, 실패 시 한국은행 OpenAPI fallback.
"""
import os
import requests
import logging

logger = logging.getLogger(__name__)

_ER_API_BASE = "https://open.er-api.com/v6/latest"


def fetch_exchange_rate(base: str = "JPY", target: str = "KRW") -> dict:
    """
    base → target 환율 조회.
    반환: {"rate": float, "source": str, "base": str, "target": str}
    실패 시 예외 발생.
    """
    # 1차: open.er-api.com (무료, API키 불필요)
    try:
        resp = requests.get(f"{_ER_API_BASE}/{base}", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("result") == "success":
            rates = data.get("rates", {})
            rate = rates.get(target)
            if rate is not None:
                return {
                    "rate": float(rate),
                    "source": "open.er-api.com",
                    "base": base,
                    "target": target,
                }
    except Exception as e:
        logger.warning("open.er-api.com 조회 실패 (fallback 시도): %s", e)

    # 2차: exchangerate-api.com v4 (무료, API키 불필요)
    try:
        resp = requests.get(f"https://api.exchangerate-api.com/v4/latest/{base}", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        rates = data.get("rates", {})
        rate = rates.get(target)
        if rate is not None:
            return {
                "rate": float(rate),
                "source": "exchangerate-api.com",
                "base": base,
                "target": target,
            }
    except Exception as e:
        logger.warning("exchangerate-api.com 조회 실패: %s", e)

    raise RuntimeError(f"환율 조회 실패: {base}/{target} — 모든 소스 응답 없음")
