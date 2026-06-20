from rest_framework import serializers
from .models import KoreanMall, MallCrawlJob, FeaturedCategory


class KoreanMallSerializer(serializers.ModelSerializer):
    class Meta:
        model = KoreanMall
        fields = ['id', 'slug', 'name', 'domain', 'logo_url', 'is_active', 'display_order']


class MallCrawlJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = MallCrawlJob
        fields = [
            'id', 'mall', 'category_url', 'category_name',
            'status', 'products_count', 'error_message',
            'last_crawled_at', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'status', 'products_count', 'error_message', 'last_crawled_at', 'created_at', 'updated_at']


class FeaturedCategorySerializer(serializers.ModelSerializer):
    mall_name = serializers.CharField(source='mall.name', read_only=True)
    mall_slug = serializers.CharField(source='mall.slug', read_only=True)
    title = serializers.CharField(read_only=True)

    class Meta:
        model = FeaturedCategory
        fields = [
            'id', 'mall', 'mall_name', 'mall_slug',
            'category_name', 'display_title', 'title',
            'display_order', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class MallCategorySerializer(serializers.Serializer):
    category_name = serializers.CharField()
    products_count = serializers.IntegerField()


class MallDetailSerializer(serializers.ModelSerializer):
    categories = serializers.SerializerMethodField()

    class Meta:
        model = KoreanMall
        fields = ['id', 'slug', 'name', 'domain', 'logo_url', 'categories']

    def get_categories(self, obj):
        from django.db.models import Count
        from apps.products.models import Product
        cats = (
            Product.objects
            .filter(mall=obj)
            .exclude(category='')
            .values('category')
            .annotate(products_count=Count('id'))
            .order_by('category')
        )
        return [{'category_name': c['category'], 'products_count': c['products_count']} for c in cats]
