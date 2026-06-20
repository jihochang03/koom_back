from django.contrib import admin
from .models import NotificationLog


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display   = ('customer_id', 'channel', 'event', 'send_status', 'order_number',
                       'recipient', 'sent_at', 'created_at')
    search_fields  = ('customer_id', 'order_number', 'recipient', 'subject')
    list_filter    = ('channel', 'event', 'send_status')
    readonly_fields = ('customer_id', 'channel', 'event', 'recipient', 'order_number',
                       'subject', 'body', 'send_status', 'error_detail', 'sent_at', 'created_at')
    ordering       = ('-created_at',)
