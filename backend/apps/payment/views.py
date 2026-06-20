import logging

from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.models import OrderGroup, PGTransaction
from .providers.base import ProviderError
from .providers.registry import get_provider

logger = logging.getLogger(__name__)

_PROVIDER = 'gmo'


def _make_order_id(group_number: str) -> str:
    return group_number.replace('/', '-')[:27]


def _get_pg(group_number: str) -> PGTransaction | None:
    return PGTransaction.objects.filter(order_number=group_number).order_by('-created_at').first()


class PaymentEntryView(APIView):
    """
    POST /api/payment/entry/

    거래 슬롯 생성 → 프론트엔드 토크나이저용 access_id/pass 반환.

    Request:  { order_group_id: int }
    Response: { provider, provider_order_id, access_id, access_pass, amount, currency }
    """

    def post(self, request):
        order_group_id = request.data.get('order_group_id')
        if not order_group_id:
            return Response({'error': 'order_group_id required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            group = OrderGroup.objects.get(pk=order_group_id)
        except OrderGroup.DoesNotExist:
            return Response({'error': 'OrderGroup not found'}, status=status.HTTP_404_NOT_FOUND)

        amount = int(group.total_paid) if group.total_paid else 0
        if amount <= 0:
            return Response({'error': 'Invalid order amount'}, status=status.HTTP_400_BAD_REQUEST)

        provider = get_provider(_PROVIDER)
        try:
            entry = provider.entry(order_id=_make_order_id(group.group_number), amount=amount, currency='JPY')
        except ProviderError as e:
            logger.error("entry failed group=%s provider=%s err=%s", group.group_number, _PROVIDER, e)
            return Response(
                {'error': 'PG 거래 등록 실패', 'provider_code': e.code, 'detail': e.message},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response({'provider': _PROVIDER, **entry.client_payload})


class PaymentExecuteView(APIView):
    """
    POST /api/payment/execute/

    결제 실행 → PGTransaction 생성.

    Request: {
        order_group_id:    int,
        provider_order_id: str,
        access_id:         str,
        access_pass:       str,
        token:             str,
        method?:           str,   # '1'=일시불(기본)
        pay_times?:        int,
    }
    Response: { status, transaction_id, approve, forward, tran_date, pg_id }
    """

    def post(self, request):
        d = request.data
        required = ('order_group_id', 'provider_order_id', 'access_id', 'access_pass', 'token')
        missing = [f for f in required if not d.get(f)]
        if missing:
            return Response({'error': f'필수 파라미터 누락: {missing}'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            group = OrderGroup.objects.get(pk=d['order_group_id'])
        except OrderGroup.DoesNotExist:
            return Response({'error': 'OrderGroup not found'}, status=status.HTTP_404_NOT_FOUND)

        provider = get_provider(_PROVIDER)
        try:
            result = provider.execute(
                provider_order_id=d['provider_order_id'],
                access_id=d['access_id'],
                access_pass=d['access_pass'],
                token=d['token'],
                method=d.get('method', '1'),
                pay_times=d.get('pay_times'),
                client_field1=group.group_number,
            )
        except ProviderError as e:
            logger.error("execute failed group=%s provider=%s err=%s", group.group_number, _PROVIDER, e)
            PGTransaction.objects.create(
                order_number=group.group_number,
                provider=_PROVIDER,
                currency='JPY',
                provider_order_id=d['provider_order_id'],
                gmo_order_id=d['provider_order_id'],
                gmo_access_id=d['access_id'],
                gmo_access_pass=d['access_pass'],
                gmo_job_cd='AUTH',
                amount_jpy=int(group.total_paid or 0),
                auth_status='failed',
                failure_reason=str(e),
                raw_payload=e.raw,
            )
            return Response(
                {'error': '결제 실패', 'provider_code': e.code, 'detail': e.message},
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )

        pg = PGTransaction.objects.create(
            order_number=group.group_number,
            provider=_PROVIDER,
            currency='JPY',
            provider_order_id=d['provider_order_id'],
            pg_transaction_id=result.transaction_id,
            gmo_order_id=d['provider_order_id'],
            gmo_access_id=d['access_id'],
            gmo_access_pass=d['access_pass'],
            gmo_forward=result.raw.get('Forward', ''),
            gmo_approve=result.raw.get('Approve', ''),
            gmo_job_cd='AUTH',
            amount_jpy=int(group.total_paid or 0),
            auth_status=result.auth_status,
            raw_payload=result.raw,
        )

        group.status = 'paid'
        group.paid_at = timezone.now()
        group.save(update_fields=['status', 'paid_at', 'updated_at'])

        return Response({
            'status':         result.auth_status,
            'transaction_id': result.transaction_id,
            'approve':        result.raw.get('Approve', ''),
            'forward':        result.raw.get('Forward', ''),
            'tran_date':      result.raw.get('TranDate', ''),
            'pg_id':          pg.id,
        })


class PaymentCaptureView(APIView):
    """
    POST /api/payment/capture/

    AUTH 후 매출 확정.

    Request:  { order_group_id: int }
    Response: { status, transaction_id }
    """

    def post(self, request):
        order_group_id = request.data.get('order_group_id')
        if not order_group_id:
            return Response({'error': 'order_group_id required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            group = OrderGroup.objects.get(pk=order_group_id)
        except OrderGroup.DoesNotExist:
            return Response({'error': 'OrderGroup not found'}, status=status.HTTP_404_NOT_FOUND)

        pg = _get_pg(group.group_number)
        if not pg:
            return Response({'error': 'PGTransaction not found'}, status=status.HTTP_404_NOT_FOUND)

        provider = get_provider(pg.provider)
        try:
            result = provider.capture(pg)
        except ProviderError as e:
            logger.error("capture failed order=%s provider=%s err=%s", group.group_number, pg.provider, e)
            return Response(
                {'error': '캡처 실패', 'provider_code': e.code, 'detail': e.message},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        pg.auth_status = result.auth_status
        pg.gmo_job_cd = 'SALES'
        pg.gmo_forward = result.raw.get('Forward', pg.gmo_forward)
        pg.gmo_approve = result.raw.get('Approve', pg.gmo_approve)
        pg.raw_payload = {**(pg.raw_payload or {}), 'capture': result.raw}
        pg.save(update_fields=['auth_status', 'gmo_job_cd', 'gmo_forward', 'gmo_approve', 'raw_payload', 'updated_at'])

        return Response({'status': result.auth_status, 'transaction_id': result.raw.get('TranID', '')})


class PaymentCancelView(APIView):
    """
    POST /api/payment/cancel/

    Request:  { order_group_id: int }
    Response: { status }
    """

    def post(self, request):
        order_group_id = request.data.get('order_group_id')
        if not order_group_id:
            return Response({'error': 'order_group_id required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            group = OrderGroup.objects.get(pk=order_group_id)
        except OrderGroup.DoesNotExist:
            return Response({'error': 'OrderGroup not found'}, status=status.HTTP_404_NOT_FOUND)

        pg = _get_pg(group.group_number)
        if not pg:
            return Response({'error': 'PGTransaction not found'}, status=status.HTTP_404_NOT_FOUND)

        provider = get_provider(pg.provider)
        try:
            result = provider.cancel(pg)
        except ProviderError as e:
            logger.error("cancel failed order=%s provider=%s err=%s", group.group_number, pg.provider, e)
            return Response(
                {'error': '취소 실패', 'provider_code': e.code, 'detail': e.message},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        pg.auth_status = result.auth_status
        pg.gmo_job_cd = 'CANCEL'
        pg.raw_payload = {**(pg.raw_payload or {}), 'cancel': result.raw}
        pg.save(update_fields=['auth_status', 'gmo_job_cd', 'raw_payload', 'updated_at'])

        group.status = 'cancelled'
        group.save(update_fields=['status', 'updated_at'])

        return Response({'status': result.auth_status})


class PaymentRefundView(APIView):
    """
    POST /api/payment/refund/

    Request:  { order_group_id: int, amount?: int }  (amount 생략 시 전액 환불)
    Response: { status, refund_amount }
    """

    def post(self, request):
        order_group_id = request.data.get('order_group_id')
        if not order_group_id:
            return Response({'error': 'order_group_id required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            group = OrderGroup.objects.get(pk=order_group_id)
        except OrderGroup.DoesNotExist:
            return Response({'error': 'OrderGroup not found'}, status=status.HTTP_404_NOT_FOUND)

        pg = _get_pg(group.group_number)
        if not pg:
            return Response({'error': 'PGTransaction not found'}, status=status.HTTP_404_NOT_FOUND)

        refund_amount = request.data.get('amount')
        if refund_amount is not None:
            refund_amount = int(refund_amount)

        from .refund import execute_pg_refund
        try:
            result, actual_refund = execute_pg_refund(pg, amount=refund_amount)
        except ProviderError as e:
            logger.error("refund failed order=%s provider=%s err=%s", group.group_number, pg.provider, e)
            return Response(
                {'error': '환불 실패', 'provider_code': e.code, 'detail': e.message},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # 부분 환불이면 그룹은 'partial', 전액이면 'cancelled'
        is_partial = bool(refund_amount) and pg.amount_jpy and refund_amount < pg.amount_jpy
        group.status = 'partial' if is_partial else 'cancelled'
        group.save(update_fields=['status', 'updated_at'])

        return Response({'status': result.auth_status, 'refund_amount': actual_refund})


class PaymentStatusView(APIView):
    """
    GET /api/payment/status/<order_id>/

    PG 거래 현황 조회.
    """

    def get(self, request, order_id):
        pg = (
            PGTransaction.objects.filter(provider_order_id=order_id).first()
            or PGTransaction.objects.filter(gmo_order_id=order_id).first()
        )
        provider_name = pg.provider if pg else _PROVIDER
        provider = get_provider(provider_name)

        try:
            result = provider.get_status(order_id)
        except ProviderError as e:
            return Response(
                {'error': '조회 실패', 'provider_code': e.code, 'detail': e.message},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response({
            **result,
            'local_status': pg.auth_status if pg else None,
        })
