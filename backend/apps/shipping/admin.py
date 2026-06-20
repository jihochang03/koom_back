from django.contrib import admin
from .models import (
    ShippingQuoteLog, ShippingRateTable, ShippingRateEntry,
    ShippingCarrierProfile, ShippingModeConfig, FuelSurcharge,
    CategoryWeightPreset,
)


class ShippingRateEntryInline(admin.TabularInline):
    model = ShippingRateEntry
    extra = 1
    fields = ['weight_break_kg', 'freight']
    ordering = ['weight_break_kg']


@admin.register(ShippingRateTable)
class ShippingRateTableAdmin(admin.ModelAdmin):
    list_display = ['table_key', 'currency', 'entry_count', 'is_active', 'updated_at']
    list_filter = ['is_active', 'currency']
    list_editable = ['is_active']
    readonly_fields = ['updated_at']
    inlines = [ShippingRateEntryInline]

    def entry_count(self, obj):
        return obj.entries.count()
    entry_count.short_description = '구간 수'


@admin.register(ShippingQuoteLog)
class ShippingQuoteLogAdmin(admin.ModelAdmin):
    list_display = ['id', 'service_provider', 'transport_mode', 'actual_weight_kg', 'is_available', 'created_at']
    list_filter = ['service_provider', 'transport_mode', 'is_available']
    readonly_fields = ['created_at']


@admin.register(ShippingCarrierProfile)
class ShippingCarrierProfileAdmin(admin.ModelAdmin):
    list_display       = ['name', 'engine', 'mode', 'fb_tier', 'fb_tax_mode',
                          'is_default', 'is_active', 'sort_order', 'updated_at']
    list_editable      = ['is_default', 'is_active', 'sort_order', 'fb_tier', 'fb_tax_mode']
    list_display_links = ['name']
    list_filter        = ['engine', 'mode', 'is_active']
    readonly_fields    = ['updated_at']
    fieldsets = (
        (None, {
            'fields': ('name', 'engine', 'mode', 'sort_order', 'is_active', 'is_default'),
            'description': '배송사명은 자유 입력 가능합니다. 엔진은 운임 계산 방식을 결정합니다.',
        }),
        ('커스텀 요율표 (엔진=TABLE 일 때)', {
            'fields': ('rate_table', 'currency'),
            'description': '엔진을 "커스텀 요율표"로 선택했을 때 연결할 요율표와 통화를 지정합니다.',
            'classes': ('collapse',),
        }),
        ('FastBox 전용 설정 (엔진=FB 일 때)', {
            'fields': ('fb_tier', 'fb_tax_mode'),
            'description': '엔진=FB 일 때만 사용됩니다. 유류할증료는 "월별 유류할증료" 메뉴에서 입력합니다.',
            'classes': ('collapse',),
        }),
        ('비고', {
            'fields': ('note', 'updated_at'),
        }),
    )


@admin.register(ShippingModeConfig)
class ShippingModeConfigAdmin(admin.ModelAdmin):
    list_display       = ['mode_selection', 'air_max_weight_kg', 'is_current', 'note', 'updated_at']
    list_editable      = ['is_current']
    list_display_links = ['mode_selection']
    readonly_fields    = ['updated_at']
    fieldsets = (
        (None, {
            'fields': ('mode_selection', 'air_max_weight_kg', 'is_current'),
            'description': (
                '현재 적용할 규칙 하나에만 "현재 적용"을 체크하세요. '
                'AUTO 선택 시: 항공 최대 무게(kg) 이하는 항공, 초과는 해운으로 자동 배정됩니다.'
            ),
        }),
        ('비고', {'fields': ('note', 'updated_at')}),
    )


@admin.register(FuelSurcharge)
class FuelSurchargeAdmin(admin.ModelAdmin):
    list_display       = ['carrier_name', 'year_month', 'amount', 'currency', 'note', 'created_at']
    list_editable      = ['amount', 'currency']
    list_display_links = ['carrier_name']
    list_filter        = ['currency', 'year_month']
    search_fields      = ['carrier_name', 'year_month']
    readonly_fields    = ['created_at']
    ordering           = ['-year_month', 'carrier_name']
    fieldsets = (
        (None, {
            'fields': ('carrier_name', 'year_month', 'amount', 'currency'),
            'description': (
                '배송사명은 배송사 프로필의 이름과 일치시켜야 자동 조회됩니다. '
                '적용 월은 YYYY-MM 형식으로 입력합니다 (예: 2025-06).'
            ),
        }),
        ('비고', {'fields': ('note', 'created_at')}),
    )


@admin.register(CategoryWeightPreset)
class CategoryWeightPresetAdmin(admin.ModelAdmin):
    list_display   = ['category_name', 'avg_weight_kg', 'updated_at']
    list_editable  = ['avg_weight_kg']
    search_fields  = ['category_name']
    readonly_fields = ['updated_at']
    ordering       = ['category_name']
