from rest_framework import serializers
from .models import Product, ProductArrivalPhoto


class ProductArrivalPhotoSerializer(serializers.ModelSerializer):
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model = ProductArrivalPhoto
        fields = ['id', 'photo', 'photo_url', 'note', 'captured_at']
        read_only_fields = ['id', 'captured_at']
        extra_kwargs = {'photo': {'write_only': True}}

    def get_photo_url(self, obj):
        request = self.context.get('request')
        if obj.photo and request:
            return request.build_absolute_uri(obj.photo.url)
        return obj.photo.url if obj.photo else None


class ProductSerializer(serializers.ModelSerializer):
    arrival_photos = ProductArrivalPhotoSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'source_url', 'url', 'product_id',
            'title', 'price_original', 'price_discounted', 'currency',
            'images', 'brand', 'rating', 'review_count', 'availability',
            'category', 'mall', 'is_prima', 'is_limited', 'is_recommended',
            'detail_data', 'detail_status', 'detail_crawled_at',
            # 입고 / 도착 상태
            'inbound_order_number', 'inbound_tracking_number', 'inbound_courier',
            'arrival_status', 'inspection_required',
            'arrived_at', 'inspected_at', 'inbound_note',
            'arrival_photos',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'arrived_at', 'inspected_at', 'created_at', 'updated_at']


class ProductBatchItemSerializer(serializers.Serializer):
    url = serializers.URLField()
    product_id = serializers.CharField(required=False, default='', allow_blank=True)
    title = serializers.CharField(required=False, default='', allow_blank=True)
    price_original = serializers.FloatField(required=False, allow_null=True, default=None)
    price_discounted = serializers.FloatField(required=False, allow_null=True, default=None)
    currency = serializers.CharField(required=False, default='KRW')
    images = serializers.ListField(
        child=serializers.CharField(), required=False, default=list
    )
    brand = serializers.CharField(required=False, allow_blank=True, default='')
    rating = serializers.FloatField(required=False, allow_null=True, default=None)
    review_count = serializers.IntegerField(required=False, allow_null=True, default=None)
    availability = serializers.CharField(required=False, default='', allow_blank=True)


class ProductBatchCreateSerializer(serializers.Serializer):
    source_url = serializers.CharField(required=False, default='', allow_blank=True)
    category = serializers.CharField(required=False, default='', allow_blank=True)
    mall_slug = serializers.CharField(required=False, default='', allow_blank=True)
    items = ProductBatchItemSerializer(many=True)
