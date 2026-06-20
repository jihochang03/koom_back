from django.shortcuts import redirect
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from .models import SocialAccount
from .services import build_auth_url, exchange_code, get_profile, issue_jwt, verify_jwt


class LineLoginView(APIView):
    """
    GET /api/auth/line/login/

    LINE OAuth 인증 페이지로 리다이렉트.
    Query param: ?state=<custom_state> (선택)
    """

    def get(self, request):
        state = request.query_params.get('state', '')
        auth_url, state = build_auth_url(state or None)
        # SPA 환경에서는 JSON으로 URL만 반환, 서버사이드 렌더링은 redirect
        if request.query_params.get('json'):
            return Response({'auth_url': auth_url, 'state': state})
        return redirect(auth_url)


class LineCallbackView(APIView):
    """
    GET /api/auth/line/callback/?code=...&state=...

    LINE callback. code → token 교환 → 프로필 조회 → JWT 발급.

    Response: { token, customer_id, display_name, picture_url, is_new }
    """

    def get(self, request):
        code  = request.query_params.get('code', '')
        error = request.query_params.get('error', '')

        if error:
            return Response({'error': error}, status=status.HTTP_400_BAD_REQUEST)
        if not code:
            return Response({'error': 'code required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token_data = exchange_code(code)
        except Exception as e:
            return Response({'error': f'LINE token exchange failed: {e}'}, status=status.HTTP_502_BAD_GATEWAY)

        access_token = token_data.get('access_token', '')
        try:
            profile = get_profile(access_token)
        except Exception as e:
            return Response({'error': f'LINE profile fetch failed: {e}'}, status=status.HTTP_502_BAD_GATEWAY)

        line_user_id  = profile.get('userId', '')
        display_name  = profile.get('displayName', '')
        picture_url   = profile.get('pictureUrl', '')

        account, is_new = SocialAccount.objects.update_or_create(
            provider='line',
            provider_uid=line_user_id,
            defaults={
                'customer_id':  line_user_id,   # LINE userId를 customer_id로 사용
                'display_name': display_name,
                'picture_url':  picture_url,
                'access_token': access_token,
            },
        )

        token = issue_jwt(customer_id=account.customer_id, line_user_id=line_user_id)
        return Response({
            'token':        token,
            'customer_id':  account.customer_id,
            'display_name': display_name,
            'picture_url':  picture_url,
            'is_new':       is_new,
        })


class TokenVerifyView(APIView):
    """
    POST /api/auth/verify/

    JWT 검증.
    Request:  { "token": "..." }
    Response: { "valid": true, "customer_id": "...", "line_user_id": "..." }
    """

    def post(self, request):
        token = request.data.get('token', '')
        if not token:
            return Response({'error': 'token required'}, status=status.HTTP_400_BAD_REQUEST)

        payload = verify_jwt(token)
        if not payload:
            return Response({'valid': False}, status=status.HTTP_401_UNAUTHORIZED)

        return Response({
            'valid':        True,
            'customer_id':  payload.get('sub', ''),
            'line_user_id': payload.get('line_user_id', ''),
        })
