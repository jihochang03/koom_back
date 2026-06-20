from django.contrib import admin
from .models import ProductSnapshot, PurchaseRecord


@admin.register(PurchaseRecord)
class PurchaseRecordAdmin(admin.ModelAdmin):
    list_display  = ('order_number', 'cs_user', 'purchase_account', 'actual_price',
                     'domestic_shipping_fee', 'currency', 'purchased_at')
    search_fields = ('order_number', 'cs_user', 'purchase_account')
    list_filter   = ('currency', 'cs_user')
    ordering      = ('-created_at',)


@admin.register(ProductSnapshot)
class ProductSnapshotAdmin(admin.ModelAdmin):
    list_display  = ('order_number', 'product_name', 'product_name_en', 'quantity', 'purchase_price', 'created_at')
    list_editable = ('product_name_en',)
    search_fields = ('order_number', 'product_name', 'product_name_en', 'seller')
    list_filter   = ('site_domain',)
    readonly_fields = ('order_number', 'snapshot_uuid', 'product_name', 'purchase_price',
                       'product_price_at_purchase', 'options', 'quantity', 'seller',
                       'site_domain', 'product_url', 'images', 'html_content', 'created_at')
    fields = ('order_number', 'snapshot_uuid', 'product_name', 'product_name_en',
              'purchase_price', 'product_price_at_purchase', 'quantity',
              'options', 'seller', 'site_domain', 'product_url', 'images',
              'html_content', 'created_at')
    ordering = ('-created_at',)
