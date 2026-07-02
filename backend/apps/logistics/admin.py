from django.contrib import admin
from .models import LogisticsInfo, ShippingTracking, TrackingEvent, CustomsClearance, DeliveryFailure


@admin.register(DeliveryFailure)
class DeliveryFailureAdmin(admin.ModelAdmin):
    list_display   = ('order_number', 'failure_reason', 'responsible', 'status',
                      'item_value', 'storage_deadline', 'customer_responded_at', 'resolved_at')
    list_filter    = ('status', 'failure_reason', 'responsible')
    search_fields  = ('order_number', 'memo')
    readonly_fields = ('order_number', 'item_value', 'notified_at', 'storage_deadline',
                       'resolved_at', 'created_at', 'updated_at')
    fields = ('order_number', 'failure_reason', 'responsible', 'cost_burden', 'status',
              'item_value', 'notified_at', 'storage_deadline', 'customer_responded_at',
              'disposition', 'resolved_at', 'memo', 'created_at', 'updated_at')
    ordering       = ('-created_at',)


@admin.register(CustomsClearance)
class CustomsClearanceAdmin(admin.ModelAdmin):
    list_display   = ('order_number', 'customs_type', 'result', 'response_deadline',
                      'customer_responded_at', 'refund_processed_at', 'refund_amount')
    list_filter    = ('result', 'customs_type')
    search_fields  = ('order_number', 'reject_reason')
    readonly_fields = ('order_number', 'notified_at', 'response_deadline',
                       'refund_processed_at', 'refund_amount', 'created_at', 'updated_at')
    fields = ('order_number', 'customs_type', 'result', 'reject_reason',
              'partial_refund_amount', 'notified_at', 'response_deadline',
              'customer_responded_at', 'refund_processed_at', 'refund_amount',
              'created_at', 'updated_at')
    ordering       = ('-created_at',)


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
    readonly_fields = ('order_number', 'fb_invoice_no', 'dhub_ord_bundle_no', 'dhub_instruction_no',
                       'dhub_delivery_type', 'carrier_status', 'events',
                       'last_api_checked_at', 'last_status_changed_at', 'next_check_at',
                       'stagnation_detected_at', 'created_at', 'updated_at')
    fields = ('order_number', 'fb_invoice_no', 'tracking_number', 'carrier',
              'current_stage', 'delivered_at', 'delivery_region',
              'customer_status', 'carrier_status',
              'dhub_ord_bundle_no', 'dhub_instruction_no', 'dhub_delivery_type',
              'delay_detected', 'delay_type', 'delay_hours', 'stagnation_detected_at',
              'is_untrackable_segment', 'last_status_changed_at', 'last_api_checked_at',
              'next_check_at', 'events', 'created_at', 'updated_at')
    list_filter    = ('current_stage', 'delay_detected', 'delay_type', 'dhub_delivery_type')
    ordering       = ('-created_at',)


@admin.register(TrackingEvent)
class TrackingEventAdmin(admin.ModelAdmin):
    list_display   = ('order_number', 'occurred_at', 'stage', 'description', 'location', 'source')
    list_filter    = ('stage', 'source')
    search_fields  = ('order_number', 'description', 'location')
    readonly_fields = ('created_at',)
    ordering       = ('-occurred_at',)
    date_hierarchy = 'occurred_at'
