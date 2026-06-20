from django.db import models


class TranslationCache(models.Model):
    source_lang = models.CharField(max_length=10, default='KO')
    target_lang = models.CharField(max_length=10, default='JA')
    source_text = models.TextField()
    translated_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['source_lang', 'target_lang', 'source_text']),
        ]
        # source_text는 너무 길어서 unique_together 불가 → 앱 레벨에서 처리
