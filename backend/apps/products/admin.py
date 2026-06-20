from django.contrib import admin
from django.utils import timezone
from .models import Product, ProductArrivalPhoto, ArrivalStatus


class ProductArrivalPhotoInline(admin.TabularInline):
    model = ProductArrivalPhoto
    extra = 1
    fields = ['photo', 'note', 'captured_at']
    readonly_fields = ['captured_at']


def mark_arrived(modeladmin, request, queryset):
    queryset.filter(
        arrival_status__in=[ArrivalStatus.ORDERED, ArrivalStatus.IN_TRANSIT]
    ).update(arrival_status=ArrivalStatus.ARRIVED, arrived_at=timezone.now())
mark_arrived.short_description = '선택 상품 → 도착 처리'


def mark_inspected(modeladmin, request, queryset):
    queryset.update(arrival_status=ArrivalStatus.INSPECTED, inspected_at=timezone.now())
mark_inspected.short_description = '선택 상품 → 검수완료 처리'


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display   = (
        'title', 'brand', 'category',
        'arrival_status', 'inspection_required',
        'inbound_tracking_number',
        'is_prima', 'is_limited', 'is_recommended',
        'detail_status', 'updated_at',
    )
    list_editable  = ('is_prima', 'is_limited', 'is_recommended', 'arrival_status', 'inspection_required')
    list_display_links = ['title']
    search_fields  = ('title', 'brand', 'url', 'product_id',
                      'inbound_order_number', 'inbound_tracking_number')
    list_filter    = ('arrival_status', 'inspection_required',
                      'category', 'currency', 'is_prima', 'is_limited', 'is_recommended',
                      'detail_status', 'mall')
    readonly_fields = ('url', 'source_url', 'product_id', 'images', 'detail_data',
                       'detail_crawled_at', 'arrived_at', 'inspected_at',
                       'created_at', 'updated_at')
    actions        = [mark_arrived, mark_inspected]
    ordering       = ('-updated_at',)
    inlines        = [ProductArrivalPhotoInline]

    fieldsets = (
        ('기본 정보', {
            'fields': ('url', 'source_url', 'product_id', 'title', 'brand',
                       'category', 'mall', 'availability'),
        }),
        ('가격', {
            'fields': ('price_original', 'price_discounted', 'currency'),
        }),
        ('뱃지', {
            'fields': ('is_prima', 'is_limited', 'is_recommended'),
        }),
        ('입고 / 도착 상태', {
            'fields': (
                'inbound_order_number', 'inbound_tracking_number', 'inbound_courier',
                'arrival_status', 'inspection_required',
                'arrived_at', 'inspected_at', 'inbound_note',
            ),
            'description': '오더번호·송장번호 입력 후 저장. 사진은 아래 "도착 사진" 섹션에서 업로드.',
        }),
        ('크롤 상세', {
            'fields': ('detail_status', 'detail_crawled_at', 'detail_data', 'images'),
            'classes': ('collapse',),
        }),
        ('타임스탬프', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


@admin.register(ProductArrivalPhoto)
class ProductArrivalPhotoAdmin(admin.ModelAdmin):
    list_display   = ['product', 'photo', 'note', 'captured_at']
    list_filter    = ['captured_at']
    search_fields  = ['product__title', 'note']
    readonly_fields = ['captured_at']
    raw_id_fields  = ['product']
