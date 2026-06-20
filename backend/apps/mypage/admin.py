from django.contrib import admin
from .models import UserAddress, Coupon, UserCoupon, PointLog, NotificationSetting


@admin.register(UserAddress)
class UserAddressAdmin(admin.ModelAdmin):
    list_display   = ('customer_id', 'name', 'name_en', 'name_kana', 'country', 'zipcode', 'is_default')
    list_editable  = ('is_default',)
    search_fields  = ('customer_id', 'name', 'name_en', 'name_kana', 'zipcode', 'address1')
    list_filter    = ('country', 'is_default')
    readonly_fields = ('customer_id', 'created_at', 'updated_at')
    ordering       = ('customer_id', '-is_default')


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display   = ('code', 'name', 'discount_type', 'discount_value', 'is_active', 'valid_from', 'valid_until')
    list_editable  = ('is_active',)
    search_fields  = ('code', 'name')
    list_filter    = ('discount_type', 'is_active')
    readonly_fields = ('created_at',)
    ordering       = ('-created_at',)


@admin.register(UserCoupon)
class UserCouponAdmin(admin.ModelAdmin):
    list_display   = ('customer_id', 'coupon', 'order_number', 'used_at', 'issued_at')
    search_fields  = ('customer_id', 'order_number', 'coupon__code')
    list_filter    = ('coupon',)
    readonly_fields = ('customer_id', 'coupon', 'order_number', 'issued_at')
    ordering       = ('-issued_at',)


@admin.register(PointLog)
class PointLogAdmin(admin.ModelAdmin):
    list_display   = ('customer_id', 'delta', 'reason', 'balance_after', 'order_number', 'created_at')
    search_fields  = ('customer_id', 'order_number', 'note')
    list_filter    = ('reason',)
    readonly_fields = ('customer_id', 'delta', 'reason', 'balance_after', 'order_number', 'created_at')
    ordering       = ('-created_at',)


@admin.register(NotificationSetting)
class NotificationSettingAdmin(admin.ModelAdmin):
    list_display   = ('customer_id', 'order_status_push', 'order_status_email',
                       'marketing_push', 'marketing_email', 'updated_at')
    list_editable  = ('order_status_push', 'order_status_email', 'marketing_push', 'marketing_email')
    search_fields  = ('customer_id',)
    readonly_fields = ('updated_at',)
