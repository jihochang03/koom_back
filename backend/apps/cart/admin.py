from django.contrib import admin
from .models import Cart, CartItem


class CartItemInline(admin.TabularInline):
    model  = CartItem
    extra  = 0
    readonly_fields = ('product', 'product_url', 'title', 'brand', 'options',
                       'price_final', 'currency', 'created_at', 'updated_at')
    fields = ('title', 'brand', 'quantity', 'price_final', 'currency',
              'options', 'product_url', 'created_at')


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display   = ('customer_id', 'created_at', 'updated_at')
    search_fields  = ('customer_id',)
    readonly_fields = ('customer_id', 'created_at', 'updated_at')
    inlines        = [CartItemInline]
    ordering       = ('-updated_at',)


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display   = ('cart', 'title', 'brand', 'quantity', 'price_final', 'currency', 'created_at')
    search_fields  = ('cart__customer_id', 'title', 'brand')
    list_filter    = ('currency',)
    readonly_fields = ('cart', 'product', 'product_url', 'title', 'brand', 'options',
                       'price_final', 'currency', 'created_at', 'updated_at')
    ordering       = ('-created_at',)
