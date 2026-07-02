from django.db import models

from .stages import TRACKING_STAGE_CHOICES, EVENT_SOURCE_CHOICES


INSPECTION_RESULT_CHOICES = [
    ('pending', '검수 대기'),
    ('pass',    '검수 완료'),
    ('issue',   '검수 이슈'),
]

CARRIER_DELAY_CHOICES = [
    ('none',    '정상'),
    ('24h',     '24시간 정체'),
    ('48h',     '48시간 정체'),
    ('extended','장기 지연'),
]

CUSTOMS_TYPE_CHOICES = [
    ('list',    '목록통관'),
    ('general', '일반통관'),
]

CUSTOMS_RESULT_CHOICES = [
    ('pending',  '통관 대기'),
    ('cleared',  '통관 완료'),
    ('rejected', '통관 거절'),
    ('returned', '반송'),
]

DELIVERY_FAILURE_REASON_CHOICES = [
    ('address_error', '주소 오류'),
    ('absence',       '부재'),
    ('refusal',       '수취 거부'),
    ('damaged',       '파손'),
    ('other',         '기타'),
]

RESPONSIBLE_CHOICES = [
    ('customer', '고객'),
    ('carrier',  '배송사'),
    ('dk',       'DK(당사)'),
]

DELIVERY_FAILURE_STATUS_CHOICES = [
    ('stored',   '보관 중'),
    ('reship',   '재배송'),
    ('returned', '반품'),
    ('disposed', '폐기'),
]

DISPOSITION_CHOICES = [
    ('dispose', '폐기'),
    ('return',  '반품'),
]


class LogisticsInfo(models.Model):
    order_number          = models.CharField(max_length=50, unique=True, db_index=True)
    expected_arrival      = models.DateTimeField(null=True, blank=True)
    arrived_at            = models.DateTimeField(null=True, blank=True)
    inspection_result     = models.CharField(max_length=10, choices=INSPECTION_RESULT_CHOICES, default='pending')
    inspection_photos     = models.JSONField(null=True, blank=True)  # list of URLs
    components_match      = models.BooleanField(null=True, blank=True)
    has_defect            = models.BooleanField(null=True, blank=True)
    issue_reason          = models.TextField(blank=True)
    post_inspection_action = models.TextField(blank=True)
    created_at            = models.DateTimeField(auto_now_add=True)
    updated_at            = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Logistics {self.order_number}"


class CustomsClearance(models.Model):
    """통관 결과 + 통관 거절 시 '해당 상품만' 부분환불 처리 (Order 단위).

    통관결과(거절 사유 포함)는 FastBox 문서 API 로는 들어오지 않으므로
    통관업자→CS 가 받은 정보를 수기 등록한다. 거절 시 CS 가 고객에게 부분환불을
    안내(notified_at)하고, 미응답인 채 response_deadline 이 지나면 CS 가
    '처리 대기' 목록(refund-due)에서 해당 Order 금액만 부분환불한다.
    """
    order_number          = models.CharField(max_length=50, unique=True, db_index=True)
    customs_type          = models.CharField(max_length=10, choices=CUSTOMS_TYPE_CHOICES, blank=True, verbose_name='통관 종류')
    result                = models.CharField(max_length=10, choices=CUSTOMS_RESULT_CHOICES, default='pending', db_index=True, verbose_name='통관 결과')
    reject_reason         = models.TextField(blank=True, verbose_name='거절 사유')

    # 해당 상품만 부분환불
    partial_refund_amount = models.FloatField(null=True, blank=True, verbose_name='해당 상품 부분환불 예정액')
    notified_at           = models.DateTimeField(null=True, blank=True, verbose_name='고객 안내(CS 발송) 시각')
    response_deadline     = models.DateTimeField(null=True, blank=True, verbose_name='고객 응답 기한')
    customer_responded_at = models.DateTimeField(null=True, blank=True, verbose_name='고객 응답 시각 (null=미응답)')
    refund_processed_at   = models.DateTimeField(null=True, blank=True, verbose_name='부분환불 실행 시각')
    refund_amount         = models.FloatField(null=True, blank=True, verbose_name='실제 환불액')

    created_at            = models.DateTimeField(auto_now_add=True)
    updated_at            = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Customs {self.order_number} [{self.result}]"


class DeliveryFailure(models.Model):
    """배송 실패(패스트박스 보관) → 재배송/반품/폐기 처리 (Order 단위).

    배달 실패(AttemptFail 등)로 패스트박스에 보관 중인 건을 관리한다. CS 가 고객에게
    현재 상태·실패 사유·재배송/반송비 부담을 안내(notified_at)하고, 미응답인 채
    storage_deadline 이 지나면 '가액 기준 분기'(고가=반품 / 저가=폐기)로 처분한다.
    주소 오류 등 고객 귀책이면 비용은 고객 부담, 폐기 시 상품가 환불 없음.
    """
    order_number          = models.CharField(max_length=50, unique=True, db_index=True)
    failure_reason        = models.CharField(max_length=20, choices=DELIVERY_FAILURE_REASON_CHOICES, default='address_error', verbose_name='실패 사유')
    responsible           = models.CharField(max_length=10, choices=RESPONSIBLE_CHOICES, default='customer', verbose_name='귀책')
    cost_burden           = models.CharField(max_length=10, choices=RESPONSIBLE_CHOICES, default='customer', verbose_name='재배송/반송비 부담')
    status                = models.CharField(max_length=10, choices=DELIVERY_FAILURE_STATUS_CHOICES, default='stored', db_index=True, verbose_name='처리 상태')

    item_value            = models.FloatField(null=True, blank=True, verbose_name='상품 가액 (처분 분기용)')
    notified_at           = models.DateTimeField(null=True, blank=True, verbose_name='고객 안내(CS 발송) 시각')
    storage_deadline      = models.DateTimeField(null=True, blank=True, verbose_name='보관 기한')
    customer_responded_at = models.DateTimeField(null=True, blank=True, verbose_name='고객 응답 시각 (null=미응답)')
    disposition           = models.CharField(max_length=10, choices=DISPOSITION_CHOICES, blank=True, verbose_name='처분 (폐기/반품)')
    resolved_at           = models.DateTimeField(null=True, blank=True, verbose_name='처리 완료 시각')
    memo                  = models.TextField(blank=True)

    created_at            = models.DateTimeField(auto_now_add=True)
    updated_at            = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"DeliveryFailure {self.order_number} [{self.status}]"


class ShippingTracking(models.Model):
    order_number             = models.CharField(max_length=50, unique=True, db_index=True)
    tracking_number          = models.CharField(max_length=100, blank=True)
    carrier                  = models.CharField(max_length=100, blank=True)
    carrier_status           = models.CharField(max_length=255, blank=True)  # raw API status
    customer_status          = models.CharField(max_length=255, blank=True)  # display status
    last_status_changed_at   = models.DateTimeField(null=True, blank=True)
    last_api_checked_at      = models.DateTimeField(null=True, blank=True)
    next_check_at            = models.DateTimeField(null=True, blank=True)
    is_untrackable_segment   = models.BooleanField(default=False)
    delay_detected           = models.BooleanField(default=False)
    delay_type               = models.CharField(max_length=10, choices=CARRIER_DELAY_CHOICES, default='none')
    delay_hours              = models.IntegerField(null=True, blank=True)
    stagnation_detected_at   = models.DateTimeField(null=True, blank=True)
    fb_invoice_no        = models.CharField(max_length=100, blank=True, db_index=True)  # FastBox 송장번호
    dhub_ord_bundle_no   = models.CharField(max_length=100, blank=True)
    dhub_instruction_no  = models.CharField(max_length=100, blank=True)
    dhub_delivery_type   = models.CharField(max_length=5, blank=True)   # FB / SD
    events                   = models.JSONField(null=True, blank=True)  # raw event list from carrier API

    # ── 고객 배송추적 화면용 (5단계 진행 바 + 최종 배송정보) ──────────────────
    current_stage     = models.CharField(
        max_length=20, choices=TRACKING_STAGE_CHOICES, default='shipment_sent',
        db_index=True, verbose_name='현재 단계',
    )
    delivered_at      = models.DateTimeField(null=True, blank=True, verbose_name='배송완료 시각')
    delivery_region   = models.CharField(max_length=255, blank=True, default='', verbose_name='배송 지역')

    created_at               = models.DateTimeField(auto_now_add=True)
    updated_at               = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Tracking {self.order_number} / {self.tracking_number}"


class TrackingEvent(models.Model):
    """
    배송 추적 타임라인의 개별 이벤트 (시간순 로그 + 5단계 분류).

    세관(입항·하선·X-Ray·통관)·국내 택배(집하·물류센터·간선·배송) 등 원천 이벤트를
    구조화해 저장한다. `stage`는 설명 텍스트로 자동 분류(stages.classify_tracking_stage).
    화면에서는 날짜별로 묶어 시간순으로 표시한다.
    """
    order_number = models.CharField(max_length=50, db_index=True)
    occurred_at  = models.DateTimeField(db_index=True, verbose_name='발생 시각')
    stage        = models.CharField(
        max_length=20, choices=TRACKING_STAGE_CHOICES, db_index=True, verbose_name='단계',
    )
    description  = models.CharField(max_length=500, verbose_name='이벤트 내용')
    location     = models.CharField(max_length=255, blank=True, default='', verbose_name='위치')
    source       = models.CharField(
        max_length=20, choices=EVENT_SOURCE_CHOICES, default='carrier', verbose_name='출처',
    )
    raw_code     = models.CharField(max_length=50, blank=True, default='', verbose_name='원천 상태코드')
    raw          = models.JSONField(null=True, blank=True, verbose_name='원천 데이터')
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['occurred_at', 'id']
        verbose_name = '배송 추적 이벤트'
        verbose_name_plural = '배송 추적 이벤트'
        indexes = [models.Index(fields=['order_number', 'occurred_at'])]
        constraints = [
            models.UniqueConstraint(
                fields=['order_number', 'occurred_at', 'description'],
                name='uniq_tracking_event',
            ),
        ]

    def __str__(self):
        return f"{self.order_number} [{self.stage}] {self.description[:30]}"
