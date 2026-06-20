from django.db import models


class SiteTemplate(models.Model):
    """
    고객사 DB에 저장되는 실제 Python 스크레이퍼 템플릿.
    scraper-agent 파일시스템 대신 여기가 진실의 원천.
    """
    domain = models.CharField(max_length=255, unique=True, db_index=True)
    filename = models.CharField(max_length=255, blank=True, default='')
    code = models.TextField()
    page_type = models.CharField(max_length=20, default='both')
    category = models.CharField(max_length=20, default='shopping', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.domain} ({self.page_type})"


class TemplateBuildLog(models.Model):
    """
    scraper-agent에 템플릿 빌드를 요청한 이력만 로컬에 저장.
    실제 템플릿 파일은 scraper-agent가 관리.
    """
    url = models.URLField(max_length=2048)
    domain = models.CharField(max_length=255, blank=True, default='', db_index=True)
    category = models.CharField(max_length=20, blank=True, default='shopping', db_index=True)
    filename = models.CharField(max_length=255, blank=True, default='')
    # 병합된 경우 기존 템플릿 파일명들 (콤마 구분)
    merged_from = models.TextField(blank=True, default='')
    success = models.BooleanField(default=False)
    error_message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{'OK' if self.success else 'FAIL'} | {self.url}"
