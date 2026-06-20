from rest_framework import serializers


class ExchangeRateRequestSerializer(serializers.Serializer):
    base = serializers.ChoiceField(
        choices=[('JPY', 'JPY'), ('USD', 'USD'), ('EUR', 'EUR')],
        default='JPY',
        required=False,
        help_text="기준 통화 (기본: JPY)"
    )
    target = serializers.ChoiceField(
        choices=[('KRW', 'KRW'), ('JPY', 'JPY'), ('USD', 'USD')],
        default='KRW',
        required=False,
        help_text="대상 통화 (기본: KRW)"
    )
    use_cache = serializers.BooleanField(
        required=False,
        default=True,
        help_text="최근 1시간 이내 캐시된 환율 사용 여부"
    )


class PricingQuoteRequestSerializer(serializers.Serializer):
    # 상품 가격
    discounted_price = serializers.FloatField(
        required=False, allow_null=True, default=None,
        help_text="할인가 (없으면 null)"
    )
    original_price = serializers.FloatField(
        required=False, allow_null=True, default=None,
        help_text="정가 (할인가 없을 때 사용)"
    )
    currency = serializers.ChoiceField(
        choices=[('KRW', 'KRW'), ('JPY', 'JPY')],
        default='KRW',
        required=False,
    )

    # 환율
    krw_per_jpy_market = serializers.FloatField(
        required=False, allow_null=True, default=None,
        help_text="시장 환율 (원/엔). 미입력 시 자동 조회"
    )

    # 배송비
    shipping_krw = serializers.FloatField(
        required=False, default=0.0,
        help_text="국내 배송비 (KRW)"
    )
    intl_shipping_jpy = serializers.FloatField(
        required=False, default=0.0,
        help_text="국제 배송비 (JPY)"
    )

    # 관세
    tariff_rate = serializers.FloatField(
        required=False, allow_null=True, default=None,
        help_text="관세율 직접 지정 (0~1). 미지정 시 자동 조회"
    )
    product_title = serializers.CharField(
        required=False, allow_blank=True, default='',
        help_text="관세율 자동 조회 시 사용할 상품명"
    )
    use_tariff_lookup = serializers.BooleanField(
        required=False, default=False,
        help_text="product_title로 관세율 자동 조회 여부"
    )

    # 수량
    quantity = serializers.IntegerField(required=False, default=1, min_value=1)

    # 부가 옵션
    bundle_consolidation = serializers.BooleanField(required=False, default=False, help_text="합배송 200엔")
    photo_inspection = serializers.BooleanField(required=False, default=False, help_text="사진검수 300엔")
    speed_shipping = serializers.BooleanField(required=False, default=False, help_text="스피드출하 500엔")
