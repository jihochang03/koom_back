from django.db import models

CHANNEL_CHOICES = [
    ('line',  'LINE'),
    ('email', 'Email'),
    ('sms',   'SMS'),
]

EVENT_CHOICES = [
    ('order_confirmed',    '주문 확인'),
    ('payment_complete',   '결제 완료'),
    ('purchase_started',   '구매 시작'),
    ('inspection_done',    '검수 완료'),
    ('shipping_kr',        '한국 발송'),
    ('shipping_intl',      '국제 배송 중'),
    ('shipping_jp',        '일본 배송 중'),
    ('delivered',          '배송 완료'),
    ('cancel_complete',    '취소 완료'),
    ('refund_complete',    '환불 완료'),
    ('customs_rejected',   '통관 거절 안내'),
    ('delivery_failed',    '배송 실패 안내'),
    ('custom',             '커스텀'),
]

STATUS_CHOICES = [
    ('pending',  '발송 대기'),
    ('sent',     '발송 성공'),
    ('failed',   '발송 실패'),
]


class NotificationLog(models.Model):
    customer_id  = models.CharField(max_length=255, db_index=True)
    channel      = models.CharField(max_length=10, choices=CHANNEL_CHOICES)
    event        = models.CharField(max_length=30, choices=EVENT_CHOICES)
    recipient    = models.CharField(max_length=255)   # LINE userId / 이메일 / 전화번호
    order_number = models.CharField(max_length=50, blank=True, db_index=True)
    subject      = models.CharField(max_length=255, blank=True)
    body         = models.TextField(blank=True)
    send_status  = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    error_detail = models.TextField(blank=True)
    sent_at      = models.DateTimeField(null=True, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes  = [models.Index(fields=['customer_id', 'channel', '-created_at'])]
