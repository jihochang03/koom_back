from django.db import models


class SocialAccount(models.Model):
    """소셜 로그인 계정 연결 정보."""
    PROVIDER_CHOICES = [('line', 'LINE')]

    customer_id  = models.CharField(max_length=255, db_index=True)
    provider     = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    provider_uid = models.CharField(max_length=255)       # LINE userId
    display_name = models.CharField(max_length=255, blank=True)
    picture_url  = models.URLField(max_length=1024, blank=True)
    access_token = models.TextField(blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['provider', 'provider_uid']]
        indexes = [models.Index(fields=['customer_id', 'provider'])]
