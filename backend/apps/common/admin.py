from django.contrib import admin
from django.utils.html import format_html
from .models import SiteConfig, PaymentMethod, OrderNotice


@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    list_display = ['key', 'value', 'colored_value', 'group', 'description_short', 'updated_at']
    list_filter = ['group']
    search_fields = ['key', 'description']
    list_editable = ['value']
    ordering = ['group', 'key']
    readonly_fields = ['updated_at']

    fieldsets = [
        (None, {'fields': ['key', 'value', 'group', 'description', 'updated_at']}),
    ]

    def colored_value(self, obj):
        return format_html('<code style="background:#f4f4f4;padding:2px 6px;border-radius:3px">{}</code>', obj.value)
    colored_value.short_description = '값'

    def description_short(self, obj):
        return obj.description[:60] + '…' if len(obj.description) > 60 else obj.description
    description_short.short_description = '설명'


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'is_active', 'display_order']
    list_editable = ['is_active', 'display_order']


@admin.register(OrderNotice)
class OrderNoticeAdmin(admin.ModelAdmin):
    list_display = ['content_short', 'display_order', 'is_active']
    list_editable = ['display_order', 'is_active']

    def content_short(self, obj):
        return obj.content[:80] + '…' if len(obj.content) > 80 else obj.content
    content_short.short_description = '내용'
