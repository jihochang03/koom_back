from rest_framework import serializers
from .models import TariffLookupLog


class TariffLookupLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = TariffLookupLog
        fields = ['id', 'product_title', 'result', 'rate', 'duty_type', 'matched_item', 'created_at']


class TariffResultSerializer(serializers.Serializer):
    rate = serializers.FloatField(allow_null=True)
    rate_source = serializers.CharField(allow_null=True)
    duty_type = serializers.CharField(allow_null=True)
    specific_yen_per_unit = serializers.FloatField(allow_null=True, required=False)
    specific_unit = serializers.CharField(allow_null=True, required=False)
    matched_item = serializers.CharField(allow_null=True)
    candidates_found = serializers.IntegerField()
    non_physical = serializers.BooleanField(default=False)
    search_expansion = serializers.CharField(allow_null=True, required=False)
    cached = serializers.BooleanField(default=False)
