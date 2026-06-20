from rest_framework import serializers
from .models import ShippingQuoteLog


class ShippingQuoteLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShippingQuoteLog
        fields = ['id', 'service_provider', 'transport_mode', 'actual_weight_kg', 'result', 'is_available', 'created_at']
