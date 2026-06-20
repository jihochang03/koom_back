from rest_framework import serializers
from .models import ScrapeRequest, ScrapeResult, UrlVisit


class ScrapeResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScrapeResult
        fields = ['id', 'raw_data', 'template_used', 'items_count', 'created_at']


class ScrapeRequestSerializer(serializers.ModelSerializer):
    result = ScrapeResultSerializer(read_only=True)

    class Meta:
        model = ScrapeRequest
        fields = [
            'id', 'url', 'domain', 'category', 'page_type',
            'status', 'error_message',
            'result', 'created_at', 'updated_at',
        ]


class UrlVisitSerializer(serializers.ModelSerializer):
    class Meta:
        model = UrlVisit
        fields = ['id', 'url', 'title', 'visited_at']


class PopularUrlSerializer(serializers.Serializer):
    url = serializers.URLField()
    visit_count = serializers.IntegerField()
