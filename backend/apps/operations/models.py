from django.db import models


ERROR_HANDLING_CHOICES = [
    ('company_burden',    '회사 부담'),
    ('cs_review',         'CS 수동 검토'),
    ('additional_charge', '고객 추가비용 요청'),
    ('cancel',            '취소'),
    ('partial_refund',    '부분환불'),
]


class ErrorCriteria(models.Model):
    """오차 처리 기준 설정. is_current=True 인 레코드가 현재 적용 기준."""
    # 소 오차 (자동 회사 부담)
    small_error_threshold_pct  = models.FloatField(default=2.0)   # 퍼센트
    small_error_threshold_abs  = models.FloatField(default=500.0) # 절대금액 (원)
    small_error_per_item       = models.BooleanField(default=True) # True=상품별, False=묶음별

    # 대 오차 (CS 전환)
    large_error_threshold_pct  = models.FloatField(default=5.0)

    # 원인별 기본 처리 방식
    handling_ai_error          = models.CharField(max_length=30, choices=ERROR_HANDLING_CHOICES, default='company_burden')
    handling_price_change      = models.CharField(max_length=30, choices=ERROR_HANDLING_CHOICES, default='cs_review')
    handling_shipping_extra    = models.CharField(max_length=30, choices=ERROR_HANDLING_CHOICES, default='company_burden')
    handling_tax               = models.CharField(max_length=30, choices=ERROR_HANDLING_CHOICES, default='cs_review')
    handling_prima_risk        = models.CharField(max_length=30, choices=ERROR_HANDLING_CHOICES, default='cs_review')
    handling_exchange_rate     = models.CharField(max_length=30, choices=ERROR_HANDLING_CHOICES, default='company_burden')

    is_current  = models.BooleanField(default=True, db_index=True)
    note        = models.TextField(blank=True)
    created_by  = models.CharField(max_length=255, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if self.is_current:
            ErrorCriteria.objects.exclude(pk=self.pk).update(is_current=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"ErrorCriteria {self.pk} (current={self.is_current})"


class ErrorCriteriaLog(models.Model):
    criteria      = models.ForeignKey(ErrorCriteria, on_delete=models.CASCADE, related_name='logs')
    changed_field = models.CharField(max_length=100)
    old_value     = models.JSONField(null=True, blank=True)
    new_value     = models.JSONField(null=True, blank=True)
    changed_by    = models.CharField(max_length=255, blank=True)
    changed_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-changed_at']

    def __str__(self):
        return f"CriteriaLog {self.criteria_id} {self.changed_field}"
