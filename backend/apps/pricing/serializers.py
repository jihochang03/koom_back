from rest_framework import serializers
from .models import ExchangeRateLog, PricingQuoteLog


class ExchangeRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExchangeRateLog
        fields = ['id', 'base_currency', 'target_currency', 'rate', 'source', 'fetched_at']


class PricingQuoteLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = PricingQuoteLog
        fields = ['id', 'original_price', 'discounted_price', 'currency', 'krw_per_jpy_market', 'result', 'created_at']
