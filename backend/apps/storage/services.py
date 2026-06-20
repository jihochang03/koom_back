"""
AWS S3 / Cloudflare R2 파일 업로드.

환경변수:
  STORAGE_USE_R2=true  → R2 사용 (endpoint: AWS_S3_ENDPOINT_URL)
  STORAGE_USE_R2=false → S3 사용 (기본)
"""
import logging
import mimetypes
import os
import uuid

from django.conf import settings

logger = logging.getLogger(__name__)


def _client():
    import boto3
    kwargs = {
        'aws_access_key_id':     getattr(settings, 'AWS_ACCESS_KEY_ID', ''),
        'aws_secret_access_key': getattr(settings, 'AWS_SECRET_ACCESS_KEY', ''),
        'region_name':           getattr(settings, 'AWS_S3_REGION_NAME', 'ap-northeast-1'),
    }
    endpoint = getattr(settings, 'AWS_S3_ENDPOINT_URL', '')
    if endpoint:
        kwargs['endpoint_url'] = endpoint
    return boto3.client('s3', **kwargs)


def _bucket() -> str:
    return getattr(settings, 'AWS_STORAGE_BUCKET_NAME', '')


def _public_url(key: str) -> str:
    base = getattr(settings, 'AWS_S3_PUBLIC_BASE_URL', '').rstrip('/')
    if base:
        return f'{base}/{key}'
    bucket = _bucket()
    region = getattr(settings, 'AWS_S3_REGION_NAME', 'ap-northeast-1')
    endpoint = getattr(settings, 'AWS_S3_ENDPOINT_URL', '')
    if endpoint:
        return f'{endpoint.rstrip("/")}/{bucket}/{key}'
    return f'https://{bucket}.s3.{region}.amazonaws.com/{key}'


def upload_file(
    file_data: bytes,
    original_name: str = '',
    purpose: str = 'other',
    order_number: str = '',
    content_type: str = '',
) -> dict:
    """
    파일을 S3/R2에 업로드.

    Returns:
        { "s3_key": "...", "public_url": "...", "size_bytes": int, "content_type": "..." }
    """
    bucket = _bucket()
    if not bucket:
        logger.error("AWS_STORAGE_BUCKET_NAME not set")
        raise ValueError("Storage bucket not configured")

    ext = ''
    if original_name and '.' in original_name:
        ext = '.' + original_name.rsplit('.', 1)[-1].lower()

    if not content_type and ext:
        content_type = mimetypes.types_map.get(ext, 'application/octet-stream')
    elif not content_type:
        content_type = 'application/octet-stream'

    prefix = f'{purpose}/{order_number}/' if order_number else f'{purpose}/'
    key = f'{prefix}{uuid.uuid4().hex}{ext}'

    try:
        client = _client()
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=file_data,
            ContentType=content_type,
        )
    except Exception as e:
        logger.error("S3 upload failed key=%s err=%s", key, e)
        raise

    return {
        's3_key':       key,
        'public_url':   _public_url(key),
        'size_bytes':   len(file_data),
        'content_type': content_type,
    }


def delete_file(s3_key: str) -> bool:
    """S3/R2에서 파일 삭제."""
    bucket = _bucket()
    if not bucket:
        return False
    try:
        _client().delete_object(Bucket=bucket, Key=s3_key)
        return True
    except Exception as e:
        logger.error("S3 delete failed key=%s err=%s", s3_key, e)
        return False


def generate_presigned_url(s3_key: str, expires_in: int = 3600) -> str:
    """임시 다운로드 URL 생성 (private 버킷용)."""
    bucket = _bucket()
    if not bucket:
        return ''
    try:
        return _client().generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': s3_key},
            ExpiresIn=expires_in,
        )
    except Exception as e:
        logger.error("Presigned URL failed key=%s err=%s", s3_key, e)
        return ''
