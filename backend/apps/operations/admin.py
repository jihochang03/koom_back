from django.contrib import admin
from .models import ErrorCriteria, ErrorCriteriaLog


class ErrorCriteriaLogInline(admin.TabularInline):
    model       = ErrorCriteriaLog
    extra       = 0
    readonly_fields = ('changed_field', 'old_value', 'new_value', 'changed_by', 'changed_at')
    can_delete  = False


@admin.register(ErrorCriteria)
class ErrorCriteriaAdmin(admin.ModelAdmin):
    list_display       = ('small_error_threshold_pct', 'small_error_threshold_abs',
                         'handling_ai_error', 'handling_price_change', 'is_current', 'created_at')
    list_display_links = ('small_error_threshold_pct',)
    list_editable      = ('is_current',)
    list_filter        = ('is_current',)
    readonly_fields = ('created_at', 'updated_at')
    inlines        = [ErrorCriteriaLogInline]
    ordering       = ('-created_at',)


@admin.register(ErrorCriteriaLog)
class ErrorCriteriaLogAdmin(admin.ModelAdmin):
    list_display   = ('criteria', 'changed_field', 'old_value', 'new_value', 'changed_by', 'changed_at')
    search_fields  = ('changed_field', 'changed_by')
    readonly_fields = ('criteria', 'changed_field', 'old_value', 'new_value', 'changed_by', 'changed_at')
    ordering       = ('-changed_at',)
