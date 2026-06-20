# Mypage API

고객별 주소·쿠폰·포인트·알림 설정.

Base URL: `/api/mypage/`

---

## 엔드포인트 목록

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/mypage/{customer_id}/addresses/` | 주소 목록 |
| POST | `/api/mypage/{customer_id}/addresses/` | 주소 추가 |
| PATCH | `/api/mypage/{customer_id}/addresses/{addr_id}/` | 주소 수정 |
| DELETE | `/api/mypage/{customer_id}/addresses/{addr_id}/` | 주소 삭제 |
| GET | `/api/mypage/{customer_id}/coupons/` | 쿠폰 목록 |
| GET | `/api/mypage/{customer_id}/points/` | 포인트 잔액 + 내역 |
| GET | `/api/mypage/{customer_id}/notifications/` | 알림 설정 조회 |
| PATCH | `/api/mypage/{customer_id}/notifications/` | 알림 설정 변경 |

---

## 주소 API

### POST `/api/mypage/{customer_id}/addresses/`

#### 수취인 정보 (통관·배송)

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `name` | string | ✅ | 수취인명 — 한자 또는 현지 표기 (예: `辛 東赫`) |
| `name_kana` | string | △ | 가타카나 (일본 배송 시 DHUB `receiver_name_voice` 필수. 예: `シン ドンヒョク`) |
| `name_en` | string | △ | 영문 (통관 서류용. 예: `SHIN DONGHYUK`) |
| `date_of_birth` | string | △ | 생년월일 `YYYY-MM-DD` (한국→일본 통관 필수) |
| `phone` | string | ✅ | 연락처 (예: `+81-80-9122-3497`) |

#### 배송지 주소

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `country` | string | ❌ | ISO 3166-1 alpha-2 국가 코드 (기본값: `JP`) |
| `zipcode` | string | ✅ | 우편번호 |
| `address1` | string | ✅ | 기본 주소 |
| `address2` | string | ❌ | 상세 주소 |
| `is_default` | boolean | ❌ | 기본 배송지 여부 (`true` 시 기존 기본 배송지 자동 해제) |

> `is_default=true`인 주소가 DHUB 주문 등록 시 기본 배송지로 사용된다.  
> `name_kana` 미입력 시 DHUB API에서 경고 발생 가능 (일본 배송 필수 필드).

### GET `/api/mypage/{customer_id}/addresses/`

응답 예시:

```json
[
  {
    "id": 1,
    "customer_id": "user_123",
    "name": "辛 東赫",
    "name_kana": "シン ドンヒョク",
    "name_en": "SHIN DONGHYUK",
    "date_of_birth": "1983-09-06",
    "phone": "+81-80-9122-3497",
    "country": "JP",
    "zipcode": "547-0024",
    "address1": "大阪府大阪市平野区瓜破 1-5-1-3F",
    "address2": "",
    "is_default": true,
    "created_at": "2026-06-19T10:00:00+09:00",
    "updated_at": "2026-06-19T10:00:00+09:00"
  }
]
```

---

## 쿠폰 API

### GET `/api/mypage/{customer_id}/coupons/`

Query: `?used=true|false` — 사용 여부 필터

응답 항목:

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | integer | PK |
| `coupon` | object | 쿠폰 정보 |
| `is_used` | boolean | 사용 여부 |
| `used_at` | string\|null | 사용 시각 |
| `order_number` | string | 사용된 주문번호 |

---

## 포인트 API

### GET `/api/mypage/{customer_id}/points/`

```json
{
  "balance": 3500,
  "logs": [
    {
      "id": 1,
      "delta": 500,
      "reason": "earn_order",
      "reason_display": "주문 적립",
      "balance_after": 3500,
      "order_number": "ORD-20260608-A1B2C3",
      "created_at": "2026-06-08T10:00:00+09:00"
    }
  ]
}
```

---

## 알림 설정 API

### PATCH `/api/mypage/{customer_id}/notifications/`

| 필드 | 타입 | 설명 |
|------|------|------|
| `order_status_push` | boolean | 주문 상태 푸시 알림 |
| `order_status_email` | boolean | 주문 상태 이메일 알림 |
| `marketing_push` | boolean | 마케팅 푸시 알림 |
| `marketing_email` | boolean | 마케팅 이메일 알림 |

---

## DB 모델 구조

### UserAddress

| 필드 | 타입 | 설명 |
|------|------|------|
| `customer_id` | CharField(255) | 고객 ID |
| `name` | CharField(100) | 수취인명 (한자/현지 표기) |
| `name_kana` | CharField(100) | 가타카나 — DHUB `receiver_name_voice` |
| `name_en` | CharField(100) | 영문 — 통관 서류용 |
| `date_of_birth` | DateField\|null | 생년월일 — 한국→일본 통관 필수 |
| `phone` | CharField(20) | 연락처 |
| `country` | CharField(2) | 국가 코드 ISO 3166-1 (기본: `JP`) |
| `zipcode` | CharField(10) | 우편번호 |
| `address1` | CharField(500) | 기본 주소 |
| `address2` | CharField(500) | 상세 주소 |
| `is_default` | BooleanField | 기본 배송지 여부 |

### Coupon
`code`(unique), `name`, `discount_type`(fixed/percent), `discount_value`, `min_order_amount`, `max_discount_amount`, `valid_from`, `valid_until`, `is_active`, `usage_limit`

### UserCoupon
`customer_id`, FK(Coupon), `order_number`, `used_at`, `issued_at`

### PointLog
`customer_id`, `delta`, `reason`, `order_number`, `balance_after`, `note`

### NotificationSetting
`customer_id`(unique), `order_status_push`, `order_status_email`, `marketing_push`, `marketing_email`

---

## 어드민 쿠폰 관리 (Section 18)

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/mypage/coupons/` | 쿠폰 전체 목록 (`?is_active=true\|false`) |
| POST | `/api/mypage/coupons/` | 쿠폰 생성 |
| GET | `/api/mypage/coupons/{id}/` | 쿠폰 상세 |
| PATCH | `/api/mypage/coupons/{id}/` | 쿠폰 수정 |
| DELETE | `/api/mypage/coupons/{id}/` | 쿠폰 비활성화 (소프트 삭제) |
| POST | `/api/mypage/coupons/{id}/issue/` | 고객에게 쿠폰 발급 |

### POST `/api/mypage/coupons/`

Coupon 모델 전체 필드 지정 가능 (`code`, `name`, `discount_type`, `discount_value`, `min_order_amount`, `max_discount_amount`, `valid_from`, `valid_until`, `is_active`, `usage_limit`).

### POST `/api/mypage/coupons/{id}/issue/`

단일 발급:
```json
{ "customer_id": "user_123" }
```

대량 발급:
```json
{ "customer_ids": ["user_123", "user_456", "user_789"] }
```

이미 발급된 고객은 건너뜀 (중복 발급 방지).
