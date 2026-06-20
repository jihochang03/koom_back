from django.db.models import Count
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView

from apps.products.models import Product
from apps.products.serializers import ProductSerializer
from .models import KoreanMall, MallCrawlJob, FeaturedCategory
from .serializers import KoreanMallSerializer, MallCrawlJobSerializer, MallDetailSerializer, FeaturedCategorySerializer
from .services import run_crawl_job


class MallListView(APIView):
    def get(self, request):
        malls = KoreanMall.objects.filter(is_active=True)
        return Response(KoreanMallSerializer(malls, many=True).data)

    def post(self, request):
        ser = KoreanMallSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        mall = ser.save()
        return Response(KoreanMallSerializer(mall).data, status=status.HTTP_201_CREATED)


class MallDetailView(APIView):
    def _get_mall(self, slug):
        try:
            return KoreanMall.objects.get(slug=slug)
        except KoreanMall.DoesNotExist:
            return None

    def get(self, request, slug):
        mall = self._get_mall(slug)
        if not mall:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(MallDetailSerializer(mall).data)

    def patch(self, request, slug):
        mall = self._get_mall(slug)
        if not mall:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        ser = KoreanMallSerializer(mall, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(KoreanMallSerializer(mall).data)


class MallProductListView(ListAPIView):
    serializer_class = ProductSerializer

    def get_queryset(self):
        slug = self.kwargs['slug']
        qs = Product.objects.filter(mall__slug=slug)
        category = self.request.query_params.get('category')
        if category:
            qs = qs.filter(category=category)
        return qs


class MallRecommendedView(APIView):
    def get(self, request, slug):
        products = Product.objects.filter(mall__slug=slug, is_recommended=True)
        return Response(ProductSerializer(products, many=True).data)


class MallCrawlJobListView(APIView):
    def get(self, request, slug):
        try:
            mall = KoreanMall.objects.get(slug=slug)
        except KoreanMall.DoesNotExist:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        jobs = MallCrawlJob.objects.filter(mall=mall)
        return Response(MallCrawlJobSerializer(jobs, many=True).data)

    def post(self, request, slug):
        try:
            mall = KoreanMall.objects.get(slug=slug)
        except KoreanMall.DoesNotExist:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        ser = MallCrawlJobSerializer(data={**request.data, 'mall': mall.id})
        ser.is_valid(raise_exception=True)
        job = ser.save(mall=mall)
        return Response(MallCrawlJobSerializer(job).data, status=status.HTTP_201_CREATED)


class FeaturedCategoryListView(APIView):
    """GET: 메인 페이지 노출 카테고리 목록 / POST: 추가 (admin)"""
    def get(self, request):
        qs = FeaturedCategory.objects.select_related('mall').filter(is_active=True)
        return Response(FeaturedCategorySerializer(qs, many=True).data)

    def post(self, request):
        ser = FeaturedCategorySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        fc = ser.save()
        return Response(FeaturedCategorySerializer(fc).data, status=status.HTTP_201_CREATED)


class FeaturedCategoryDetailView(APIView):
    """PATCH: 수정 / DELETE: 삭제 (admin)"""
    def _get(self, pk):
        try:
            return FeaturedCategory.objects.select_related('mall').get(pk=pk)
        except FeaturedCategory.DoesNotExist:
            return None

    def patch(self, request, pk):
        fc = self._get(pk)
        if not fc:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        ser = FeaturedCategorySerializer(fc, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(FeaturedCategorySerializer(fc).data)

    def delete(self, request, pk):
        fc = self._get(pk)
        if not fc:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        fc.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MallCrawlJobTriggerView(APIView):
    def post(self, request, slug, job_id):
        try:
            job = MallCrawlJob.objects.select_related('mall').get(id=job_id, mall__slug=slug)
        except MallCrawlJob.DoesNotExist:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        run_crawl_job(job)
        return Response(MallCrawlJobSerializer(job).data)
