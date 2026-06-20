from django.contrib import admin
from .models import TariffLookupLog


@admin.register(TariffLookupLog)
class TariffLookupLogAdmin(admin.ModelAdmin):
    list_display = ['id', 'product_title', 'rate', 'duty_type', 'matched_item', 'created_at']
    search_fields = ['product_title', 'matched_item']
    readonly_fields = ['created_at']
