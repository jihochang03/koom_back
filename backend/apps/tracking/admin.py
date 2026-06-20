from django.contrib import admin
from .models import TrackingCache


@admin.register(TrackingCache)
class TrackingCacheAdmin(admin.ModelAdmin):
    list_display   = ('carrier_code', 'tracking_number', 'region', 'fetched_at')
    search_fields  = ('carrier_code', 'tracking_number')
    list_filter    = ('carrier_code', 'region')
    readonly_fields = ('carrier_code', 'tracking_number', 'region', 'result', 'fetched_at')
    ordering       = ('-fetched_at',)
