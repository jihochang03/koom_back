from django.contrib import admin
from .models import TranslationCache


@admin.register(TranslationCache)
class TranslationCacheAdmin(admin.ModelAdmin):
    list_display   = ('source_lang', 'target_lang', 'source_text', 'translated_text', 'created_at')
    search_fields  = ('source_text', 'translated_text')
    list_filter    = ('source_lang', 'target_lang')
    readonly_fields = ('source_lang', 'target_lang', 'source_text', 'translated_text', 'created_at')
    ordering       = ('-created_at',)
