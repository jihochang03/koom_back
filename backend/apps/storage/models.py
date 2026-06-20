from django.db import models

PURPOSE_CHOICES = [
    ('inspection', '검수 사진'),
    ('product',    '상품 이미지'),
    ('receipt',    '영수증'),
    ('other',      '기타'),
]


class UploadedFile(models.Model):
    order_number = models.CharField(max_length=50, blank=True, db_index=True)
    customer_id  = models.CharField(max_length=255, blank=True, db_index=True)
    purpose      = models.CharField(max_length=20, choices=PURPOSE_CHOICES, default='other')
    original_name = models.CharField(max_length=255, blank=True)
    s3_key       = models.CharField(max_length=1024)
    public_url   = models.URLField(max_length=2048)
    content_type = models.CharField(max_length=100, blank=True)
    size_bytes   = models.BigIntegerField(default=0)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes  = [models.Index(fields=['order_number', 'purpose'])]
