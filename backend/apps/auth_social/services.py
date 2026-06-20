"""
LINE Login OAuth 2.0 서비스.

흐름:
  1. GET /api/auth/line/login/ → LINE OAuth 인증 URL로 리다이렉트
  2. LINE이 callback URL로 code + state 전달
  3. GET /api/auth/line/callback/?code=...&state=... → 토큰 교환 → JWT 발급
"""
import logging
import os
import secrets
import urllib.parse

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

LINE_AUTH_URL   = 'https://access.line.me/oauth2/v2.1/authorize'
LINE_TOKEN_URL  = 'https://api.line.me/oauth2/v2.1/token'
LINE_VERIFY_URL = 'https://api.line.me/oauth2/v2.1/verify'
LINE_PROFILE_URL = 'https://api.line.me/v2/profile'


def _client_id() -> str:
    return getattr(settings, 'LINE_LOGIN_CLIENT_ID', '') or os.environ.get('LINE_LOGIN_CLIENT_ID', '')


def _client_secret() -> str:
    return getattr(settings, 'LINE_LOGIN_CLIENT_SECRET', '') or os.environ.get('LINE_LOGIN_CLIENT_SECRET', '')


def _redirect_uri() -> str:
    return getattr(settings, 'LINE_LOGIN_REDIRECT_URI', '')


def build_auth_url(state: str | None = None) -> tuple[str, str]:
    """
    LINE 인증 URL 생성.
    Returns: (auth_url, state)
    """
    if not state:
        state = secrets.token_urlsafe(16)

    params = {
        'response_type': 'code',
        'client_id':     _client_id(),
        'redirect_uri':  _redirect_uri(),
        'state':         state,
        'scope':         'profile openid email',
    }
    url = LINE_AUTH_URL + '?' + urllib.parse.urlencode(params)
    return url, state


def exchange_code(code: str) -> dict:
    """
    Authorization Code → Access Token 교환.
    Returns LINE token response dict.
    """
    try:
        resp = requests.post(
            LINE_TOKEN_URL,
            data={
                'grant_type':    'authorization_code',
                'code':          code,
                'redirect_uri':  _redirect_uri(),
                'client_id':     _client_id(),
                'client_secret': _client_secret(),
            },
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error("LINE token exchange failed: %s", e)
        raise


def get_profile(access_token: str) -> dict:
    """LINE 프로필 조회 (userId, displayName, pictureUrl)."""
    try:
        resp = requests.get(
            LINE_PROFILE_URL,
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error("LINE profile fetch failed: %s", e)
        raise


def issue_jwt(customer_id: str, line_user_id: str) -> str:
    """내부 서비스 JWT 발급."""
    import jwt as _jwt
    secret     = getattr(settings, 'JWT_SECRET', settings.SECRET_KEY)
    expire_hrs = getattr(settings, 'JWT_EXPIRE_HOURS', 720)

    payload = {
        'sub':          customer_id,
        'line_user_id': line_user_id,
        'iat':          int(timezone.now().timestamp()),
        'exp':          int((timezone.now() + timezone.timedelta(hours=expire_hrs)).timestamp()),
    }
    return _jwt.encode(payload, secret, algorithm='HS256')


def verify_jwt(token: str) -> dict | None:
    """JWT 검증. 실패 시 None 반환."""
    import jwt as _jwt
    secret = getattr(settings, 'JWT_SECRET', settings.SECRET_KEY)
    try:
        return _jwt.decode(token, secret, algorithms=['HS256'])
    except Exception as e:
        logger.warning("JWT verify failed: %s", e)
        return None
