from django.contrib import admin
from .models import LogisticsInfo, ShippingTracking


@admin.register(LogisticsInfo)
class LogisticsInfoAdmin(admin.ModelAdmin):
    list_display   = ('order_number', 'inspection_result', 'arrived_at', 'expected_arrival',
                       'components_match', 'has_defect')
    list_editable  = ('inspection_result',)
    search_fields  = ('order_number',)
    list_filter    = ('inspection_result', 'components_match', 'has_defect')
    readonly_fields = ('order_number', 'created_at', 'updated_at')
    ordering       = ('-created_at',)


@admin.register(ShippingTracking)
class ShippingTrackingAdmin(admin.ModelAdmin):
    list_display   = ('order_number', 'fb_invoice_no', 'tracking_number', 'carrier',
                       'customer_status', 'delay_detected', 'last_api_checked_at')
    search_fields  = ('order_number', 'fb_invoice_no', 'tracking_number')
    list_filter    = ('delay_detected', 'delay_type', 'dhub_delivery_type')
    readonly_fields = ('order_number', 'fb_invoice_no', 'dhub_ord_bundle_no', 'dhub_instruction_no',
                       'dhub_delivery_type', 'carrier_status', 'events',
                       'last_api_checked_at', 'last_status_changed_at', 'next_check_at',
                       'stagnation_detected_at', 'created_at', 'updated_at')
    fields = ('order_number', 'fb_invoice_no', 'tracking_number', 'carrier',
              'customer_status', 'carrier_status',
              'dhub_ord_bundle_no', 'dhub_instruction_no', 'dhub_delivery_type',
              'delay_detected', 'delay_type', 'delay_hours', 'stagnation_detected_at',
              'is_untrackable_segment', 'last_status_changed_at', 'last_api_checked_at',
              'next_check_at', 'events', 'created_at', 'updated_at')
    ordering       = ('-created_at',)
