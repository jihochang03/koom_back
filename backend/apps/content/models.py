from django.db import models


POLICY_TYPE_CHOICES = [
    ('privacy',  '개인정보 처리방침'),
    ('terms',    '이용약관'),
    ('shipping', '배송 정책'),
    ('refund',   '환불 정책'),
    ('guide',    '이용 가이드'),
]


class FAQ(models.Model):
    category   = models.CharField(max_length=100, db_index=True)
    question   = models.CharField(max_length=500)
    answer     = models.TextField()
    sort_order = models.PositiveIntegerField(default=0, db_index=True)
    is_active  = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', '-created_at']

    def __str__(self):
        return f"[{self.category}] {self.question}"


class Notice(models.Model):
    title        = models.CharField(max_length=500)
    content      = models.TextField()
    is_pinned    = models.BooleanField(default=False, db_index=True)
    is_active    = models.BooleanField(default=True, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_pinned', '-published_at', '-created_at']

    def __str__(self):
        return self.title


class EventBanner(models.Model):
    title      = models.CharField(max_length=255)
    image_url  = models.URLField()
    link_url   = models.URLField(blank=True)
    sort_order = models.PositiveIntegerField(default=0, db_index=True)
    is_active  = models.BooleanField(default=True, db_index=True)
    starts_at  = models.DateTimeField(null=True, blank=True)
    ends_at    = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', '-created_at']

    def __str__(self):
        return self.title


class Policy(models.Model):
    policy_type    = models.CharField(max_length=20, choices=POLICY_TYPE_CHOICES, db_index=True)
    title          = models.CharField(max_length=255)
    content        = models.TextField()
    version        = models.CharField(max_length=20)
    effective_date = models.DateField()
    is_current     = models.BooleanField(default=False, db_index=True)
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-effective_date']

    def __str__(self):
        return f"{self.policy_type} v{self.version}"
