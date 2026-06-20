from django.db import models


class SupportedSite(models.Model):
    name = models.CharField(max_length=100)           # 쿠팡
    domain = models.CharField(max_length=255, unique=True)  # coupang.com
    icon_url = models.URLField(blank=True, default='')
    is_active = models.BooleanField(default=True, db_index=True)
    sort_order = models.PositiveIntegerField(default=0, db_index=True)
    # URL 분류 패턴 (path prefix 목록)
    product_url_patterns = models.JSONField(default=list)  # ["/vp/products/"]
    search_url_patterns  = models.JSONField(default=list)  # ["/np/search", "/search"]
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name
