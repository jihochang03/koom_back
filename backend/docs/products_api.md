# Products API

상품 목록 크롤 결과를 저장하고, 카테고리 분류·상세 크롤 상태·입고/도착 상태를 관리하는 앱.

Base URL: `/api/products/`

---

## 엔드포인트 목록

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/products/` | 상품 목록 조회 |
| POST | `/api/products/batch/` | 상품 일괄 저장 (목록 크롤 결과) |
| GET | `/api/products/categories/` | 사용 중인 카테고리 목록 |
| PATCH | `/api/products/{id}/category/` | 카테고리 변경 |
| PATCH | `/api/products/{id}/badges/` | 뱃지 변경 (is_prima, is_limited) |
| POST | `/api/products/{id}/detail/` | 상세 데이터 저장 (scraper-agent → Django) |
| POST | `/api/products/{id}/refresh/` | 재크롤 요청 (detail_status → pending) |
| GET | `/api/products/{id}/page/` | 상품 상세 페이지 통합 데이터 |
| PATCH | `/api/products/{id}/inbound/` | 입고 정보 업데이트 (오더번호·송장번호·도착상태) |
| GET | `/api/products/{id}/arrival-photos/` | 도착 사진 목록 조회 |
| POST | `/api/products/{id}/arrival-photos/` | 도착 사진 업로드 (multipart) |
| DELETE | `/api/products/arrival-photos/{photo_id}/` | 도착 사진 삭제 |

---

## GET `/api/products/`

저장된 상품 목록을 페이지네이션으로 조회한다.

### Query Parameters

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `category` | string | 카테고리로 필터링 (빈 문자열이면 미분류만) |
| `source_url` | string | 수집 출처 URL로 필터링 |
| `page` | integer | 페이지 번호 (기본 1, 페이지당 20개) |

### Response Body (200 OK)

```json
{
  "count": 80,
  "next": "http://localhost:8000/api/products/?page=2",
  "previous": null,
  "results": [
    {
      "id": 1,
      "source_url": "https://www.coupang.com/np/search?q=이어폰",
      "url": "https://www.coupang.com/vp/products/123456",
      "product_id": "item_0",
      "title": "무선 블루투스 이어폰",
      "price_original": 29000,
      "price_discounted": 19900,
      "currency": "KRW",
      "images": ["https://..."],
      "brand": "삼성",
      "rating": 4.5,
      "review_count": 1230,
      "availability": "in_stock",
      "category": "이어폰",
      "detail_data": {},
      "detail_status": "pending",
      "detail_crawled_at": null,
      "created_at": "2026-06-01T10:00:00+09:00",
      "updated_at": "2026-06-01T10:00:00+09:00"
    }
  ]
}
```

---

## POST `/api/products/batch/`

목록 크롤 결과로 얻은 상품들을 일괄 저장한다.  
같은 `url`의 상품이 이미 있으면 업데이트(upsert)하고 `detail_status`를 `pending`으로 초기화한다.

> **Note:** scraper-agent의 `/api/products/batch`를 통해 호출하면 저장 후 자동으로 백그라운드 prefetch 큐에 등록된다.

### Request Body

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `source_url` | string | ❌ | 수집 출처 목록 페이지 URL |
| `category` | string | ❌ | 일괄 적용할 카테고리 레이블 |
| `items` | array | ✅ | 상품 항목 배열 (아래 참조) |

**`items` 항목 필드**

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `url` | string (URL) | ✅ | 상품 상세 URL |
| `product_id` | string | ❌ | 사이트 내 상품 ID |
| `title` | string | ❌ | 상품명 |
| `price_original` | number\|null | ❌ | 원가 |
| `price_discounted` | number\|null | ❌ | 할인가 |
| `currency` | string | ❌ | 통화 코드 (기본 `KRW`) |
| `images` | string[] | ❌ | 이미지 URL 배열 |
| `brand` | string | ❌ | 브랜드명 |
| `rating` | number\|null | ❌ | 평점 |
| `review_count` | integer\|null | ❌ | 리뷰 수 |
| `availability` | string | ❌ | 재고 상태 |

### Request 예시

```json
{
  "source_url": "https://www.coupang.com/np/search?q=이어폰",
  "category": "이어폰",
  "items": [
    {
      "url": "https://www.coupang.com/vp/products/123456",
      "product_id": "item_0",
      "title": "무선 블루투스 이어폰",
      "price_original": 29000,
      "price_discounted": 19900,
      "currency": "KRW",
      "images": ["https://..."],
      "availability": "in_stock"
    }
  ]
}
```

### Response Body (201 Created)

저장된 상품 객체 배열. 각 항목은 `GET /api/products/` 결과 구조와 동일.

---

## GET `/api/products/categories/`

현재 DB에 존재하는 고유 카테고리 레이블 목록을 반환한다.

### Response Body (200 OK)

```json
{
  "categories": ["가전", "이어폰", "패션"]
}
```

---

## PATCH `/api/products/{id}/category/`

사용자가 상품에 카테고리를 지정하거나 변경한다.

### Request Body

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `category` | string | ✅ | 새 카테고리 레이블 (빈 문자열 = 미분류) |

### Response Body (200 OK)

업데이트된 상품 객체.

### 에러 응답

| 상태 코드 | 조건 |
|-----------|------|
| `404 Not Found` | 해당 ID 없음 |

---

## POST `/api/products/{id}/detail/`

scraper-agent가 크롤링 완료 후 상세 데이터를 밀어넣는 웹훅.

### Request Body

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `detail_data` | object | ✅ | 크롤링된 상세 JSON |
| `detail_status` | string | ❌ | 상태 (`ready` 또는 `failed`, 기본 `ready`) |

**`detail_status` 허용값**

| 값 | 설명 |
|----|------|
| `pending` | 대기 |
| `prefetching` | 수집 중 |
| `ready` | 완료 |
| `failed` | 실패 |

### Response Body (200 OK)

업데이트된 상품 객체. `detail_crawled_at`이 현재 시각으로 갱신됨.

---

## POST `/api/products/{id}/refresh/`

`detail_status`를 `pending`으로 되돌려 재크롤을 요청한다.

> **Note:** scraper-agent의 `/api/products/{id}/refresh`를 통해 호출하면 즉시 prefetch 큐에도 재등록된다.

### Response Body (200 OK)

업데이트된 상품 객체.

---

## DB 모델 구조

### Product

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | BigAutoField | PK |
| `source_url` | URLField(2048) | 수집 출처 목록 페이지 URL |
| `url` | URLField(2048) | 상품 상세 URL (upsert 키, 인덱스) |
| `product_id` | CharField(255) | 사이트 내부 상품 ID |
| `title` | CharField(1024) | 상품명 |
| `price_original` | FloatField\|null | 원가 |
| `price_discounted` | FloatField\|null | 할인가 |
| `currency` | CharField(10) | 통화 코드 |
| `images` | JSONField | 이미지 URL 배열 |
| `brand` | CharField(255) | 브랜드명 |
| `rating` | FloatField\|null | 평점 |
| `review_count` | IntegerField\|null | 리뷰 수 |
| `availability` | CharField(50) | 재고 상태 |
| `category` | CharField(100) | 사용자 지정 카테고리 (인덱스) |
| `is_prima` | BooleanField | 현지 판매자 확인 필요 뱃지 (인덱스) |
| `is_limited` | BooleanField | 한정판 뱃지 (인덱스) |
| `detail_data` | JSONField | 사전 크롤된 상세 데이터 |
| `detail_status` | CharField(20) | 크롤 상태 (인덱스) |
| `detail_crawled_at` | DateTimeField\|null | 마지막 상세 크롤 시각 |
| `created_at` | DateTimeField | 생성 시각 |
| `mall` | FK(KoreanMall)\|null | 소속 쇼핑몰 |
| `is_recommended` | BooleanField | 추천 상품 여부 |
| `updated_at` | DateTimeField | 수정 시각 |

---

## GET `/api/products/{id}/page/`

상품 상세 페이지에 필요한 모든 데이터를 한 번에 반환한다.

### Response

```json
{
  "product": { "id": 1, "brand": "COSRX", "title": "어드밴스드 스네일 96 무신 파워 에센스", "price_original": 18000, "price_discounted": 14400, "currency": "KRW", "images": ["https://..."], ... },
  "pricing_jpy": {
    "product_price_jpy": 1028,
    "intl_shipping_jpy": 800,
    "customs_estimate_jpy": 0,
    "total_jpy": 2128,
    "duty_free": true,
    "disclaimer": "추정 금액입니다. 실제 관세·환율은 결제(송금) 시점 및 품목·신고에 따라 달라질 수 있습니다."
  },
  "exchange_rate": { "krw_per_jpy": 9.42, "jpy_per_krw": 0.1061 },
  "delivery": {
    "stages": [
      {"key": "receive",   "label": "상품 입고",  "days": 3},
      {"key": "inspect",   "label": "상품 검수",  "days": 1},
      {"key": "kr_ship",   "label": "한국발송",   "days": 1},
      {"key": "intl_ship", "label": "국제 배송",  "days": 5},
      {"key": "jp_ship",   "label": "일본 배송",  "days": 3}
    ],
    "total_days": 13,
    "estimated_arrival_date": "2026-06-22",
    "estimated_arrival_label": "오늘로부터 약 13일"
  },
  "payment_methods": [
    {"id": 1, "name": "신용카드", "code": "credit_card", "icon_url": "", "display_order": 0}
  ],
  "order_notices": [
    {"id": 1, "content": "주문 후 변경/취소는 구매 확정 전까지만 가능합니다.", "display_order": 0}
  ]
}
```

### 배송 소요일 설정 (SiteConfig, group=delivery)

| key | 기본값 | 설명 |
|-----|--------|------|
| `DELIVERY_DAYS_RECEIVE` | 3 | 상품 입고 소요일 |
| `DELIVERY_DAYS_INSPECT` | 1 | 상품 검수 소요일 |
| `DELIVERY_DAYS_KR_SHIP` | 1 | 한국발송 소요일 |
| `DELIVERY_DAYS_INTL_SHIP` | 5 | 국제 배송 소요일 |
| `DELIVERY_DAYS_JP_SHIP` | 3 | 일본 배송 소요일 |

국제 배송비 기본값: `SiteConfig` key=`DEFAULT_INTL_SHIPPING_JPY` (기본 800엔)

---

## PATCH `/api/products/{id}/inbound/`

입고 정보(오더번호, 송장번호, 도착 상태 등)를 업데이트한다.  
`arrival_status=arrived` 지정 시 `arrived_at` 자동 기록.  
`arrival_status=inspected` 지정 시 `inspected_at` 자동 기록.

### Request Body (변경할 필드만 포함)

| 필드 | 타입 | 설명 |
|------|------|------|
| `inbound_order_number` | string | 구매 오더번호 (이메일 수신 후 입력) |
| `inbound_tracking_number` | string | 송장번호 |
| `inbound_courier` | string | 택배사명 (예: CJ대한통운, 우체국) |
| `arrival_status` | string | 도착 상태 (허용값 참조) |
| `inspection_required` | boolean | 검수 서비스 신청 여부 |
| `inbound_note` | string | 메모 |

**`arrival_status` 허용값**

| 값 | 설명 |
|----|------|
| `ordered` | 주문완료 (기본) |
| `in_transit` | 배송중 |
| `arrived` | 도착 |
| `inspected` | 검수완료 |

### Request 예시

```json
{
  "inbound_order_number": "ORD-2025-001234",
  "inbound_tracking_number": "123456789012",
  "inbound_courier": "CJ대한통운",
  "arrival_status": "in_transit"
}
```

---

## POST `/api/products/{id}/arrival-photos/`

도착 사진을 업로드한다 (`multipart/form-data`).  
사진 저장 시 상품의 `arrival_status`가 자동으로 `arrived`로 갱신된다.

### Request (multipart)

| 필드 | 필수 | 설명 |
|------|------|------|
| `photo` | 필수 | 이미지 파일 (jpg, png 등) |
| `note` | 선택 | 메모 문자열 |

### Response (201 Created)

```json
{
  "id": 3,
  "photo_url": "http://localhost:8000/media/arrival_photos/2025/06/product_001.jpg",
  "note": "",
  "captured_at": "2025-06-19T10:30:00+09:00"
}
```

---

## DB 모델 — 입고/도착 관련 추가 필드

### Product — 입고 필드 (기존 Product 모델에 추가)

| 필드 | 타입 | 설명 |
|------|------|------|
| `inbound_order_number` | CharField(100) | 구매 오더번호 (인덱스) |
| `inbound_tracking_number` | CharField(100) | 송장번호 (인덱스) |
| `inbound_courier` | CharField(50) | 택배사명 |
| `arrival_status` | CharField(15) | 도착 상태 (인덱스) |
| `inspection_required` | BooleanField | 검수 서비스 신청 여부 |
| `arrived_at` | DateTimeField\|null | 도착 확인 시각 (자동 기록) |
| `inspected_at` | DateTimeField\|null | 검수 완료 시각 (자동 기록) |
| `inbound_note` | TextField | 입고 메모 |

### ProductArrivalPhoto — 도착 사진

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | BigAutoField | PK |
| `product` | FK(Product) | 상품 (related_name: arrival_photos) |
| `photo` | FileField | 사진 파일 (저장 경로: `media/arrival_photos/YYYY/MM/`) |
| `note` | CharField(255) | 메모 |
| `captured_at` | DateTimeField | 촬영/업로드 시각 (자동 기록) |

사진 저장 시 `product.arrival_status`가 `arrived` 미만이면 자동으로 `arrived`로 갱신된다.
