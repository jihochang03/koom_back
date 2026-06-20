from rest_framework import serializers
from .models import PageType

CATEGORY_CHOICES = [
    ('shopping', '쇼핑'),
    ('news', '뉴스/블로그'),
    ('real_estate', '부동산'),
    ('jobs', '채용/구인'),
    ('general', '일반'),
]


class AnalyzeRequestSerializer(serializers.Serializer):
    url = serializers.URLField(
        help_text="분석할 페이지 URL"
    )
    category = serializers.ChoiceField(
        choices=CATEGORY_CHOICES,
        default='shopping',
        required=False,
        help_text="사이트 카테고리 (shopping/news/real_estate/jobs/general)",
    )
    page_type = serializers.ChoiceField(
        choices=PageType.choices,
        default=PageType.AUTO,
        required=False,
        help_text=(
            "페이지 유형 힌트. "
            "auto: scraper-agent가 자동 판단, "
            "list: 목록 페이지 (모든 항목 수집), "
            "detail: 상세 페이지 (단일 항목 수집)"
        ),
    )
    max_items = serializers.IntegerField(
        required=False,
        default=None,
        allow_null=True,
        min_value=1,
        help_text="list 타입에서 수집할 최대 아이템 수 (선택)"
    )
    collect_detail = serializers.BooleanField(
        required=False,
        default=True,
        help_text="list 타입에서 각 아이템의 상세 정보까지 수집할지 여부"
    )
    customer_id = serializers.CharField(
        required=False,
        default='',
        allow_blank=True,
        help_text="방문 기록용 고객 ID (있을 때만 저장)",
    )
