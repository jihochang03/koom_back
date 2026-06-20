from django.db import models


class ExchangeRateLog(models.Model):
    """환율 조회 이력 (단기 캐시용)"""
    base_currency = models.CharField(max_length=5, default='JPY')
    target_currency = models.CharField(max_length=5, default='KRW')
    rate = models.FloatField()
    source = models.CharField(max_length=100, blank=True, default='')
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fetched_at']

    def __str__(self):
        return f"1 {self.base_currency} = {self.rate} {self.target_currency}"


class PricingQuoteLog(models.Model):
    """DK 견적 계산 이력"""
    original_price = models.FloatField(null=True, blank=True)
    discounted_price = models.FloatField(null=True, blank=True)
    currency = models.CharField(max_length=5, default='KRW')
    krw_per_jpy_market = models.FloatField()
    result = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
