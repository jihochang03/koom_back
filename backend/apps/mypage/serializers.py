from rest_framework import serializers
from .models import UserAddress, Coupon, UserCoupon, PointLog, NotificationSetting


class UserAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserAddress
        fields = [
            'id', 'customer_id',
            'name', 'name_kana', 'name_en', 'date_of_birth',
            'phone', 'country', 'zipcode', 'address1', 'address2',
            'is_default', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'customer_id', 'created_at', 'updated_at']


class UserAddressWriteSerializer(serializers.Serializer):
    name           = serializers.CharField(max_length=100)
    name_kana      = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    name_en        = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    date_of_birth  = serializers.DateField(required=False, allow_null=True, default=None)
    phone          = serializers.CharField(max_length=20)
    country        = serializers.CharField(max_length=2, required=False, default='JP')
    zipcode        = serializers.CharField(max_length=10)
    address1       = serializers.CharField(max_length=500)
    address2       = serializers.CharField(max_length=500, required=False, allow_blank=True, default='')
    is_default     = serializers.BooleanField(default=False)


class CouponSerializer(serializers.ModelSerializer):
    discount_type_display = serializers.CharField(source='get_discount_type_display', read_only=True)

    class Meta:
        model = Coupon
        fields = ['id', 'code', 'name', 'discount_type', 'discount_type_display',
                  'discount_value', 'min_order_amount', 'max_discount_amount',
                  'valid_from', 'valid_until', 'is_active', 'usage_limit', 'created_at']


class UserCouponSerializer(serializers.ModelSerializer):
    coupon = CouponSerializer(read_only=True)
    is_used = serializers.SerializerMethodField()

    class Meta:
        model = UserCoupon
        fields = ['id', 'customer_id', 'coupon', 'order_number', 'used_at', 'issued_at', 'is_used']

    def get_is_used(self, obj):
        return obj.used_at is not None


class PointLogSerializer(serializers.ModelSerializer):
    reason_display = serializers.CharField(source='get_reason_display', read_only=True)

    class Meta:
        model = PointLog
        fields = ['id', 'customer_id', 'delta', 'reason', 'reason_display',
                  'order_number', 'balance_after', 'note', 'created_at']


class NotificationSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationSetting
        fields = ['customer_id', 'order_status_push', 'order_status_email',
                  'marketing_push', 'marketing_email', 'updated_at']
        read_only_fields = ['customer_id', 'updated_at']
