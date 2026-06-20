from django.db import models


class KoreanMall(models.Model):
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=100)
    domain = models.CharField(max_length=255)
    logo_url = models.URLField(blank=True, default='')
    is_active = models.BooleanField(default=True, db_index=True)
    display_order = models.IntegerField(default=0)

    class Meta:
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name


class MallCrawlJobStatus(models.TextChoices):
    PENDING = 'pending', '대기'
    PROCESSING = 'processing', '크롤중'
    COMPLETED = 'completed', '완료'
    FAILED = 'failed', '실패'


class MallCrawlJob(models.Model):
    mall = models.ForeignKey(KoreanMall, on_delete=models.CASCADE, related_name='crawl_jobs')
    category_url = models.URLField(max_length=2048)
    category_name = models.CharField(max_length=100)
    status = models.CharField(
        max_length=20,
        choices=MallCrawlJobStatus.choices,
        default=MallCrawlJobStatus.PENDING,
        db_index=True,
    )
    products_count = models.IntegerField(default=0)
    error_message = models.TextField(blank=True, default='')
    last_crawled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.mall.name} / {self.category_name}"


class FeaturedCategory(models.Model):
    """어드민이 메인 페이지에 노출할 쇼핑몰+카테고리 조합을 지정"""
    mall = models.ForeignKey(KoreanMall, on_delete=models.CASCADE, related_name='featured_categories')
    category_name = models.CharField(max_length=100, help_text="Product.category 값과 일치해야 함")
    display_title = models.CharField(max_length=100, blank=True, default='', help_text="비워두면 category_name 사용")
    display_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_order', 'mall__name', 'category_name']
        unique_together = [['mall', 'category_name']]

    @property
    def title(self):
        return self.display_title or self.category_name

    def __str__(self):
        return f"{self.mall.name} / {self.title}"
