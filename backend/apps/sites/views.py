from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status as http_status
from .models import SupportedSite
from .serializers import SupportedSiteSerializer
from .services import classify_url


class SiteListView(APIView):
    def get(self, request):
        sites = SupportedSite.objects.filter(is_active=True)
        return Response(SupportedSiteSerializer(sites, many=True).data)


class URLClassifyView(APIView):
    def post(self, request):
        url = request.data.get('url', '').strip()
        if not url:
            return Response({'error': 'url 필드가 필요합니다.'}, status=http_status.HTTP_400_BAD_REQUEST)
        result = classify_url(url)
        site = result.pop('site')
        return Response({
            **result,
            'site': SupportedSiteSerializer(site).data if site else None,
        })
