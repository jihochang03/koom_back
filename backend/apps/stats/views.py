from django.db.models import Sum, Avg, Count, Q
from rest_framework.views import APIView
from rest_framework.response import Response


class DKBurdenStatsView(APIView):
    """Section 15.1 — 자동 DK 부담 손실액"""

    def get(self, request):
        from apps.orders.models import Order

        agg = Order.objects.aggregate(
            total_burden=Sum('price_dk_burden'),
            tariff_advance=Sum('company_burden_tariff'),
            error_small=Sum('company_burden_error_small'),
            shipping_error=Sum('company_burden_shipping_error'),
            other=Sum('company_burden_other'),
            total_revenue=Sum('price_total'),
            order_count=Count('id'),
        )

        burden = agg['total_burden'] or 0
        revenue = agg['total_revenue'] or 1
        order_count = agg['order_count'] or 1

        return Response({
            'total_burden': burden,
            'tariff_advance': agg['tariff_advance'] or 0,
            'error_small_burden': agg['error_small'] or 0,
            'shipping_error_burden': agg['shipping_error'] or 0,
            'other_burden': agg['other'] or 0,
            'avg_burden_per_order': round(burden / order_count, 2),
            'burden_rate_pct': round(burden / revenue * 100, 2) if revenue else 0,
            'order_count': order_count,
        })


class ErrorRateStatsView(APIView):
    """Section 15.2 — 견적 오차율 및 오차 금액"""

    def get(self, request):
        from apps.orders.models import ErrorInfo

        agg = ErrorInfo.objects.aggregate(
            avg_rate=Avg('error_rate'),
            total_amount=Sum('error_amount'),
            count=Count('id'),
        )

        by_handling = dict(
            ErrorInfo.objects
            .values_list('handling_method')
            .annotate(cnt=Count('id'))
            .values_list('handling_method', 'cnt')
        )

        # Cause breakdown: flatten JSONField causes at Python level
        causes_raw = list(ErrorInfo.objects.exclude(error_causes=None).values_list('error_causes', flat=True))
        cause_counts = {}
        for causes in causes_raw:
            if isinstance(causes, list):
                for c in causes:
                    cause_counts[c] = cause_counts.get(c, 0) + 1

        return Response({
            'avg_error_rate_pct': round((agg['avg_rate'] or 0) * 100, 2),
            'total_error_amount': agg['total_amount'] or 0,
            'error_order_count': agg['count'],
            'by_handling_method': by_handling,
            'by_cause': cause_counts,
        })


class CSConversionStatsView(APIView):
    """Section 15.3 — CS 수동 검토 전환율"""

    def get(self, request):
        from apps.orders.models import Order, ErrorInfo
        from apps.cs.models import Inquiry, CancelRequest, RefundRequest

        total_orders = Order.objects.count()
        cs_order_numbers = set(
            Inquiry.objects.exclude(order_number='').values_list('order_number', flat=True)
        ) | set(
            CancelRequest.objects.values_list('order_number', flat=True)
        ) | set(
            RefundRequest.objects.values_list('order_number', flat=True)
        )

        cs_review_count = ErrorInfo.objects.filter(handling_method='cs_review').count()

        from apps.cs.models import Inquiry
        open_inquiries = Inquiry.objects.filter(status__in=['open', 'in_progress'])
        resolved_inquiries = Inquiry.objects.filter(status__in=['resolved', 'closed'])

        return Response({
            'total_orders': total_orders,
            'cs_touched_orders': len(cs_order_numbers),
            'cs_conversion_rate_pct': round(len(cs_order_numbers) / total_orders * 100, 2) if total_orders else 0,
            'cs_review_from_error': cs_review_count,
            'open_inquiries': open_inquiries.count(),
            'resolved_inquiries': resolved_inquiries.count(),
        })


class SiteParsingStatsView(APIView):
    """Section 17.2 — 사이트별 파싱·오차·취소 통계"""

    def get(self, request):
        from apps.orders.models import Order, ErrorInfo
        from django.db.models import Count

        site_totals = {
            row['site_domain']: row['total']
            for row in Order.objects.values('site_domain').annotate(total=Count('id'))
        }
        site_cancelled = {
            row['site_domain']: row['cnt']
            for row in Order.objects.filter(
                status__in=['cancelled', 'refunded', 'partial_refund']
            ).values('site_domain').annotate(cnt=Count('id'))
        }
        site_shipping_extra = {
            row['site_domain']: row['cnt']
            for row in Order.objects.filter(
                company_burden_shipping_error__gt=0
            ).values('site_domain').annotate(cnt=Count('id'))
        }

        order_to_site = dict(Order.objects.values_list('order_number', 'site_domain'))
        site_error_rates = {}
        for ei in ErrorInfo.objects.exclude(error_rate=None).values('order_number', 'error_rate'):
            domain = order_to_site.get(ei['order_number'])
            if domain:
                site_error_rates.setdefault(domain, []).append(ei['error_rate'])

        result = []
        for domain, total in site_totals.items():
            if not total:
                continue
            errors = site_error_rates.get(domain, [])
            result.append({
                'site_domain': domain,
                'total_orders': total,
                'cancel_refund_rate_pct': round(site_cancelled.get(domain, 0) / total * 100, 2),
                'shipping_extra_rate_pct': round(site_shipping_extra.get(domain, 0) / total * 100, 2),
                'avg_error_rate_pct': round(sum(errors) / len(errors) * 100, 2) if errors else 0,
                'error_order_count': len(errors),
            })

        return Response(sorted(result, key=lambda x: x['total_orders'], reverse=True))


class MonitoringOverviewView(APIView):
    """실시간 운영 모니터링 (FR-MON-01).

    - scope=all  (기본, 본사 H-11): 전체 주문·배송·지연·오차 집계
    - scope=mine (CS C-05): cs_user 가 대리구매한 주문만 집계 (NFR-SEC-02 격리)
        → ?scope=mine&cs_user=<id> 필수
    """

    def get(self, request):
        from apps.orders.models import Order, PurchaseRecord
        from apps.logistics.models import ShippingTracking, LogisticsInfo
        from apps.orders.models import ErrorInfo

        scope   = request.query_params.get('scope', 'all')
        cs_user = request.query_params.get('cs_user')

        scoped = None  # None = 전체, set = 한정 order_number 집합
        if scope == 'mine':
            if not cs_user:
                return Response({'error': 'scope=mine 에는 cs_user 가 필요합니다.'}, status=400)
            scoped = set(PurchaseRecord.objects.filter(cs_user=cs_user).values_list('order_number', flat=True))

        def filt(qs):
            return qs.filter(order_number__in=scoped) if scoped is not None else qs

        orders = Order.objects.all()
        if scoped is not None:
            orders = orders.filter(order_number__in=scoped)

        # 1) 주문 상태별 집계
        status_counts = dict(
            orders.values_list('status').annotate(cnt=Count('id')).values_list('status', 'cnt')
        )

        # 2) 대리구매 대기 (결제완료 & 미처리)
        done_orders = set(PurchaseRecord.objects.values_list('order_number', flat=True))
        pending_qs = Order.objects.filter(status='paid').exclude(order_number__in=done_orders)
        if scoped is not None:
            pending_qs = pending_qs.filter(order_number__in=scoped)
        purchase_pending = pending_qs.count()

        # 3) 배송 추적 / 지연 (FR-LOG-03, 04)
        tracking = filt(ShippingTracking.objects.all())
        delay_counts = dict(
            tracking.values_list('delay_type').annotate(cnt=Count('id')).values_list('delay_type', 'cnt')
        )
        shipping = {
            'tracked_total':  tracking.count(),
            'delay_24h':      delay_counts.get('24h', 0),
            'delay_48h':      delay_counts.get('48h', 0),
            'delay_extended': delay_counts.get('extended', 0),
            'delay_total':    tracking.filter(delay_detected=True).count(),
        }

        # 4) 검수 이슈 (FR-LOG-05)
        inspection_issues = filt(LogisticsInfo.objects.filter(inspection_result='issue')).count()

        # 5) 가격 오차 / CS 전환 (FR-ORD-04)
        errors = filt(ErrorInfo.objects.all())
        error_summary = {
            'total':           errors.count(),
            'cs_review':       errors.filter(handling_method='cs_review').count(),
            'auto_company':    errors.filter(auto_processed=True).count(),
        }

        return Response({
            'scope':                scope,
            'cs_user':              cs_user or None,
            'order_status_counts':  status_counts,
            'purchase_tasks_pending': purchase_pending,
            'shipping':             shipping,
            'inspection_issues':    inspection_issues,
            'price_error':          error_summary,
        })
