from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

# Sentry — DSN이 있을 때만 초기화
_SENTRY_DSN = os.getenv('SENTRY_DSN', '')
if _SENTRY_DSN:
    import sentry_sdk
    sentry_sdk.init(
        dsn=_SENTRY_DSN,
        traces_sample_rate=float(os.getenv('SENTRY_TRACES_RATE', '0.1')),
        environment=os.getenv('SENTRY_ENV', 'development'),
        send_default_pii=False,
    )

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-wxz^hh#l*v#16awpxt0t_k(wy5pd@8ws&&8g=zjg@csrchf#(&')

DEBUG = os.getenv('DEBUG', 'True') == 'True'

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '*').split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'apps.scraping',
    'apps.scrape_template',
    'apps.tariff',
    'apps.shipping',
    'apps.pricing',
    'apps.common',
    'apps.products',
    'apps.cart',
    'apps.sites',
    'apps.orders',
    'apps.wishlist',
    'apps.cs',
    'apps.mypage',
    'apps.content',
    'apps.logistics',
    'apps.operations',
    'apps.stats',
    'apps.prohibited',
    'apps.malls',
    'apps.payment',
    'apps.utils',
    'apps.translate',
    'apps.notify',
    'apps.tracking',
    'apps.storage',
    'apps.auth_social',
]

TARIFF_CACHE_TTL_HOURS = int(os.getenv('TARIFF_CACHE_TTL_HOURS', '24'))
EXCHANGE_CACHE_MINUTES = int(os.getenv('EXCHANGE_CACHE_MINUTES', '60'))

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'ko-kr'
TIME_ZONE = 'Asia/Seoul'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.MultiPartParser',
        'rest_framework.parsers.FormParser',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}

# scraper-agent API 설정
SCRAPER_AGENT_BASE_URL = os.getenv('SCRAPER_AGENT_BASE_URL', 'http://localhost:3000')
SCRAPER_AGENT_TIMEOUT = int(os.getenv('SCRAPER_AGENT_TIMEOUT', '120'))

# DHUB (FastBox) 국제 물류 API
DHUB_BASE_URL     = os.getenv('DHUB_BASE_URL', 'https://dhub-api-qa.hanpda.com')
DHUB_MALL_ID      = os.getenv('DHUB_MALL_ID', '')
DHUB_TOKEN        = os.getenv('DHUB_TOKEN', '')
DHUB_CONSUMER_KEY = os.getenv('DHUB_CONSUMER_KEY', '')
DHUB_SELLER_NAME  = os.getenv('DHUB_SELLER_NAME', 'Boltlab DK')

# DeepL 번역
DEEPL_API_KEY      = os.getenv('DEEPL_API_KEY', '')
DEEPL_CACHE_HOURS  = int(os.getenv('DEEPL_CACHE_HOURS', '720'))   # 30일

# LINE Messaging API
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', '')
LINE_CHANNEL_SECRET       = os.getenv('LINE_CHANNEL_SECRET', '')

# LINE Login (소셜 로그인)
LINE_LOGIN_CLIENT_ID     = os.getenv('LINE_LOGIN_CLIENT_ID', '')
LINE_LOGIN_CLIENT_SECRET = os.getenv('LINE_LOGIN_CLIENT_SECRET', '')
LINE_LOGIN_REDIRECT_URI  = os.getenv('LINE_LOGIN_REDIRECT_URI', 'http://localhost:8000/api/auth/line/callback/')

# SendGrid 이메일
SENDGRID_API_KEY   = os.getenv('SENDGRID_API_KEY', '')
SENDGRID_FROM_EMAIL = os.getenv('SENDGRID_FROM_EMAIL', 'noreply@koom.jp')
SENDGRID_FROM_NAME  = os.getenv('SENDGRID_FROM_NAME', 'koom')

# Twilio SMS
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID', '')
TWILIO_AUTH_TOKEN  = os.getenv('TWILIO_AUTH_TOKEN', '')
TWILIO_FROM_NUMBER = os.getenv('TWILIO_FROM_NUMBER', '')

# AWS S3 / Cloudflare R2 파일 스토리지
STORAGE_USE_R2          = os.getenv('STORAGE_USE_R2', 'false').lower() == 'true'
AWS_ACCESS_KEY_ID       = os.getenv('AWS_ACCESS_KEY_ID', '')
AWS_SECRET_ACCESS_KEY   = os.getenv('AWS_SECRET_ACCESS_KEY', '')
AWS_STORAGE_BUCKET_NAME = os.getenv('AWS_STORAGE_BUCKET_NAME', '')
AWS_S3_REGION_NAME      = os.getenv('AWS_S3_REGION_NAME', 'ap-northeast-1')
AWS_S3_ENDPOINT_URL     = os.getenv('AWS_S3_ENDPOINT_URL', '')   # R2 사용 시 설정
AWS_S3_PUBLIC_BASE_URL  = os.getenv('AWS_S3_PUBLIC_BASE_URL', '')  # CDN 도메인

# JWT (소셜 로그인 토큰 발급)
JWT_SECRET  = os.getenv('JWT_SECRET', SECRET_KEY)
JWT_EXPIRE_HOURS = int(os.getenv('JWT_EXPIRE_HOURS', '720'))  # 30일

# 배송 추적
SMART_TRACKER_BASE_URL = os.getenv('SMART_TRACKER_BASE_URL', 'https://info.sweettracker.co.kr')
SMART_TRACKER_API_KEY  = os.getenv('SMART_TRACKER_API_KEY', '')
TRACKING_CACHE_MINUTES = int(os.getenv('TRACKING_CACHE_MINUTES', '30'))
