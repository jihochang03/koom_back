from django.db.models import Count
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.utils import extract_domain
from .models import ScrapeRequest, ScrapeResult, ScrapeStatus, UrlVisit
from .serializers import ScrapeRequestSerializer, UrlVisitSerializer, PopularUrlSerializer
from .request_serializers import AnalyzeRequestSerializer
from .services import analyze_url, ScraperAgentError


class AnalyzeView(APIView):
    def post(self, request):
        req_serializer = AnalyzeRequestSerializer(data=request.data)
        req_serializer.is_valid(raise_exception=True)
        data = req_serializer.validated_data

        url = data['url']
        customer_id = data.get('customer_id', '')
        domain = extract_domain(url)

        if customer_id:
            UrlVisit.objects.create(customer_id=customer_id, url=url)

        scrape_request = ScrapeRequest.objects.create(
            url=url,
            domain=domain,
            category=data.get('category', 'shopping'),
            page_type=data.get('page_type', 'auto'),
            status=ScrapeStatus.PROCESSING,
        )

        try:
            result = analyze_url(
                url=url,
                category=data.get('category', 'shopping'),
                page_type=data.get('page_type', 'auto'),
                max_items=data.get('max_items'),
                collect_detail=data.get('collect_detail', True),
            )
            ScrapeResult.objects.create(
                scrape_request=scrape_request,
                raw_data=result['data'],
                template_used=result['template_used'],
                items_count=result['items_count'],
            )
            scrape_request.status = ScrapeStatus.COMPLETED
            scrape_request.save(update_fields=['status', 'updated_at'])

        except ScraperAgentError as e:
            scrape_request.status = ScrapeStatus.FAILED
            scrape_request.error_message = str(e)
            scrape_request.save(update_fields=['status', 'error_message', 'updated_at'])
            return Response({'error': str(e)}, status=status.HTTP_502_BAD_GATEWAY)

        serializer = ScrapeRequestSerializer(scrape_request)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ScrapeRequestListView(generics.ListAPIView):
    serializer_class = ScrapeRequestSerializer

    def get_queryset(self):
        qs = ScrapeRequest.objects.select_related('result').all()
        domain = self.request.query_params.get('domain')
        category = self.request.query_params.get('category')
        if domain:
            qs = qs.filter(domain=domain)
        if category:
            qs = qs.filter(category=category)
        return qs


class ScrapeRequestDetailView(generics.RetrieveAPIView):
    queryset = ScrapeRequest.objects.select_related('result').all()
    serializer_class = ScrapeRequestSerializer


class UrlVisitRecentView(APIView):
    """GET ?customer_id=xxx&limit=10 — 사용자 최근 방문 URL"""
    def get(self, request):
        customer_id = request.query_params.get('customer_id', '')
        if not customer_id:
            return Response({'error': 'customer_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        limit = min(int(request.query_params.get('limit', 10)), 50)
        visits = UrlVisit.objects.filter(customer_id=customer_id)[:limit]
        return Response(UrlVisitSerializer(visits, many=True).data)


class UrlPopularView(APIView):
    """GET ?limit=10 — 전체 사용자 인기 URL (방문 횟수 기준)"""
    def get(self, request):
        limit = min(int(request.query_params.get('limit', 10)), 50)
        popular = (
            UrlVisit.objects
            .values('url')
            .annotate(visit_count=Count('id'))
            .order_by('-visit_count')[:limit]
        )
        return Response(PopularUrlSerializer(popular, many=True).data)
