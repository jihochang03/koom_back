from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status as http_status
from django.shortcuts import get_object_or_404
from .models import Inquiry, CancelRequest, RefundRequest
from .serializers import (
    InquirySerializer, InquiryCreateSerializer, InquiryReplySerializer,
    CancelRequestSerializer, CancelRequestCreateSerializer, CancelRequestAdminSerializer,
    RefundRequestSerializer, RefundRequestCreateSerializer, RefundRequestAdminSerializer,
    PurchaseCompleteSerializer,
)

def _guard_change_of_mind(order_number, reason_type):
    """단순변심 취소/환불 컷오프 가드.

    `reason_type == 'change_of_mind'` 이고 주문이 FastBox 인계(preparing_dispatch)
    이후이면 차단 사유 dict 를 반환, 그 외엔 None(통과). 귀책 사유는 항상 통과.
    """
    if reason_type != 'change_of_mind':
        return None
    from apps.orders.models import Order
    from apps.orders.policy import cancel_eligibility

    order = Order.objects.filter(order_number=order_number).first()
    if not order:
        return None
    elig = cancel_eligibility(order)
    if elig['can_cancel_change_of_mind']:
        return None
    return {
        'error':         elig['reason'],
        'current_stage': elig['current_stage'],
        'cutoff_stage':  elig['cutoff_stage'],
    }


# ── Inquiry ───────────────────────────────────────────────────────────────────

class InquiryListView(APIView):
    def get(self, request):
        customer_id = request.query_params.get('customer_id')
        status_f    = request.query_params.get('status')
        qs = Inquiry.objects.all()
        if customer_id:
            qs = qs.filter(customer_id=customer_id)
        if status_f:
            qs = qs.filter(status=status_f)
        return Response(InquirySerializer(qs, many=True).data)

    def post(self, request):
        ser = InquiryCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        inquiry = Inquiry.objects.create(**d)
        return Response(InquirySerializer(inquiry).data, status=http_status.HTTP_201_CREATED)


class InquiryDetailView(APIView):
    def get(self, request, pk):
        inquiry = get_object_or_404(Inquiry, pk=pk)
        return Response(InquirySerializer(inquiry).data)

    def patch(self, request, pk):
        """어드민: 답변 등록 + 상태 변경"""
        inquiry = get_object_or_404(Inquiry, pk=pk)
        ser = InquiryReplySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        inquiry.admin_reply = d['admin_reply']
        inquiry.status      = d['status']
        inquiry.replied_at  = timezone.now()
        inquiry.save()
        return Response(InquirySerializer(inquiry).data)


# ── Cancel ────────────────────────────────────────────────────────────────────

class CancelRequestListView(APIView):
    def get(self, request):
        customer_id = request.query_params.get('customer_id')
        status_f    = request.query_params.get('status')
        qs = CancelRequest.objects.all()
        if customer_id:
            qs = qs.filter(customer_id=customer_id)
        if status_f:
            qs = qs.filter(status=status_f)
        return Response(CancelRequestSerializer(qs, many=True).data)

    def post(self, request):
        ser = CancelRequestCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        if CancelRequest.objects.filter(order_number=d['order_number']).exists():
            return Response({'error': '이미 취소 요청이 존재합니다.'}, status=http_status.HTTP_409_CONFLICT)
        blocked = _guard_change_of_mind(d['order_number'], d['reason_type'])
        if blocked:
            return Response(blocked, status=http_status.HTTP_409_CONFLICT)
        obj = CancelRequest.objects.create(**d)
        return Response(CancelRequestSerializer(obj).data, status=http_status.HTTP_201_CREATED)


class CancelRequestDetailView(APIView):
    def get(self, request, pk):
        return Response(CancelRequestSerializer(get_object_or_404(CancelRequest, pk=pk)).data)

    def patch(self, request, pk):
        """어드민: 취소 요청 처리"""
        obj = get_object_or_404(CancelRequest, pk=pk)
        ser = CancelRequestAdminSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        obj.status = d['status']
        if 'shipping_fee_burden' in d:
            obj.shipping_fee_burden = d['shipping_fee_burden']
        if 'admin_notes' in d:
            obj.admin_notes = d['admin_notes']
        if d['status'] in ('approved', 'completed', 'rejected'):
            obj.processed_at = timezone.now()
        obj.save()
        return Response(CancelRequestSerializer(obj).data)


# ── Refund ────────────────────────────────────────────────────────────────────

class RefundRequestListView(APIView):
    def get(self, request):
        customer_id = request.query_params.get('customer_id')
        status_f    = request.query_params.get('status')
        qs = RefundRequest.objects.all()
        if customer_id:
            qs = qs.filter(customer_id=customer_id)
        if status_f:
            qs = qs.filter(status=status_f)
        return Response(RefundRequestSerializer(qs, many=True).data)

    def post(self, request):
        ser = RefundRequestCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        if RefundRequest.objects.filter(order_number=d['order_number']).exists():
            return Response({'error': '이미 환불 요청이 존재합니다.'}, status=http_status.HTTP_409_CONFLICT)
        blocked = _guard_change_of_mind(d['order_number'], d['reason_type'])
        if blocked:
            return Response(blocked, status=http_status.HTTP_409_CONFLICT)
        obj = RefundRequest.objects.create(**d)
        return Response(RefundRequestSerializer(obj).data, status=http_status.HTTP_201_CREATED)


class RefundRequestDetailView(APIView):
    def get(self, request, pk):
        return Response(RefundRequestSerializer(get_object_or_404(RefundRequest, pk=pk)).data)

    def patch(self, request, pk):
        """어드민: 환불 요청 처리"""
        obj = get_object_or_404(RefundRequest, pk=pk)
        ser = RefundRequestAdminSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        obj.status = d['status']
        if 'approved_amount' in d:
            obj.approved_amount = d['approved_amount']
        if 'admin_notes' in d:
            obj.admin_notes = d['admin_notes']
        if d['status'] in ('approved', 'partial_approved', 'rejected', 'completed'):
            obj.processed_at = timezone.now()
        obj.save()
        return Response(RefundRequestSerializer(obj).data)


class RefundExecuteView(APIView):
    """본사: 승인된 환불을 GMO로 실행 (FR-CS-03·FR-PAY-04, 화면 H-03).

    CS 접수·1차 처리(RefundRequestDetailView)로 status가 approved/partial_approved 가 된 뒤,
    본사가 이 엔드포인트로 실제 GMO 환불을 실행한다.
    실행 시: GMO 환불 → PGTransaction 갱신 → RefundRequest=completed →
            Order.refund_amount·status(refunded/partial_refund) → 이력 기록.

    Request body(선택): { hq_user: str }
    """

    def post(self, request, pk):
        obj = get_object_or_404(RefundRequest, pk=pk)
        if obj.status not in ('approved', 'partial_approved'):
            return Response(
                {'error': '환불 승인(approved/partial_approved) 상태에서만 실행할 수 있습니다.',
                 'current_status': obj.status},
                status=http_status.HTTP_409_CONFLICT,
            )

        from apps.orders.models import Order, PGTransaction, AdminActionLog, OrderStatusLog
        from apps.payment.refund import execute_pg_refund
        from apps.payment.providers.base import ProviderError

        amount = obj.approved_amount if obj.approved_amount is not None else obj.requested_amount

        # 개별 주문 → 그룹 번호로 PG 조회 (PG는 그룹 단위). 못 찾으면 order_number를 그룹으로 간주.
        order = Order.objects.filter(order_number=obj.order_number).first()
        group_number = order.group.group_number if order and order.group_id else obj.order_number
        pg = PGTransaction.objects.filter(order_number=group_number).order_by('-created_at').first()
        if not pg:
            return Response({'error': 'PG 거래를 찾을 수 없습니다.', 'group_number': group_number},
                            status=http_status.HTTP_404_NOT_FOUND)

        try:
            result, actual = execute_pg_refund(pg, amount=int(amount) if amount else None)
        except ProviderError as e:
            return Response({'error': 'GMO 환불 실패', 'provider_code': e.code, 'detail': e.message},
                            status=http_status.HTTP_502_BAD_GATEWAY)

        now = timezone.now()
        obj.status = 'completed'
        obj.approved_amount = actual
        obj.processed_at = now
        obj.save()

        order_status = None
        if order:
            full = bool(pg.amount_jpy) and actual >= pg.amount_jpy
            order.refund_amount = actual
            order.refund_reason = obj.reason
            order.status = 'refunded' if full else 'partial_refund'
            order.save(update_fields=['refund_amount', 'refund_reason', 'status', 'updated_at'])
            order_status = order.status
            OrderStatusLog.objects.create(
                order_number=order.order_number, stage='cancelled_or_refunded',
                changed_at=now, responsible_party='dk', memo=f"환불 실행 {actual} {pg.currency}",
            )
            AdminActionLog.objects.create(
                order_number=order.order_number, changed_field='refund_execute',
                old_value={'status': 'approved'},
                new_value={'refund_amount': actual, 'status': order.status},
                actor_type='operator', actor_id=request.data.get('hq_user', ''),
                reason='본사 환불 승인·실행',
            )

        return Response({
            'status': 'completed',
            'refund_amount': actual,
            'pg_status': result.auth_status,
            'order_status': order_status,
        })


# ── 대리구매 작업 (FR-ORD-07, C-01) ─────────────────────────────────────────────

def _purchase_task_payload(order, record=None):
    """대리구매 작업 카드 데이터 (CS가 직접 구매할 때 필요한 원본 정보)."""
    return {
        'order_number':  order.order_number,
        'group_number':  order.group.group_number if order.group_id else '',
        'customer_id':   order.customer_id,
        'site_domain':   order.site_domain,
        'product_url':   order.product_url,        # 원본 URL — CS가 이 링크로 직접 구매
        'title':         order.title,
        'options':       order.options,
        'quantity':      order.quantity,
        'expected_price': order.price_product,     # 예상 상품가
        'price_total':   order.price_total,
        'currency':      order.currency,
        'status':        order.status,
        'purchase_record': _record_data(record) if record else None,
    }


def _record_data(r):
    return {
        'order_number':          r.order_number,
        'purchase_account':      r.purchase_account,
        'collection_address':    r.collection_address,
        'actual_price':          r.actual_price,
        'domestic_shipping_fee': r.domestic_shipping_fee,
        'currency':              r.currency,
        'cs_user':               r.cs_user,
        'memo':                  r.memo,
        'purchased_at':          r.purchased_at,
        'updated_at':            r.updated_at,
    }


class PurchaseTaskListView(APIView):
    """대리구매 대기/처리 목록. ?state=pending|done, ?cs_user= (담당 필터)"""

    def get(self, request):
        from apps.orders.models import Order, PurchaseRecord

        state   = request.query_params.get('state', 'pending')
        cs_user = request.query_params.get('cs_user')

        done_orders = set(PurchaseRecord.objects.values_list('order_number', flat=True))

        if state == 'done':
            qs = Order.objects.select_related('group').filter(order_number__in=done_orders)
            if cs_user:
                mine = set(PurchaseRecord.objects.filter(cs_user=cs_user).values_list('order_number', flat=True))
                qs = qs.filter(order_number__in=mine)
            records = {r.order_number: r for r in PurchaseRecord.objects.filter(
                order_number__in=qs.values_list('order_number', flat=True))}
            return Response([_purchase_task_payload(o, records.get(o.order_number)) for o in qs])

        # pending: 결제 완료(paid)이고 아직 대리구매 기록이 없는 주문
        qs = Order.objects.select_related('group').filter(status='paid').exclude(order_number__in=done_orders)
        return Response([_purchase_task_payload(o) for o in qs])


class PurchaseTaskCompleteView(APIView):
    """대리구매 완료 — 구매 계정·집하주소·실제가·국내배송비 입력 (FR-ORD-07).

    저장 시: PurchaseRecord upsert → Order.status paid→purchasing,
    가격 오차 검사(FR-ORD-04) → ErrorCriteria 기준 자동/CS전환,
    OrderStatusLog(purchase_complete) + AdminActionLog 기록.
    """

    def post(self, request, order_number):
        from apps.orders.models import Order, PurchaseRecord, OrderStatusLog, AdminActionLog, ErrorInfo

        order = get_object_or_404(Order, order_number=order_number)
        ser = PurchaseCompleteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        record, _ = PurchaseRecord.objects.update_or_create(
            order_number=order_number,
            defaults={
                'purchase_account':      d.get('purchase_account', ''),
                'collection_address':    d.get('collection_address', ''),
                'actual_price':          d['actual_price'],
                'domestic_shipping_fee': d.get('domestic_shipping_fee', 0),
                'currency':              d.get('currency', 'KRW'),
                'cs_user':               d.get('cs_user', ''),
                'memo':                  d.get('memo', ''),
                'purchased_at':          d.get('purchased_at') or timezone.now(),
            },
        )

        # 주문에 실제 구매가 반영 + 상태 전이
        order.price_actual = d['actual_price']
        prev_status = order.status
        order.status = 'purchasing'
        order.save(update_fields=['price_actual', 'status', 'updated_at'])

        # 가격 오차 검사 (FR-ORD-04)
        error_result = _evaluate_price_error(order, d['actual_price'])

        # 이력 기록
        OrderStatusLog.objects.create(
            order_number=order_number, stage='purchase_complete',
            changed_at=timezone.now(), responsible_party='dk',
            memo=f"CS 대리구매 완료 (계정: {d.get('purchase_account', '-') or '-'})",
        )
        AdminActionLog.objects.create(
            order_number=order_number, changed_field='purchase_complete',
            old_value={'status': prev_status}, new_value={'status': 'purchasing', 'actual_price': d['actual_price']},
            actor_type='operator', actor_id=d.get('cs_user', ''),
            reason='CS 대리구매 작업 완료',
        )

        return Response({
            'purchase_record': _record_data(record),
            'order_status': order.status,
            'price_error': error_result,
        }, status=http_status.HTTP_200_OK)


def _evaluate_price_error(order, actual_price):
    """실제 구매가 vs 예상가 오차 → ErrorCriteria 기준으로 자동/CS전환 판정."""
    from apps.orders.models import ErrorInfo
    try:
        from apps.operations.models import ErrorCriteria
        criteria = ErrorCriteria.objects.filter(is_current=True).first()
    except Exception:
        criteria = None

    base = order.price_product or 0
    error_amount = actual_price - base
    error_rate = (error_amount / base * 100) if base else 0

    small_pct = criteria.small_error_threshold_pct if criteria else 2.0
    small_abs = criteria.small_error_threshold_abs if criteria else 500.0
    large_pct = criteria.large_error_threshold_pct if criteria else 5.0

    if abs(error_rate) <= small_pct or abs(error_amount) <= small_abs:
        handling, auto = 'company_burden', True
    elif abs(error_rate) > large_pct:
        handling, auto = 'cs_review', False
    else:
        handling, auto = 'cs_review', False

    ErrorInfo.objects.update_or_create(
        order_number=order.order_number,
        defaults={
            'error_rate': round(error_rate, 2),
            'error_amount': error_amount,
            'error_causes': ['price_change'],
            'handling_method': handling,
            'auto_processed': auto,
            'cs_review_reason': '' if auto else f"가격 오차율 {round(error_rate, 2)}% (기준 {large_pct}% 초과)",
        },
    )

    # 회사 부담 자동 처리 시 DK 부담액 반영 (회사가 초과분 흡수)
    if auto and error_amount > 0:
        order.price_dk_burden = error_amount
        order.company_burden_error_small = error_amount
        order.save(update_fields=['price_dk_burden', 'company_burden_error_small', 'updated_at'])

    return {
        'error_rate': round(error_rate, 2),
        'error_amount': error_amount,
        'handling_method': handling,
        'auto_processed': auto,
    }
