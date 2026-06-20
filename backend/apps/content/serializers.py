from rest_framework import serializers
from .models import FAQ, Notice, EventBanner, Policy


class FAQSerializer(serializers.ModelSerializer):
    class Meta:
        model = FAQ
        fields = ['id', 'category', 'question', 'answer', 'sort_order', 'is_active', 'created_at', 'updated_at']


class NoticeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notice
        fields = ['id', 'title', 'content', 'is_pinned', 'is_active', 'published_at', 'created_at', 'updated_at']


class EventBannerSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventBanner
        fields = ['id', 'title', 'image_url', 'link_url', 'sort_order', 'is_active', 'starts_at', 'ends_at', 'created_at']


class PolicySerializer(serializers.ModelSerializer):
    policy_type_display = serializers.CharField(source='get_policy_type_display', read_only=True)

    class Meta:
        model = Policy
        fields = ['id', 'policy_type', 'policy_type_display', 'title', 'content',
                  'version', 'effective_date', 'is_current', 'created_at', 'updated_at']
