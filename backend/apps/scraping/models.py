from django.db import models


class ScrapeStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    PROCESSING = 'processing', 'Processing'
    COMPLETED = 'completed', 'Completed'
    FAILED = 'failed', 'Failed'


class PageType(models.TextChoices):
    AUTO = 'auto', 'Auto'
    LIST = 'list', 'List'
    DETAIL = 'detail', 'Detail'


class ScrapeCategory(models.TextChoices):
    SHOPPING = 'shopping', '쇼핑'
    NEWS = 'news', '뉴스/블로그'
    REAL_ESTATE = 'real_estate', '부동산'
    JOBS = 'jobs', '채용/구인'
    GENERAL = 'general', '일반'


class ScrapeRequest(models.Model):
    url = models.URLField(max_length=2048)
    domain = models.CharField(max_length=255, blank=True, default='', db_index=True)
    category = models.CharField(
        max_length=20,
        choices=ScrapeCategory.choices,
        default=ScrapeCategory.SHOPPING,
        db_index=True,
    )
    page_type = models.CharField(
        max_length=10,
        choices=PageType.choices,
        default=PageType.AUTO,
    )
    status = models.CharField(
        max_length=20,
        choices=ScrapeStatus.choices,
        default=ScrapeStatus.PENDING,
    )
    error_message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.status}] {self.url}"


class UrlVisit(models.Model):
    customer_id = models.CharField(max_length=255, db_index=True)
    url = models.URLField(max_length=2048)
    title = models.CharField(max_length=1024, blank=True, default='')
    visited_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-visited_at']
        indexes = [
            models.Index(fields=['customer_id', '-visited_at']),
        ]

    def __str__(self):
        return f"[{self.customer_id}] {self.url}"


class ScrapeResult(models.Model):
    scrape_request = models.OneToOneField(
        ScrapeRequest,
        on_delete=models.CASCADE,
        related_name='result',
    )
    raw_data = models.JSONField(default=dict)
    template_used = models.CharField(max_length=255, blank=True, default='')
    # list 페이지 수집 시 아이템 수
    items_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Result for {self.scrape_request.url}"
