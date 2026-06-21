# Cart API

고객별 장바구니. 제목·옵션·최종 가격을 저장하며 상품과 느슨하게 연결된다.

Base URL: `/api/cart/`

---

## 엔드포인트 목록

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/cart/{customer_id}/` | 고객 장바구니 조회 (없으면 빈 카트 생성) |
| DELETE | `/api/cart/{customer_id}/` | 장바구니 전체 비우기 |
| POST | `/api/cart/{customer_id}/items/` | 항목 추가 |
| PATCH | `/api/cart/{customer_id}/items/{item_id}/` | 항목 수정 (수량·옵션·가격) |
| DELETE | `/api/cart/{customer_id}/items/{item_id}/` | 항목 삭제 |
| GET | `/api/cart/{customer_id}/page/` | 장바구니 화면 데이터 (JPY 가격·포인트 포함) |
| GET | `/api/cart/{customer_id}/checkout/` | 결제 화면 통합 데이터 |

---

## GET `/api/cart/{customer_id}/page/`

장바구니 화면에 필요한 데이터. 상품 목록(JPY 환산 가격·포인트), 요약, 배송 예상.

### Response

```json
{
  "items": [
    {
      "id": 1,
      "title": "어드밴스드 스네일 96 에센스",
      "brand": "COSRX",
      "site_name": "올리브영",
      "price_jpy": 1028,
      "quantity": 2,
      "total_jpy": 2056,
      "points_earn": 20,
      "options": [{"name": "용량", "value": "100ml"}],
      "product_url": "https://..."
    }
  ],
  "summary": {
    "total_jpy": 2056,
    "total_points_earn": 20
  },
  "delivery": {
    "stages": [
      {"key": "receive", "label": "상품 입고", "days": 3},
      {"key": "inspect", "label": "상품 검수", "days": 1},
      {"key": "kr_ship", "label": "한국발송", "days": 1},
      {"key": "intl_ship", "label": "국제 배송", "days": 5},
      {"key": "jp_ship", "label": "일본 배송", "days": 3}
    ],
    "total_days": 13,
    "estimated_arrival_date": "2026-06-22",
    "estimated_arrival_label": "오늘로부터 약 13일"
  }
}
```

---

## GET `/api/cart/{customer_id}/checkout/`

결제 화면에 필요한 모든 데이터 통합 반환.

### Response 구조

| 키 | 설명 |
|----|------|
| `items` | 상품 목록 (brand, site_name, points_earn, quantity, price_jpy) |
| `addresses` | 고객 배송지 목록 (is_default로 기본 배송지 식별) |
| `points.balance` | 현재 보유 포인트 |
| `points.earn_this_order` | 이번 주문 예상 적립 포인트 |
| `points.rules` | 포인트 적립 규칙 표시용 데이터 |
| `coupons` | 사용 가능한 쿠폰 목록 (미사용 + 유효기간 내) |
| `order_summary` | 주문 금액 요약 |
| `policies.refund` | 취소·환불 정책 (content.Policy type=refund, is_current=True) |
| `policies.cancel` | 배송 정책 (content.Policy type=shipping, is_current=True) |
| `payment_methods` | 결제 수단 목록 |

### `points.rules` 예시

```json
{
  "rate_pct": 1.0,
  "threshold_jpy": 1000,
  "points_to_koom_rate": 1.0,
  "description": "1000엔마다 1.0% 적립 | 1포인트 = 1.0 koom"
}
```

포인트 규칙 SiteConfig 키:
- `DK_POINTS_RATE` (group=pricing, 기본 0.01) — 적립률
- `POINTS_THRESHOLD_JPY` (기본 1000) — N엔마다 적립
- `POINTS_TO_KOOM_RATE` (기본 1.0) — 1포인트 = N koom

### `order_summary` 예시

```json
{
  "product_price_jpy": 2056,
  "intl_shipping_jpy": 800,
  "customs_estimate_jpy": 0,
  "subtotal_jpy": 2856,
  "coupon_discount_jpy": 0,
  "points_applied_jpy": 0,
  "total_jpy": 2856,
  "points_earn": 20
}
```

쿠폰·포인트 적용 금액은 프론트가 선택 후 주문 생성 시 서버에서 최종 확정.

---

## GET `/api/cart/{customer_id}/`

고객의 장바구니를 반환한다. 없으면 빈 카트를 생성해 반환.

### Path Parameters

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `customer_id` | string | 고객 식별자 (이메일·UUID 등, 호출측 결정) |

### Response Body (200 OK)

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | integer | 카트 ID |
| `customer_id` | string | 고객 식별자 |
| `items` | array | 장바구니 항목 배열 |
| `item_count` | integer | 총 수량 합계 |
| `total_price` | float | `price_final × quantity` 합계 |
| `created_at` | string | 생성 시각 |
| `updated_at` | string | 수정 시각 |

**`items` 항목 구조**

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | integer | 항목 ID |
| `product` | integer\|null | 연결된 Product ID |
| `product_detail` | object\|null | Product 전체 정보 (is_limited 뱃지 포함) |
| `product_url` | string | 상품 URL |
| `title` | string | 상품 제목 |
| `options` | array | 선택된 옵션 목록 |
| `price_final` | float | 최종 확정 가격 |
| `currency` | string | 통화 코드 |
| `quantity` | integer | 수량 |
| `created_at` | string | 추가 시각 |

**`options` 구조**

```json
[
  {"name": "색상", "value": "블랙"},
  {"name": "사이즈", "value": "L"}
]
```

### Response 예시

```json
{
  "id": 1,
  "customer_id": "user@example.com",
  "items": [
    {
      "id": 3,
      "product": 42,
      "product_detail": {
        "id": 42,
        "title": "무선 블루투스 이어폰",
        "is_limited": false,
        ...
      },
      "product_url": "https://www.coupang.com/vp/products/123456",
      "title": "무선 블루투스 이어폰",
      "options": [
        {"name": "색상", "value": "블랙"}
      ],
      "price_final": 22500,
      "currency": "KRW",
      "quantity": 2,
      "created_at": "2026-06-01T10:00:00+09:00",
      "updated_at": "2026-06-01T10:00:00+09:00"
    }
  ],
  "item_count": 2,
  "total_price": 45000,
  "created_at": "2026-06-01T09:00:00+09:00",
  "updated_at": "2026-06-01T10:00:00+09:00"
}
```

---

## DELETE `/api/cart/{customer_id}/`

장바구니의 모든 항목을 삭제한다. 카트 자체는 유지.

### Response Body (200 OK)

비워진 카트 객체 (items 빈 배열).

---

## POST `/api/cart/{customer_id}/items/`

장바구니에 항목을 추가한다.

### Request Body

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `title` | string | ✅ | 상품 제목 |
| `price_final` | float | ✅ | 최종 확정 가격 |
| `product_id` | integer | ❌ | DB Product ID (있으면 product_url 자동 설정) |
| `product_url` | string | ❌ | 상품 URL |
| `options` | array | ❌ | 선택된 옵션 목록 |
| `currency` | string | ❌ | 통화 코드 (기본 `KRW`) |
| `quantity` | integer | ❌ | 수량 (기본 1, 최소 1) |

### Request 예시

```json
{
  "product_id": 42,
  "title": "무선 블루투스 이어폰",
  "options": [
    {"name": "색상", "value": "블랙"}
  ],
  "price_final": 22500,
  "currency": "KRW",
  "quantity": 2
}
```

### Response Body (201 Created)

추가된 CartItem 객체.

---

## PATCH `/api/cart/{customer_id}/items/{item_id}/`

항목의 수량·옵션·가격을 수정한다.

### Request Body (모두 optional)

| 필드 | 타입 | 설명 |
|------|------|------|
| `quantity` | integer | 새 수량 (최소 1) |
| `options` | array | 새 옵션 목록 |
| `price_final` | float | 새 최종 가격 |

### Response Body (200 OK)

수정된 CartItem 객체.

### 에러 응답

| 상태 코드 | 조건 |
|-----------|------|
| `404 Not Found` | 해당 customer_id + item_id 조합이 없음 |

---

## DELETE `/api/cart/{customer_id}/items/{item_id}/`

장바구니에서 특정 항목을 제거한다.

### Response Body (204 No Content)

---

## DB 모델 구조

### Cart

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | BigAutoField | PK |
| `customer_id` | CharField(255) | 고객 식별자 (unique, 인덱스) |
| `created_at` | DateTimeField | 생성 시각 |
| `updated_at` | DateTimeField | 수정 시각 |

### CartItem

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | BigAutoField | PK |
| `cart` | ForeignKey(Cart) | 소속 카트 |
| `product` | ForeignKey(Product)\|null | 연결된 DB 상품 (optional) |
| `product_url` | URLField(2048) | 상품 URL |
| `title` | CharField(1024) | 상품 제목 |
| `options` | JSONField | 선택 옵션 `[{name, value}]` |
| `price_final` | FloatField | 최종 확정 가격 |
| `currency` | CharField(10) | 통화 코드 |
| `quantity` | PositiveIntegerField | 수량 |
| `created_at` | DateTimeField | 추가 시각 |
| `updated_at` | DateTimeField | 수정 시각 |
