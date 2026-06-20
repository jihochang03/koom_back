from django.contrib import admin
from .models import KoreanMall, MallCrawlJob, FeaturedCategory


@admin.register(KoreanMall)
class KoreanMallAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'domain', 'is_active', 'display_order']
    list_editable = ['is_active', 'display_order']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(MallCrawlJob)
class MallCrawlJobAdmin(admin.ModelAdmin):
    list_display = ['mall', 'category_name', 'status', 'products_count', 'last_crawled_at']
    list_filter = ['mall', 'status']
    readonly_fields = ['status', 'products_count', 'error_message', 'last_crawled_at', 'created_at', 'updated_at']


@admin.register(FeaturedCategory)
class FeaturedCategoryAdmin(admin.ModelAdmin):
    list_display = ['mall', 'category_name', 'display_title', 'display_order', 'is_active']
    list_editable = ['display_order', 'is_active']
    list_filter = ['mall', 'is_active']
