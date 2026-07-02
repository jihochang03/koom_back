from rest_framework import serializers
from .models import LogisticsInfo, ShippingTracking, TrackingEvent, CustomsClearance, DeliveryFailure


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


class CustomsClearanceSerializer(serializers.ModelSerializer):
    customs_type_display = serializers.CharField(source='get_customs_type_display', read_only=True)
    result_display       = serializers.CharField(source='get_result_display', read_only=True)

    class Meta:
        model = CustomsClearance
        fields = [
            'id', 'order_number', 'customs_type', 'customs_type_display',
            'result', 'result_display', 'reject_reason',
            'partial_refund_amount', 'notified_at', 'response_deadline',
            'customer_responded_at', 'refund_processed_at', 'refund_amount',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields


class CustomsResultSerializer(serializers.Serializer):
    """통관 결과 등록. result=rejected 시 고객 안내 발송 + 응답 기한 설정."""
    result        = serializers.ChoiceField(choices=['pending', 'cleared', 'rejected', 'returned'])
    customs_type  = serializers.ChoiceField(choices=['list', 'general'], required=False, allow_blank=True, default='')
    reject_reason = serializers.CharField(required=False, allow_blank=True, default='')
    operator      = serializers.CharField(required=False, allow_blank=True, default='')


class DeliveryFailureSerializer(serializers.ModelSerializer):
    failure_reason_display = serializers.CharField(source='get_failure_reason_display', read_only=True)
    status_display         = serializers.CharField(source='get_status_display', read_only=True)
    responsible_display    = serializers.CharField(source='get_responsible_display', read_only=True)

    class Meta:
        model = DeliveryFailure
        fields = [
            'id', 'order_number', 'failure_reason', 'failure_reason_display',
            'responsible', 'responsible_display', 'cost_burden',
            'status', 'status_display', 'item_value',
            'notified_at', 'storage_deadline', 'customer_responded_at',
            'disposition', 'resolved_at', 'memo', 'created_at', 'updated_at',
        ]
        read_only_fields = fields


class DeliveryFailureCreateSerializer(serializers.Serializer):
    """배송 실패 등록 → 보관 + 고객 안내 발송."""
    failure_reason = serializers.ChoiceField(
        choices=['address_error', 'absence', 'refusal', 'damaged', 'other'], default='address_error')
    responsible    = serializers.ChoiceField(choices=['customer', 'carrier', 'dk'], default='customer')
    cost_burden    = serializers.ChoiceField(choices=['customer', 'carrier', 'dk'], default='customer')
    memo           = serializers.CharField(required=False, allow_blank=True, default='')
    operator       = serializers.CharField(required=False, allow_blank=True, default='')


class DeliveryFailureRespondSerializer(serializers.Serializer):
    """고객 응답 — 재배송/반품 선택."""
    action = serializers.ChoiceField(choices=['reship', 'return'])


class DeliveryFailureResolveSerializer(serializers.Serializer):
    """미응답·기한경과 처분 실행. disposition 생략 시 가액 기준 자동 분기."""
    disposition = serializers.ChoiceField(choices=['dispose', 'return'], required=False, allow_blank=True, default='')
    hq_user     = serializers.CharField(required=False, allow_blank=True, default='')


class ShippingTrackingSerializer(serializers.ModelSerializer):
    delay_type_display = serializers.CharField(source='get_delay_type_display', read_only=True)
    current_stage_display = serializers.CharField(source='get_current_stage_display', read_only=True)

    class Meta:
        model = ShippingTracking
        fields = [
            'id', 'order_number', 'tracking_number', 'carrier',
            'carrier_status', 'customer_status',
            'current_stage', 'current_stage_display', 'delivered_at', 'delivery_region',
            'last_status_changed_at', 'last_api_checked_at', 'next_check_at',
            'is_untrackable_segment', 'delay_detected', 'delay_type', 'delay_type_display',
            'delay_hours', 'stagnation_detected_at', 'events',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'delay_type_display', 'current_stage_display']


class TrackingEventSerializer(serializers.ModelSerializer):
    stage_display = serializers.CharField(source='get_stage_display', read_only=True)
    source_display = serializers.CharField(source='get_source_display', read_only=True)

    class Meta:
        model = TrackingEvent
        fields = [
            'id', 'order_number', 'occurred_at', 'stage', 'stage_display',
            'description', 'location', 'source', 'source_display', 'raw_code', 'created_at',
        ]
        read_only_fields = ['id', 'created_at', 'stage_display', 'source_display']
