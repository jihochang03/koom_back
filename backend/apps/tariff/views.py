import os
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import timedelta

from apps.products.models import Product
from .models import TariffLookupLog, ProductHsClassification
from .serializers import (
    TariffLookupLogSerializer,
    TariffClassifyResultSerializer,
    ProductHsClassificationSerializer,
)
from .request_serializers import (
    TariffLookupRequestSerializer,
    TariffClassifyRequestSerializer,
    HsClassificationConfirmSerializer,
)
from .utils.tariff_lookup import lookup_tariff_with_claude, classify_tariff

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


class TariffClassifyView(APIView):
    """
    POST /api/tariff/classify/
    상품명 → AI 추천 HS코드/분류경로 + 선정 사유 + 대안 후보.
    검수 담당자가 fastbox 통관 분류를 확인·선택할 때 쓰는 stateless 엔드포인트.
    """
    def post(self, request):
        req = TariffClassifyRequestSerializer(data=request.data)
        req.is_valid(raise_exception=True)
        result = classify_tariff(
            product_title=req.validated_data['product_title'],
            api_key=os.getenv('ANTHROPIC_API_KEY'),
            top_n=req.validated_data.get('top_n', 5),
        )
        return Response(TariffClassifyResultSerializer(result).data)


def _classification_payload(record, classify_result=None):
    """검수 화면 응답: 저장된 분류 레코드 + (있으면) 최신 AI 분류 결과."""
    data = ProductHsClassificationSerializer(record).data
    if classify_result is not None:
        data['classify'] = TariffClassifyResultSerializer(classify_result).data
    return data


class ProductHsClassificationView(APIView):
    """
    GET  /api/tariff/products/{pk}/classification/
        상품의 HS 분류 추천을 조회. 레코드가 없으면 상품명으로 AI 분류를 생성·저장.
        ?refresh=1 이면 미확정(pending) 레코드의 AI 추천을 다시 계산.

    POST /api/tariff/products/{pk}/classification/  (= confirm)
        검수 담당자가 HS코드·통관 카테고리를 확정/수정하고 피드백을 남긴다.
    """

    def _ensure_record(self, product, *, refresh=False):
        record, created = ProductHsClassification.objects.get_or_create(product=product)
        classify_result = None
        # 신규 생성이거나, 아직 미확정 상태에서 refresh 요청 시 AI 분류 (재)계산
        if created or (refresh and record.status != ProductHsClassification.Status.CONFIRMED):
            classify_result = classify_tariff(
                product_title=product.title,
                api_key=os.getenv('ANTHROPIC_API_KEY'),
            )
            record.ai_suggested = classify_result.get('selected') or {}
            record.ai_alternatives = classify_result.get('alternatives') or []
            record.ai_search_expansion = classify_result.get('search_expansion') or ''
            record.save(update_fields=[
                'ai_suggested', 'ai_alternatives', 'ai_search_expansion', 'updated_at',
            ])
        return record, classify_result

    def get(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        refresh = request.query_params.get('refresh') in ('1', 'true', 'yes')
        record, classify_result = self._ensure_record(product, refresh=refresh)
        return Response(_classification_payload(record, classify_result))

    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        req = HsClassificationConfirmSerializer(data=request.data)
        req.is_valid(raise_exception=True)
        d = req.validated_data

        record, _ = ProductHsClassification.objects.get_or_create(product=product)
        record.final_hs_code = d.get('final_hs_code', '')
        record.final_category = d.get('final_category', '')
        record.final_full_path = d.get('final_full_path', '')
        record.decision_source = d.get('decision_source', 'manual')
        record.inspector = d.get('inspector', '')
        record.inspector_note = d.get('inspector_note', '')
        record.status = ProductHsClassification.Status.CONFIRMED
        record.confirmed_at = timezone.now()
        record.save()

        return Response(_classification_payload(record), status=status.HTTP_200_OK)
