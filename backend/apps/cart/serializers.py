from rest_framework import serializers
from apps.products.serializers import ProductSerializer
from .models import Cart, CartItem


class CartItemSerializer(serializers.ModelSerializer):
    product_detail = ProductSerializer(source='product', read_only=True)

    class Meta:
        model = CartItem
        fields = [
            'id', 'product', 'product_detail', 'product_url',
            'title', 'brand', 'options', 'price_final', 'currency', 'quantity',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class CartItemWriteSerializer(serializers.Serializer):
    product_id = serializers.IntegerField(required=False, allow_null=True)
    product_url = serializers.URLField(required=False, allow_blank=True, default='')
    title = serializers.CharField(max_length=1024)
    brand = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    options = serializers.ListField(
        child=serializers.DictField(), required=False, default=list
    )
    price_final = serializers.FloatField()
    currency = serializers.CharField(max_length=10, default='KRW')
    quantity = serializers.IntegerField(min_value=1, default=1)


class CartItemUpdateSerializer(serializers.Serializer):
    options = serializers.ListField(
        child=serializers.DictField(), required=False
    )
    price_final = serializers.FloatField(required=False)
    quantity = serializers.IntegerField(min_value=1, required=False)


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total_price = serializers.SerializerMethodField()
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = [
            'id', 'customer_id', 'items',
            'item_count', 'total_price',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_total_price(self, obj) -> float:
        return sum(item.price_final * item.quantity for item in obj.items.all())

    def get_item_count(self, obj) -> int:
        return sum(item.quantity for item in obj.items.all())
