from rest_framework import serializers


class ShippingQuoteRequestSerializer(serializers.Serializer):
    # 필수
    service_provider = serializers.ChoiceField(
        choices=[('KSE', 'KSE'), ('CJL', 'CJL'), ('FB', 'FastBox'), ('EMS', 'EMS')],
        help_text="배송 서비스 (KSE / CJL / FB / EMS)"
    )
    transport_mode = serializers.ChoiceField(
        choices=[('SEA', 'SEA'), ('AIR', 'AIR'), ('SDEX', 'SDEX'), ('DOOR_TO_DOOR', 'DOOR_TO_DOOR')],
        help_text="운송 수단 (KSE: SEA/AIR/SDEX | CJL: DOOR_TO_DOOR)"
    )
    actual_weight_kg = serializers.FloatField(min_value=0.001, help_text="실제 무게 (kg)")

    # 치수 (옵션)
    width_cm = serializers.FloatField(required=False, allow_null=True, default=None)
    length_cm = serializers.FloatField(required=False, allow_null=True, default=None)
    height_cm = serializers.FloatField(required=False, allow_null=True, default=None)
    thickness_cm = serializers.FloatField(required=False, allow_null=True, default=None, help_text="KSE Light 판정용 두께")
    longest_side_cm = serializers.FloatField(required=False, allow_null=True, default=None)
    girth_sum_cm = serializers.FloatField(required=False, allow_null=True, default=None)

    # 통관/지역
    invoice_value_jpy = serializers.FloatField(required=False, default=0.0, help_text="신고 금액 (JPY)")
    destination_region = serializers.ChoiceField(
        choices=[('EAST_JAPAN', '동일본'), ('WEST_JAPAN', '서일본'), ('JEJU', '제주')],
        required=False,
        default='EAST_JAPAN',
    )
    export_declaration_type = serializers.ChoiceField(
        choices=[('NONE', 'NONE'), ('MANIFEST', '목록통관'), ('SIMPLIFIED', '간이수출신고'), ('LIST_CONVERSION', '목록변환신고')],
        required=False,
        default='NONE',
    )
    vat_rate = serializers.FloatField(required=False, allow_null=True, default=None)

    # 서비스 옵션
    box_count = serializers.IntegerField(required=False, default=1, min_value=1)
    item_count = serializers.IntegerField(required=False, default=1, min_value=1)
    fsc_amount_jpy = serializers.FloatField(required=False, allow_null=True, default=None, help_text="AIR FSC (JPY)")
    requested_service_class = serializers.ChoiceField(
        choices=[('LIGHT', 'Light'), ('STANDARD', 'Standard')],
        required=False,
        allow_null=True,
        default=None,
        help_text="KSE 서비스 클래스 힌트 (미지정 시 자동 판정)"
    )

    # 화물 특성
    has_battery = serializers.BooleanField(required=False, default=False)
    is_alcohol = serializers.BooleanField(required=False, default=False)
    is_tobacco = serializers.BooleanField(required=False, default=False)
    is_food_or_quarantine = serializers.BooleanField(required=False, default=False)
    is_dangerous_goods = serializers.BooleanField(required=False, default=False)

    # FastBox 전용
    fb_tier = serializers.ChoiceField(
        choices=[('STANDARD', '표준'), ('VIP', 'VIP'), ('SVIP', 'SVIP'), ('SSVIP', 'SSVIP')],
        required=False, default='STANDARD', help_text='FB 등급 (carrier=FB 일 때)'
    )
    fb_tax_mode = serializers.ChoiceField(
        choices=[('DDU', 'DDU'), ('DDP', 'DDP')],
        required=False, default='DDU', help_text='FB 세금 납부 방식'
    )
    fb_fsc_krw = serializers.FloatField(
        required=False, allow_null=True, default=None, help_text='FastBox 유류할증료 (KRW)'
    )

    # 3PL (선택)
    inbound_type = serializers.ChoiceField(
        choices=[('PALLET', 'PALLET'), ('BOX', 'BOX')],
        required=False, allow_null=True, default=None
    )
    storage_type = serializers.ChoiceField(
        choices=[('PALLET', 'PALLET'), ('SHELF', 'SHELF')],
        required=False, allow_null=True, default=None
    )
    label_work_count = serializers.IntegerField(required=False, default=0)
    return_processing_count = serializers.IntegerField(required=False, default=0)
