from rest_framework import serializers
from .models import Inquiry, CancelRequest, RefundRequest


class InquirySerializer(serializers.ModelSerializer):
    status_display       = serializers.CharField(source='get_status_display', read_only=True)
    inquiry_type_display = serializers.CharField(source='get_inquiry_type_display', read_only=True)

    class Meta:
        model = Inquiry
        fields = [
            'id', 'customer_id', 'order_number', 'inquiry_type', 'inquiry_type_display',
            'title', 'content', 'images', 'status', 'status_display',
            'admin_reply', 'replied_at', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'status', 'admin_reply', 'replied_at', 'created_at', 'updated_at',
                            'status_display', 'inquiry_type_display']


class InquiryCreateSerializer(serializers.Serializer):
    customer_id  = serializers.CharField(max_length=255)
    order_number = serializers.CharField(max_length=50, required=False, allow_blank=True, default='')
    inquiry_type = serializers.ChoiceField(choices=[c[0] for c in [
        ('general',''),('cancel',''),('refund',''),('exchange',''),('return',''),
        ('shipping',''),('shipping_delay',''),('price_error',''),('inspection_issue',''),('other','')
    ]], default='general')
    title   = serializers.CharField(max_length=255)
    content = serializers.CharField()
    images  = serializers.JSONField(required=False, allow_null=True, default=None)


class InquiryReplySerializer(serializers.Serializer):
    admin_reply = serializers.CharField()
    status      = serializers.ChoiceField(choices=['open', 'in_progress', 'resolved', 'closed'])


class CancelRequestSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = CancelRequest
        fields = [
            'id', 'order_number', 'customer_id', 'reason',
            'status', 'status_display', 'shipping_fee_burden',
            'admin_notes', 'processed_at', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'status', 'shipping_fee_burden', 'admin_notes',
                            'processed_at', 'created_at', 'updated_at', 'status_display']


class CancelRequestCreateSerializer(serializers.Serializer):
    customer_id  = serializers.CharField(max_length=255)
    order_number = serializers.CharField(max_length=50)
    reason       = serializers.CharField()


class CancelRequestAdminSerializer(serializers.Serializer):
    status              = serializers.ChoiceField(choices=['pending', 'approved', 'rejected', 'completed'])
    shipping_fee_burden = serializers.BooleanField(required=False)
    admin_notes         = serializers.CharField(required=False, allow_blank=True)


class RefundRequestSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = RefundRequest
        fields = [
            'id', 'order_number', 'customer_id', 'reason',
            'requested_amount', 'approved_amount',
            'status', 'status_display', 'admin_notes',
            'processed_at', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'status', 'approved_amount', 'admin_notes',
                            'processed_at', 'created_at', 'updated_at', 'status_display']


class RefundRequestCreateSerializer(serializers.Serializer):
    customer_id      = serializers.CharField(max_length=255)
    order_number     = serializers.CharField(max_length=50)
    reason           = serializers.CharField()
    requested_amount = serializers.FloatField(min_value=0)


class RefundRequestAdminSerializer(serializers.Serializer):
    status          = serializers.ChoiceField(choices=['pending', 'approved', 'partial_approved', 'rejected', 'completed'])
    approved_amount = serializers.FloatField(required=False, allow_null=True)
    admin_notes     = serializers.CharField(required=False, allow_blank=True)


# ── 대리구매 작업 (FR-ORD-07) ──────────────────────────────────────────────────

class PurchaseCompleteSerializer(serializers.Serializer):
    """CS가 대리구매 완료 후 입력하는 구매 내역."""
    purchase_account      = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    collection_address    = serializers.CharField(required=False, allow_blank=True, default='')
    actual_price          = serializers.FloatField(min_value=0)
    domestic_shipping_fee = serializers.FloatField(min_value=0, required=False, default=0)
    currency              = serializers.CharField(max_length=10, required=False, default='KRW')
    cs_user               = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    memo                  = serializers.CharField(required=False, allow_blank=True, default='')
    purchased_at          = serializers.DateTimeField(required=False, allow_null=True)
