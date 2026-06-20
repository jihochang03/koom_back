from django.db import models


class TariffLookupLog(models.Model):
    """관세율 조회 이력 및 캐시 (Claude API 중복 호출 방지)"""
    product_title = models.CharField(max_length=500)
    # 조회 결과 전체 (tariff_lookup.py 반환 dict)
    result = models.JSONField(default=dict)
    # 최종 적용 세율 (빠른 필터링용)
    rate = models.FloatField(null=True, blank=True)
    duty_type = models.CharField(max_length=20, blank=True, default='')
    matched_item = models.CharField(max_length=500, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.product_title[:50]} → rate={self.rate}"
