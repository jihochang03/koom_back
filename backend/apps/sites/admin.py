from django.contrib import admin
from .models import SupportedSite


@admin.register(SupportedSite)
class SupportedSiteAdmin(admin.ModelAdmin):
    list_display   = ('name', 'domain', 'sort_order', 'is_active', 'created_at')
    list_editable  = ('sort_order', 'is_active')
    search_fields  = ('name', 'domain')
    list_filter    = ('is_active',)
    readonly_fields = ('created_at', 'updated_at')
    ordering       = ('sort_order', 'name')
