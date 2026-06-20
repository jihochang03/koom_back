from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status as http_status
from django.shortcuts import get_object_or_404
from .models import WishlistItem
from .serializers import WishlistItemSerializer, WishlistItemAddSerializer


class WishlistView(APIView):
    def get(self, request, customer_id):
        items = WishlistItem.objects.filter(customer_id=customer_id)
        return Response(WishlistItemSerializer(items, many=True).data)


class WishlistItemAddView(APIView):
    def post(self, request, customer_id):
        ser = WishlistItemAddSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        item, created = WishlistItem.objects.get_or_create(
            customer_id=customer_id,
            product_url=d['product_url'],
            defaults={
                'title':          d.get('title', ''),
                'site_domain':    d.get('site_domain', ''),
                'images':         d.get('images', []),
                'price_snapshot': d.get('price_snapshot'),
                'currency':       d.get('currency', 'KRW'),
                'options':        d.get('options', []),
            },
        )
        code = http_status.HTTP_201_CREATED if created else http_status.HTTP_200_OK
        return Response(WishlistItemSerializer(item).data, status=code)


class WishlistItemDeleteView(APIView):
    def delete(self, request, customer_id, item_id):
        item = get_object_or_404(WishlistItem, id=item_id, customer_id=customer_id)
        item.delete()
        return Response(status=http_status.HTTP_204_NO_CONTENT)
