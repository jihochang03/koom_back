import math
from datetime import timedelta

from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Product, ProductDetailStatus, ProductArrivalPhoto, ArrivalStatus
from .serializers import ProductSerializer, ProductBatchCreateSerializer, ProductArrivalPhotoSerializer


class ProductListView(generics.ListAPIView):
    serializer_class = ProductSerializer

    def get_queryset(self):
        qs = Product.objects.all()
        category = self.request.query_params.get('category')
        source_url = self.request.query_params.get('source_url')
        mall = self.request.query_params.get('mall')
        is_recommended = self.request.query_params.get('is_recommended')
        if category is not None:
            qs = qs.filter(category=category)
        if source_url:
            qs = qs.filter(source_url=source_url)
        if mall:
            qs = qs.filter(mall__slug=mall)
        if is_recommended is not None:
            qs = qs.filter(is_recommended=is_recommended.lower() == 'true')
        return qs


class ProductBatchCreateView(APIView):
    """
    POST { source_url, category, items: [{url, product_id, title, ...}] }
    Creates or updates products; returns created list with their DB IDs.
    """
    def post(self, request):
        ser = ProductBatchCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        source_url = data.get('source_url', '')
        category = data.get('category', '')
        mall_slug = data.get('mall_slug', '')
        items = data['items']

        mall = None
        if mall_slug:
            from apps.malls.models import KoreanMall
            mall = KoreanMall.objects.filter(slug=mall_slug).first()

        created = []
        for item in items:
            defaults = {
                'product_id': item.get('product_id', ''),
                'title': item.get('title', ''),
                'price_original': item.get('price_original'),
                'price_discounted': item.get('price_discounted'),
                'currency': item.get('currency', 'KRW'),
                'images': item.get('images', []),
                'brand': item.get('brand', ''),
                'rating': item.get('rating'),
                'review_count': item.get('review_count'),
                'availability': item.get('availability', ''),
                'category': category,
                'detail_status': ProductDetailStatus.PENDING,
            }
            if mall is not None:
                defaults['mall'] = mall
            if source_url:
                defaults['source_url'] = source_url

            product, _ = Product.objects.update_or_create(
                url=item['url'],
                defaults=defaults,
            )
            created.append(product)

        return Response(ProductSerializer(created, many=True).data, status=status.HTTP_201_CREATED)


class ProductDetailUpdateView(APIView):
    """
    POST { detail_data, detail_status }
    Called by scraper-agent to push crawled detail back to DB.
    """
    def post(self, request, pk):
        try:
            product = Product.objects.get(pk=pk)
        except Product.DoesNotExist:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        product.detail_data = request.data.get('detail_data', {})
        product.detail_status = request.data.get('detail_status', ProductDetailStatus.READY)
        product.detail_crawled_at = timezone.now()
        product.save(update_fields=['detail_data', 'detail_status', 'detail_crawled_at', 'updated_at'])

        return Response(ProductSerializer(product).data)


class ProductCategoryUpdateView(APIView):
    """PATCH { category } — update the user-assigned category label."""
    def patch(self, request, pk):
        try:
            product = Product.objects.get(pk=pk)
        except Product.DoesNotExist:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        product.category = request.data.get('category', '')
        product.save(update_fields=['category', 'updated_at'])
        return Response(ProductSerializer(product).data)


class ProductBadgeUpdateView(APIView):
    """PATCH { is_limited } — update badge flags."""
    def patch(self, request, pk):
        try:
            product = Product.objects.get(pk=pk)
        except Product.DoesNotExist:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        updated = []
        if 'is_limited' in request.data:
            product.is_limited = bool(request.data['is_limited'])
            updated.append('is_limited')
        if updated:
            product.save(update_fields=updated + ['updated_at'])
        return Response(ProductSerializer(product).data)


class ProductRefreshView(APIView):
    """POST — reset detail_status to PENDING so the prefetch queue re-crawls it."""
    def post(self, request, pk):
        try:
            product = Product.objects.get(pk=pk)
        except Product.DoesNotExist:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        product.detail_status = ProductDetailStatus.PENDING
        product.save(update_fields=['detail_status', 'updated_at'])
        return Response(ProductSerializer(product).data)


class ProductInboundUpdateView(APIView):
    """
    PATCH /api/products/{pk}/inbound/
    오더번호·송장번호·택배사·도착상태·검수 여부·메모 업데이트.
    arrival_status=inspected 지정 시 inspected_at 자동 기록.
    """

    INBOUND_FIELDS = [
        'inbound_order_number',
        'inbound_tracking_number',
        'inbound_courier',
        'arrival_status',
        'inspection_required',
        'inbound_note',
    ]

    def patch(self, request, pk):
        try:
            product = Product.objects.get(pk=pk)
        except Product.DoesNotExist:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        updated = []
        for field in self.INBOUND_FIELDS:
            if field in request.data:
                setattr(product, field, request.data[field])
                updated.append(field)

        if not updated:
            return Response({'error': '변경할 필드가 없습니다.'}, status=status.HTTP_400_BAD_REQUEST)

        # 검수완료로 바꿀 때 inspected_at 자동 기록
        if 'arrival_status' in updated and product.arrival_status == ArrivalStatus.INSPECTED:
            if not product.inspected_at:
                product.inspected_at = timezone.now()
                updated.append('inspected_at')

        # 도착으로 바꿀 때 arrived_at 자동 기록
        if 'arrival_status' in updated and product.arrival_status == ArrivalStatus.ARRIVED:
            if not product.arrived_at:
                product.arrived_at = timezone.now()
                updated.append('arrived_at')

        product.save(update_fields=updated + ['updated_at'])
        return Response(ProductSerializer(product, context={'request': request}).data)


class ArrivalPhotoListCreateView(APIView):
    """
    GET  /api/products/{pk}/arrival-photos/  — 사진 목록
    POST /api/products/{pk}/arrival-photos/  — 사진 업로드 (multipart)

    사진 업로드 시 상품의 arrival_status가 자동으로 'arrived'로 갱신된다.
    """

    def get(self, request, pk):
        product = self._get_product(pk)
        if product is None:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        photos = product.arrival_photos.all()
        return Response(ProductArrivalPhotoSerializer(photos, many=True, context={'request': request}).data)

    def post(self, request, pk):
        product = self._get_product(pk)
        if product is None:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        if 'photo' not in request.FILES:
            return Response({'error': '사진 파일(photo)이 필요합니다.'}, status=status.HTTP_400_BAD_REQUEST)

        photo = ProductArrivalPhoto(
            product=product,
            note=request.data.get('note', ''),
        )
        photo.photo = request.FILES['photo']
        photo.save()  # save() 내부에서 arrival_status 자동 갱신

        return Response(
            ProductArrivalPhotoSerializer(photo, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )

    @staticmethod
    def _get_product(pk):
        try:
            return Product.objects.get(pk=pk)
        except Product.DoesNotExist:
            return None


class ArrivalPhotoDeleteView(APIView):
    """DELETE /api/products/arrival-photos/{photo_id}/"""

    def delete(self, request, photo_id):
        try:
            photo = ProductArrivalPhoto.objects.get(pk=photo_id)
        except ProductArrivalPhoto.DoesNotExist:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        photo.photo.delete(save=False)  # 실제 파일 삭제
        photo.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProductCategoryListView(APIView):
    """GET — distinct category labels currently in use."""
    def get(self, request):
        cats = (
            Product.objects
            .exclude(category='')
            .values_list('category', flat=True)
            .distinct()
            .order_by('category')
        )
        return Response({'categories': list(cats)})


class ProductDetailPageView(APIView):
    """
    GET — 상품 상세 페이지에 필요한 데이터 통합 반환.
    상품 정보 + JPY 가격 분해 + 배송 소요일 + 결제 수단 + 주문 주의사항
    """
    DELIVERY_STAGES = [
        ('receive',   '상품 입고',   'DELIVERY_DAYS_RECEIVE'),
        ('inspect',   '상품 검수',   'DELIVERY_DAYS_INSPECT'),
        ('kr_ship',   '한국발송',    'DELIVERY_DAYS_KR_SHIP'),
        ('intl_ship', '국제 배송',   'DELIVERY_DAYS_INTL_SHIP'),
        ('jp_ship',   '일본 배송',   'DELIVERY_DAYS_JP_SHIP'),
    ]

    def get(self, request, pk):
        try:
            product = Product.objects.get(pk=pk)
        except Product.DoesNotExist:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        from apps.common.models import SiteConfig, PaymentMethod, OrderNotice
        from apps.pricing.views import _get_exchange_rate
        from apps.pricing.utils.dk_pricing import compute_dk_pricing

        # 환율 (JPY → KRW)
        try:
            krw_per_jpy, _ = _get_exchange_rate('JPY', 'KRW', use_cache=True)
        except Exception:
            krw_per_jpy = 10.0

        # 기본 국제 배송비 (SiteConfig 'DEFAULT_INTL_SHIPPING_JPY', 없으면 800엔)
        default_intl_jpy = SiteConfig.get_int('DEFAULT_INTL_SHIPPING_JPY', 800)

        pricing_cfg = SiteConfig.get_group('pricing')
        dk = compute_dk_pricing(
            discounted_price=product.price_discounted,
            original_price=product.price_original,
            currency=product.currency or 'KRW',
            krw_per_jpy_market=krw_per_jpy,
            req_data={'intl_shipping_jpy': default_intl_jpy},
            cfg=pricing_cfg,
        )

        # JPY 가격 분해
        pricing_jpy = self._extract_pricing_jpy(dk, default_intl_jpy)

        # 배송 소요일 계산
        delivery = self._build_delivery(SiteConfig)

        # 결제 수단
        payment_methods = list(
            PaymentMethod.objects.filter(is_active=True)
            .values('id', 'name', 'code', 'icon_url', 'display_order')
        )

        # 주문 주의사항
        order_notices = list(
            OrderNotice.objects.filter(is_active=True)
            .values('id', 'content', 'display_order')
        )

        return Response({
            'product': ProductSerializer(product).data,
            'pricing_jpy': pricing_jpy,
            'exchange_rate': {
                'krw_per_jpy': round(krw_per_jpy, 4),
                'jpy_per_krw': round(1 / krw_per_jpy, 6) if krw_per_jpy else None,
            },
            'delivery': delivery,
            'payment_methods': payment_methods,
            'order_notices': order_notices,
        })

    def _extract_pricing_jpy(self, dk, default_intl_jpy):
        if dk is None:
            return None

        product_jpy = dk.get('product_jpy_nominal_market', 0)

        # lines에서 intl_shipping, customs 추출
        intl_jpy = 0.0
        customs_jpy = 0.0
        for line in dk.get('lines', []):
            if line['code'] == 'intl_shipping':
                intl_jpy = line.get('jpy', 0)
            elif line['code'] == 'customs_duty_vat':
                customs_jpy = line.get('jpy', 0)

        if intl_jpy == 0:
            intl_jpy = float(default_intl_jpy)

        total_jpy = dk.get('total_jpy_estimated', 0)

        return {
            'product_price_jpy': math.ceil(product_jpy),
            'intl_shipping_jpy': math.ceil(intl_jpy),
            'customs_estimate_jpy': math.ceil(customs_jpy),
            'total_jpy': math.ceil(total_jpy),
            'duty_free': dk.get('customs', {}).get('duty_free', True),
            'disclaimer': dk.get('disclaimer', ''),
        }

    def _build_delivery(self, SiteConfig):
        days_cfg = SiteConfig.get_delivery_days()
        today = timezone.localdate()
        total_days = 0
        stages = []
        for key, label, cfg_key in self.DELIVERY_STAGES:
            days = days_cfg.get(cfg_key, 1)
            total_days += days
            stages.append({'key': key, 'label': label, 'days': days})

        arrival_date = today + timedelta(days=total_days)
        return {
            'stages': stages,
            'total_days': total_days,
            'estimated_arrival_date': arrival_date.isoformat(),
            'estimated_arrival_label': f'오늘로부터 약 {total_days}일',
        }
