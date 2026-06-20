"""
일본 배송사 추적.

Sagawa, Yamato, Japan Post는 공개 REST API가 없어서
각사 조회 페이지 URL 생성 + 향후 웹훅/공식 API 연동 자리 마련.

현재 구현: 각사 공식 조회 URL 반환 (프론트에서 iframe or 링크로 표시).
실제 파싱이 필요하면 scraper-agent 경유 구현 권장.
"""

CARRIER_INFO = {
    'sagawa': {
        'name':     '佐川急便',
        'url_tmpl': 'https://k2k.sagawa-exp.co.jp/p/web/okurijosearch.do?okurijoNo={number}',
    },
    'yamato': {
        'name':     'クロネコヤマト',
        'url_tmpl': 'https://jizen.kuronekoyamato.co.jp/jizen/servlet/crjz.b.NQ0010?id={number}',
    },
    'japanpost': {
        'name':     '日本郵便',
        'url_tmpl': 'https://trackings.post.japanpost.jp/services/srv/search/direct?reqCodeNo1={number}',
    },
    'seino': {
        'name':     '西濃運輸',
        'url_tmpl': 'https://track.seino.co.jp/cgi-bin/gnpquery.pgm?GNPNO1={number}',
    },
    'fukuyama': {
        'name':     '福山通運',
        'url_tmpl': 'https://corp.fukutsu.co.jp/situation/tracking_no_hunt/{number}',
    },
}


def track(carrier_code: str, tracking_number: str) -> dict:
    """
    일본 배송사 추적 URL 반환.

    Returns:
        {
          "carrier": "sagawa",
          "carrier_name": "佐川急便",
          "tracking_number": "...",
          "tracking_url": "https://...",
          "status": "inquiry_required",
          "events": [],
          "error": null
        }
    """
    info = CARRIER_INFO.get(carrier_code)
    if not info:
        return {
            'carrier':         carrier_code,
            'carrier_name':    '',
            'tracking_number': tracking_number,
            'tracking_url':    '',
            'status':          'unknown_carrier',
            'events':          [],
            'error':           f'Unknown JP carrier: {carrier_code}',
        }

    url = info['url_tmpl'].format(number=tracking_number)
    return {
        'carrier':         carrier_code,
        'carrier_name':    info['name'],
        'tracking_number': tracking_number,
        'tracking_url':    url,
        'status':          'inquiry_required',
        'events':          [],
        'error':           None,
    }


def list_carriers() -> list[dict]:
    return [
        {'code': code, 'name': info['name']}
        for code, info in CARRIER_INFO.items()
    ]
