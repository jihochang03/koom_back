from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status as http_status
from .models import LogisticsInfo, ShippingTracking
from .serializers import LogisticsInfoSerializer, ShippingTrackingSerializer, InspectionSerializer


def _record_transition(order_number, *, stage, new_status=None, actor_id='',
                       field='', reason='', responsible='logistics', extra_new=None):
    """주문 상태 전이 + OrderStatusLog/AdminActionLog 기록 (검수·FastBox 인계 공통)."""
    from django.utils import timezone
    from apps.orders.models import Order, OrderStatusLog, AdminActionLog

    order = Order.objects.filter(order_number=order_number).first()
    prev = order.status if order else None
    if order and new_status and order.status != new_status:
        order.status = new_status
        order.save(update_fields=['status', 'updated_at'])

    OrderStatusLog.objects.create(
        order_number=order_number, stage=stage, changed_at=timezone.now(),
        responsible_party=responsible, memo=reason,
    )
    if field:
        AdminActionLog.objects.create(
            order_number=order_number, changed_field=field,
            old_value={'status': prev}, new_value=(extra_new or {'status': new_status}),
            actor_type='logistics', actor_id=actor_id, reason=reason,
        )
    return order


def _default_address(customer_id):
    """고객 기본 배송지(UserAddress) → DHUB CONSIGNEE 필드 매핑. 없으면 빈 dict."""
    try:
        from apps.mypage.models import UserAddress
        a = (UserAddress.objects.filter(customer_id=customer_id, is_default=True).first()
             or UserAddress.objects.filter(customer_id=customer_id).first())
    except Exception:
        a = None
    if not a:
        return {}
    return {
        'receiver_name':       a.name,
        'receiver_name_voice': a.name_kana,   # 가타카나 (DHUB 필수)
        'receiver_name_en':    a.name_en,     # 영문 (CI 서류)
        'receiver_cell':       a.phone,
        'receiver_zipcode':    a.zipcode,
        'receiver_address1':   a.address1,
        'receiver_address2':   a.address2,
        'date_of_birth':       a.date_of_birth.isoformat() if a.date_of_birth else '',
    }


class LogisticsInfoView(APIView):
    def get(self, request, order_number):
        try:
            obj = LogisticsInfo.objects.get(order_number=order_number)
            return Response(LogisticsInfoSerializer(obj).data)
        except LogisticsInfo.DoesNotExist:
            return Response({'error': 'not found'}, status=http_status.HTTP_404_NOT_FOUND)

    def put(self, request, order_number):
        obj, created = LogisticsInfo.objects.get_or_create(order_number=order_number)
        ser = LogisticsInfoSerializer(obj, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, status=http_status.HTTP_201_CREATED if created else http_status.HTTP_200_OK)


class InspectionView(APIView):
    """상품 검수 등록 (FR-LOG-05, 화면 C-02).

    result=pass → 검수 완료 / result=issue → 이슈 기록 + CS Inquiry 자동 생성.
    공통: LogisticsInfo upsert, Order.status → inspection,
          OrderStatusLog(inspection_complete) + AdminActionLog 기록.
    """

    def post(self, request, order_number):
        from django.utils import timezone

        ser = InspectionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        info, _ = LogisticsInfo.objects.get_or_create(order_number=order_number)
        if not info.arrived_at:
            info.arrived_at = timezone.now()
        info.inspection_result = d['result']
        for f in ['components_match', 'has_defect', 'issue_reason',
                  'post_inspection_action', 'inspection_photos']:
            if f in d and d[f] is not None:
                setattr(info, f, d[f])
        info.save()

        inquiry_id = None
        if d['result'] == 'issue':
            from apps.orders.models import Order
            reason = d.get('issue_reason') or '검수 이슈 발생'
            order = Order.objects.filter(order_number=order_number).first()
            if order:
                order.inspection_notes = reason
                order.save(update_fields=['inspection_notes', 'updated_at'])
                try:
                    from apps.cs.models import Inquiry
                    inq = Inquiry.objects.create(
                        customer_id=order.customer_id, order_number=order_number,
                        inquiry_type='inspection_issue', title=f'[검수이슈] {order_number}',
                        content=reason, status='open',
                    )
                    inquiry_id = inq.id
                except Exception:
                    pass

        _record_transition(
            order_number, stage='inspection_complete', new_status='inspection',
            actor_id=d.get('inspector', ''), field='inspection',
            reason=f"검수 {d['result']}", extra_new={'inspection_result': d['result']},
        )

        return Response({
            'logistics':    LogisticsInfoSerializer(info).data,
            'inquiry_id':   inquiry_id,
            'order_status': 'inspection',
        }, status=http_status.HTTP_200_OK)


class ShippingTrackingView(APIView):
    def get(self, request, order_number):
        try:
            obj = ShippingTracking.objects.get(order_number=order_number)
            return Response(ShippingTrackingSerializer(obj).data)
        except ShippingTracking.DoesNotExist:
            return Response({'error': 'not found'}, status=http_status.HTTP_404_NOT_FOUND)

    def put(self, request, order_number):
        obj, created = ShippingTracking.objects.get_or_create(order_number=order_number)
        ser = ShippingTrackingSerializer(obj, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, status=http_status.HTTP_201_CREATED if created else http_status.HTTP_200_OK)


class StagnatedShipmentsView(APIView):
    """24시간 이상 정체된 배송 목록"""
    def get(self, request):
        hours = int(request.query_params.get('hours', 24))
        from django.utils import timezone
        from datetime import timedelta
        threshold = timezone.now() - timedelta(hours=hours)
        qs = ShippingTracking.objects.filter(
            last_status_changed_at__lt=threshold,
            delay_detected=True,
        ).exclude(customer_status__in=['delivered', 'cancelled'])
        return Response(ShippingTrackingSerializer(qs, many=True).data)


# ── DHUB (FastBox) 연동 ────────────────────────────────────────────────────────

class DHubRegisterView(APIView):
    """
    주문 등록 → FB 송장번호 채번.
    연동 시점: Order.status → purchase_complete 전환 시
    POST body: { address: { receiver_name, receiver_cell, receiver_email, ... } }
    """

    def post(self, request, order_number):
        from .dhub_client import DHubClient, DHubError

        try:
            from apps.orders.models import Order
            order = Order.objects.get(order_number=order_number)
        except Exception:
            return Response({'error': '주문을 찾을 수 없습니다.'}, status=404)

        # 고객 기본 배송지(UserAddress)에서 자동 채움 → 요청 body 값이 우선
        address = {**_default_address(order.customer_id), **request.data.get('address', {})}
        required = ['receiver_name', 'receiver_cell', 'receiver_email',
                    'receiver_zipcode', 'receiver_address1']
        missing = [f for f in required if not address.get(f)]
        if missing:
            return Response({
                'error': f'필수 필드 누락: {missing}',
                'hint': 'receiver_email 등 UserAddress에 없는 값은 body로 전달해야 합니다.',
            }, status=400)

        try:
            client = DHubClient()
            result = client.register_order(order, address)
        except DHubError as e:
            return Response({'error': e.message, 'dhub_code': e.code}, status=502)
        except Exception as e:
            return Response({'error': str(e)}, status=500)

        if not result.get('result', False):
            return Response({
                'error': 'DHUB 주문 등록 실패',
                'result_reason': result.get('result_reason'),
            }, status=422)

        tracking, _ = ShippingTracking.objects.get_or_create(order_number=order_number)
        tracking.fb_invoice_no       = result.get('fb_invoice_no', '')
        tracking.dhub_ord_bundle_no  = result.get('ord_bundle_no', '')
        tracking.dhub_delivery_type  = result.get('delivery_type', '')
        tracking.carrier_status      = 'ORE'
        tracking.customer_status     = '주문 접수'
        tracking.save()

        # 출고 준비 단계 기록 (FB 송장 채번 = FastBox 인계 시작)
        _record_transition(
            order_number, stage='preparing_dispatch',
            actor_id=request.data.get('operator', ''), field='dhub_register',
            reason=f"DHUB 주문 등록 (FB {result.get('fb_invoice_no')})",
            extra_new={'fb_invoice_no': result.get('fb_invoice_no')},
        )

        return Response({
            'fb_invoice_no':  result.get('fb_invoice_no'),
            'ord_no':         result.get('ord_no'),
            'delivery_type':  result.get('delivery_type'),
        }, status=http_status.HTTP_201_CREATED)


class DHubTrackingSyncView(APIView):
    """
    배송추적 동기화 → ShippingTracking 업데이트.
    연동 시점: 주기적 폴링 또는 어드민 수동 동기화
    """

    def post(self, request, order_number):
        from .dhub_client import DHubClient, DHubError
        from django.utils import timezone

        try:
            tracking = ShippingTracking.objects.get(order_number=order_number)
        except ShippingTracking.DoesNotExist:
            return Response({'error': '배송 추적 정보가 없습니다.'}, status=404)

        if not tracking.fb_invoice_no:
            return Response({'error': 'FB 송장번호가 없습니다. 먼저 DHUB 주문 등록이 필요합니다.'}, status=400)

        try:
            client = DHubClient()
            data = client.get_tracking(tracking.fb_invoice_no)
        except DHubError as e:
            return Response({'error': e.message, 'dhub_code': e.code}, status=502)
        except Exception as e:
            return Response({'error': str(e)}, status=500)

        now = timezone.now()
        trace_list = data.get('trace', [])

        tracking.events            = trace_list
        tracking.last_api_checked_at = now

        if trace_list:
            latest = trace_list[-1]
            status_code = latest.get('status_code', '')
            status_info = client.map_status(status_code)
            prev_status = tracking.carrier_status

            if status_code != prev_status:
                tracking.carrier_status        = status_code
                tracking.customer_status       = status_info.get('customer_status', status_code)
                tracking.last_status_changed_at = now

            order_info = data.get('order', {})
            jp_no = order_info.get('Domestic_Invoice_No', '')
            if jp_no:
                tracking.tracking_number = jp_no
                tracking.carrier = order_info.get('Shipping_Company', tracking.carrier)

        # 지연 감지
        if tracking.last_status_changed_at:
            diff_hours = (now - tracking.last_status_changed_at).total_seconds() / 3600
            if diff_hours >= 48:
                tracking.delay_detected = True
                tracking.delay_type     = '48h'
                tracking.delay_hours    = int(diff_hours)
                if not tracking.stagnation_detected_at:
                    tracking.stagnation_detected_at = now
            elif diff_hours >= 24:
                tracking.delay_detected = True
                tracking.delay_type     = '24h'
                tracking.delay_hours    = int(diff_hours)
                if not tracking.stagnation_detected_at:
                    tracking.stagnation_detected_at = now

        tracking.save()

        return Response({
            'carrier_status':       tracking.carrier_status,
            'customer_status':      tracking.customer_status,
            'tracking_number':      tracking.tracking_number,
            'events_count':         len(trace_list),
            'delay_detected':       tracking.delay_detected,
            'last_api_checked_at':  tracking.last_api_checked_at,
        })


class DHubDeliveryInstructionView(APIView):
    """
    배송지시: 창고 입고 완료 후 국제 발송 지시.
    연동 시점: LogisticsInfo.arrived_at 입력 후 (어드민 수동)
    POST body: { fb_invoice_nos: [...], requester_name, requester_phone, arrival_due_date }
    """

    def post(self, request):
        from .dhub_client import DHubClient, DHubError

        fb_invoice_nos  = request.data.get('fb_invoice_nos', [])
        requester_name  = request.data.get('requester_name', '')
        requester_phone = request.data.get('requester_phone', '')
        arrival_due     = request.data.get('arrival_due_date', '')

        if not fb_invoice_nos:
            return Response({'error': 'fb_invoice_nos 필수'}, status=400)
        if not arrival_due:
            return Response({'error': 'arrival_due_date 필수 (YYYY-MM-DD)'}, status=400)

        try:
            client = DHubClient()
            result = client.instruct_delivery(fb_invoice_nos, requester_name, requester_phone, arrival_due)
        except DHubError as e:
            return Response({'error': e.message, 'dhub_code': e.code}, status=502)
        except Exception as e:
            return Response({'error': str(e)}, status=500)

        instruction_no = result.get('instruction_no') if isinstance(result, dict) else None
        transitioned = []
        if instruction_no:
            affected = list(ShippingTracking.objects.filter(fb_invoice_no__in=fb_invoice_nos))
            ShippingTracking.objects.filter(
                fb_invoice_no__in=fb_invoice_nos
            ).update(dhub_instruction_no=instruction_no)
            # 배송지시 = 국제 발송 개시 → 주문 상태 shipping_intl 전이
            for t in affected:
                _record_transition(
                    t.order_number, stage='intl_shipping', new_status='shipping_intl',
                    actor_id=requester_name, field='dhub_instruction',
                    reason=f"DHUB 배송지시 {instruction_no}",
                    extra_new={'instruction_no': instruction_no},
                )
                transitioned.append(t.order_number)

        return Response({
            'instruction_no': instruction_no,
            'result':         result.get('result', []),
            'transitioned_orders': transitioned,
        })
