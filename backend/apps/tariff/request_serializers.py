from rest_framework import serializers


class TariffLookupRequestSerializer(serializers.Serializer):
    product_title = serializers.CharField(
        max_length=500,
        help_text="관세율을 조회할 상품명 (예: '블루투스 이어폰 노이즈캔슬링')"
    )
    use_cache = serializers.BooleanField(
        required=False,
        default=True,
        help_text="동일 상품명 최근 조회 결과 캐시 사용 여부"
    )
