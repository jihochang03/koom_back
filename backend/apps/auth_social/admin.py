from django.contrib import admin
from .models import SocialAccount


@admin.register(SocialAccount)
class SocialAccountAdmin(admin.ModelAdmin):
    list_display   = ('customer_id', 'provider', 'provider_uid', 'display_name', 'created_at')
    search_fields  = ('customer_id', 'provider_uid', 'display_name')
    list_filter    = ('provider',)
    readonly_fields = ('customer_id', 'provider', 'provider_uid', 'access_token', 'created_at', 'updated_at')
    ordering       = ('-created_at',)
