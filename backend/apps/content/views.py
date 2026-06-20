from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status as http_status
from .models import FAQ, Notice, EventBanner, Policy
from .serializers import FAQSerializer, NoticeSerializer, EventBannerSerializer, PolicySerializer


# ── FAQ ───────────────────────────────────────────────────────────────────────

class FAQListView(APIView):
    def get(self, request):
        category = request.query_params.get('category')
        show_all = request.query_params.get('all') == 'true'
        qs = FAQ.objects.all() if show_all else FAQ.objects.filter(is_active=True)
        if category:
            qs = qs.filter(category=category)
        return Response(FAQSerializer(qs, many=True).data)

    def post(self, request):
        ser = FAQSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        obj = ser.save()
        return Response(FAQSerializer(obj).data, status=http_status.HTTP_201_CREATED)


class FAQDetailView(APIView):
    def get(self, request, pk):
        return Response(FAQSerializer(get_object_or_404(FAQ, pk=pk)).data)

    def patch(self, request, pk):
        obj = get_object_or_404(FAQ, pk=pk)
        ser = FAQSerializer(obj, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(FAQSerializer(obj).data)

    def delete(self, request, pk):
        obj = get_object_or_404(FAQ, pk=pk)
        obj.is_active = False
        obj.save()
        return Response(status=http_status.HTTP_204_NO_CONTENT)


# ── Notice ────────────────────────────────────────────────────────────────────

class NoticeListView(APIView):
    def get(self, request):
        show_all = request.query_params.get('all') == 'true'
        qs = Notice.objects.all() if show_all else Notice.objects.filter(is_active=True)
        return Response(NoticeSerializer(qs, many=True).data)

    def post(self, request):
        ser = NoticeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        obj = ser.save()
        return Response(NoticeSerializer(obj).data, status=http_status.HTTP_201_CREATED)


class NoticeDetailView(APIView):
    def get(self, request, pk):
        show_all = request.query_params.get('all') == 'true'
        qs = Notice.objects.all() if show_all else Notice.objects.filter(is_active=True)
        notice = get_object_or_404(qs, pk=pk)
        return Response(NoticeSerializer(notice).data)

    def patch(self, request, pk):
        obj = get_object_or_404(Notice, pk=pk)
        ser = NoticeSerializer(obj, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(NoticeSerializer(obj).data)

    def delete(self, request, pk):
        obj = get_object_or_404(Notice, pk=pk)
        obj.is_active = False
        obj.save()
        return Response(status=http_status.HTTP_204_NO_CONTENT)


# ── EventBanner ───────────────────────────────────────────────────────────────

class EventBannerListView(APIView):
    def get(self, request):
        show_all = request.query_params.get('all') == 'true'
        if show_all:
            qs = EventBanner.objects.all()
        else:
            now = timezone.now()
            qs = EventBanner.objects.filter(is_active=True).exclude(ends_at__lt=now)
        return Response(EventBannerSerializer(qs, many=True).data)

    def post(self, request):
        ser = EventBannerSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        obj = ser.save()
        return Response(EventBannerSerializer(obj).data, status=http_status.HTTP_201_CREATED)


class EventBannerDetailView(APIView):
    def get(self, request, pk):
        return Response(EventBannerSerializer(get_object_or_404(EventBanner, pk=pk)).data)

    def patch(self, request, pk):
        obj = get_object_or_404(EventBanner, pk=pk)
        ser = EventBannerSerializer(obj, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(EventBannerSerializer(obj).data)

    def delete(self, request, pk):
        obj = get_object_or_404(EventBanner, pk=pk)
        obj.is_active = False
        obj.save()
        return Response(status=http_status.HTTP_204_NO_CONTENT)


# ── Policy ────────────────────────────────────────────────────────────────────

class PolicyListView(APIView):
    def get(self, request):
        qs = Policy.objects.filter(is_current=True)
        return Response(PolicySerializer(qs, many=True).data)

    def post(self, request):
        """새 정책 버전 생성. is_current=true이면 같은 policy_type의 기존 버전 비활성화."""
        ser = PolicySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        if d.get('is_current', False):
            Policy.objects.filter(policy_type=d['policy_type'], is_current=True).update(is_current=False)
        obj = ser.save()
        return Response(PolicySerializer(obj).data, status=http_status.HTTP_201_CREATED)


class PolicyDetailView(APIView):
    def get(self, request, policy_type):
        policy = get_object_or_404(Policy, policy_type=policy_type, is_current=True)
        return Response(PolicySerializer(policy).data)

    def patch(self, request, policy_type):
        policy = get_object_or_404(Policy, policy_type=policy_type, is_current=True)
        ser = PolicySerializer(policy, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(PolicySerializer(policy).data)
