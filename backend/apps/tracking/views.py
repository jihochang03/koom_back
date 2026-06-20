from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from .models import TrackingCache
from .services import kr_tracker, jp_tracker

KR_CARRIERS = set(kr_tracker.CARRIER_CODES.keys())
JP_CARRIERS = set(jp_tracker.CARRIER_INFO.keys())


def _cache_ttl() -> int:
    return getattr(settings, 'TRACKING_CACHE_MINUTES', 30)


class TrackingView(APIView):
    """
    GET /api/tracking/<carrier_code>/<tracking_number>/

    배송 추적. 캐시 TTL 내에는 DB 캐시 반환.

    carrier_code:
      한국: cj, hanjin, lotte, logen, epost, coupang, gs
      일본: sagawa, yamato, japanpost, seino, fukuyama
    """

    def get(self, request, carrier_code, tracking_number):
        # 캐시 확인
        cutoff = timezone.now() - timedelta(minutes=_cache_ttl())
        cached = TrackingCache.objects.filter(
            carrier_code=carrier_code,
            tracking_number=tracking_number,
            fetched_at__gte=cutoff,
        ).first()
        if cached:
            return Response({**cached.result, 'cached': True})

        # 실시간 조회
        if carrier_code in KR_CARRIERS:
            region = 'kr'
            result = kr_tracker.track(carrier_code, tracking_number)
        elif carrier_code in JP_CARRIERS:
            region = 'jp'
            result = jp_tracker.track(carrier_code, tracking_number)
        else:
            return Response(
                {'error': f'Unknown carrier: {carrier_code}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 캐시 저장 (에러여도 저장해 재시도 방지)
        TrackingCache.objects.update_or_create(
            carrier_code=carrier_code,
            tracking_number=tracking_number,
            defaults={'result': result, 'region': region},
        )

        return Response({**result, 'cached': False})


class TrackingCarriersView(APIView):
    """
    GET /api/tracking/carriers/

    지원 배송사 목록.
    """

    def get(self, request):
        kr = [{'code': c, 'region': 'kr'} for c in KR_CARRIERS]
        jp = jp_tracker.list_carriers()
        for item in jp:
            item['region'] = 'jp'
        return Response({'carriers': kr + jp})
