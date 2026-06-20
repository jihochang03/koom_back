from django.contrib import admin
from .models import ScrapeRequest, ScrapeResult


class ScrapeResultInline(admin.StackedInline):
    model = ScrapeResult
    readonly_fields = ['raw_data', 'template_used', 'created_at']
    extra = 0


@admin.register(ScrapeRequest)
class ScrapeRequestAdmin(admin.ModelAdmin):
    list_display = ['id', 'url', 'status', 'created_at', 'updated_at']
    list_filter = ['status']
    search_fields = ['url']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [ScrapeResultInline]
