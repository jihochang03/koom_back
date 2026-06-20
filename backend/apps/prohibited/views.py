from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status as http_status
from django.shortcuts import get_object_or_404
from .models import ProhibitedKeyword
from .serializers import ProhibitedKeywordSerializer


class ProhibitedKeywordListView(APIView):
    def get(self, request):
        risk = request.query_params.get('risk_level')
        category = request.query_params.get('category')
        qs = ProhibitedKeyword.objects.filter(is_active=True)
        if risk:
            qs = qs.filter(risk_level=risk)
        if category:
            qs = qs.filter(category=category)
        return Response(ProhibitedKeywordSerializer(qs, many=True).data)

    def post(self, request):
        ser = ProhibitedKeywordSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        obj = ser.save()
        return Response(ProhibitedKeywordSerializer(obj).data, status=http_status.HTTP_201_CREATED)


class ProhibitedKeywordDetailView(APIView):
    def get(self, request, pk):
        obj = get_object_or_404(ProhibitedKeyword, pk=pk)
        return Response(ProhibitedKeywordSerializer(obj).data)

    def patch(self, request, pk):
        obj = get_object_or_404(ProhibitedKeyword, pk=pk)
        ser = ProhibitedKeywordSerializer(obj, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ProhibitedKeywordSerializer(obj).data)

    def delete(self, request, pk):
        obj = get_object_or_404(ProhibitedKeyword, pk=pk)
        obj.is_active = False
        obj.save()
        return Response(status=http_status.HTTP_204_NO_CONTENT)


class ProhibitedCheckView(APIView):
    """상품 제목을 받아 금지 품목 키워드 매칭 결과 반환"""
    def post(self, request):
        title = request.data.get('title', '').lower()
        if not title:
            return Response({'matches': [], 'risk_level': None})

        keywords = ProhibitedKeyword.objects.filter(is_active=True)
        matches = []
        highest_risk = None
        risk_order = {'prohibited': 3, 'restricted': 2, 'warning': 1}

        for kw in keywords:
            if kw.keyword.lower() in title:
                matches.append(ProhibitedKeywordSerializer(kw).data)
                if highest_risk is None or risk_order.get(kw.risk_level, 0) > risk_order.get(highest_risk, 0):
                    highest_risk = kw.risk_level

        return Response({'matches': matches, 'risk_level': highest_risk, 'title_checked': title})
