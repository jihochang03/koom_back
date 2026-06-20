from django.db import models


RISK_CHOICES = [
    ('prohibited', '수입 금지'),
    ('restricted', '수입 제한'),
    ('warning',    '주의'),
]


class ProhibitedKeyword(models.Model):
    keyword           = models.CharField(max_length=255, unique=True)
    category          = models.CharField(max_length=100, blank=True)
    risk_level        = models.CharField(max_length=20, choices=RISK_CHOICES, db_index=True)
    description       = models.TextField(blank=True)
    customs_reference = models.URLField(blank=True)
    is_active         = models.BooleanField(default=True, db_index=True)
    created_at        = models.DateTimeField(auto_now_add=True)
    updated_at        = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['risk_level', 'keyword']

    def __str__(self):
        return f"[{self.risk_level}] {self.keyword}"
