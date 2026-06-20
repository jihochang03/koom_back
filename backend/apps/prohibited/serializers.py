from rest_framework import serializers
from .models import ProhibitedKeyword


class ProhibitedKeywordSerializer(serializers.ModelSerializer):
    risk_level_display = serializers.CharField(source='get_risk_level_display', read_only=True)

    class Meta:
        model = ProhibitedKeyword
        fields = ['id', 'keyword', 'category', 'risk_level', 'risk_level_display',
                  'description', 'customs_reference', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at', 'risk_level_display']
