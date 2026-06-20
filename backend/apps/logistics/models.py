from django.db import models


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
    created_at               = models.DateTimeField(auto_now_add=True)
    updated_at               = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Tracking {self.order_number} / {self.tracking_number}"
