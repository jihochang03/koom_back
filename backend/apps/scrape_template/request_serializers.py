from rest_framework import serializers

CATEGORY_CHOICES = [
    ('shopping', '쇼핑'),
    ('news', '뉴스/블로그'),
    ('real_estate', '부동산'),
    ('jobs', '채용/구인'),
    ('general', '일반'),
]

PAGE_TYPE_CHOICES = [
    ('detail', '상세 페이지'),
    ('list', '목록 페이지'),
    ('both', '목록 + 상세'),
]


class TemplateBuildRequestSerializer(serializers.Serializer):
    url = serializers.URLField(
        help_text="템플릿을 생성할 사이트 URL"
    )
    category = serializers.ChoiceField(
        choices=CATEGORY_CHOICES,
        default='shopping',
        required=False,
        help_text="사이트 카테고리 (shopping/news/real_estate/jobs/general)",
    )
    page_type = serializers.ChoiceField(
        choices=PAGE_TYPE_CHOICES,
        default='detail',
        required=False,
        help_text="페이지 유형 (detail/list/both)",
    )
    message = serializers.CharField(
        required=False,
        allow_blank=True,
        default='',
        help_text="에이전트에게 전달할 추가 지시사항"
    )
