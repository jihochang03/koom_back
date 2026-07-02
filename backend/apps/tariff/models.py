from django.db import models


class TariffLookupLog(models.Model):
    """관세율 조회 이력 및 캐시 (Claude API 중복 호출 방지)"""
    product_title = models.CharField(max_length=500)
    # 조회 결과 전체 (tariff_lookup.py 반환 dict)
    result = models.JSONField(default=dict)
    # 최종 적용 세율 (빠른 필터링용)
    rate = models.FloatField(null=True, blank=True)
    duty_type = models.CharField(max_length=20, blank=True, default='')
    matched_item = models.CharField(max_length=500, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.product_title[:50]} → rate={self.rate}"


class ProductHsClassification(models.Model):
    """
    검수 담당자가 fastbox 통관 등록 전에 확정하는 상품별 HS코드·통관 카테고리.

    AI(classify_tariff)가 제목으로 추천한 HS코드/분류 경로와 그 **선정 사유**,
    그리고 채택될 여지가 있는 **대안 후보**를 스냅샷으로 보관한다.
    검수 담당자는 추천을 그대로 확정하거나, 대안 선택 또는 직접 입력으로 수정하고
    피드백을 남긴다. 확정값(final_*)이 fastbox 통관 등록에 사용된다.
    """

    class Status(models.TextChoices):
        PENDING   = 'pending',   '확인 대기'
        CONFIRMED = 'confirmed', '확정'

    class DecisionSource(models.TextChoices):
        AI_CONFIRMED = 'ai_confirmed', 'AI 추천 그대로 확정'
        ALTERNATIVE  = 'alternative',  '대안 후보 선택'
        MANUAL       = 'manual',       '직접 입력 수정'

    product = models.OneToOneField(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='hs_classification',
        verbose_name='상품',
    )

    # ── AI 추천 스냅샷 (classify_tariff 결과) ────────────────────────────────
    ai_suggested = models.JSONField(
        default=dict, blank=True,
        verbose_name='AI 추천',
        help_text='{hs_code, matched_item, full_path, depth_path, rate, reason, ...}',
    )
    ai_alternatives = models.JSONField(
        default=list, blank=True,
        verbose_name='AI 대안 후보',
        help_text='채택 여지가 있는 다른 분류 후보 목록',
    )
    ai_search_expansion = models.CharField(
        max_length=500, blank=True, default='',
        verbose_name='AI 검색 확장어',
    )

    # ── 검수 담당자 확정값 (fastbox 통관에 사용) ──────────────────────────────
    final_hs_code = models.CharField(
        max_length=30, blank=True, default='', db_index=True,
        verbose_name='확정 HS코드(순번)',
    )
    final_category = models.CharField(
        max_length=500, blank=True, default='',
        verbose_name='확정 통관 카테고리(품명)',
    )
    final_full_path = models.TextField(
        blank=True, default='',
        verbose_name='확정 분류 경로',
    )

    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDING,
        db_index=True, verbose_name='상태',
    )
    decision_source = models.CharField(
        max_length=15, choices=DecisionSource.choices, blank=True, default='',
        verbose_name='확정 방식',
    )
    inspector = models.CharField(
        max_length=100, blank=True, default='',
        verbose_name='검수 담당자',
    )
    inspector_note = models.TextField(
        blank=True, default='',
        verbose_name='검수 피드백/메모',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True, verbose_name='확정 시각')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name = '상품 HS 분류'
        verbose_name_plural = '상품 HS 분류'

    def __str__(self):
        return f"{self.product_id} → {self.final_hs_code or '미확정'} ({self.status})"
