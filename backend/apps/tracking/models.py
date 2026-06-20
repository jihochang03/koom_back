from django.db import models


CARRIER_REGION_CHOICES = [
    ('kr', '한국'),
    ('jp', '일본'),
    ('intl', '국제'),
]


class TrackingCache(models.Model):
    """배송 추적 결과 캐시 (TTL: TRACKING_CACHE_MINUTES)."""
    carrier_code  = models.CharField(max_length=30, db_index=True)
    tracking_number = models.CharField(max_length=100, db_index=True)
    region        = models.CharField(max_length=10, choices=CARRIER_REGION_CHOICES, default='kr')
    result        = models.JSONField()
    fetched_at    = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['carrier_code', 'tracking_number']]
        ordering = ['-fetched_at']
