import os
from typing import Optional
from urllib.parse import parse_qs

import requests

SANDBOX_BASE = 'https://pt01.mul-pay.jp/payment/'
PROD_BASE    = 'https://p01.mul-pay.jp/payment/'


class GmoPgError(Exception):
    def __init__(self, err_code: str, err_info: str, raw: dict):
        self.err_code = err_code
        self.err_info = err_info
        self.raw = raw
        super().__init__(f"GMO-PG {err_code}: {err_info}")


def _base_url() -> str:
    sandbox = os.environ.get('GMO_SANDBOX', 'true').lower()
    return SANDBOX_BASE if sandbox == 'true' else PROD_BASE


def _credentials() -> dict:
    return {
        'ShopID':   os.environ.get('GMO_SHOP_ID', ''),
        'ShopPass': os.environ.get('GMO_SHOP_PASS', ''),
    }


def _post(path: str, params: dict) -> dict:
    url = _base_url() + path
    timeout = int(os.environ.get('GMO_TIMEOUT', '30'))
    resp = requests.post(url, data=params, timeout=timeout)
    resp.raise_for_status()
    raw = parse_qs(resp.text, keep_blank_values=True)
    result = {k: v[0] for k, v in raw.items()}
    if result.get('ErrCode'):
        raise GmoPgError(
            result.get('ErrCode', ''),
            result.get('ErrInfo', ''),
            result,
        )
    return result


def entry_tran(order_id: str, amount: int, job_cd: str = 'AUTH') -> dict:
    """EntryTran — 거래 슬롯 생성. AccessID, AccessPass 반환."""
    params = {
        **_credentials(),
        'OrderID': order_id,
        'JobCd':   job_cd,
        'Amount':  str(amount),
    }
    return _post('EntryTran.idPass', params)


def exec_tran(
    access_id: str,
    access_pass: str,
    order_id: str,
    token: str,
    method: str = '1',
    pay_times: Optional[int] = None,
    client_field1: str = '',
    client_field2: str = '',
    client_field3: str = '',
) -> dict:
    """ExecTran — 토큰으로 결제 실행. TranID, Approve, Forward 반환."""
    params = {
        'AccessID':    access_id,
        'AccessPass':  access_pass,
        'OrderID':     order_id,
        'Method':      method,
        'Token':       token,
        'ClientField1': client_field1,
        'ClientField2': client_field2,
        'ClientField3': client_field3,
    }
    if pay_times and method in ('2', '4'):
        params['PayTimes'] = str(pay_times)
    return _post('ExecTran.idPass', params)


def alter_tran(
    access_id: str,
    access_pass: str,
    job_cd: str,
    amount: Optional[int] = None,
) -> dict:
    """AlterTran — 캡처(SALES) / 취소(CANCEL) / 환불(RETURN)."""
    params = {
        **_credentials(),
        'AccessID':  access_id,
        'AccessPass': access_pass,
        'JobCd':     job_cd,
    }
    if amount is not None:
        params['Amount'] = str(amount)
    return _post('AlterTran.idPass', params)


def search_trade(order_id: str) -> dict:
    """SearchTrade — 거래 조회."""
    params = {
        **_credentials(),
        'OrderID': order_id,
    }
    return _post('SearchTrade.idPass', params)
