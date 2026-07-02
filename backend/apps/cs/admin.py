from django.contrib import admin
from .models import Inquiry, CancelRequest, RefundRequest


@admin.register(Inquiry)
class InquiryAdmin(admin.ModelAdmin):
    list_display   = ('customer_id', 'inquiry_type', 'title', 'status', 'order_number', 'created_at')
    list_editable  = ('status',)
    search_fields  = ('customer_id', 'order_number', 'title', 'content')
    list_filter    = ('inquiry_type', 'status')
    readonly_fields = ('customer_id', 'order_number', 'inquiry_type', 'title', 'content',
                       'images', 'created_at', 'updated_at')
    fields = ('customer_id', 'order_number', 'inquiry_type', 'title', 'content',
              'images', 'status', 'admin_reply', 'replied_at', 'created_at', 'updated_at')
    ordering       = ('-created_at',)


@admin.register(CancelRequest)
class CancelRequestAdmin(admin.ModelAdmin):
    list_display   = ('order_number', 'customer_id', 'reason_type', 'status', 'shipping_fee_burden', 'created_at')
    list_editable  = ('status',)
    search_fields  = ('order_number', 'customer_id')
    list_filter    = ('status', 'reason_type', 'shipping_fee_burden')
    readonly_fields = ('order_number', 'customer_id', 'reason', 'reason_type', 'created_at', 'updated_at')
    fields = ('order_number', 'customer_id', 'reason_type', 'reason', 'status', 'shipping_fee_burden',
              'admin_notes', 'processed_at', 'created_at', 'updated_at')
    ordering       = ('-created_at',)


@admin.register(RefundRequest)
class RefundRequestAdmin(admin.ModelAdmin):
    list_display   = ('order_number', 'customer_id', 'reason_type', 'requested_amount', 'approved_amount', 'status', 'created_at')
    list_editable  = ('status', 'approved_amount')
    search_fields  = ('order_number', 'customer_id')
    list_filter    = ('status', 'reason_type')
    readonly_fields = ('order_number', 'customer_id', 'reason', 'reason_type', 'requested_amount', 'created_at', 'updated_at')
    fields = ('order_number', 'customer_id', 'reason_type', 'reason', 'requested_amount', 'approved_amount',
              'status', 'admin_notes', 'processed_at', 'created_at', 'updated_at')
    ordering       = ('-created_at',)
