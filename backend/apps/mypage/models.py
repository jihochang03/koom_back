from django.db import models


DISCOUNT_TYPE_CHOICES = [
    ('fixed',   '정액 할인'),
    ('percent', '정률 할인'),
]


class UserAddress(models.Model):
    customer_id  = models.CharField(max_length=255, db_index=True)
    # 수취인 이름 — 통관·배송사별 표기 형식이 다르므로 3가지 저장
    name         = models.CharField(max_length=100)        # 한자 또는 현지 표기 (예: 辛 東赫)
    name_kana    = models.CharField(max_length=100, blank=True)  # 가타카나 (DHUB receiver_name_voice, 일본 배송 필수)
    name_en      = models.CharField(max_length=100, blank=True)  # 영문 (통관 서류용, 예: SHIN DONGHYUK)
    date_of_birth = models.DateField(null=True, blank=True) # 생년월일 (한국→일본 통관 필수)
    phone        = models.CharField(max_length=20)
    country      = models.CharField(max_length=2, default='JP')  # ISO 3166-1 alpha-2
    zipcode      = models.CharField(max_length=10)
    address1     = models.CharField(max_length=500)
    address2     = models.CharField(max_length=500, blank=True)
    is_default   = models.BooleanField(default=False, db_index=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_default', '-created_at']

    def __str__(self):
        return f"{self.customer_id} — {self.name}"


class Coupon(models.Model):
    code               = models.CharField(max_length=100, unique=True)
    name               = models.CharField(max_length=255)
    discount_type      = models.CharField(max_length=10, choices=DISCOUNT_TYPE_CHOICES)
    discount_value     = models.FloatField()
    min_order_amount   = models.FloatField(default=0)
    max_discount_amount = models.FloatField(null=True, blank=True)  # percent 타입 상한
    valid_from         = models.DateTimeField()
    valid_until        = models.DateTimeField()
    is_active          = models.BooleanField(default=True, db_index=True)
    usage_limit        = models.IntegerField(null=True, blank=True)  # null = 무제한
    created_at         = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.code} ({self.name})"


class UserCoupon(models.Model):
    customer_id = models.CharField(max_length=255, db_index=True)
    coupon      = models.ForeignKey(Coupon, on_delete=models.PROTECT, related_name='user_coupons')
    order_number = models.CharField(max_length=50, blank=True)  # 사용된 주문
    used_at     = models.DateTimeField(null=True, blank=True)
    issued_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-issued_at']

    def __str__(self):
        return f"{self.customer_id} — {self.coupon.code}"


class PointLog(models.Model):
    REASON_CHOICES = [
        ('earn_order',  '주문 적립'),
        ('earn_event',  '이벤트 적립'),
        ('earn_admin',  '관리자 지급'),
        ('use_order',   '주문 사용'),
        ('expire',      '만료'),
        ('refund',      '환불 복원'),
    ]

    customer_id   = models.CharField(max_length=255, db_index=True)
    delta         = models.IntegerField()            # + 적립, - 사용
    reason        = models.CharField(max_length=30, choices=REASON_CHOICES)
    order_number  = models.CharField(max_length=50, blank=True)
    balance_after = models.IntegerField()
    note          = models.CharField(max_length=255, blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class NotificationSetting(models.Model):
    customer_id          = models.CharField(max_length=255, unique=True)
    order_status_push    = models.BooleanField(default=True)
    order_status_email   = models.BooleanField(default=True)
    marketing_push       = models.BooleanField(default=False)
    marketing_email      = models.BooleanField(default=False)
    updated_at           = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.customer_id
