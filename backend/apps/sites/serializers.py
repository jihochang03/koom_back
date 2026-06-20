from rest_framework import serializers
from .models import SupportedSite


class SupportedSiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportedSite
        fields = [
            'id', 'name', 'domain', 'icon_url',
            'is_active', 'sort_order',
            'product_url_patterns', 'search_url_patterns',
            'updated_at',
        ]
