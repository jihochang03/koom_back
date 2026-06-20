from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.utils import extract_domain
from .models import TemplateBuildLog
from .serializers import TemplateBuildLogSerializer
from .request_serializers import TemplateBuildRequestSerializer
from .services import (
    list_templates,
    list_templates_by_domain,
    get_template,
    delete_template,
    build_template,
    ScraperAgentError,
)


class TemplateListView(APIView):
    def get(self, request):
        # {"files": [...]} 형태 유지 (프론트 호환)
        return Response({"files": list_templates()})


class TemplateDetailView(APIView):
    def get(self, request, filename):
        try:
            template = get_template(filename)
        except ScraperAgentError as e:
            return Response({'error': str(e)}, status=status.HTTP_404_NOT_FOUND)
        return Response(template)

    def delete(self, request, filename):
        try:
            result = delete_template(filename)
        except ScraperAgentError as e:
            return Response({'error': str(e)}, status=status.HTTP_404_NOT_FOUND)
        return Response(result)


class TemplateByDomainView(APIView):
    """특정 도메인에 속한 모든 템플릿 조회 (내용 포함)"""

    def get(self, request, domain):
        templates = list_templates_by_domain(domain)
        return Response(templates)


class TemplateBuildView(APIView):
    def post(self, request):
        req_serializer = TemplateBuildRequestSerializer(data=request.data)
        req_serializer.is_valid(raise_exception=True)
        data = req_serializer.validated_data

        url = data['url']
        domain = extract_domain(url)

        # 동일 도메인의 기존 템플릿 수집 → 병합 컨텍스트로 전달
        existing_templates = list_templates_by_domain(domain)
        merged_from_names = [t['filename'] for t in existing_templates]

        log = TemplateBuildLog.objects.create(
            url=url,
            domain=domain,
            category=data.get('category', 'shopping'),
            merged_from=','.join(merged_from_names),
        )

        try:
            result = build_template(
                url=url,
                category=data.get('category', 'shopping'),
                page_type=data.get('page_type', 'detail'),
                message=data.get('message', ''),
                existing_templates=existing_templates if existing_templates else None,
            )
            filename = result.get('filename', result.get('template', ''))
            log.success = True
            log.filename = filename
            log.save(update_fields=['success', 'filename'])
        except ScraperAgentError as e:
            log.error_message = str(e)
            log.save(update_fields=['error_message'])
            return Response({'error': str(e)}, status=status.HTTP_502_BAD_GATEWAY)

        response_data = {
            **result,
            "merged_from": merged_from_names,
        }
        return Response(response_data, status=status.HTTP_201_CREATED)


class TemplateBuildLogListView(APIView):
    def get(self, request):
        qs = TemplateBuildLog.objects.all()
        domain = request.query_params.get('domain')
        if domain:
            qs = qs.filter(domain=domain)
        serializer = TemplateBuildLogSerializer(qs, many=True)
        return Response(serializer.data)
