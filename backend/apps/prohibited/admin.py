from django.contrib import admin
from .models import ProhibitedKeyword


@admin.register(ProhibitedKeyword)
class ProhibitedKeywordAdmin(admin.ModelAdmin):
    list_display   = ('keyword', 'category', 'risk_level', 'is_active', 'customs_reference')
    list_editable  = ('is_active', 'risk_level')
    search_fields  = ('keyword', 'category', 'description')
    list_filter    = ('risk_level', 'is_active', 'category')
    readonly_fields = ('created_at', 'updated_at')
    ordering       = ('risk_level', 'category', 'keyword')
