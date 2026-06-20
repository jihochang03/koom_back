"""환불 실행 공통 서비스.

GMO 환불 호출 + PGTransaction 갱신을 한 곳에서 처리한다.
- PaymentRefundView (그룹 단위 직접 환불)
- cs.RefundExecuteView (본사 승인 → 요청 단위 환불)
두 진입점이 동일 로직을 공유한다.
"""
from django.utils import timezone

from .providers.registry import get_provider


def execute_pg_refund(pg, amount=None):
    """GMO 환불 실행 후 PGTransaction 갱신.

    Args:
        pg: PGTransaction
        amount: 부분 환불 금액(JPY). None 이면 전액.
    Returns:
        (AlterResult, actual_refund_amount)
    Raises:
        ProviderError
    """
    provider = get_provider(pg.provider)
    result = provider.refund(pg, amount=amount)

    now = timezone.now()
    actual = amount if amount else pg.amount_jpy
    pg.auth_status = result.auth_status
    pg.gmo_job_cd = 'RETURN'
    pg.refund_amount = actual
    pg.refund_requested_at = now
    pg.refund_completed_at = now
    pg.raw_payload = {**(pg.raw_payload or {}), 'refund': result.raw}
    pg.save(update_fields=[
        'auth_status', 'gmo_job_cd', 'refund_amount',
        'refund_requested_at', 'refund_completed_at', 'raw_payload', 'updated_at',
    ])
    return result, actual
