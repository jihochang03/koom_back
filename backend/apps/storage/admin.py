from django.contrib import admin
from .models import UploadedFile


@admin.register(UploadedFile)
class UploadedFileAdmin(admin.ModelAdmin):
    list_display   = ('original_name', 'purpose', 'order_number', 'customer_id',
                       'content_type', 'size_bytes', 'created_at')
    search_fields  = ('order_number', 'customer_id', 'original_name', 's3_key')
    list_filter    = ('purpose', 'content_type')
    readonly_fields = ('order_number', 'customer_id', 'purpose', 'original_name',
                       's3_key', 'public_url', 'content_type', 'size_bytes', 'created_at')
    ordering       = ('-created_at',)
