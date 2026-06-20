from rest_framework import serializers
from .models import ErrorCriteria, ErrorCriteriaLog


class ErrorCriteriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ErrorCriteria
        fields = [
            'id', 'small_error_threshold_pct', 'small_error_threshold_abs', 'small_error_per_item',
            'large_error_threshold_pct',
            'handling_ai_error', 'handling_price_change', 'handling_shipping_extra',
            'handling_tax', 'handling_prima_risk', 'handling_exchange_rate',
            'is_current', 'note', 'created_by', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'is_current', 'created_at', 'updated_at']


class ErrorCriteriaLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ErrorCriteriaLog
        fields = ['id', 'criteria', 'changed_field', 'old_value', 'new_value', 'changed_by', 'changed_at']
