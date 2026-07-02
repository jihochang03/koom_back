from rest_framework import serializers
from .models import TariffLookupLog, ProductHsClassification


class TariffLookupLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = TariffLookupLog
        fields = ['id', 'product_title', 'result', 'rate', 'duty_type', 'matched_item', 'created_at']


class TariffCandidateSerializer(serializers.Serializer):
    """검수자 화면용 후보(추천/대안) 요약."""
    hs_code = serializers.IntegerField(source='순번', allow_null=True)
    matched_item = serializers.CharField(allow_null=True)
    full_path = serializers.CharField(allow_null=True, required=False)
    depth_path = serializers.ListField(child=serializers.CharField(), required=False)
    rate = serializers.FloatField(allow_null=True)
    rate_source = serializers.CharField(allow_null=True, required=False)
    duty_type = serializers.CharField(allow_null=True, required=False)
    specific_yen_per_unit = serializers.FloatField(allow_null=True, required=False)
    specific_unit = serializers.CharField(allow_null=True, required=False)
    reason = serializers.CharField(required=False)
    rank = serializers.IntegerField(required=False)


class TariffClassifyResultSerializer(serializers.Serializer):
    """classify_tariff() 반환 구조."""
    product_title = serializers.CharField()
    non_physical = serializers.BooleanField(default=False)
    search_expansion = serializers.CharField(allow_null=True, required=False)
    candidates_found = serializers.IntegerField()
    selected = TariffCandidateSerializer(allow_null=True)
    alternatives = TariffCandidateSerializer(many=True)


class ProductHsClassificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductHsClassification
        fields = [
            'id', 'product', 'ai_suggested', 'ai_alternatives', 'ai_search_expansion',
            'final_hs_code', 'final_category', 'final_full_path',
            'status', 'decision_source', 'inspector', 'inspector_note',
            'created_at', 'confirmed_at', 'updated_at',
        ]


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
