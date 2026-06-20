from rest_framework import serializers
from .models import Order, OrderGroup


class OrderSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'group', 'customer_id',
            'site_domain', 'product_url', 'title', 'options', 'quantity',
            'price_product', 'price_domestic_shipping', 'price_intl_shipping',
            'price_tariff', 'price_fee', 'price_total', 'currency',
            'price_dk_burden', 'price_actual',
            'status', 'status_display',
            'tracking_number', 'estimated_delivery_min', 'estimated_delivery_max',
            'product_snapshot', 'product_copy_url', 'admin_notes', 'inspection_notes',
            'refund_amount', 'refund_reason',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'order_number', 'created_at', 'updated_at', 'status_display']


class OrderGroupSerializer(serializers.ModelSerializer):
    orders = OrderSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    order_count = serializers.IntegerField(source='orders.count', read_only=True)

    class Meta:
        model = OrderGroup
        fields = [
            'id', 'group_number', 'customer_id', 'status', 'status_display',
            'bundle_fee', 'coupon_discount', 'point_discount', 'total_paid',
            'currency', 'paid_at', 'order_count', 'orders',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'group_number', 'created_at', 'updated_at', 'status_display']


class OrderGroupSummarySerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    order_count = serializers.IntegerField(source='orders.count', read_only=True)

    class Meta:
        model = OrderGroup
        fields = [
            'id', 'group_number', 'customer_id', 'status', 'status_display',
            'bundle_fee', 'total_paid', 'currency',
            'order_count', 'paid_at', 'created_at', 'updated_at',
        ]


class OrderCreateItemSerializer(serializers.Serializer):
    product_url   = serializers.URLField()
    title         = serializers.CharField(max_length=1024)
    options       = serializers.ListField(child=serializers.DictField(), default=list)
    quantity      = serializers.IntegerField(min_value=1, default=1)
    price_product           = serializers.FloatField()
    price_domestic_shipping = serializers.FloatField(default=0)
    price_intl_shipping     = serializers.FloatField(default=0)
    price_tariff            = serializers.FloatField(default=0)
    price_fee               = serializers.FloatField(default=0)
    price_total             = serializers.FloatField()
    currency                = serializers.CharField(max_length=10, default='KRW')
    site_domain             = serializers.CharField(max_length=255, default='', allow_blank=True)
    product_snapshot        = serializers.DictField(default=dict)
    estimated_delivery_min  = serializers.IntegerField(required=False, allow_null=True)
    estimated_delivery_max  = serializers.IntegerField(required=False, allow_null=True)


class OrderGroupCreateSerializer(serializers.Serializer):
    customer_id     = serializers.CharField(max_length=255)
    items           = OrderCreateItemSerializer(many=True)
    bundle_fee      = serializers.FloatField(default=0)
    coupon_discount = serializers.FloatField(default=0)
    point_discount  = serializers.FloatField(default=0)


class OrderStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=[c[0] for c in [
        ('pending',''), ('paid',''), ('purchasing',''), ('shipping_domestic',''),
        ('inspection',''), ('shipping_intl',''), ('delivered',''),
        ('cancelled',''), ('refunded',''), ('partial_refund',''),
    ]])
    tracking_number        = serializers.CharField(required=False, allow_blank=True)
    estimated_delivery_min = serializers.IntegerField(required=False, allow_null=True)
    estimated_delivery_max = serializers.IntegerField(required=False, allow_null=True)


class OrderAdminUpdateSerializer(serializers.Serializer):
    price_dk_burden  = serializers.FloatField(required=False)
    price_actual     = serializers.FloatField(required=False, allow_null=True)
    admin_notes      = serializers.CharField(required=False, allow_blank=True)
    inspection_notes = serializers.CharField(required=False, allow_blank=True)
    refund_amount    = serializers.FloatField(required=False, allow_null=True)
    refund_reason    = serializers.CharField(required=False, allow_blank=True)
