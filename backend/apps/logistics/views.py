import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status as http_status
from .models import LogisticsInfo, ShippingTracking, CustomsClearance, DeliveryFailure
from .serializers import (
    LogisticsInfoSerializer, ShippingTrackingSerializer, InspectionSerializer,
    CustomsClearanceSerializer, CustomsResultSerializer,
    DeliveryFailureSerializer, DeliveryFailureCreateSerializer,
    DeliveryFailureRespondSerializer, DeliveryFailureResolveSerializer,
)

logger = logging.getLogger(__name__)


def _notify_customer(customer_id, event, context, order_number=''):
    """고객 알림 best-effort 발송 (NotificationLog 기록). 실패해도 본 처리 막지 않음.

    수신자 주소 저장소가 아직 없어, 고객 알림 선호도(NotificationSetting)를 존중하되
    customer_id 가 이메일 형식이면 email 채널로 발송한다.
    """
    try:
        from apps.notify.dispatcher import notify_order_event
        from apps.mypage.models import NotificationSetting

        ns = NotificationSetting.objects.filter(customer_id=customer_id).first()
        channels, recipients = [], {}
        if (ns.order_status_email if ns else True) and '@' in (customer_id or ''):
            channels.append('email')
            recipients['email'] = customer_id
        if not channels:
            return {}
        return notify_order_event(
            customer_id=customer_id, event=event, channels=channels,
            recipients=recipients, context=context or {}, order_number=order_number,
        )
    except Exception:
        logger.exception("notify failed event=%s order=%s", event, order_number)
        return {}


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


def _confirmed_hs_classification(order):
    """
    주문 상품의 **확정된** HS 분류(ProductHsClassification) 조회.

    Order ↔ Product 직접 FK가 없으므로 `Order.product_url == Product.url`로 연결.
    검수 담당자가 확정(status=confirmed)하고 final_hs_code가 있을 때만 반환.
    """
    try:
        from apps.products.models import Product
        from apps.tariff.models import ProductHsClassification
    except Exception:
        return None
    if not getattr(order, 'product_url', ''):
        return None
    product = Product.objects.filter(url=order.product_url).first()
    if not product:
        return None
    cls = (
        ProductHsClassification.objects
        .filter(product=product, status=ProductHsClassification.Status.CONFIRMED)
        .exclude(final_hs_code='')
        .first()
    )
    return cls


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


class TrackingTimelineView(APIView):
    """
    GET  /api/logistics/{order_number}/timeline/
        고객 배송추적 화면 페이로드 — 5단계 진행 바 + 날짜별 이벤트 로그 + 최종 배송정보.

    POST /api/logistics/{order_number}/timeline/
        원천 이벤트 적재. body: { events: [{occurred_at, description, location?, source?, raw_code?}], source? }
        각 이벤트는 설명 텍스트로 5단계 자동 분류되고, 현재 단계·배송완료 정보가 재계산된다.
    """

    def get(self, request, order_number):
        from .timeline import build_timeline
        return Response(build_timeline(order_number))

    def post(self, request, order_number):
        from .timeline import ingest_tracking_events, build_timeline

        events = request.data.get('events')
        if not isinstance(events, list):
            return Response({'error': 'events 는 리스트여야 합니다.'}, status=400)
        default_source = request.data.get('source', 'carrier')
        summary = ingest_tracking_events(order_number, events, default_source=default_source)

        return Response({
            'ingested': summary,
            'timeline': build_timeline(order_number),
        }, status=http_status.HTTP_200_OK)


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

        # 검수 담당자가 확정한 HS코드·통관 카테고리 자동 주입 (body 명시값이 우선)
        hs_source = 'default'
        cls = _confirmed_hs_classification(order)
        if cls:
            if not address.get('hs_code'):
                address['hs_code'] = cls.final_hs_code
                hs_source = 'inspection_confirmed'
            else:
                hs_source = 'request_body'
            if not address.get('prd_category') and cls.final_category:
                address['prd_category'] = cls.final_category
        elif address.get('hs_code'):
            hs_source = 'request_body'

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
            'hs_code':        address.get('hs_code') or '621790',
            'hs_code_source': hs_source,   # inspection_confirmed | request_body | default
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

        # 타임라인(고객 화면)용 구조화 이벤트 적재 → 진행 바(4단계) 재계산.
        # FastBox trace 는 {status_code, location, timestamp} 구조라 description 이 없어
        # 그대로 넣으면 normalize_event 가 드롭한다. status_code 매핑으로
        # description(고객 표시 상태)·stage(권위 4단계)를 주입해 적재한다.
        # tracking.save() 이후 호출해야 current_stage/delivered_at 갱신이 덮어쓰이지 않음.
        timeline_summary = None
        if trace_list:
            from .timeline import ingest_tracking_events
            enriched = []
            for ev in trace_list:
                if not isinstance(ev, dict):
                    continue
                code = ev.get('status_code', '')
                info = client.map_status(code)
                enriched.append({
                    **ev,
                    'description': ev.get('description') or info['customer_status'] or code,
                    'stage':       info['stage'],
                    'raw_code':    code,
                    'source':      'carrier',
                })
            timeline_summary = ingest_tracking_events(order_number, enriched, default_source='carrier')

        return Response({
            'carrier_status':       tracking.carrier_status,
            'customer_status':      tracking.customer_status,
            'tracking_number':      tracking.tracking_number,
            'events_count':         len(trace_list),
            'delay_detected':       tracking.delay_detected,
            'last_api_checked_at':  tracking.last_api_checked_at,
            'timeline':             timeline_summary,
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


# ── 통관 결과 / 통관 거절 → 해당 상품만 부분환불 ─────────────────────────────────

def _no_response_days() -> int:
    """고객 미응답 부분환불 기한(일). SiteConfig 로 조정 가능 (기본 7일)."""
    try:
        from apps.common.models import SiteConfig
        return SiteConfig.get_int('CUSTOMS_REFUND_NO_RESPONSE_DAYS', 7)
    except Exception:
        return 7


def _order_item_amount(order_number):
    """'해당 상품만' 부분환불 예정액 = 해당 Order 실청구액(없으면 예상총액)."""
    try:
        from apps.orders.models import Order
        o = Order.objects.filter(order_number=order_number).first()
        if not o:
            return None
        return o.price_final_charged if o.price_final_charged is not None else o.price_total
    except Exception:
        return None


class CustomsClearanceView(APIView):
    """
    GET  /api/logistics/{order_number}/customs/   통관 결과 조회
    POST /api/logistics/{order_number}/customs/   통관 결과 등록

    POST body: { result, customs_type?, reject_reason?, operator? }
      - result=rejected → 고객에게 '해당 상품만 부분환불' 안내 발송(CS) +
        응답 기한(notified_at + N일) 설정. 미응답 채 기한 경과 시 refund-due 목록에 노출.
    """

    def get(self, request, order_number):
        try:
            cc = CustomsClearance.objects.get(order_number=order_number)
        except CustomsClearance.DoesNotExist:
            return Response({'error': 'not found'}, status=http_status.HTTP_404_NOT_FOUND)
        return Response(CustomsClearanceSerializer(cc).data)

    def post(self, request, order_number):
        from django.utils import timezone
        from datetime import timedelta

        ser = CustomsResultSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        cc, _ = CustomsClearance.objects.get_or_create(order_number=order_number)
        cc.result = d['result']
        if d.get('customs_type'):
            cc.customs_type = d['customs_type']
        if d['result'] == 'rejected':
            cc.reject_reason = d.get('reject_reason', '')

        notified = False
        if d['result'] in ('rejected', 'returned'):
            now = timezone.now()
            cc.partial_refund_amount = _order_item_amount(order_number)
            cc.notified_at = now
            cc.response_deadline = now + timedelta(days=_no_response_days())
            cc.customer_responded_at = None
            cc.save()

            # CS 고객 안내 발송 — 해당 상품만 부분환불 안내
            from apps.orders.models import Order
            order = Order.objects.filter(order_number=order_number).first()
            if order:
                _notify_customer(
                    order.customer_id, 'customs_rejected',
                    {
                        'order_number': order_number,
                        'product_title': order.title,
                        'reject_reason': cc.reject_reason,
                        'partial_refund_amount': cc.partial_refund_amount,
                        'response_deadline': cc.response_deadline.isoformat(),
                    },
                    order_number=order_number,
                )
                notified = True
                _record_transition(
                    order_number, stage='cancelled_or_refunded',
                    actor_id=d.get('operator', ''), field='customs_result',
                    reason=f"통관 거절: {cc.reject_reason}"[:200],
                    extra_new={'result': cc.result, 'customs_type': cc.customs_type},
                )
        else:
            cc.save()

        return Response({
            'customs': CustomsClearanceSerializer(cc).data,
            'notified': notified,
            'no_response_days': _no_response_days(),
        }, status=http_status.HTTP_200_OK)


class CustomsRespondView(APIView):
    """
    POST /api/logistics/{order_number}/customs/respond/
    고객(또는 CS 대행)이 통관 거절 안내에 응답했음을 기록 → 자동 부분환불 대상에서 제외.
    """

    def post(self, request, order_number):
        from django.utils import timezone
        try:
            cc = CustomsClearance.objects.get(order_number=order_number)
        except CustomsClearance.DoesNotExist:
            return Response({'error': 'not found'}, status=http_status.HTTP_404_NOT_FOUND)
        cc.customer_responded_at = timezone.now()
        cc.save(update_fields=['customer_responded_at', 'updated_at'])
        return Response(CustomsClearanceSerializer(cc).data)


class CustomsRefundDueView(APIView):
    """
    GET /api/logistics/customs/refund-due/
    부분환불 처리 대기 목록 — 통관 거절/반송 + 고객 미응답 + 응답기한 경과 + 미환불.
    CS 가 이 목록에서 건별로 부분환불을 실행한다.
    """

    def get(self, request):
        from django.utils import timezone
        qs = CustomsClearance.objects.filter(
            result__in=['rejected', 'returned'],
            customer_responded_at__isnull=True,
            refund_processed_at__isnull=True,
            response_deadline__lte=timezone.now(),
        ).order_by('response_deadline')
        return Response(CustomsClearanceSerializer(qs, many=True).data)


class CustomsRefundView(APIView):
    """
    POST /api/logistics/{order_number}/customs/refund/
    CS 수동 확인 후 '해당 상품만' 부분환불 실행 (FastBox 인계와 무관한 통관 귀책 환불).

    body(선택): { amount?, hq_user? }  amount 생략 시 partial_refund_amount 사용.
    """

    def post(self, request, order_number):
        from django.utils import timezone
        from apps.orders.models import Order, PGTransaction
        from apps.payment.refund import execute_pg_refund
        from apps.payment.providers.base import ProviderError

        try:
            cc = CustomsClearance.objects.get(order_number=order_number)
        except CustomsClearance.DoesNotExist:
            return Response({'error': 'not found'}, status=http_status.HTTP_404_NOT_FOUND)

        if cc.result not in ('rejected', 'returned'):
            return Response({'error': '통관 거절/반송 건만 부분환불할 수 있습니다.',
                             'result': cc.result}, status=http_status.HTTP_409_CONFLICT)
        if cc.refund_processed_at:
            return Response({'error': '이미 부분환불 처리된 건입니다.'}, status=http_status.HTTP_409_CONFLICT)

        amount = request.data.get('amount')
        amount = float(amount) if amount is not None else cc.partial_refund_amount
        if not amount or amount <= 0:
            return Response({'error': '환불 금액을 확인할 수 없습니다. amount 를 지정하세요.'},
                            status=http_status.HTTP_400_BAD_REQUEST)

        # PG 는 그룹 단위 → order → group → PGTransaction
        order = Order.objects.filter(order_number=order_number).first()
        group_number = order.group.group_number if order and order.group_id else order_number
        pg = PGTransaction.objects.filter(order_number=group_number).order_by('-created_at').first()
        if not pg:
            return Response({'error': 'PG 거래를 찾을 수 없습니다.', 'group_number': group_number},
                            status=http_status.HTTP_404_NOT_FOUND)

        try:
            result, actual = execute_pg_refund(pg, amount=int(amount))
        except ProviderError as e:
            return Response({'error': '부분환불 실패', 'provider_code': e.code, 'detail': e.message},
                            status=http_status.HTTP_502_BAD_GATEWAY)

        now = timezone.now()
        cc.refund_processed_at = now
        cc.refund_amount = actual
        cc.save(update_fields=['refund_processed_at', 'refund_amount', 'updated_at'])

        if order:
            order.refund_amount = actual
            order.refund_reason = f"통관 거절 부분환불: {cc.reject_reason}"[:500]
            order.status = 'partial_refund'
            order.save(update_fields=['refund_amount', 'refund_reason', 'status', 'updated_at'])
            _record_transition(
                order_number, stage='cancelled_or_refunded', new_status='partial_refund',
                actor_id=request.data.get('hq_user', ''), field='customs_partial_refund',
                reason=f"통관 거절 해당상품 부분환불 {actual}",
                extra_new={'refund_amount': actual},
            )
            _notify_customer(
                order.customer_id, 'refund_complete',
                {'order_number': order_number, 'refund_amount': actual,
                 'product_title': order.title},
                order_number=order_number,
            )

        return Response({
            'status': 'refunded',
            'refund_amount': actual,
            'pg_status': result.auth_status,
            'customs': CustomsClearanceSerializer(cc).data,
        })


# ── 배송 실패(패스트박스 보관) → 재배송 / 반품 / 폐기 ────────────────────────────

def _storage_days() -> int:
    """배송 실패 보관 기한(일). SiteConfig 로 조정 가능 (기본 14일)."""
    try:
        from apps.common.models import SiteConfig
        return SiteConfig.get_int('DELIVERY_FAILURE_STORAGE_DAYS', 14)
    except Exception:
        return 14


def _return_threshold() -> float:
    """처분 가액 분기 기준(엔). 이 금액 이상이면 반품, 미만이면 폐기. SiteConfig 조정 가능."""
    try:
        from apps.common.models import SiteConfig
        return SiteConfig.get_float('DELIVERY_FAILURE_RETURN_THRESHOLD_JPY', 10000)
    except Exception:
        return 10000.0


def _recommended_disposition(item_value) -> str:
    """가액 기준 분기: 기준액 이상이면 반품, 미만이면 폐기."""
    return 'return' if (item_value or 0) >= _return_threshold() else 'dispose'


class DeliveryFailureView(APIView):
    """
    GET  /api/logistics/{order_number}/failure/   배송 실패 건 조회
    POST /api/logistics/{order_number}/failure/   배송 실패 등록 (보관 + 고객 안내)

    POST body: { failure_reason?, responsible?, cost_burden?, memo?, operator? }
      → status=stored, item_value(해당 Order 가액), notified_at, storage_deadline(+N일) 설정.
        고객에게 현재 상태·실패 사유·재배송/반송비 부담 안내 발송.
    """

    def get(self, request, order_number):
        try:
            df = DeliveryFailure.objects.get(order_number=order_number)
        except DeliveryFailure.DoesNotExist:
            return Response({'error': 'not found'}, status=http_status.HTTP_404_NOT_FOUND)
        return Response(DeliveryFailureSerializer(df).data)

    def post(self, request, order_number):
        from django.utils import timezone
        from datetime import timedelta

        ser = DeliveryFailureCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        now = timezone.now()
        df, _ = DeliveryFailure.objects.get_or_create(order_number=order_number)
        df.failure_reason = d['failure_reason']
        df.responsible    = d['responsible']
        df.cost_burden    = d['cost_burden']
        if d.get('memo'):
            df.memo = d['memo']
        df.status            = 'stored'
        df.item_value        = _order_item_amount(order_number)
        df.notified_at       = now
        df.storage_deadline  = now + timedelta(days=_storage_days())
        df.customer_responded_at = None
        df.resolved_at       = None
        df.save()

        from apps.orders.models import Order
        order = Order.objects.filter(order_number=order_number).first()
        if order:
            _notify_customer(
                order.customer_id, 'delivery_failed',
                {
                    'order_number': order_number,
                    'product_title': order.title,
                    'failure_reason': df.get_failure_reason_display(),
                    'status': '패스트박스 보관 중',
                    'cost_burden': df.cost_burden,   # 고객 부담 안내
                    'storage_deadline': df.storage_deadline.isoformat(),
                },
                order_number=order_number,
            )
            _record_transition(
                order_number, stage='intl_shipping',
                actor_id=d.get('operator', ''), field='delivery_failure',
                reason=f"배송 실패({df.get_failure_reason_display()}) 보관",
                extra_new={'status': 'stored', 'failure_reason': df.failure_reason},
            )

        return Response({
            'failure': DeliveryFailureSerializer(df).data,
            'storage_days': _storage_days(),
            'recommended_disposition': _recommended_disposition(df.item_value),
        }, status=http_status.HTTP_200_OK)


class DeliveryFailureRespondView(APIView):
    """
    POST /api/logistics/{order_number}/failure/respond/
    고객 응답 — 재배송(reship) / 반품(return) 선택. 자동 처분 대상에서 제외.
    body: { action: 'reship' | 'return' }
    """

    def post(self, request, order_number):
        from django.utils import timezone
        try:
            df = DeliveryFailure.objects.get(order_number=order_number)
        except DeliveryFailure.DoesNotExist:
            return Response({'error': 'not found'}, status=http_status.HTTP_404_NOT_FOUND)

        ser = DeliveryFailureRespondSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        action = ser.validated_data['action']

        df.customer_responded_at = timezone.now()
        df.status = 'reship' if action == 'reship' else 'returned'
        df.save(update_fields=['customer_responded_at', 'status', 'updated_at'])
        return Response(DeliveryFailureSerializer(df).data)


class DeliveryFailureActionDueView(APIView):
    """
    GET /api/logistics/failure/action-due/
    처분 처리 대기 목록 — 보관 중 + 고객 미응답 + 보관기한 경과 + 미처리.
    각 건에 가액 기준 권장 처분(recommended_disposition) 포함.
    """

    def get(self, request):
        from django.utils import timezone
        qs = DeliveryFailure.objects.filter(
            status='stored',
            customer_responded_at__isnull=True,
            resolved_at__isnull=True,
            storage_deadline__lte=timezone.now(),
        ).order_by('storage_deadline')
        data = []
        for df in qs:
            row = DeliveryFailureSerializer(df).data
            row['recommended_disposition'] = _recommended_disposition(df.item_value)
            data.append(row)
        return Response(data)


class DeliveryFailureResolveView(APIView):
    """
    POST /api/logistics/{order_number}/failure/resolve/
    CS 수동 처분 실행 (폐기/반품). disposition 생략 시 가액 기준 자동 분기.
    고객 귀책(주소 오류 등) 폐기 시 상품가 환불 없음.
    body(선택): { disposition?: 'dispose'|'return', hq_user? }
    """

    def post(self, request, order_number):
        from django.utils import timezone

        try:
            df = DeliveryFailure.objects.get(order_number=order_number)
        except DeliveryFailure.DoesNotExist:
            return Response({'error': 'not found'}, status=http_status.HTTP_404_NOT_FOUND)

        if df.resolved_at:
            return Response({'error': '이미 처리된 건입니다.', 'status': df.status},
                            status=http_status.HTTP_409_CONFLICT)

        ser = DeliveryFailureResolveSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        disposition = ser.validated_data.get('disposition') or _recommended_disposition(df.item_value)

        df.disposition = disposition
        df.status = 'disposed' if disposition == 'dispose' else 'returned'
        df.resolved_at = timezone.now()
        df.save(update_fields=['disposition', 'status', 'resolved_at', 'updated_at'])

        _record_transition(
            order_number, stage='cancelled_or_refunded',
            actor_id=request.data.get('hq_user', ''), field='delivery_failure_resolve',
            reason=f"배송실패 처분: {df.get_status_display()} (가액 {df.item_value})",
            extra_new={'disposition': disposition, 'status': df.status},
        )

        return Response({
            'status': df.status,
            'disposition': disposition,
            'refund': False,   # 고객 귀책 → 상품가 환불 없음
            'failure': DeliveryFailureSerializer(df).data,
        })
