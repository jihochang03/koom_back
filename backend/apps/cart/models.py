from django.db import models
from apps.products.models import Product


class Cart(models.Model):
    """고객별 장바구니. customer_id는 호출측이 결정 (이메일·UUID 등)."""
    customer_id = models.CharField(max_length=255, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"Cart({self.customer_id})"


class CartItem(models.Model):
    """
    장바구니 항목.
    - product: DB 상품과 연결 (optional — URL만 있는 경우도 허용)
    - options: 선택된 옵션 목록  [{"name": "색상", "value": "블랙"}, ...]
    - price_final: 최종 확정 가격
    """
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(
        Product, on_delete=models.SET_NULL, null=True, blank=True, related_name='cart_items'
    )
    product_url = models.URLField(max_length=2048, blank=True, default='')
    title = models.CharField(max_length=1024)
    brand = models.CharField(max_length=255, blank=True, default='')
    options = models.JSONField(default=list)  # [{name, value}, ...]
    price_final = models.FloatField()
    currency = models.CharField(max_length=10, default='KRW')
    quantity = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title[:40]} x{self.quantity}"
