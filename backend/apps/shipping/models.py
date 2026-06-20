from django.db import models
from django.core.cache import cache


class ShippingQuoteLog(models.Model):
    service_provider = models.CharField(max_length=10)
    transport_mode = models.CharField(max_length=20)
    actual_weight_kg = models.FloatField()
    result = models.JSONField(default=dict)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class ShippingRateTable(models.Model):
    TABLE_KEY_CHOICES = [
        ('KSE_SEA_STANDARD',  'KSE 해상 Standard (JPY)'),
        ('KSE_SEA_LIGHT',     'KSE 해상 Light (JPY)'),
        ('KSE_AIR_STANDARD',  'KSE 항공 Standard (JPY)'),
        ('KSE_AIR_LIGHT',     'KSE 항공 Light (JPY)'),
        ('KSE_SDEX_STANDARD', 'KSE SDEX Standard (JPY)'),
        ('KSE_SDEX_LIGHT',    'KSE SDEX Light (JPY)'),
        ('CJL_DOOR_TO_DOOR',  'CJL Door to Door (KRW)'),
        # FastBox (DHUB) 항공 특송 4개 등급 (KRW)
        ('FB_AIR_STANDARD',   'FastBox 항공 Standard (KRW)'),
        ('FB_AIR_VIP',        'FastBox 항공 VIP — 월 1,000건+ (KRW)'),
        ('FB_AIR_SVIP',       'FastBox 항공 SVIP — 월 3,000건+ (KRW)'),
        ('FB_AIR_SSVIP',      'FastBox 항공 SSVIP — 월 7,000건+ (KRW)'),
        # EMS (한국우편 EMS → 일본) (KRW)
        ('EMS_JP_STANDARD',   '한국우편 EMS → 일본 Standard (KRW)'),
        # 커스텀 배송사 요율표 (admin 직접 입력)
        ('CUSTOM_1',  '커스텀 요율표 1'),
        ('CUSTOM_2',  '커스텀 요율표 2'),
        ('CUSTOM_3',  '커스텀 요율표 3'),
        ('CUSTOM_4',  '커스텀 요율표 4'),
        ('CUSTOM_5',  '커스텀 요율표 5'),
    ]

    table_key = models.CharField(
        max_length=30, unique=True, choices=TABLE_KEY_CHOICES, verbose_name='요율표 종류'
    )
    currency = models.CharField(max_length=5, default='JPY', verbose_name='통화')
    is_active = models.BooleanField(default=True, verbose_name='활성화')
    note = models.TextField(blank=True, default='', verbose_name='비고')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['table_key']
        verbose_name = '배송 요율표'
        verbose_name_plural = '배송 요율표'

    def __str__(self):
        return self.get_table_key_display()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        cache.delete('shipping_rate_tables')

    def to_dict(self) -> dict:
        return {e.weight_break_kg: e.freight for e in self.entries.order_by('weight_break_kg')}


class ShippingRateEntry(models.Model):
    table = models.ForeignKey(
        ShippingRateTable, on_delete=models.CASCADE, related_name='entries'
    )
    weight_break_kg = models.FloatField(verbose_name='구간 무게 (kg)')
    freight = models.IntegerField(verbose_name='운임')

    class Meta:
        ordering = ['weight_break_kg']
        unique_together = [['table', 'weight_break_kg']]
        verbose_name = '요율 구간'
        verbose_name_plural = '요율 구간'

    def __str__(self):
        return f'{self.weight_break_kg} kg → {self.freight:,}'


class ShippingCarrierProfile(models.Model):
    """
    배송사 프로필 — Admin에서 배송사명을 자유 입력하고,
    엔진(계산 방식)을 선택해 자동 견적에 활용.
    """

    ENGINE_CHOICES = [
        ('FB',       'FastBox (DHUB) 항공특송'),
        ('KSE_AIR',  'KSE 항공'),
        ('KSE_SEA',  'KSE 해운'),
        ('KSE_SDEX', 'KSE SDEX'),
        ('CJL',      'CJL Door to Door'),
        ('EMS',      '한국우편 EMS'),
        ('TABLE',    '커스텀 요율표 (신규 배송사)'),
    ]
    MODE_CHOICES = [
        ('AIR', '항공'),
        ('SEA', '해운'),
        ('EMS', 'EMS'),
    ]
    FB_TIER_CHOICES = [
        ('STANDARD', '표준'),
        ('VIP',      'VIP (월 1,000건+)'),
        ('SVIP',     'SVIP (월 3,000건+)'),
        ('SSVIP',    'SSVIP (월 7,000건+)'),
    ]
    FB_TAX_CHOICES = [
        ('DDU', 'DDU — 구매자 납부'),
        ('DDP', 'DDP — 판매자 납부'),
    ]

    name       = models.CharField(max_length=60, verbose_name='배송사명',
                                  help_text='자유 입력 (예: FastBox VIP 항공, 야마토운수)')
    engine     = models.CharField(
        max_length=15, choices=ENGINE_CHOICES, verbose_name='계산 엔진',
        help_text='운임 계산에 사용할 엔진. TABLE 선택 시 아래 요율표를 지정하세요.'
    )
    mode       = models.CharField(max_length=10, choices=MODE_CHOICES, verbose_name='운송 방식')
    rate_table = models.ForeignKey(
        ShippingRateTable, null=True, blank=True, on_delete=models.SET_NULL,
        verbose_name='요율표', help_text='TABLE 엔진 선택 시 필수. 다른 엔진은 생략 가능.'
    )
    currency   = models.CharField(
        max_length=5, default='KRW', verbose_name='통화',
        help_text='TABLE 엔진일 때 요율표 통화 (KRW 또는 JPY)'
    )
    fb_tier    = models.CharField(
        max_length=10, choices=FB_TIER_CHOICES, blank=True, default='STANDARD',
        verbose_name='FB 등급', help_text='엔진=FB 일 때만 사용'
    )
    fb_tax_mode = models.CharField(
        max_length=5, choices=FB_TAX_CHOICES, blank=True, default='DDU',
        verbose_name='FB 세금 납부', help_text='엔진=FB 일 때만 사용'
    )
    is_default  = models.BooleanField(
        default=False, verbose_name='기본 배송사',
        help_text='같은 mode 내에서 기본으로 사용할 배송사를 지정'
    )
    is_active   = models.BooleanField(default=True, verbose_name='활성화')
    sort_order  = models.IntegerField(default=0, verbose_name='정렬 순서')
    note        = models.TextField(blank=True, verbose_name='비고')
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'engine']
        verbose_name = '배송사 프로필'
        verbose_name_plural = '배송사 프로필'

    def __str__(self):
        tier = f' [{self.fb_tier}]' if self.engine == 'FB' else ''
        return f'{self.name} ({self.get_engine_display()} / {self.get_mode_display()}{tier})'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        cache.delete('shipping_rate_tables')


class ShippingModeConfig(models.Model):
    """
    무게 기반 국제 배송 방식 자동 결정 규칙.
    is_current=True 인 레코드가 현재 적용 규칙.
    """

    SELECTION_CHOICES = [
        ('AUTO',     '무게 기반 자동 (항공 ↔ 해운)'),
        ('AIR_ONLY', '항공만'),
        ('SEA_ONLY', '해운만'),
    ]

    mode_selection    = models.CharField(
        max_length=10, choices=SELECTION_CHOICES, default='AUTO', verbose_name='운송 방식 선택'
    )
    air_max_weight_kg = models.FloatField(
        default=3.0, verbose_name='항공 최대 무게 (kg)',
        help_text='AUTO일 때: 이 무게 이하 → 항공, 초과 → 해운. 기본값 3.0 kg.'
    )
    is_current        = models.BooleanField(default=True, verbose_name='현재 적용')
    note              = models.TextField(blank=True, verbose_name='비고')
    updated_at        = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_current', '-updated_at']
        verbose_name = '배송 방식 규칙'
        verbose_name_plural = '배송 방식 규칙'

    def __str__(self):
        if self.mode_selection == 'AUTO':
            return f'자동 ({self.air_max_weight_kg} kg 기준)'
        return self.get_mode_selection_display()


class FuelSurcharge(models.Model):
    """
    월별 유류할증료 (FSC) — Admin에서 직접 입력.
    carrier_name + year_month 가 고유 키.
    """

    CURRENCY_CHOICES = [
        ('KRW', 'KRW (원)'),
        ('JPY', 'JPY (엔)'),
    ]

    carrier_name = models.CharField(max_length=60, verbose_name='배송사명',
                                    help_text='배송사 프로필의 배송사명과 맞춰 입력')
    year_month   = models.CharField(max_length=7, verbose_name='적용 월',
                                    help_text='YYYY-MM 형식 (예: 2025-06)')
    amount       = models.IntegerField(verbose_name='유류할증료 금액')
    currency     = models.CharField(max_length=5, choices=CURRENCY_CHOICES,
                                    default='KRW', verbose_name='통화')
    note         = models.TextField(blank=True, verbose_name='비고')
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [['carrier_name', 'year_month']]
        ordering = ['-year_month', 'carrier_name']
        verbose_name = '월별 유류할증료'
        verbose_name_plural = '월별 유류할증료'

    def __str__(self):
        return f'{self.carrier_name} {self.year_month}: {self.amount:,} {self.currency}'


class CategoryWeightPreset(models.Model):
    """카테고리별 평균 무게 — 국제 배송비 자동 계산에 사용."""

    category_name = models.CharField(max_length=100, unique=True, verbose_name='카테고리명')
    avg_weight_kg = models.FloatField(verbose_name='평균 무게 (kg)')
    note          = models.TextField(blank=True, verbose_name='비고')
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category_name']
        verbose_name = '카테고리 평균 무게'
        verbose_name_plural = '카테고리 평균 무게'

    def __str__(self):
        return f'{self.category_name} ({self.avg_weight_kg} kg)'


def load_rate_tables() -> dict | None:
    """
    DB에서 활성화된 요율표를 로드해 cfg dict로 반환.
    DB에 요율표가 없으면 None 반환 → 호출측이 기본값 사용.
    5분 캐시 적용.
    """
    cached = cache.get('shipping_rate_tables')
    if cached is not None:
        return cached

    from apps.shipping.utils.japan_shipping import (
        TransportMode, ServiceClass, FbTier,
        KSE_RATE_TABLES, CJL_RATE_TABLE, FB_RATE_TABLES, EMS_RATE_TABLE,
    )

    tables = list(
        ShippingRateTable.objects.filter(is_active=True).prefetch_related('entries')
    )
    if not tables:
        return None

    kse_key_map = {
        'KSE_SEA_STANDARD':  (TransportMode.SEA,  ServiceClass.STANDARD),
        'KSE_SEA_LIGHT':     (TransportMode.SEA,  ServiceClass.LIGHT),
        'KSE_AIR_STANDARD':  (TransportMode.AIR,  ServiceClass.STANDARD),
        'KSE_AIR_LIGHT':     (TransportMode.AIR,  ServiceClass.LIGHT),
        'KSE_SDEX_STANDARD': (TransportMode.SDEX, ServiceClass.STANDARD),
        'KSE_SDEX_LIGHT':    (TransportMode.SDEX, ServiceClass.LIGHT),
    }
    fb_key_map = {
        'FB_AIR_STANDARD': FbTier.STANDARD,
        'FB_AIR_VIP':      FbTier.VIP,
        'FB_AIR_SVIP':     FbTier.SVIP,
        'FB_AIR_SSVIP':    FbTier.SSVIP,
    }

    kse_override = dict(KSE_RATE_TABLES)
    cjl_override = dict(CJL_RATE_TABLE)
    fb_override  = dict(FB_RATE_TABLES)
    ems_override = dict(EMS_RATE_TABLE)

    for t in tables:
        rate_dict = t.to_dict()
        if t.table_key in kse_key_map:
            kse_override[kse_key_map[t.table_key]] = rate_dict
        elif t.table_key == 'CJL_DOOR_TO_DOOR':
            cjl_override = rate_dict
        elif t.table_key in fb_key_map:
            fb_override[fb_key_map[t.table_key]] = rate_dict
        elif t.table_key == 'EMS_JP_STANDARD':
            ems_override = rate_dict

    result = {
        'kse_rate_tables': kse_override,
        'cjl_rate_table':  cjl_override,
        'fb_rate_tables':  fb_override,
        'ems_rate_table':  ems_override,
    }
    cache.set('shipping_rate_tables', result, timeout=300)
    return result
