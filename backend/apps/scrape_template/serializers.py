from rest_framework import serializers
from .models import SiteTemplate, TemplateBuildLog


class SiteTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteTemplate
        fields = [
            'id', 'domain', 'filename', 'code',
            'page_type', 'category',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class TemplateSerializer(serializers.Serializer):
    """scraper-agent에서 반환하는 템플릿 데이터"""
    filename = serializers.CharField()
    domain = serializers.CharField(required=False, allow_blank=True)
    type = serializers.CharField(required=False, allow_blank=True)
    content = serializers.JSONField(required=False, allow_null=True)


class TemplateBuildLogSerializer(serializers.ModelSerializer):
    merged_from_list = serializers.SerializerMethodField()

    class Meta:
        model = TemplateBuildLog
        fields = [
            'id', 'url', 'domain', 'category', 'filename',
            'merged_from', 'merged_from_list',
            'success', 'error_message', 'created_at',
        ]

    def get_merged_from_list(self, obj) -> list:
        if not obj.merged_from:
            return []
        return [f.strip() for f in obj.merged_from.split(',') if f.strip()]
