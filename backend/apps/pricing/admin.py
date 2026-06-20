from django.contrib import admin
from .models import ExchangeRateLog, PricingQuoteLog


@admin.register(ExchangeRateLog)
class ExchangeRateLogAdmin(admin.ModelAdmin):
    list_display = ['id', 'base_currency', 'target_currency', 'rate', 'source', 'fetched_at']
    readonly_fields = ['fetched_at']


@admin.register(PricingQuoteLog)
class PricingQuoteLogAdmin(admin.ModelAdmin):
    list_display = ['id', 'currency', 'discounted_price', 'krw_per_jpy_market', 'created_at']
    readonly_fields = ['created_at']
