"""
스마트택배 (SweetTracker) 통합 API — 한국 택배사 추적.

지원 택배사 코드 (sweettracker t_code):
  04 = CJ대한통운, 05 = 한진택배, 06 = 롯데택배, 08 = 로젠택배,
  01 = 우체국, 23 = 쿠팡로켓, 32 = 로고스택배 등
"""
import logging
import os

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# 대표 택배사 코드 매핑 (사용자 친화 코드 → sweettracker t_code)
CARRIER_CODES = {
    'cj':      '04',
    'hanjin':  '05',
    'lotte':   '06',
    'logen':   '08',
    'epost':   '01',
    'coupang': '23',
    'gs':      '26',
}


def _base_url() -> str:
    return getattr(settings, 'SMART_TRACKER_BASE_URL', 'https://info.sweettracker.co.kr')


def _api_key() -> str:
    return getattr(settings, 'SMART_TRACKER_API_KEY', '') or os.environ.get('SMART_TRACKER_API_KEY', '')


def track(carrier_code: str, tracking_number: str) -> dict:
    """
    스마트택배 API로 배송 조회.

    Returns:
        {
          "carrier": "cj",
          "carrier_name": "CJ대한통운",
          "tracking_number": "...",
          "status": "배송완료",
          "level": 6,
          "events": [
            {"time": "2026-06-09 10:00", "location": "서울", "description": "배송완료", "level": 6}
          ]
        }
    """
    api_key = _api_key()
    if not api_key:
        logger.warning("SMART_TRACKER_API_KEY not set")
        return _empty_result(carrier_code, tracking_number, error='API key not configured')

    t_code = CARRIER_CODES.get(carrier_code, carrier_code)
    try:
        resp = requests.get(
            f'{_base_url()}/api/v1/trackingInfo',
            params={
                't_key':  api_key,
                't_code': t_code,
                't_invoice': tracking_number,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error("kr_tracker failed carrier=%s num=%s err=%s", carrier_code, tracking_number, e)
        return _empty_result(carrier_code, tracking_number, error=str(e))

    if not data.get('complete') and data.get('msg'):
        return _empty_result(carrier_code, tracking_number, error=data['msg'])

    events = []
    for item in data.get('trackingDetails', []):
        events.append({
            'time':        item.get('timeString', ''),
            'location':    item.get('where', ''),
            'description': item.get('detail', ''),
            'level':       item.get('level', 0),
        })

    return {
        'carrier':         carrier_code,
        'carrier_name':    data.get('companyName', ''),
        'tracking_number': tracking_number,
        'status':          data.get('status', {}).get('text', ''),
        'level':           data.get('status', {}).get('level', 0),
        'events':          events,
        'error':           None,
    }


def _empty_result(carrier_code: str, tracking_number: str, error: str = '') -> dict:
    return {
        'carrier':         carrier_code,
        'carrier_name':    '',
        'tracking_number': tracking_number,
        'status':          '',
        'level':           0,
        'events':          [],
        'error':           error,
    }
