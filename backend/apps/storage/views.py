from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from .models import UploadedFile
from .services import upload_file, delete_file, generate_presigned_url


class FileUploadView(APIView):
    """
    POST /api/storage/upload/

    파일 업로드 → S3/R2 저장 후 URL 반환.

    multipart/form-data:
      file        : 파일 (required)
      purpose     : inspection | product | receipt | other (기본 other)
      order_number: 주문 번호 (선택)
      customer_id : 고객 ID (선택)
    """
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'error': 'file required'}, status=status.HTTP_400_BAD_REQUEST)

        purpose      = request.data.get('purpose', 'other')
        order_number = request.data.get('order_number', '')
        customer_id  = request.data.get('customer_id', '')

        try:
            result = upload_file(
                file_data=file_obj.read(),
                original_name=file_obj.name,
                purpose=purpose,
                order_number=order_number,
                content_type=file_obj.content_type or '',
            )
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_502_BAD_GATEWAY)

        record = UploadedFile.objects.create(
            order_number=order_number,
            customer_id=customer_id,
            purpose=purpose,
            original_name=file_obj.name,
            s3_key=result['s3_key'],
            public_url=result['public_url'],
            content_type=result['content_type'],
            size_bytes=result['size_bytes'],
        )

        return Response({
            'id':           record.id,
            'public_url':   record.public_url,
            's3_key':       record.s3_key,
            'size_bytes':   record.size_bytes,
            'content_type': record.content_type,
        }, status=status.HTTP_201_CREATED)


class FileListView(APIView):
    """
    GET /api/storage/files/?order_number=xxx&purpose=inspection

    업로드 파일 목록 조회.
    """

    def get(self, request):
        order_number = request.query_params.get('order_number', '')
        purpose      = request.query_params.get('purpose', '')
        customer_id  = request.query_params.get('customer_id', '')

        qs = UploadedFile.objects.all()
        if order_number:
            qs = qs.filter(order_number=order_number)
        if purpose:
            qs = qs.filter(purpose=purpose)
        if customer_id:
            qs = qs.filter(customer_id=customer_id)

        files = list(qs.values(
            'id', 'order_number', 'customer_id', 'purpose',
            'original_name', 'public_url', 's3_key',
            'content_type', 'size_bytes', 'created_at',
        )[:50])
        return Response({'files': files})


class FileDeleteView(APIView):
    """DELETE /api/storage/files/<id>/"""

    def delete(self, request, pk):
        try:
            record = UploadedFile.objects.get(pk=pk)
        except UploadedFile.DoesNotExist:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        delete_file(record.s3_key)
        record.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PresignedUrlView(APIView):
    """
    GET /api/storage/files/<id>/presigned/

    임시 다운로드 URL 생성 (private 버킷용).
    """

    def get(self, request, pk):
        try:
            record = UploadedFile.objects.get(pk=pk)
        except UploadedFile.DoesNotExist:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        expires_in = int(request.query_params.get('expires_in', 3600))
        url = generate_presigned_url(record.s3_key, expires_in=expires_in)
        return Response({'url': url, 'expires_in': expires_in})
