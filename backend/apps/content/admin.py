from django.contrib import admin
from .models import FAQ, Notice, EventBanner, Policy


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display   = ('category', 'question', 'sort_order', 'is_active', 'created_at')
    list_editable  = ('sort_order', 'is_active')
    search_fields  = ('category', 'question', 'answer')
    list_filter    = ('category', 'is_active')
    ordering       = ('category', 'sort_order')


@admin.register(Notice)
class NoticeAdmin(admin.ModelAdmin):
    list_display   = ('title', 'is_pinned', 'is_active', 'published_at', 'created_at')
    list_editable  = ('is_pinned', 'is_active')
    search_fields  = ('title', 'content')
    list_filter    = ('is_pinned', 'is_active')
    ordering       = ('-is_pinned', '-published_at')


@admin.register(EventBanner)
class EventBannerAdmin(admin.ModelAdmin):
    list_display   = ('title', 'sort_order', 'is_active', 'starts_at', 'ends_at')
    list_editable  = ('sort_order', 'is_active')
    search_fields  = ('title',)
    list_filter    = ('is_active',)
    ordering       = ('sort_order',)


@admin.register(Policy)
class PolicyAdmin(admin.ModelAdmin):
    list_display   = ('policy_type', 'title', 'version', 'effective_date', 'is_current')
    list_editable  = ('is_current',)
    search_fields  = ('title', 'content')
    list_filter    = ('policy_type', 'is_current')
    readonly_fields = ('created_at', 'updated_at')
    ordering       = ('policy_type', '-effective_date')
