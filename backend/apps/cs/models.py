from django.db import models


INQUIRY_TYPE_CHOICES = [
    ('general',  '일반 문의'),
    ('cancel',   '취소 문의'),
    ('refund',   '환불 문의'),
    ('exchange', '교환 문의'),
    ('return',   '반품 문의'),
    ('shipping',       '배송 문의'),
    ('shipping_delay', '배송 지연'),
    ('price_error',    '가격 오차'),
    ('inspection_issue', '검수 이슈'),
    ('other',          '기타'),
]

INQUIRY_STATUS_CHOICES = [
    ('open',        '접수'),
    ('in_progress', '처리 중'),
    ('resolved',    '해결됨'),
    ('closed',      '종료'),
]

CANCEL_STATUS_CHOICES = [
    ('pending',   '취소 요청'),
    ('approved',  '취소 승인'),
    ('rejected',  '취소 반려'),
    ('completed', '취소 완료'),
]

REFUND_STATUS_CHOICES = [
    ('pending',           '환불 요청'),
    ('approved',          '환불 승인'),
    ('partial_approved',  '부분 환불 승인'),
    ('rejected',          '환불 반려'),
    ('completed',         '환불 완료'),
]


class Inquiry(models.Model):
    customer_id   = models.CharField(max_length=255, db_index=True)
    order_number  = models.CharField(max_length=50, blank=True, db_index=True)
    inquiry_type  = models.CharField(max_length=20, choices=INQUIRY_TYPE_CHOICES, default='general', db_index=True)
    title         = models.CharField(max_length=255)
    content       = models.TextField()
    images        = models.JSONField(null=True, blank=True)  # list of image URLs
    status        = models.CharField(max_length=20, choices=INQUIRY_STATUS_CHOICES, default='open', db_index=True)
    admin_reply   = models.TextField(blank=True)
    replied_at    = models.DateTimeField(null=True, blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.inquiry_type}] {self.title}"


class CancelRequest(models.Model):
    order_number        = models.CharField(max_length=50, unique=True, db_index=True)
    customer_id         = models.CharField(max_length=255, db_index=True)
    reason              = models.TextField()
    status              = models.CharField(max_length=20, choices=CANCEL_STATUS_CHOICES, default='pending', db_index=True)
    shipping_fee_burden = models.BooleanField(default=False)  # 고객 배송비 부담 여부
    admin_notes         = models.TextField(blank=True)
    processed_at        = models.DateTimeField(null=True, blank=True)
    created_at          = models.DateTimeField(auto_now_add=True)
    updated_at          = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"취소요청 {self.order_number}"


class RefundRequest(models.Model):
    order_number      = models.CharField(max_length=50, unique=True, db_index=True)
    customer_id       = models.CharField(max_length=255, db_index=True)
    reason            = models.TextField()
    requested_amount  = models.FloatField()
    approved_amount   = models.FloatField(null=True, blank=True)
    status            = models.CharField(max_length=20, choices=REFUND_STATUS_CHOICES, default='pending', db_index=True)
    admin_notes       = models.TextField(blank=True)
    processed_at      = models.DateTimeField(null=True, blank=True)
    created_at        = models.DateTimeField(auto_now_add=True)
    updated_at        = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"환불요청 {self.order_number}"
