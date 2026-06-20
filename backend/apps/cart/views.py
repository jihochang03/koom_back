import math
from urllib.parse import urlparse

from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.products.models import Product
from .models import Cart, CartItem
from .serializers import (
    CartSerializer,
    CartItemSerializer,
    CartItemWriteSerializer,
    CartItemUpdateSerializer,
)


def _get_exchange_rate_safe() -> float:
    try:
        from apps.pricing.views import _get_exchange_rate
        rate, _ = _get_exchange_rate('JPY', 'KRW', use_cache=True)
        return rate if rate > 0 else 10.0
    except Exception:
        return 10.0


def _to_jpy(price: float, currency: str, krw_per_jpy: float) -> float:
    if not price:
        return 0.0
    if currency.upper() == 'JPY':
        return price
    return price / krw_per_jpy if krw_per_jpy else price / 10.0


def _site_name(item: CartItem) -> str:
    if item.product and item.product.mall:
        return item.product.mall.name
    url = item.product_url or (item.product.url if item.product else '')
    if url:
        try:
            host = urlparse(url).hostname or ''
            return host.replace('www.', '').split('.')[0]
        except Exception:
            pass
    return ''


def _build_delivery_estimate():
    from apps.common.models import SiteConfig
    from datetime import timedelta
    STAGES = [
        ('receive',   '상품 입고',   'DELIVERY_DAYS_RECEIVE',   3),
        ('inspect',   '상품 검수',   'DELIVERY_DAYS_INSPECT',   1),
        ('kr_ship',   '한국발송',    'DELIVERY_DAYS_KR_SHIP',   1),
        ('intl_ship', '국제 배송',   'DELIVERY_DAYS_INTL_SHIP', 5),
        ('jp_ship',   '일본 배송',   'DELIVERY_DAYS_JP_SHIP',   3),
    ]
    total_days = 0
    stages = []
    for key, label, cfg_key, default in STAGES:
        days = SiteConfig.get_int(cfg_key, default)
        total_days += days
        stages.append({'key': key, 'label': label, 'days': days})
    arrival = timezone.localdate() + timedelta(days=total_days)
    return {
        'stages': stages,
        'total_days': total_days,
        'estimated_arrival_date': arrival.isoformat(),
        'estimated_arrival_label': f'오늘로부터 약 {total_days}일',
    }


def _get_or_create_cart(customer_id: str) -> Cart:
    cart, _ = Cart.objects.get_or_create(customer_id=customer_id)
    return cart


class CartView(APIView):
    """GET /api/cart/{customer_id}/ — 고객 장바구니 조회 (없으면 빈 카트 생성)."""

    def get(self, request, customer_id):
        cart = _get_or_create_cart(customer_id)
        return Response(CartSerializer(cart).data)

    def delete(self, request, customer_id):
        """장바구니 전체 비우기 (카트 자체는 유지)."""
        cart = _get_or_create_cart(customer_id)
        cart.items.all().delete()
        return Response(CartSerializer(cart).data)


class CartItemListView(APIView):
    """POST /api/cart/{customer_id}/items/ — 항목 추가."""

    def post(self, request, customer_id):
        ser = CartItemWriteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        cart = _get_or_create_cart(customer_id)

        product = None
        product_url = data.get('product_url', '')
        if data.get('product_id'):
            try:
                product = Product.objects.get(pk=data['product_id'])
                if not product_url:
                    product_url = product.url
            except Product.DoesNotExist:
                pass

        brand = data.get('brand', '')
        if not brand and product:
            brand = product.brand or ''

        item = CartItem.objects.create(
            cart=cart,
            product=product,
            product_url=product_url,
            title=data['title'],
            brand=brand,
            options=data.get('options', []),
            price_final=data['price_final'],
            currency=data.get('currency', 'KRW'),
            quantity=data.get('quantity', 1),
        )
        return Response(CartItemSerializer(item).data, status=status.HTTP_201_CREATED)


class CartItemDetailView(APIView):
    """
    PATCH /api/cart/{customer_id}/items/{item_id}/ — 수량·옵션·가격 수정
    DELETE /api/cart/{customer_id}/items/{item_id}/ — 항목 삭제
    """

    def _get_item(self, customer_id: str, item_id: int):
        try:
            return CartItem.objects.select_related('cart').get(
                pk=item_id, cart__customer_id=customer_id
            )
        except CartItem.DoesNotExist:
            return None

    def patch(self, request, customer_id, item_id):
        item = self._get_item(customer_id, item_id)
        if not item:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        ser = CartItemUpdateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        updated = []
        if 'options' in data:
            item.options = data['options']
            updated.append('options')
        if 'price_final' in data:
            item.price_final = data['price_final']
            updated.append('price_final')
        if 'quantity' in data:
            item.quantity = data['quantity']
            updated.append('quantity')
        if updated:
            item.save(update_fields=updated + ['updated_at'])

        return Response(CartItemSerializer(item).data)

    def delete(self, request, customer_id, item_id):
        item = self._get_item(customer_id, item_id)
        if not item:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CartPageView(APIView):
    """GET — 장바구니 화면 데이터. 상품 목록(브랜드·포인트·JPY 가격) + 요약."""

    def get(self, request, customer_id):
        from apps.common.models import SiteConfig
        cart = _get_or_create_cart(customer_id)
        krw_per_jpy = _get_exchange_rate_safe()
        points_rate = SiteConfig.get_float('DK_POINTS_RATE', 0.01)

        items = []
        total_jpy = 0.0
        total_points_earn = 0

        for item in cart.items.select_related('product', 'product__mall').all():
            price_jpy = _to_jpy(item.price_final, item.currency, krw_per_jpy)
            item_total_jpy = price_jpy * item.quantity
            points_earn = int(item_total_jpy * points_rate)

            items.append({
                'id': item.id,
                'title': item.title,
                'brand': item.brand or (item.product.brand if item.product else ''),
                'site_name': _site_name(item),
                'price_jpy': math.ceil(price_jpy),
                'quantity': item.quantity,
                'total_jpy': math.ceil(item_total_jpy),
                'points_earn': points_earn,
                'options': item.options,
                'product_url': item.product_url or (item.product.url if item.product else ''),
            })
            total_jpy += item_total_jpy
            total_points_earn += points_earn

        return Response({
            'items': items,
            'summary': {
                'total_jpy': math.ceil(total_jpy),
                'total_points_earn': total_points_earn,
            },
            'delivery': _build_delivery_estimate(),
        })


class CartCheckoutView(APIView):
    """GET — 결제 화면 통합 데이터."""

    def get(self, request, customer_id):
        from apps.common.models import SiteConfig, PaymentMethod
        from apps.mypage.models import UserAddress, UserCoupon, PointLog
        from apps.mypage.serializers import UserAddressSerializer, UserCouponSerializer
        from apps.content.models import Policy

        cart = _get_or_create_cart(customer_id)
        krw_per_jpy = _get_exchange_rate_safe()

        points_rate = SiteConfig.get_float('DK_POINTS_RATE', 0.01)
        points_threshold_jpy = SiteConfig.get_int('POINTS_THRESHOLD_JPY', 1000)
        points_to_koom = SiteConfig.get_float('POINTS_TO_KOOM_RATE', 1.0)
        default_intl_jpy = SiteConfig.get_int('DEFAULT_INTL_SHIPPING_JPY', 800)

        # 상품 목록
        items = []
        total_product_jpy = 0.0
        total_points_earn = 0

        for item in cart.items.select_related('product', 'product__mall').all():
            price_jpy = _to_jpy(item.price_final, item.currency, krw_per_jpy)
            item_total_jpy = price_jpy * item.quantity
            points_earn = int(item_total_jpy * points_rate)

            items.append({
                'id': item.id,
                'title': item.title,
                'brand': item.brand or (item.product.brand if item.product else ''),
                'site_name': _site_name(item),
                'price_jpy': math.ceil(price_jpy),
                'quantity': item.quantity,
                'total_jpy': math.ceil(item_total_jpy),
                'points_earn': points_earn,
            })
            total_product_jpy += item_total_jpy
            total_points_earn += points_earn

        # 배송지
        addresses = UserAddress.objects.filter(customer_id=customer_id)

        # 포인트 잔액
        point_log = PointLog.objects.filter(customer_id=customer_id).first()
        points_balance = point_log.balance_after if point_log else 0

        # 사용 가능 쿠폰
        now = timezone.now()
        available_coupons = UserCoupon.objects.filter(
            customer_id=customer_id,
            used_at=None,
            coupon__is_active=True,
            coupon__valid_from__lte=now,
            coupon__valid_until__gte=now,
        ).select_related('coupon')

        # 주문 요약 (쿠폰·포인트 미적용 초기값)
        cif = total_product_jpy + default_intl_jpy
        customs_jpy = 0
        if cif * 0.6 > 10000:
            # 관세(5%) + 소비세(10%) 합산 추정
            duty = cif * 0.05
            customs_jpy = math.ceil(duty + (cif + duty) * 0.10)
        total_jpy = math.ceil(total_product_jpy + default_intl_jpy + customs_jpy)

        # 취소·환불 정책
        refund_policy = Policy.objects.filter(policy_type='refund', is_current=True).first()
        cancel_policy = Policy.objects.filter(policy_type='shipping', is_current=True).first()

        return Response({
            'items': items,
            'addresses': UserAddressSerializer(addresses, many=True).data,
            'points': {
                'balance': points_balance,
                'earn_this_order': total_points_earn,
                'rules': {
                    'rate_pct': round(points_rate * 100, 1),
                    'threshold_jpy': points_threshold_jpy,
                    'points_to_koom_rate': points_to_koom,
                    'description': f'{points_threshold_jpy}엔마다 {round(points_rate * 100, 1)}% 적립 | 1포인트 = {points_to_koom} koom',
                },
            },
            'coupons': UserCouponSerializer(available_coupons, many=True).data,
            'order_summary': {
                'product_price_jpy': math.ceil(total_product_jpy),
                'intl_shipping_jpy': default_intl_jpy,
                'customs_estimate_jpy': customs_jpy,
                'subtotal_jpy': total_jpy,
                'coupon_discount_jpy': 0,
                'points_applied_jpy': 0,
                'total_jpy': total_jpy,
                'points_earn': total_points_earn,
            },
            'policies': {
                'refund': {'title': refund_policy.title, 'content': refund_policy.content} if refund_policy else None,
                'cancel': {'title': cancel_policy.title, 'content': cancel_policy.content} if cancel_policy else None,
            },
            'payment_methods': list(
                PaymentMethod.objects.filter(is_active=True)
                .values('id', 'name', 'code', 'icon_url', 'display_order')
            ),
        })
