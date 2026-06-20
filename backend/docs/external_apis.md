# 외부 API 통합 현황

## 연결된 외부 API 전체 목록

| # | 서비스 | 앱 | 엔드포인트 | 환경변수 키 |
|---|--------|-----|-----------|------------|
| 1 | Anthropic Claude | `apps.tariff` | 관세 분류 | `ANTHROPIC_API_KEY` |
| 2 | OpenAI Embeddings | `apps.tariff` | 관세 벡터 검색 | `OPENAI_API_KEY` |
| 3 | Exchange Rate API | `apps.pricing` | JPY↔KRW 환율 | 키 불필요 (무료) |
| 4 | GMO-PG 카드 결제 | `apps.payment` | `/api/payment/` | `GMO_SHOP_ID`, `GMO_SHOP_PASS` |
| 5 | GMO-PG PayPay | `apps.payment` | `/api/payment/paypay/` | 동일 |
| 6 | DHUB/FastBox 물류 | `apps.logistics` | 국제배송 등록/추적 | `DHUB_TOKEN`, `DHUB_CONSUMER_KEY` | → [dhub_carrier_api.md](dhub_carrier_api.md) |
| 7 | Scraper-agent | `apps.scraping` | 한국 쇼핑몰 크롤 | `SCRAPER_AGENT_BASE_URL` |
| 8 | Sentry | `config.settings` | 에러 모니터링 | `SENTRY_DSN` |
| 9 | Zipcloud 우편번호 | `apps.utils` | `/api/utils/zipcode/` | 키 불필요 (무료) |
| 10 | DeepL 번역 | `apps.translate` | `/api/translate/` | `DEEPL_API_KEY` |
| 11 | LINE Messaging | `apps.notify` | `/api/notify/send/` | `LINE_CHANNEL_ACCESS_TOKEN` |
| 12 | SendGrid 이메일 | `apps.notify` | 동일 | `SENDGRID_API_KEY` |
| 13 | Twilio SMS | `apps.notify` | 동일 | `TWILIO_ACCOUNT_SID` |
| 14 | 스마트택배 추적 | `apps.tracking` | `/api/tracking/` | `SMART_TRACKER_API_KEY` |
| 15 | 일본 배송사 URL | `apps.tracking` | 동일 | 없음 |
| 16 | AWS S3 / R2 | `apps.storage` | `/api/storage/` | `AWS_ACCESS_KEY_ID` |
| 17 | LINE Login | `apps.auth_social` | `/api/auth/line/` | `LINE_LOGIN_CLIENT_ID` |

---

## 앱별 상세

### `apps.utils` — 일본 우편번호 (zipcloud)

`GET /api/utils/zipcode/<7자리>/`

```json
{
  "zipcode": "1060032",
  "prefecture": "東京都",
  "city": "港区",
  "town": "六本木",
  "kana": { "prefecture": "とうきょうと", "city": "みなとく", "town": "ろっぽんぎ" }
}
```

- 무료, 키 불필요
- zipcloud.ibsnet.co.jp 프록시

---

### `apps.translate` — DeepL 번역

`POST /api/translate/`

단건:
```json
{ "text": "수분 크림", "source_lang": "KO", "target_lang": "JA" }
→ { "translated": "保湿クリーム" }
```

다건:
```json
{ "texts": ["수분 크림", "선크림"], "source_lang": "KO", "target_lang": "JA" }
→ { "translated": ["保湿クリーム", "日焼け止め"] }
```

- DB 캐시 TTL: `DEEPL_CACHE_HOURS` (기본 720h = 30일)
- `DEEPL_API_KEY` 없으면 원문 그대로 반환 (폴백)

---

### `apps.notify` — 알림 통합 (LINE + 이메일 + SMS)

`POST /api/notify/send/`

```json
{
  "customer_id": "U1234567890abcdef",
  "event": "payment_complete",
  "channels": ["line", "email", "sms"],
  "recipients": {
    "line":  "U1234567890abcdef",
    "email": "user@example.com",
    "sms":   "+819012345678"
  },
  "context": { "order_number": "ORD-20260609-ABC", "amount_jpy": 3200 },
  "order_number": "ORD-20260609-ABC"
}
```

`GET /api/notify/logs/?customer_id=xxx&limit=20`

**지원 이벤트:**
`order_confirmed` / `payment_complete` / `purchase_started` / `inspection_done` /
`shipping_kr` / `shipping_intl` / `shipping_jp` / `delivered` / `cancel_complete` / `refund_complete`

**채널 환경변수:**

| 채널 | 필수 변수 |
|------|----------|
| `line` | `LINE_CHANNEL_ACCESS_TOKEN` |
| `email` | `SENDGRID_API_KEY`, `SENDGRID_FROM_EMAIL` |
| `sms` | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` |

---

### `apps.tracking` — 배송 추적

`GET /api/tracking/<carrier_code>/<tracking_number>/`

`GET /api/tracking/carriers/` — 지원 배송사 목록

**한국 택배 carrier_code:**

| 코드 | 택배사 |
|------|--------|
| `cj` | CJ대한통운 |
| `hanjin` | 한진택배 |
| `lotte` | 롯데택배 |
| `logen` | 로젠택배 |
| `epost` | 우체국 |
| `coupang` | 쿠팡로켓 |

한국 택배 응답 예시:
```json
{
  "carrier": "cj", "carrier_name": "CJ대한통운",
  "tracking_number": "1234567890",
  "status": "배송완료", "level": 6,
  "events": [{ "time": "2026-06-09 14:00", "location": "서울", "description": "배송완료", "level": 6 }]
}
```

**일본 배송사 carrier_code:** `sagawa` / `yamato` / `japanpost` / `seino` / `fukuyama`

일본 배송사 응답 예시:
```json
{
  "carrier": "sagawa", "carrier_name": "佐川急便",
  "tracking_number": "123456789012",
  "tracking_url": "https://k2k.sagawa-exp.co.jp/...",
  "status": "inquiry_required"
}
```

- 캐시 TTL: `TRACKING_CACHE_MINUTES` (기본 30분)
- 한국: `SMART_TRACKER_API_KEY` 필요

---

### `apps.storage` — 파일/이미지 저장

`POST /api/storage/upload/` (multipart/form-data)

| 파라미터 | 설명 |
|---------|------|
| `file` | 파일 (필수) |
| `purpose` | `inspection` / `product` / `receipt` / `other` |
| `order_number` | 주문 번호 |
| `customer_id` | 고객 ID |

응답:
```json
{ "id": 1, "public_url": "https://cdn.../inspection/ORD.../uuid.jpg", "size_bytes": 102400 }
```

`GET /api/storage/files/?order_number=xxx&purpose=inspection`

`DELETE /api/storage/files/<id>/`

`GET /api/storage/files/<id>/presigned/?expires_in=3600` — 임시 URL

**환경변수:**

| 변수 | 설명 |
|------|------|
| `STORAGE_USE_R2` | `true`면 Cloudflare R2 사용 |
| `AWS_ACCESS_KEY_ID` | S3/R2 Access Key |
| `AWS_SECRET_ACCESS_KEY` | S3/R2 Secret |
| `AWS_STORAGE_BUCKET_NAME` | 버킷명 |
| `AWS_S3_ENDPOINT_URL` | R2 endpoint (R2 사용 시) |
| `AWS_S3_PUBLIC_BASE_URL` | CDN 도메인 |

---

### `apps.auth_social` — LINE 소셜 로그인

`GET /api/auth/line/login/` → LINE OAuth 인증 페이지로 리다이렉트

`GET /api/auth/line/login/?json=1` → `{ "auth_url": "...", "state": "..." }` (SPA용)

`GET /api/auth/line/callback/?code=...&state=...` → JWT 발급

```json
{
  "token": "eyJhbGc...",
  "customer_id": "U1234567890abcdef",
  "display_name": "山田太郎",
  "picture_url": "https://profile.line-scdn.net/...",
  "is_new": true
}
```

`POST /api/auth/verify/` → `{ "token": "..." }` → `{ "valid": true, "customer_id": "..." }`

**환경변수:**

| 변수 | 설명 |
|------|------|
| `LINE_LOGIN_CLIENT_ID` | LINE Login Channel ID |
| `LINE_LOGIN_CLIENT_SECRET` | LINE Login Channel Secret |
| `LINE_LOGIN_REDIRECT_URI` | Callback URL (LINE 콘솔에도 등록 필요) |
| `JWT_SECRET` | JWT 서명 키 (기본: SECRET_KEY) |
| `JWT_EXPIRE_HOURS` | 토큰 유효기간 (기본 720h) |

---

### `apps.payment` PayPay 추가 — GMO-PG PayPay

`POST /api/payment/paypay/entry/`

```json
{ "order_group_id": 1, "return_url": "https://koom.jp/payment/complete" }
→ { "gmo_order_id": "PP-GRP-20260609-ABC", "access_id": "...", "access_pass": "...", "qr_url": "https://...", "amount_jpy": 3200 }
```

`POST /api/payment/paypay/execute/`

```json
{ "order_group_id": 1, "gmo_order_id": "PP-...", "access_id": "...", "access_pass": "..." }
→ { "status": "captured", "tran_id": "...", "forward": "..." }
```

`GET /api/payment/paypay/status/<gmo_order_id>/`

---

## 환경변수 전체 목록

```env
# Sentry
SENTRY_DSN=
SENTRY_ENV=production
SENTRY_TRACES_RATE=0.1

# DeepL
DEEPL_API_KEY=
DEEPL_CACHE_HOURS=720

# LINE Messaging
LINE_CHANNEL_ACCESS_TOKEN=
LINE_CHANNEL_SECRET=

# LINE Login
LINE_LOGIN_CLIENT_ID=
LINE_LOGIN_CLIENT_SECRET=
LINE_LOGIN_REDIRECT_URI=https://koom.jp/api/auth/line/callback/

# SendGrid
SENDGRID_API_KEY=
SENDGRID_FROM_EMAIL=noreply@koom.jp
SENDGRID_FROM_NAME=koom

# Twilio
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=

# S3 / R2
STORAGE_USE_R2=false
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_STORAGE_BUCKET_NAME=koom-files
AWS_S3_REGION_NAME=ap-northeast-1
AWS_S3_ENDPOINT_URL=          # R2: https://<ACCOUNT_ID>.r2.cloudflarestorage.com
AWS_S3_PUBLIC_BASE_URL=       # CDN: https://cdn.koom.jp

# JWT
JWT_SECRET=
JWT_EXPIRE_HOURS=720

# 배송 추적
SMART_TRACKER_API_KEY=
TRACKING_CACHE_MINUTES=30

# GMO-PG (기존)
GMO_SHOP_ID=
GMO_SHOP_PASS=
GMO_SANDBOX=true
GMO_TIMEOUT=30
```
