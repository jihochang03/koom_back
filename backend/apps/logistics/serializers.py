from rest_framework import serializers
from .models import LogisticsInfo, ShippingTracking


class LogisticsInfoSerializer(serializers.ModelSerializer):
    inspection_result_display = serializers.CharField(source='get_inspection_result_display', read_only=True)

    class Meta:
        model = LogisticsInfo
        fields = [
            'id', 'order_number', 'expected_arrival', 'arrived_at',
            'inspection_result', 'inspection_result_display',
            'inspection_photos', 'components_match', 'has_defect',
            'issue_reason', 'post_inspection_action', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'inspection_result_display']


class InspectionSerializer(serializers.Serializer):
    """검수 결과 등록 (FR-LOG-05, 화면 C-02)."""
    result                 = serializers.ChoiceField(choices=['pass', 'issue'])
    components_match       = serializers.BooleanField(required=False, allow_null=True)
    has_defect             = serializers.BooleanField(required=False, allow_null=True)
    issue_reason           = serializers.CharField(required=False, allow_blank=True, default='')
    post_inspection_action = serializers.CharField(required=False, allow_blank=True, default='')
    inspection_photos      = serializers.JSONField(required=False, allow_null=True)
    inspector              = serializers.CharField(required=False, allow_blank=True, default='')


class ShippingTrackingSerializer(serializers.ModelSerializer):
    delay_type_display = serializers.CharField(source='get_delay_type_display', read_only=True)

    class Meta:
        model = ShippingTracking
        fields = [
            'id', 'order_number', 'tracking_number', 'carrier',
            'carrier_status', 'customer_status',
            'last_status_changed_at', 'last_api_checked_at', 'next_check_at',
            'is_untrackable_segment', 'delay_detected', 'delay_type', 'delay_type_display',
            'delay_hours', 'stagnation_detected_at', 'events',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'delay_type_display']
