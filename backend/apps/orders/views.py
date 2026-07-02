from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status as http_status
from django.shortcuts import get_object_or_404
from .models import (Order, OrderGroup, OrderStatusLog, AdminActionLog, ErrorInfo, PGTransaction, ProductSnapshot)
from .serializers import (
    OrderSerializer, OrderGroupSerializer, OrderGroupSummarySerializer,
    OrderGroupCreateSerializer, OrderStatusUpdateSerializer, OrderAdminUpdateSerializer,
)


class OrderGroupCreateView(APIView):
    """장바구니 → 주문 그룹 생성 (결제 전 pending 상태)"""

    def post(self, request):
        ser = OrderGroupCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        group = OrderGroup.objects.create(
            customer_id=data['customer_id'],
            bundle_fee=data['bundle_fee'],
            coupon_discount=data['coupon_discount'],
            point_discount=data['point_discount'],
        )

        orders = []
        for item in data['items']:
            orders.append(Order(
                group=group,
                customer_id=data['customer_id'],
                **{k: item[k] for k in item if k in {
                    'product_url', 'title', 'options', 'quantity',
                    'price_product', 'price_domestic_shipping', 'price_intl_shipping',
                    'price_tariff', 'price_fee', 'price_total', 'currency',
                    'site_domain', 'product_snapshot',
                    'estimated_delivery_min', 'estimated_delivery_max',
                } and k in item}
            ))
        Order.objects.bulk_create(orders)

        group.total_paid = sum(o.price_total for o in orders) + group.bundle_fee - group.coupon_discount - group.point_discount
        group.save(update_fields=['total_paid'])

        return Response(OrderGroupSerializer(group).data, status=http_status.HTTP_201_CREATED)


class OrderGroupListView(APIView):
    def get(self, request):
        customer_id = request.query_params.get('customer_id')
        qs = OrderGroup.objects.all()
        if customer_id:
            qs = qs.filter(customer_id=customer_id)
        return Response(OrderGroupSummarySerializer(qs, many=True).data)


class OrderGroupDetailView(APIView):
    def get(self, request, group_number):
        group = get_object_or_404(OrderGroup, group_number=group_number)
        return Response(OrderGroupSerializer(group).data)


class OrderListView(APIView):
    def get(self, request):
        customer_id = request.query_params.get('customer_id')
        status_filter = request.query_params.get('status')
        qs = Order.objects.select_related('group').all()
        if customer_id:
            qs = qs.filter(customer_id=customer_id)
        if status_filter:
            qs = qs.filter(status=status_filter)
        return Response(OrderSerializer(qs, many=True).data)


class OrderDetailView(APIView):
    def get(self, request, order_number):
        order = get_object_or_404(Order, order_number=order_number)
        from .policy import cancel_eligibility
        data = OrderSerializer(order).data
        # 단순변심 취소 가능 여부 (프론트 취소 버튼 노출 제어) — FastBox 인계 컷오프
        data['cancel_eligibility'] = cancel_eligibility(order)
        return Response(data)


class OrderStatusUpdateView(APIView):
    """배송 상태 업데이트 (어드민)"""

    def patch(self, request, order_number):
        order = get_object_or_404(Order, order_number=order_number)
        ser = OrderStatusUpdateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        order.status = d['status']
        if 'tracking_number' in d:
            order.tracking_number = d['tracking_number']
        if 'estimated_delivery_min' in d:
            order.estimated_delivery_min = d['estimated_delivery_min']
        if 'estimated_delivery_max' in d:
            order.estimated_delivery_max = d['estimated_delivery_max']
        order.save()

        # 그룹 상태 자동 동기화
        _sync_group_status(order.group)

        return Response(OrderSerializer(order).data)


class OrderAdminUpdateView(APIView):
    """DK 부담액·검수 이슈·환불 등 어드민 전용 업데이트"""

    def patch(self, request, order_number):
        order = get_object_or_404(Order, order_number=order_number)
        ser = OrderAdminUpdateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        for field in ['price_dk_burden', 'price_actual', 'admin_notes',
                      'inspection_notes', 'refund_amount', 'refund_reason']:
            if field in d:
                setattr(order, field, d[field])
        order.save()
        return Response(OrderSerializer(order).data)


def _sync_group_status(group: OrderGroup):
    statuses = set(group.orders.values_list('status', flat=True))
    if statuses <= {'delivered'}:
        group.status = 'completed'
    elif statuses & {'cancelled', 'refunded'}:
        group.status = 'partial'
    elif 'paid' in statuses:
        group.status = 'paid'
    group.save(update_fields=['status'])


# ── Admin dashboard ───────────────────────────────────────────────────────────

class AdminDashboardView(APIView):
    """
    어드민 운영 대시보드: 미해결 검토 건, 지연/정체, CS 현황.
    현재는 DB 직접 집계. CS 앱 연동은 CS 앱 설치 후 자동 반영.
    """

    def get(self, request):
        from django.db.models import Q

        # 수동 확인 대기
        inspection_issues = Order.objects.filter(
            inspection_notes__gt='', status__in=['inspection', 'shipping_intl', 'delivered']
        ).count()

        refunds_pending = Order.objects.filter(
            refund_amount__isnull=False, status='partial_refund'
        ).count()

        # 배송 지연/정체: 3일 이상 status 미변경 (updated_at 기준)
        from django.utils import timezone
        from datetime import timedelta
        stale_threshold = timezone.now() - timedelta(days=3)
        shipping_stalled = Order.objects.filter(
            status__in=['shipping_domestic', 'inspection', 'shipping_intl'],
            updated_at__lt=stale_threshold,
        ).count()

        # CS 미해결 건 (cs 앱이 없으면 0)
        cs_open = 0
        try:
            from apps.cs.models import Inquiry, CancelRequest, RefundRequest
            cs_open = (
                Inquiry.objects.filter(status__in=['open', 'in_progress']).count()
                + CancelRequest.objects.filter(status='pending').count()
                + RefundRequest.objects.filter(status='pending').count()
            )
        except Exception:
            pass

        # 상태별 주문 집계
        from django.db.models import Count
        status_counts = dict(
            Order.objects.values_list('status').annotate(cnt=Count('id')).values_list('status', 'cnt')
        )

        return Response({
            'manual_review': {
                'inspection_issues': inspection_issues,
                'refunds_pending':   refunds_pending,
            },
            'delays': {
                'shipping_stalled': shipping_stalled,
            },
            'cs_open': cs_open,
            'order_status_counts': status_counts,
        })


class AdminOrderListView(APIView):
    """
    어드민 주문 목록: 기간·상태·환불·오류 필터 지원.
    tabs: all | in_progress | completed | refund | error
    """

    def get(self, request):
        from django.utils.dateparse import parse_date

        qs = Order.objects.select_related('group').all()

        tab = request.query_params.get('tab', 'all')
        if tab == 'in_progress':
            qs = qs.filter(status__in=['paid', 'purchasing', 'shipping_domestic', 'inspection', 'shipping_intl'])
        elif tab == 'completed':
            qs = qs.filter(status='delivered')
        elif tab == 'refund':
            qs = qs.filter(status__in=['refunded', 'partial_refund'])
        elif tab == 'error':
            qs = qs.filter(inspection_notes__gt='')

        date_from = request.query_params.get('date_from')
        date_to   = request.query_params.get('date_to')
        if date_from:
            qs = qs.filter(created_at__date__gte=parse_date(date_from))
        if date_to:
            qs = qs.filter(created_at__date__lte=parse_date(date_to))

        status_f = request.query_params.get('status')
        if status_f:
            qs = qs.filter(status=status_f)

        has_refund = request.query_params.get('has_refund')
        if has_refund == 'true':
            qs = qs.filter(status__in=['refunded', 'partial_refund'])

        has_error = request.query_params.get('has_error')
        if has_error == 'true':
            qs = qs.filter(inspection_notes__gt='')

        return Response(OrderSerializer(qs, many=True).data)


# ── Order Status Log ──────────────────────────────────────────────────────────

class OrderStatusLogView(APIView):
    def get(self, request, order_number):
        logs = OrderStatusLog.objects.filter(order_number=order_number)
        return Response([{
            'id': l.id, 'stage': l.stage, 'stage_display': l.get_stage_display(),
            'changed_at': l.changed_at, 'responsible_party': l.responsible_party,
            'responsible_party_display': l.get_responsible_party_display(),
            'memo': l.memo, 'available_actions': l.available_actions,
        } for l in logs])

    def post(self, request, order_number):
        from django.utils import timezone
        data = request.data
        stage = data.get('stage')
        if not stage:
            return Response({'error': 'stage required'}, status=400)
        log = OrderStatusLog.objects.create(
            order_number=order_number,
            stage=stage,
            changed_at=data.get('changed_at') or timezone.now(),
            responsible_party=data.get('responsible_party', 'system'),
            memo=data.get('memo', ''),
            available_actions=data.get('available_actions'),
        )
        return Response({'id': log.id, 'stage': log.stage}, status=201)


# ── Admin Action Log ──────────────────────────────────────────────────────────

class AdminActionLogView(APIView):
    def get(self, request, order_number):
        logs = AdminActionLog.objects.filter(order_number=order_number)
        return Response([{
            'id': l.id, 'changed_field': l.changed_field, 'old_value': l.old_value,
            'new_value': l.new_value, 'actor_type': l.actor_type,
            'actor_type_display': l.get_actor_type_display(),
            'actor_id': l.actor_id, 'reason': l.reason, 'changed_at': l.changed_at,
        } for l in logs])

    def post(self, request, order_number):
        data = request.data
        log = AdminActionLog.objects.create(
            order_number=order_number,
            changed_field=data.get('changed_field', ''),
            old_value=data.get('old_value'),
            new_value=data.get('new_value'),
            actor_type=data.get('actor_type', 'operator'),
            actor_id=data.get('actor_id', ''),
            reason=data.get('reason', ''),
        )
        return Response({'id': log.id}, status=201)


# ── Error Info ────────────────────────────────────────────────────────────────

class ErrorInfoView(APIView):
    def get(self, request, order_number):
        try:
            ei = ErrorInfo.objects.get(order_number=order_number)
        except ErrorInfo.DoesNotExist:
            return Response({'error': 'not found'}, status=404)
        return Response({
            'id': ei.id, 'order_number': ei.order_number,
            'error_rate': ei.error_rate, 'error_amount': ei.error_amount,
            'error_causes': ei.error_causes,
            'handling_method': ei.handling_method,
            'handling_method_display': ei.get_handling_method_display(),
            'auto_processed': ei.auto_processed,
            'cs_review_reason': ei.cs_review_reason,
            'additional_charge_amount': ei.additional_charge_amount,
            'additional_charge_sent_at': ei.additional_charge_sent_at,
            'additional_charge_accepted_at': ei.additional_charge_accepted_at,
            'updated_at': ei.updated_at,
        })

    def put(self, request, order_number):
        ei, _ = ErrorInfo.objects.get_or_create(order_number=order_number)
        d = request.data
        for field in ['error_rate', 'error_amount', 'error_causes', 'handling_method',
                      'auto_processed', 'cs_review_reason', 'additional_charge_amount',
                      'additional_charge_sent_at', 'additional_charge_accepted_at']:
            if field in d:
                setattr(ei, field, d[field])
        ei.save()
        return Response({'id': ei.id, 'order_number': ei.order_number, 'updated_at': str(ei.updated_at)})


# ── PG Transaction ────────────────────────────────────────────────────────────

class PGTransactionListView(APIView):
    def get(self, request, order_number):
        txns = PGTransaction.objects.filter(order_number=order_number)
        return Response([{
            'id': t.id, 'pg_transaction_id': t.pg_transaction_id,
            'auth_status': t.auth_status,
            'auth_status_display': t.get_auth_status_display(),
            'refund_amount': t.refund_amount,
            'refund_requested_at': t.refund_requested_at,
            'refund_completed_at': t.refund_completed_at,
            'failure_reason': t.failure_reason,
            'raw_payload': t.raw_payload,
            'created_at': t.created_at,
        } for t in txns])

    def post(self, request, order_number):
        d = request.data
        pg_id = d.get('pg_transaction_id')
        if not pg_id:
            return Response({'error': 'pg_transaction_id required'}, status=400)
        txn, created = PGTransaction.objects.get_or_create(
            pg_transaction_id=pg_id,
            defaults={
                'order_number': order_number,
                'auth_status': d.get('auth_status', 'pending'),
                'refund_amount': d.get('refund_amount'),
                'failure_reason': d.get('failure_reason', ''),
                'raw_payload': d.get('raw_payload'),
            }
        )
        if not created:
            for field in ['auth_status', 'refund_amount', 'refund_requested_at',
                          'refund_completed_at', 'failure_reason', 'raw_payload']:
                if field in d:
                    setattr(txn, field, d[field])
            txn.save()
        return Response({'id': txn.id, 'pg_transaction_id': txn.pg_transaction_id}, status=201 if created else 200)


# ── Product Snapshot (Section 19) ──────────────────────────────────────────────

class ProductSnapshotView(APIView):
    """구매 완료 상품의 사본 생성·조회 (어드민)."""

    def get(self, request, order_number):
        try:
            snap = ProductSnapshot.objects.get(order_number=order_number)
        except ProductSnapshot.DoesNotExist:
            return Response({'error': 'not found'}, status=404)
        return Response(_snap_data(snap))

    def put(self, request, order_number):
        snap, created = ProductSnapshot.objects.get_or_create(order_number=order_number)
        d = request.data
        for field in ['product_name', 'product_name_en', 'purchase_price',
                      'product_price_at_purchase', 'options', 'quantity',
                      'seller', 'site_domain', 'product_url', 'images', 'html_content']:
            if field in d:
                setattr(snap, field, d[field])
        snap.save()

        # Order.product_copy_url 자동 업데이트
        try:
            from django.conf import settings
            base = getattr(settings, 'SITE_BASE_URL', 'https://koom.jp')
            copy_url = f"{base}/snapshots/{snap.snapshot_uuid}/"
            Order.objects.filter(order_number=order_number).update(product_copy_url=copy_url)
        except Exception:
            pass

        return Response(_snap_data(snap), status=201 if created else 200)


class ProductSnapshotPublicView(APIView):
    """세관 제출용 공개 사본 페이지 JSON (UUID 기반)."""

    def get(self, request, snapshot_uuid):
        try:
            snap = ProductSnapshot.objects.get(snapshot_uuid=snapshot_uuid)
        except ProductSnapshot.DoesNotExist:
            return Response({'error': 'not found'}, status=404)
        return Response(_snap_data(snap))


class ProductSnapshotHTMLView(APIView):
    """세관 제출용 공개 사본 페이지 HTML 렌더링 (UUID 기반)."""

    def get(self, request, snapshot_uuid):
        from django.shortcuts import render
        try:
            snap = ProductSnapshot.objects.get(snapshot_uuid=snapshot_uuid)
        except ProductSnapshot.DoesNotExist:
            from django.http import Http404
            raise Http404
        return render(request, 'orders/product_snapshot.html', {'snap': snap})


def _snap_data(snap):
    return {
        'order_number': snap.order_number,
        'snapshot_uuid': str(snap.snapshot_uuid),
        'product_name': snap.product_name,
        'product_name_en': snap.product_name_en,
        'purchase_price': snap.purchase_price,
        'product_price_at_purchase': snap.product_price_at_purchase,
        'options': snap.options,
        'quantity': snap.quantity,
        'seller': snap.seller,
        'site_domain': snap.site_domain,
        'product_url': snap.product_url,
        'images': snap.images,
        'html_content': snap.html_content,
        'created_at': snap.created_at,
    }
