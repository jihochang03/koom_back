import os
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from datetime import timedelta

from .models import TariffLookupLog
from .serializers import TariffLookupLogSerializer
from .request_serializers import TariffLookupRequestSerializer
from .utils.tariff_lookup import lookup_tariff_with_claude

_DEFAULT_CACHE_TTL_HOURS = int(os.getenv('TARIFF_CACHE_TTL_HOURS', '24'))


def _get_cache_ttl():
    try:
        from apps.common.models import SiteConfig
        return SiteConfig.get_int('TARIFF_CACHE_TTL_HOURS', _DEFAULT_CACHE_TTL_HOURS)
    except Exception:
        return _DEFAULT_CACHE_TTL_HOURS


class TariffLookupView(APIView):
    def post(self, request):
        req = TariffLookupRequestSerializer(data=request.data)
        req.is_valid(raise_exception=True)
        title = req.validated_data['product_title']
        use_cache = req.validated_data.get('use_cache', True)

        if use_cache:
            cutoff = timezone.now() - timedelta(hours=_get_cache_ttl())
            cached = (
                TariffLookupLog.objects
                .filter(product_title=title, created_at__gte=cutoff)
                .order_by('-created_at')
                .first()
            )
            if cached:
                return Response({**cached.result, 'cached': True})

        result = lookup_tariff_with_claude(
            product_title=title,
            api_key=os.getenv('ANTHROPIC_API_KEY'),
        )

        TariffLookupLog.objects.create(
            product_title=title,
            result=result,
            rate=result.get('rate'),
            duty_type=result.get('duty_type') or '',
            matched_item=result.get('matched_item') or '',
        )

        return Response({**result, 'cached': False}, status=status.HTTP_200_OK)


class TariffLookupLogListView(APIView):
    def get(self, request):
        qs = TariffLookupLog.objects.all()[:50]
        return Response(TariffLookupLogSerializer(qs, many=True).data)
