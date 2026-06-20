import logging

from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.models import OrderGroup, PGTransaction
from .providers.base import ProviderError
from .providers.registry import get_provider

logger = logging.getLogger(__name__)

_PROVIDER = 'gmo_paypay'


def _make_order_id(group_number: str) -> str:
    return ('PP-' + group_number.replace('/', '-'))[:27]


def _get_pg(group_number: str) -> PGTransaction | None:
    return PGTransaction.objects.filter(order_number=group_number, provider=_PROVIDER).order_by('-created_at').first()


class PayPayEntryView(APIView):
    """
    POST /api/payment/paypay/entry/

    PayPay 거래 등록 → QR 결제 URL 반환.

    Request:  { order_group_id: int, return_url: str }
    Response: { provider, provider_order_id, access_id, access_pass, qr_url, amount, currency }
    """

    def post(self, request):
        order_group_id = request.data.get('order_group_id')
        return_url     = request.data.get('return_url', '')

        if not order_group_id or not return_url:
            return Response({'error': 'order_group_id and return_url required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            group = OrderGroup.objects.get(pk=order_group_id)
        except OrderGroup.DoesNotExist:
            return Response({'error': 'OrderGroup not found'}, status=status.HTTP_404_NOT_FOUND)

        amount = int(group.total_paid) if group.total_paid else 0
        if amount <= 0:
            return Response({'error': 'Invalid order amount'}, status=status.HTTP_400_BAD_REQUEST)

        provider = get_provider(_PROVIDER)
        try:
            entry = provider.entry(
                order_id=_make_order_id(group.group_number),
                amount=amount,
                currency='JPY',
                return_url=return_url,
            )
        except ProviderError as e:
            logger.error("PayPay entry failed group=%s err=%s", group.group_number, e)
            return Response(
                {'error': 'PayPay 거래 등록 실패', 'provider_code': e.code, 'detail': e.message},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response({'provider': _PROVIDER, **entry.client_payload})


class PayPayExecuteView(APIView):
    """
    POST /api/payment/paypay/execute/

    고객 PayPay 결제 완료 후 서버에서 확정 처리.

    Request:  { order_group_id: int, provider_order_id: str, access_id: str, access_pass: str }
    Response: { status, transaction_id, forward, tran_date, pg_id }
    """

    def post(self, request):
        d = request.data
        required = ('order_group_id', 'provider_order_id', 'access_id', 'access_pass')
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
            )
        except ProviderError as e:
            logger.error("PayPay execute failed group=%s err=%s", group.group_number, e)
            return Response(
                {'error': 'PayPay 결제 확정 실패', 'provider_code': e.code, 'detail': e.message},
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
            gmo_job_cd='CAPTURE',
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
            'forward':        result.raw.get('Forward', ''),
            'tran_date':      result.raw.get('TranDate', ''),
            'pg_id':          pg.id,
        })


class PayPayStatusView(APIView):
    """
    GET /api/payment/paypay/status/<order_id>/

    PayPay 거래 상태 조회.
    """

    def get(self, request, order_id):
        provider = get_provider(_PROVIDER)
        try:
            result = provider.get_status(order_id)
        except ProviderError as e:
            return Response(
                {'error': '조회 실패', 'provider_code': e.code, 'detail': e.message},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        pg = (
            PGTransaction.objects.filter(provider_order_id=order_id, provider=_PROVIDER).first()
            or PGTransaction.objects.filter(gmo_order_id=order_id).first()
        )
        return Response({**result, 'local_status': pg.auth_status if pg else None})
