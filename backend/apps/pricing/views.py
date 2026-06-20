import os
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from datetime import timedelta

from .models import ExchangeRateLog, PricingQuoteLog
from .serializers import ExchangeRateSerializer, PricingQuoteLogSerializer
from .request_serializers import ExchangeRateRequestSerializer, PricingQuoteRequestSerializer
from .utils.exchange_rate import fetch_exchange_rate
from .utils.dk_pricing import compute_dk_pricing

EXCHANGE_CACHE_MINUTES = int(os.getenv('EXCHANGE_CACHE_MINUTES', '60'))


def _get_exchange_rate(base: str, target: str, use_cache: bool) -> tuple[float, bool]:
    """환율 반환 (rate, cached). 캐시 미스 또는 use_cache=False 시 외부 API 호출."""
    if use_cache:
        cutoff = timezone.now() - timedelta(minutes=EXCHANGE_CACHE_MINUTES)
        cached = (
            ExchangeRateLog.objects
            .filter(base_currency=base, target_currency=target, fetched_at__gte=cutoff)
            .order_by('-fetched_at')
            .first()
        )
        if cached:
            return cached.rate, True

    result = fetch_exchange_rate(base=base, target=target)
    ExchangeRateLog.objects.create(
        base_currency=base,
        target_currency=target,
        rate=result['rate'],
        source=result['source'],
    )
    return result['rate'], False


class ExchangeRateView(APIView):
    def get(self, request):
        req = ExchangeRateRequestSerializer(data=request.query_params)
        req.is_valid(raise_exception=True)
        data = req.validated_data
        base = data.get('base', 'JPY')
        target = data.get('target', 'KRW')
        use_cache = data.get('use_cache', True)

        try:
            rate, cached = _get_exchange_rate(base, target, use_cache)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response({
            'base': base,
            'target': target,
            'rate': rate,
            'cached': cached,
            'cache_ttl_minutes': EXCHANGE_CACHE_MINUTES,
        })


class PricingQuoteView(APIView):
    def post(self, request):
        req = PricingQuoteRequestSerializer(data=request.data)
        req.is_valid(raise_exception=True)
        data = req.validated_data

        # 환율 확보 (직접 입력 우선, 없으면 자동 조회)
        krw_per_jpy = data.get('krw_per_jpy_market')
        exchange_cached = None
        if krw_per_jpy is None:
            try:
                krw_per_jpy, exchange_cached = _get_exchange_rate('JPY', 'KRW', True)
            except Exception as e:
                return Response(
                    {'error': f'환율 자동 조회 실패: {e}. krw_per_jpy_market을 직접 입력해주세요.'},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

        # 관세율 조회 (선택)
        tariff_lookup: dict = {}
        if data.get('use_tariff_lookup') and data.get('product_title'):
            try:
                from apps.tariff.utils.tariff_lookup import lookup_tariff_with_claude
                tariff_lookup = lookup_tariff_with_claude(
                    product_title=data['product_title'],
                    api_key=os.getenv('ANTHROPIC_API_KEY'),
                )
            except Exception as e:
                tariff_lookup = {}

        req_data = {
            'shipping_krw': data.get('shipping_krw', 0),
            'intl_shipping_jpy': data.get('intl_shipping_jpy', 0),
            'quantity': data.get('quantity', 1),
            'bundle_consolidation': data.get('bundle_consolidation', False),
            'photo_inspection': data.get('photo_inspection', False),
            'speed_shipping': data.get('speed_shipping', False),
            '_tariff_lookup': tariff_lookup,
        }
        if data.get('tariff_rate') is not None:
            req_data['tariff_rate'] = data['tariff_rate']

        from apps.common.models import SiteConfig
        pricing_cfg = SiteConfig.get_group('pricing')
        result = compute_dk_pricing(
            discounted_price=data.get('discounted_price'),
            original_price=data.get('original_price'),
            currency=data.get('currency', 'KRW'),
            krw_per_jpy_market=krw_per_jpy,
            req_data=req_data,
            cfg=pricing_cfg if pricing_cfg else None,
        )

        if result is None:
            return Response({'error': '가격 정보가 없습니다.'}, status=status.HTTP_400_BAD_REQUEST)

        PricingQuoteLog.objects.create(
            original_price=data.get('original_price'),
            discounted_price=data.get('discounted_price'),
            currency=data.get('currency', 'KRW'),
            krw_per_jpy_market=krw_per_jpy,
            result=result,
        )

        return Response({
            **result,
            '_meta': {
                'krw_per_jpy_market_used': krw_per_jpy,
                'exchange_rate_cached': exchange_cached,
                'tariff_lookup_used': bool(tariff_lookup),
            },
        })


class PricingQuoteLogListView(APIView):
    def get(self, request):
        qs = PricingQuoteLog.objects.all()[:50]
        return Response(PricingQuoteLogSerializer(qs, many=True).data)
