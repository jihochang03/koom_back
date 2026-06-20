# Wishlist API

고객별 찜 목록.

Base URL: `/api/wishlist/`

---

## 엔드포인트 목록

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/wishlist/{customer_id}/` | 찜 목록 조회 |
| POST | `/api/wishlist/{customer_id}/items/` | 찜 추가 (이미 있으면 200) |
| DELETE | `/api/wishlist/{customer_id}/items/{item_id}/` | 찜 삭제 |

---

## GET `/api/wishlist/{customer_id}/`

고객의 찜 목록 반환.

### Response Body (200 OK)

배열. 각 항목:

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | integer | PK |
| `customer_id` | string | 고객 식별자 |
| `product_url` | string | 상품 URL |
| `site_domain` | string | 사이트 도메인 |
| `title` | string | 상품명 |
| `images` | string[] | 이미지 URL 배열 |
| `price_snapshot` | float\|null | 찜 당시 가격 |
| `currency` | string | 통화 코드 |
| `options` | array | 옵션 [{name, value}] |
| `created_at` | string | 찜한 시각 |

---

## POST `/api/wishlist/{customer_id}/items/`

찜 항목 추가. 같은 `product_url`이 이미 있으면 200으로 기존 항목 반환.

### Request Body

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `product_url` | string | ✅ | 상품 URL |
| `title` | string | ❌ | 상품명 |
| `site_domain` | string | ❌ | 사이트 도메인 |
| `images` | string[] | ❌ | 이미지 URL 배열 |
| `price_snapshot` | float | ❌ | 현재 가격 |
| `currency` | string | ❌ | 통화 코드 (기본 KRW) |
| `options` | array | ❌ | 선택 옵션 |

### Response

- `201 Created` — 새로 추가
- `200 OK` — 이미 존재 (기존 항목 반환)

---

## DELETE `/api/wishlist/{customer_id}/items/{item_id}/`

찜 항목 삭제.

### Response Body

`204 No Content`

### 에러 응답

| 상태 코드 | 조건 |
|-----------|------|
| `404 Not Found` | 해당 item_id가 customer_id에 속하지 않음 |

---

## DB 모델 구조

### WishlistItem

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | BigAutoField | PK |
| `customer_id` | CharField(255) | 고객 식별자 (인덱스) |
| `product_url` | URLField(2048) | 상품 URL |
| `site_domain` | CharField(255) | 사이트 도메인 (인덱스) |
| `title` | CharField(1024) | 상품명 |
| `images` | JSONField | 이미지 URL 배열 |
| `price_snapshot` | FloatField\|null | 찜 당시 가격 |
| `currency` | CharField(10) | 통화 코드 |
| `options` | JSONField | 선택 옵션 [{name, value}] |
| `created_at` | DateTimeField | 찜한 시각 |

unique_together: `(customer_id, product_url)`
