"""
배송 추적 4단계 정의 + 이벤트 텍스트 → 단계 자동 분류.

배송 추적 화면 진행 바(4단계) — **FastBox(DHUB) status_code 가 권위 소스**:
  1. 상품발송      shipment_sent      주문접수·발송준비 (ORE/RPE)
  2. 국제운송      intl_transit       국제 운송 중 (RFI/InTransit)
  3. 현지배송      domestic_delivery  현지 택배사 배달 (OutForDelivery/AttemptFail)
  4. 배송완료      delivered          고객 수령 완료 (Delivered)

> "통관" 단계는 제거됨. FastBox 는 통관 전용 status_code 를 주지 않고(현지측 일본어
  이벤트라 한국어 키워드 분류도 신뢰 불가), 통관 데이터를 넣어줄 자동 피드도 없다.
  진행 바는 추론 대신 FastBox status_code 로 직접 구동한다
  (코드→단계 매핑: dhub_client.DHUB_STATUS_MAP['stage']).
  분류기(classify_tracking_stage)는 수동 `POST /timeline/` 등 description 기반
  원천 이벤트용 폴백으로만 남는다.
"""
from __future__ import annotations

import re

TRACKING_STAGE_CHOICES = [
    ('shipment_sent',     '상품발송'),
    ('intl_transit',      '국제운송'),
    ('domestic_delivery', '현지배송'),
    ('delivered',         '배송완료'),
]

# 진행 순서 (인덱스 = 진척도). 큰 인덱스가 더 진행된 단계.
TRACKING_STAGE_ORDER = [
    'shipment_sent', 'intl_transit', 'domestic_delivery', 'delivered',
]

STAGE_LABELS = dict(TRACKING_STAGE_CHOICES)

EVENT_SOURCE_CHOICES = [
    ('seller',   '판매자'),
    ('intl',     '국제운송사'),
    ('customs',  '세관'),
    ('carrier',  '국내 택배사'),
    ('system',   '시스템'),
]

# 단계별 키워드 (우선순위 순으로 검사 — 위에서부터 먼저 매칭). 정규식 단어 조각.
# 진행 바는 FastBox status_code 로 구동하며, 이 분류기는 description 기반 원천
# 이벤트(수동 /timeline/ 적재 등)용 폴백이다.
# delivered는 '완료' 오분류를 피하려 '배송/배달/수령/인수' 한정.
_STAGE_KEYWORDS = [
    ('delivered', [
        r'배송\s*완료', r'배달\s*완료', r'수령\s*완료', r'인수\s*완료',
        r'고객\s*수령', r'배송완료', r'delivered',
    ]),
    ('domestic_delivery', [
        r'집하', r'물류\s*센터', r'물류센터', r'간선', r'상차', r'하차',
        r'배송\s*출발', r'배송출발', r'배달\s*출발', r'배송\s*예정', r'배달\s*예정',
        r'허브', r'hub', r'택배', r'인계', r'입고', r'출고\s*완료',
        r'out\s*for\s*delivery',
    ]),
    ('intl_transit', [
        r'국제', r'항공', r'선박', r'출항', r'해외', r'international',
        r'국제\s*운송', r'국제운송', r'이원지', r'in\s*transit', r'intransit',
    ]),
    ('shipment_sent', [
        r'발송', r'출고', r'접수', r'상품\s*준비', r'배송\s*준비',
        r'dispatch', r'shipped', r'ship',
    ]),
]


def classify_tracking_stage(description: str, raw_code: str = '') -> str:
    """
    이벤트 설명(+선택적 상태코드) → 5단계 중 하나.

    매칭 실패 시 가장 앞 단계('상품발송')로 폴백 — 알 수 없는 초기 이벤트로 간주.
    """
    text = f"{description or ''} {raw_code or ''}".strip().lower()
    if not text:
        return 'shipment_sent'
    for stage, patterns in _STAGE_KEYWORDS:
        for pat in patterns:
            if re.search(pat, text, re.IGNORECASE):
                return stage
    return 'shipment_sent'


def stage_index(stage: str) -> int:
    """단계 → 진척 인덱스(0~4). 알 수 없으면 -1."""
    try:
        return TRACKING_STAGE_ORDER.index(stage)
    except ValueError:
        return -1


def max_stage(stages) -> str:
    """여러 단계 중 가장 진행된 단계 반환. 비면 'shipment_sent'."""
    best = -1
    best_stage = 'shipment_sent'
    for s in stages:
        idx = stage_index(s)
        if idx > best:
            best = idx
            best_stage = s
    return best_stage
