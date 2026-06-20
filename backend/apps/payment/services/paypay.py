"""
GMO-PG PayPay 결제.

엔드포인트:
  EntryTranPaypay.idPass  — 거래 등록 → AccessID/Pass + QR URL
  ExecTranPaypay.idPass   — 거래 실행 (고객이 QR 스캔 완료 후 호출)
  SearchTrade.idPass      — 상태 조회 (기존 공통 함수 재사용)

PayPay 결제 흐름:
  1. EntryTranPaypay → QR URL 반환 → 고객에게 표시
  2. 고객이 PayPay 앱으로 QR 스캔 후 결제 완료
  3. ExecTranPaypay → 결제 확정 (webhook or polling)
"""
import os
from urllib.parse import parse_qs

import requests
from django.conf import settings

from .gmopg import _base_url, _credentials, GmoPgError


def _post_paypay(path: str, params: dict) -> dict:
    url = _base_url() + path
    timeout = int(os.environ.get('GMO_TIMEOUT', '30'))
    resp = requests.post(url, data=params, timeout=timeout)
    resp.raise_for_status()
    raw = parse_qs(resp.text, keep_blank_values=True)
    result = {k: v[0] for k, v in raw.items()}
    if result.get('ErrCode'):
        raise GmoPgError(result.get('ErrCode', ''), result.get('ErrInfo', ''), result)
    return result


def entry_tran_paypay(
    order_id: str,
    amount: int,
    return_url: str,
    job_cd: str = 'CAPTURE',
) -> dict:
    """
    PayPay 거래 등록.

    Returns: { AccessID, AccessPass, Token, StartURL (QR 결제 URL) }
    """
    params = {
        **_credentials(),
        'OrderID':   order_id,
        'JobCd':     job_cd,
        'Amount':    str(amount),
        'RetURL':    return_url,    # 결제 완료 후 리다이렉트 URL
    }
    return _post_paypay('EntryTranPaypay.idPass', params)


def exec_tran_paypay(access_id: str, access_pass: str, order_id: str) -> dict:
    """
    PayPay 거래 실행 — 고객 결제 완료 후 확정.

    Returns: { OrderID, Status, Forward, TranID, TranDate }
    """
    params = {
        'AccessID':  access_id,
        'AccessPass': access_pass,
        'OrderID':   order_id,
    }
    return _post_paypay('ExecTranPaypay.idPass', params)
