import uuid
from django.db import models
from django.utils import timezone


ORDER_STATUS_CHOICES = [
    ('pending',           '주문 대기'),
    ('paid',              '결제 완료'),
    ('purchasing',        '현지 구매 중'),
    ('shipping_domestic', '현지 배송 중'),
    ('inspection',        '검수 중'),
    ('shipping_intl',     '국제 배송 중'),
    ('delivered',         '배송 완료'),
    ('cancelled',         '취소'),
    ('refunded',          '환불 완료'),
    ('partial_refund',    '부분 환불'),
]

GROUP_STATUS_CHOICES = [
    ('pending',   '결제 대기'),
    ('paid',      '결제 완료'),
    ('partial',   '일부 처리 중'),
    ('completed', '전체 완료'),
    ('cancelled', '취소'),
]


def _gen_group_number():
    date = timezone.now().strftime('%Y%m%d')
    uid = uuid.uuid4().hex[:6].upper()
    return f"GRP-{date}-{uid}"


def _gen_order_number():
    date = timezone.now().strftime('%Y%m%d')
    uid = uuid.uuid4().hex[:6].upper()
    return f"ORD-{date}-{uid}"


class OrderGroup(models.Model):
    group_number  = models.CharField(max_length=50, unique=True, default=_gen_group_number, db_index=True)
    customer_id   = models.CharField(max_length=255, db_index=True)
    status        = models.CharField(max_length=30, choices=GROUP_STATUS_CHOICES, default='pending', db_index=True)
    bundle_fee    = models.FloatField(default=0)       # 묶음 배송 수수료
    coupon_discount = models.FloatField(default=0)
    point_discount  = models.FloatField(default=0)
    total_paid    = models.FloatField(default=0)       # 실제 결제 금액
    currency      = models.CharField(max_length=10, default='KRW')
    paid_at       = models.DateTimeField(null=True, blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.group_number


class Order(models.Model):
    order_number  = models.CharField(max_length=50, unique=True, default=_gen_order_number, db_index=True)
    group         = models.ForeignKey(OrderGroup, on_delete=models.PROTECT, related_name='orders')
    customer_id   = models.CharField(max_length=255, db_index=True)
    site_domain   = models.CharField(max_length=255, blank=True, db_index=True)
    product_url   = models.URLField(max_length=2048)
    title         = models.CharField(max_length=1024)
    options       = models.JSONField(default=list)     # [{name, value}]
    quantity      = models.PositiveIntegerField(default=1)

    # 가격 내역 (KRW)
    price_product           = models.FloatField()
    price_domestic_shipping = models.FloatField(default=0)   # 예상 일본 내 배송비
    price_intl_shipping     = models.FloatField(default=0)   # 예상 국제배송비
    price_tariff            = models.FloatField(default=0)   # 예상 관부가세
    price_fee               = models.FloatField(default=0)   # 수수료
    price_total             = models.FloatField()            # 예상 총액
    currency                = models.CharField(max_length=10, default='KRW')

    # 어드민 전용
    price_dk_burden = models.FloatField(default=0)           # DK 부담액 (가격 오차)
    price_actual    = models.FloatField(null=True, blank=True) # 실제 구매가
    admin_notes     = models.TextField(blank=True)
    inspection_notes = models.TextField(blank=True)          # 검수 이슈 메모
    refund_amount   = models.FloatField(null=True, blank=True)
    refund_reason   = models.TextField(blank=True)

    status = models.CharField(max_length=30, choices=ORDER_STATUS_CHOICES, default='pending', db_index=True)

    # 배송
    tracking_number          = models.CharField(max_length=255, blank=True)
    estimated_delivery_min   = models.IntegerField(null=True, blank=True)  # days
    estimated_delivery_max   = models.IntegerField(null=True, blank=True)

    # 주문 당시 스냅샷
    product_snapshot = models.JSONField(default=dict)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # 13.2 상품 상세
    product_copy_url    = models.CharField(max_length=500, blank=True)
    product_category    = models.CharField(max_length=200, blank=True)
    prohibited_review   = models.JSONField(null=True, blank=True)

    # 13.6 금액 상세
    price_initial_payment     = models.FloatField(null=True, blank=True)
    price_discount            = models.FloatField(default=0)
    price_points_used         = models.FloatField(default=0)
    price_final_charged       = models.FloatField(null=True, blank=True)
    company_burden_tariff     = models.FloatField(default=0)
    company_burden_error_small = models.FloatField(default=0)
    company_burden_shipping_error = models.FloatField(default=0)
    company_burden_other      = models.FloatField(default=0)
    refund_partial_error      = models.FloatField(default=0)
    refund_customer_request   = models.FloatField(default=0)
    refund_inspection         = models.FloatField(default=0)
    refund_cancellation       = models.FloatField(default=0)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.order_number


ORDER_STAGE_CHOICES = [
    ('order_received',        '주문 접수'),
    ('purchase_review',       '구매 검토'),
    ('purchase_complete',     '구매 완료'),
    ('pre_arrival',           '입고 대기'),
    ('arrived',               '입고 완료'),
    ('inspection_in_progress','검수 중'),
    ('inspection_complete',   '검수 완료'),
    ('preparing_dispatch',    '출고 준비'),
    ('intl_shipping',         '국제 배송 중'),
    ('jp_carrier_handover',   '일본 배송사 인계'),
    ('delivered',             '배송 완료'),
    ('cancelled_or_refunded', '취소/반품/환불'),
]

RESPONSIBLE_PARTY_CHOICES = [
    ('dk',             'DK(당사)'),
    ('seller',         '판매처'),
    ('logistics',      '물류센터'),
    ('carrier',        '배송사'),
    ('system',         '시스템'),
    ('customer',       '고객'),
]

ACTOR_TYPE_CHOICES = [
    ('system',      '시스템'),
    ('operator',    '운영자'),
    ('logistics',   '물류센터'),
    ('pg',          'PG'),
    ('carrier_api', '배송사 API'),
]

ERROR_HANDLING_CHOICES = [
    ('company_burden',    '회사 부담'),
    ('cs_review',         'CS 수동 검토'),
    ('additional_charge', '고객 추가비용 요청'),
    ('cancel',            '취소'),
    ('partial_refund',    '부분환불'),
]

PG_AUTH_STATUS_CHOICES = [
    ('pending',           '인증 대기'),
    ('auth_complete',     '결제 인증 완료'),
    ('capture_pending',   '매출 확정 대기'),
    ('captured',          '매출 확정 완료'),
    ('cancel_in_progress','취소/환불 진행 중'),
    ('cancelled',         '취소 완료'),
    ('refunded',          '환불 완료'),
    ('failed',            '실패'),
]


class OrderStatusLog(models.Model):
    order_number      = models.CharField(max_length=50, db_index=True)
    stage             = models.CharField(max_length=30, choices=ORDER_STAGE_CHOICES, db_index=True)
    changed_at        = models.DateTimeField()
    responsible_party = models.CharField(max_length=20, choices=RESPONSIBLE_PARTY_CHOICES, default='system')
    memo              = models.TextField(blank=True)
    available_actions = models.JSONField(null=True, blank=True)
    created_at        = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['changed_at']

    def __str__(self):
        return f"{self.order_number} → {self.stage}"


class AdminActionLog(models.Model):
    order_number  = models.CharField(max_length=50, db_index=True)
    changed_field = models.CharField(max_length=100)
    old_value     = models.JSONField(null=True, blank=True)
    new_value     = models.JSONField(null=True, blank=True)
    actor_type    = models.CharField(max_length=20, choices=ACTOR_TYPE_CHOICES, default='operator')
    actor_id      = models.CharField(max_length=255, blank=True)
    reason        = models.TextField(blank=True)
    changed_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-changed_at']

    def __str__(self):
        return f"{self.order_number} {self.changed_field}"


class ErrorInfo(models.Model):
    order_number              = models.CharField(max_length=50, unique=True, db_index=True)
    error_rate                = models.FloatField(null=True, blank=True)
    error_amount              = models.FloatField(null=True, blank=True)
    error_causes              = models.JSONField(null=True, blank=True)
    handling_method           = models.CharField(max_length=30, choices=ERROR_HANDLING_CHOICES, blank=True)
    auto_processed            = models.BooleanField(default=False)
    cs_review_reason          = models.TextField(blank=True)
    additional_charge_amount  = models.FloatField(null=True, blank=True)
    additional_charge_sent_at = models.DateTimeField(null=True, blank=True)
    additional_charge_accepted_at = models.DateTimeField(null=True, blank=True)
    created_at                = models.DateTimeField(auto_now_add=True)
    updated_at                = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"ErrorInfo {self.order_number}"


PROVIDER_CHOICES = [
    ('gmo',       'GMO Payment Gateway'),
    ('gmo_paypay', 'GMO PayPay'),
    ('stripe',    'Stripe'),
    ('adyen',     'Adyen'),
]


class PGTransaction(models.Model):
    order_number         = models.CharField(max_length=50, db_index=True)
    # PG 공통 필드
    provider             = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default='gmo')
    currency             = models.CharField(max_length=3, default='JPY')
    provider_order_id    = models.CharField(max_length=100, blank=True, default='', db_index=True)
    pg_transaction_id    = models.CharField(max_length=255, blank=True, default='', db_index=True)
    auth_status          = models.CharField(max_length=30, choices=PG_AUTH_STATUS_CHOICES, default='pending')
    refund_amount        = models.FloatField(null=True, blank=True)
    refund_requested_at  = models.DateTimeField(null=True, blank=True)
    refund_completed_at  = models.DateTimeField(null=True, blank=True)
    failure_reason       = models.TextField(blank=True)
    raw_payload          = models.JSONField(null=True, blank=True)
    # GMO-PG 전용 필드 (레거시 호환 유지)
    gmo_order_id         = models.CharField(max_length=50, blank=True, default='', db_index=True)
    gmo_access_id        = models.CharField(max_length=255, blank=True, default='')
    gmo_access_pass      = models.CharField(max_length=255, blank=True, default='')
    gmo_forward          = models.CharField(max_length=50, blank=True, default='')
    gmo_approve          = models.CharField(max_length=50, blank=True, default='')
    gmo_job_cd           = models.CharField(max_length=20, blank=True, default='')
    amount_jpy           = models.IntegerField(default=0)
    created_at           = models.DateTimeField(auto_now_add=True)
    updated_at           = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"PG {self.pg_transaction_id}"


import uuid as _uuid


class ProductSnapshot(models.Model):
    """세관 제출용 구매 상품 사본 (Commercial Invoice / Section 19)."""
    order_number              = models.CharField(max_length=50, unique=True, db_index=True)
    snapshot_uuid             = models.UUIDField(default=_uuid.uuid4, unique=True, editable=False)
    product_name              = models.CharField(max_length=500)           # 한국어 품목명
    product_name_en           = models.CharField(max_length=500, blank=True)  # 영문 품목명 (세관 Invoice 필수)
    purchase_price            = models.FloatField()
    product_price_at_purchase = models.FloatField()
    options                   = models.JSONField(null=True, blank=True)
    quantity                  = models.IntegerField(default=1)
    seller                    = models.CharField(max_length=255, blank=True)
    site_domain               = models.CharField(max_length=255, blank=True)
    product_url               = models.URLField(max_length=1000, blank=True)
    images                    = models.JSONField(null=True, blank=True)
    html_content              = models.TextField(blank=True)
    created_at                = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Snapshot {self.order_number}"


class PurchaseRecord(models.Model):
    """CS 대리구매 작업 내역 (FR-ORD-07).

    고객 결제 후 CS가 현지 쇼핑몰에서 직접 대리구매한 결과를 기록한다.
    order_number 키 컨벤션은 ErrorInfo / ProductSnapshot / LogisticsInfo 와 동일.
    """
    order_number          = models.CharField(max_length=50, unique=True, db_index=True)
    purchase_account      = models.CharField(max_length=255, blank=True)   # 어떤 계정으로 구매했는지
    collection_address    = models.TextField(blank=True)                   # 쇼핑몰이 물건을 보낼 국내 집하 주소 (고객 일본주소와 별개)
    actual_price          = models.FloatField(null=True, blank=True)       # 실제 구매가
    domestic_shipping_fee = models.FloatField(default=0)                   # 국내 배송비
    currency              = models.CharField(max_length=10, default='KRW')
    cs_user               = models.CharField(max_length=255, blank=True, db_index=True)  # 담당 CS
    memo                  = models.TextField(blank=True)
    purchased_at          = models.DateTimeField(null=True, blank=True)
    created_at            = models.DateTimeField(auto_now_add=True)
    updated_at            = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"PurchaseRecord {self.order_number}"
