from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status as http_status
from django.shortcuts import get_object_or_404
from .models import ErrorCriteria, ErrorCriteriaLog
from .serializers import ErrorCriteriaSerializer, ErrorCriteriaLogSerializer


class ErrorCriteriaView(APIView):
    def get(self, request):
        try:
            current = ErrorCriteria.objects.filter(is_current=True).latest('created_at')
            return Response(ErrorCriteriaSerializer(current).data)
        except ErrorCriteria.DoesNotExist:
            return Response({'error': '설정된 기준이 없습니다.'}, status=http_status.HTTP_404_NOT_FOUND)

    def post(self, request):
        """새 기준 버전 생성 (이전 버전 is_current=False 자동 처리)"""
        ser = ErrorCriteriaSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        obj = ErrorCriteria(**ser.validated_data, is_current=True)
        obj.save()
        return Response(ErrorCriteriaSerializer(obj).data, status=http_status.HTTP_201_CREATED)

    def patch(self, request):
        """현재 기준 부분 수정 + 변경 이력 기록"""
        try:
            current = ErrorCriteria.objects.filter(is_current=True).latest('created_at')
        except ErrorCriteria.DoesNotExist:
            return Response({'error': 'not found'}, status=http_status.HTTP_404_NOT_FOUND)

        changed_by = request.data.pop('changed_by', '')
        logs = []
        for field, new_val in request.data.items():
            if hasattr(current, field):
                old_val = getattr(current, field)
                if old_val != new_val:
                    logs.append(ErrorCriteriaLog(
                        criteria=current,
                        changed_field=field,
                        old_value=old_val,
                        new_value=new_val,
                        changed_by=changed_by,
                    ))
                    setattr(current, field, new_val)
        current.save()
        ErrorCriteriaLog.objects.bulk_create(logs)
        return Response(ErrorCriteriaSerializer(current).data)


class ErrorCriteriaHistoryView(APIView):
    def get(self, request):
        qs = ErrorCriteria.objects.all()
        return Response(ErrorCriteriaSerializer(qs, many=True).data)


class ErrorCriteriaLogView(APIView):
    def get(self, request, pk):
        criteria = get_object_or_404(ErrorCriteria, pk=pk)
        logs = ErrorCriteriaLog.objects.filter(criteria=criteria)
        return Response(ErrorCriteriaLogSerializer(logs, many=True).data)
