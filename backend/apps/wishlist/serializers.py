from rest_framework import serializers
from .models import WishlistItem


class WishlistItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = WishlistItem
        fields = [
            'id', 'customer_id', 'product_url', 'site_domain',
            'title', 'images', 'price_snapshot', 'currency',
            'options', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class WishlistItemAddSerializer(serializers.Serializer):
    product_url    = serializers.URLField()
    title          = serializers.CharField(max_length=1024, required=False, allow_blank=True, default='')
    site_domain    = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    images         = serializers.ListField(child=serializers.URLField(), required=False, default=list)
    price_snapshot = serializers.FloatField(required=False, allow_null=True)
    currency       = serializers.CharField(max_length=10, required=False, default='KRW')
    options        = serializers.ListField(child=serializers.DictField(), required=False, default=list)
