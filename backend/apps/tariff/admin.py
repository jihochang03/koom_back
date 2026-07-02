from django.contrib import admin
from .models import TariffLookupLog, ProductHsClassification


@admin.register(TariffLookupLog)
class TariffLookupLogAdmin(admin.ModelAdmin):
    list_display = ['id', 'product_title', 'rate', 'duty_type', 'matched_item', 'created_at']
    search_fields = ['product_title', 'matched_item']
    readonly_fields = ['created_at']


@admin.register(ProductHsClassification)
class ProductHsClassificationAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'product', 'status', 'final_hs_code', 'final_category',
        'decision_source', 'inspector', 'updated_at',
    ]
    list_filter = ['status', 'decision_source']
    search_fields = ['final_hs_code', 'final_category', 'product__title', 'inspector']
    readonly_fields = ['ai_suggested', 'ai_alternatives', 'ai_search_expansion', 'created_at', 'updated_at']
    list_editable = ['status', 'final_hs_code']
