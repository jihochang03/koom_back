"""주문 취소/환불 정책.

단순변심 취소 컷오프 = **FastBox 인계(`preparing_dispatch`, FB송장 채번)**.
이 단계부터(포함) 단순변심 취소를 금지하면, 반품 경로가 항상 2단계 이내
(DK물류센터 → 판매자)로 유지된다. 컷오프 이후 허용하면
FastBox 수거 → DK물류센터 → 판매자(3단계)가 되어 CS 부담이 커지므로 차단한다.

하자/오배송/검수이슈 등 **DK 귀책 사유 환불은 단계와 무관하게 허용**한다
(이 컷오프는 `reason_type == 'change_of_mind'` 에만 적용).
"""
from .models import OrderStatusLog

# 운영 단계 진행 순서 (ORDER_STAGE_CHOICES 기준, 터미널 단계 제외).
# 인덱스가 클수록 더 진행된 단계.
STAGE_PROGRESSION = [
    'order_received',
    'purchase_review',
    'purchase_complete',
    'pre_arrival',
    'arrived',
    'inspection_in_progress',
    'inspection_complete',
    'preparing_dispatch',      # ← 단순변심 취소 컷오프 (FastBox 인계)
    'intl_shipping',
    'jp_carrier_handover',
    'delivered',
]

# 이 단계부터(포함) 단순변심 취소 불가.
CANCEL_CUTOFF_STAGE = 'preparing_dispatch'

# Order.status → 진행 단계 매핑 (OrderStatusLog 누락 대비 폴백).
_STATUS_TO_STAGE = {
    'pending':           'order_received',
    'paid':              'order_received',
    'purchasing':        'purchase_complete',
    'shipping_domestic': 'pre_arrival',
    'inspection':        'inspection_in_progress',
    'shipping_intl':     'intl_shipping',
    'delivered':         'delivered',
}

_TERMINAL_STATUSES = {'cancelled', 'refunded', 'partial_refund'}


def _stage_index(stage):
    try:
        return STAGE_PROGRESSION.index(stage)
    except ValueError:
        return -1


def current_progress_index(order):
    """주문의 현재 진행 인덱스 — OrderStatusLog 최대 단계와 Order.status 매핑 중 큰 값."""
    idx = -1
    for s in OrderStatusLog.objects.filter(order_number=order.order_number).values_list('stage', flat=True):
        idx = max(idx, _stage_index(s))
    idx = max(idx, _stage_index(_STATUS_TO_STAGE.get(order.status, '')))
    return idx


def cancel_eligibility(order):
    """단순변심 취소 가능 여부 + 사유.

    반환: {
        can_cancel_change_of_mind: bool,
        current_stage: str,            # 현재 진행 단계 key (또는 터미널 status)
        cutoff_stage: 'preparing_dispatch',
        reason: str,                   # 불가 시 사유 (가능하면 '')
    }
    """
    cutoff = _stage_index(CANCEL_CUTOFF_STAGE)

    if order.status in _TERMINAL_STATUSES:
        return {
            'can_cancel_change_of_mind': False,
            'current_stage': order.status,
            'cutoff_stage': CANCEL_CUTOFF_STAGE,
            'reason': '이미 취소/환불 처리된 주문입니다.',
        }

    idx = current_progress_index(order)
    cur_stage = STAGE_PROGRESSION[idx] if 0 <= idx < len(STAGE_PROGRESSION) else 'order_received'

    if idx >= cutoff:
        return {
            'can_cancel_change_of_mind': False,
            'current_stage': cur_stage,
            'cutoff_stage': CANCEL_CUTOFF_STAGE,
            'reason': 'FastBox 인계(출고 준비) 이후에는 단순변심 취소가 불가합니다. '
                      '하자·오배송 등 귀책 사유는 환불 요청으로 접수해 주세요.',
        }

    return {
        'can_cancel_change_of_mind': True,
        'current_stage': cur_stage,
        'cutoff_stage': CANCEL_CUTOFF_STAGE,
        'reason': '',
    }


def can_cancel_change_of_mind(order):
    """단순변심 취소 가능 여부 (bool 단축)."""
    return cancel_eligibility(order)['can_cancel_change_of_mind']
