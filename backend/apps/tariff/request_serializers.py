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


class TariffClassifyRequestSerializer(serializers.Serializer):
    product_title = serializers.CharField(
        max_length=500,
        help_text="분류할 상품명"
    )
    top_n = serializers.IntegerField(
        required=False, default=5, min_value=0, max_value=10,
        help_text="제시할 대안 후보 개수"
    )


class HsClassificationConfirmSerializer(serializers.Serializer):
    """검수 담당자의 HS코드·통관 카테고리 확정/수정."""
    final_hs_code = serializers.CharField(
        max_length=30, allow_blank=True, required=False, default='',
        help_text="확정 HS코드(순번)"
    )
    final_category = serializers.CharField(
        max_length=500, allow_blank=True, required=False, default='',
        help_text="확정 통관 카테고리(한글품명)"
    )
    final_full_path = serializers.CharField(
        allow_blank=True, required=False, default='',
        help_text="확정 분류 경로 (대분류 > ... > 품목)"
    )
    decision_source = serializers.ChoiceField(
        choices=['ai_confirmed', 'alternative', 'manual'],
        required=False, default='manual',
        help_text="확정 방식"
    )
    inspector = serializers.CharField(
        max_length=100, allow_blank=True, required=False, default='',
        help_text="검수 담당자"
    )
    inspector_note = serializers.CharField(
        allow_blank=True, required=False, default='',
        help_text="검수 피드백/메모"
    )
