from django.contrib import admin
from .models import WishlistItem


@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display   = ('customer_id', 'title', 'site_domain', 'price_snapshot', 'currency', 'created_at')
    search_fields  = ('customer_id', 'title', 'site_domain', 'product_url')
    list_filter    = ('site_domain', 'currency')
    readonly_fields = ('customer_id', 'product_url', 'site_domain', 'title', 'images',
                       'price_snapshot', 'currency', 'options', 'created_at')
    ordering       = ('-created_at',)
