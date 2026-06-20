# Orders API

주문 및 결제 묶음(그룹) 관리.

Base URL: `/api/orders/`

---

## 엔드포인트 목록

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/orders/` | 주문 목록 조회 |
| GET | `/api/orders/groups/` | 그룹 목록 조회 |
| POST | `/api/orders/groups/create/` | 주문 그룹 생성 (장바구니 → 주문) |
| GET | `/api/orders/groups/{group_number}/` | 그룹 상세 |
| GET | `/api/orders/{order_number}/` | 주문 상세 |
| PATCH | `/api/orders/{order_number}/status/` | 상태 업데이트 (어드민) |
| PATCH | `/api/orders/{order_number}/admin/` | 어드민 전용 업데이트 |

---

## POST `/api/orders/groups/create/`

장바구니 항목을 하나의 결제 묶음(OrderGroup)으로 변환해 주문을 생성한다.

### Request Body

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `customer_id` | string | ✅ | 고객 식별자 |
| `items` | array | ✅ | 주문 항목 배열 |
| `bundle_fee` | float | ❌ | 묶음 배송 수수료 (기본 0) |
| `coupon_discount` | float | ❌ | 쿠폰 할인 (기본 0) |
| `point_discount` | float | ❌ | 포인트 할인 (기본 0) |

**`items` 항목 필드**

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `product_url` | string | ✅ | 상품 URL |
| `title` | string | ✅ | 상품명 |
| `price_product` | float | ✅ | 상품가 (KRW) |
| `price_total` | float | ✅ | 예상 총액 (KRW) |
| `options` | array | ❌ | 선택 옵션 [{name, value}] |
| `quantity` | integer | ❌ | 수량 (기본 1) |
| `price_domestic_shipping` | float | ❌ | 예상 일본 내 배송비 |
| `price_intl_shipping` | float | ❌ | 예상 국제배송비 |
| `price_tariff` | float | ❌ | 예상 관부가세 |
| `price_fee` | float | ❌ | 수수료 |
| `site_domain` | string | ❌ | 사이트 도메인 |
| `product_snapshot` | object | ❌ | 주문 당시 상품 스냅샷 |
| `estimated_delivery_min` | integer | ❌ | 최소 예상 배송일 (일) |
| `estimated_delivery_max` | integer | ❌ | 최대 예상 배송일 (일) |

### Response Body (201 Created)

생성된 OrderGroup (orders 배열 포함).

---

## GET `/api/orders/`

### Query Parameters

| 파라미터 | 설명 |
|----------|------|
| `customer_id` | 고객 식별자 필터 |
| `status` | 주문 상태 필터 |

---

## PATCH `/api/orders/{order_number}/status/`

### Request Body

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `status` | string | ✅ | 새 상태 |
| `tracking_number` | string | ❌ | 운송장 번호 |
| `estimated_delivery_min` | integer | ❌ | 최소 예상 배송일 |
| `estimated_delivery_max` | integer | ❌ | 최대 예상 배송일 |

**`status` 허용값**

| 값 | 설명 |
|----|------|
| `pending` | 주문 대기 |
| `paid` | 결제 완료 |
| `purchasing` | 현지 구매 중 |
| `shipping_domestic` | 현지 배송 중 |
| `inspection` | 검수 중 |
| `shipping_intl` | 국제 배송 중 |
| `delivered` | 배송 완료 |
| `cancelled` | 취소 |
| `refunded` | 환불 완료 |
| `partial_refund` | 부분 환불 |

---

## PATCH `/api/orders/{order_number}/admin/`

DK 부담액·검수 이슈·환불 등 어드민 전용 필드 업데이트.

| 필드 | 타입 | 설명 |
|------|------|------|
| `price_dk_burden` | float | DK 부담액 (가격 오차) |
| `price_actual` | float | 실제 구매가 |
| `admin_notes` | string | 어드민 메모 |
| `inspection_notes` | string | 검수 이슈 메모 |
| `refund_amount` | float | 환불 금액 |
| `refund_reason` | string | 환불 사유 |

---

## DB 모델 구조

### OrderGroup

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | BigAutoField | PK |
| `group_number` | CharField(50) | 그룹번호 (unique, e.g. GRP-20260608-A1B2C3) |
| `customer_id` | CharField(255) | 고객 식별자 (인덱스) |
| `status` | CharField(30) | 그룹 상태 (인덱스) |
| `bundle_fee` | FloatField | 묶음 배송 수수료 |
| `coupon_discount` | FloatField | 쿠폰 할인 |
| `point_discount` | FloatField | 포인트 할인 |
| `total_paid` | FloatField | 실제 결제 금액 |
| `currency` | CharField(10) | 통화 코드 |
| `paid_at` | DateTimeField\|null | 결제 시각 |
| `created_at` | DateTimeField | 생성 시각 |
| `updated_at` | DateTimeField | 수정 시각 |

### Order

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | BigAutoField | PK |
| `order_number` | CharField(50) | 주문번호 (unique, e.g. ORD-20260608-A1B2C3) |
| `group` | ForeignKey(OrderGroup) | 소속 그룹 |
| `customer_id` | CharField(255) | 고객 식별자 (인덱스) |
| `site_domain` | CharField(255) | 사이트 도메인 (인덱스) |
| `product_url` | URLField(2048) | 상품 URL |
| `title` | CharField(1024) | 상품명 |
| `options` | JSONField | 선택 옵션 [{name, value}] |
| `quantity` | PositiveIntegerField | 수량 |
| `price_product` | FloatField | 상품가 |
| `price_domestic_shipping` | FloatField | 예상 일본 내 배송비 |
| `price_intl_shipping` | FloatField | 예상 국제배송비 |
| `price_tariff` | FloatField | 예상 관부가세 |
| `price_fee` | FloatField | 수수료 |
| `price_total` | FloatField | 예상 총액 |
| `currency` | CharField(10) | 통화 코드 |
| `price_dk_burden` | FloatField | DK 부담액 (어드민) |
| `price_actual` | FloatField\|null | 실제 구매가 (어드민) |
| `status` | CharField(30) | 주문 상태 (인덱스) |
| `tracking_number` | CharField(255) | 운송장 번호 |
| `estimated_delivery_min` | IntegerField\|null | 최소 예상 배송일 |
| `estimated_delivery_max` | IntegerField\|null | 최대 예상 배송일 |
| `product_snapshot` | JSONField | 주문 당시 상품 스냅샷 |
| `admin_notes` | TextField | 어드민 메모 |
| `inspection_notes` | TextField | 검수 이슈 메모 |
| `refund_amount` | FloatField\|null | 환불 금액 |
| `refund_reason` | TextField | 환불 사유 |
| `created_at` | DateTimeField | 생성 시각 |
| `updated_at` | DateTimeField | 수정 시각 |

---

## 주문 상세 서브리소스 API (Section 13)

### GET `/api/orders/{order_number}/status-log/`

상품별 진행 내역 (단계별 상태 이력).

**stage 허용값:**

| 값 | 설명 |
|----|------|
| `order_received` | 주문 접수 |
| `purchase_review` | 구매 검토 |
| `purchase_complete` | 구매 완료 |
| `pre_arrival` | 입고 대기 |
| `arrived` | 입고 완료 |
| `inspection_in_progress` | 검수 중 |
| `inspection_complete` | 검수 완료 |
| `preparing_dispatch` | 출고 준비 |
| `intl_shipping` | 국제 배송 중 |
| `jp_carrier_handover` | 일본 배송사 인계 |
| `delivered` | 배송 완료 |
| `cancelled_or_refunded` | 취소/반품/환불 |

**responsible_party 허용값:** `dk` / `seller` / `logistics` / `carrier` / `system` / `customer`

### POST `/api/orders/{order_number}/status-log/`

| 필드 | 타입 | 필수 |
|------|------|------|
| `stage` | string | ✅ |
| `changed_at` | datetime | ❌ (기본: now) |
| `responsible_party` | string | ❌ |
| `memo` | string | ❌ |
| `available_actions` | array | ❌ |

---

### GET `/api/orders/{order_number}/action-log/`

어드민 액션 로그 (변경 이력).

**actor_type 허용값:** `system` / `operator` / `logistics` / `pg` / `carrier_api`

### POST `/api/orders/{order_number}/action-log/`

| 필드 | 타입 | 설명 |
|------|------|------|
| `changed_field` | string | 변경 항목 |
| `old_value` | any | 변경 전 값 |
| `new_value` | any | 변경 후 값 |
| `actor_type` | string | 처리 주체 유형 |
| `actor_id` | string | 운영자 ID |
| `reason` | string | 변경 사유 |

---

### GET `/api/orders/{order_number}/error/`

오차 정보 조회.

### PUT `/api/orders/{order_number}/error/`

오차 정보 등록/수정 (upsert).

| 필드 | 타입 | 설명 |
|------|------|------|
| `error_rate` | float | 오차율 (0.05 = 5%) |
| `error_amount` | float | 오차 금액 |
| `error_causes` | array | 원인 목록 |
| `handling_method` | string | 처리 방식 |
| `auto_processed` | boolean | 자동 처리 여부 |
| `cs_review_reason` | string | CS 전환 사유 |
| `additional_charge_amount` | float | 추가비용 요청액 |
| `additional_charge_sent_at` | datetime | 요청 발송 시각 |
| `additional_charge_accepted_at` | datetime | 고객 수락 시각 |

**handling_method 허용값:** `company_burden` / `cs_review` / `additional_charge` / `cancel` / `partial_refund`

**error_causes 예시값:** `price_change` / `ai_parsing_error` / `option_parsing_error` / `domestic_shipping_extra` / `intl_shipping_weight_diff` / `tax_tariff_extra` / `prima_risk` / `exchange_rate_diff`

---

### GET `/api/orders/{order_number}/pg/`

PG 결제 이력 목록.

### POST `/api/orders/{order_number}/pg/`

PG 거래 등록 (pg_transaction_id가 이미 있으면 update).

| 필드 | 타입 | 설명 |
|------|------|------|
| `pg_transaction_id` | string | PG 거래 ID (unique) |
| `auth_status` | string | 결제 상태 |
| `refund_amount` | float | 환불 금액 |
| `refund_requested_at` | datetime | 환불 요청 시각 |
| `refund_completed_at` | datetime | 환불 완료 시각 |
| `failure_reason` | string | 실패 사유 |
| `raw_payload` | object | PG 원본 응답 |

**auth_status 허용값:** `pending` / `auth_complete` / `capture_pending` / `captured` / `cancel_in_progress` / `cancelled` / `refunded` / `failed`

---

### Order 추가 필드 (migration 0002)

| 필드 | 타입 | 설명 |
|------|------|------|
| `product_copy_url` | string | 사본 URL (관세 제출용) |
| `product_category` | string | 상품 카테고리 |
| `prohibited_review` | JSON\|null | 금지/제한 품목 검토 결과 |
| `price_initial_payment` | float\|null | 최초 결제/가승인 금액 |
| `price_discount` | float | 할인 금액 |
| `price_points_used` | float | 포인트 사용액 |
| `price_final_charged` | float\|null | 최종 고객 청구 금액 |
| `company_burden_tariff` | float | 관부가세 대납금 |
| `company_burden_error_small` | float | 소오차 회사 부담 |
| `company_burden_shipping_error` | float | 배송비 오차 부담 |
| `company_burden_other` | float | 기타 운영 부담 |
| `refund_partial_error` | float | 오차 부분환불 |
| `refund_customer_request` | float | 고객 요청 환불 |
| `refund_inspection` | float | 검수 이슈 환불 |
| `refund_cancellation` | float | 취소 환불 |

---

## 상품 사본 API (Section 19)

### GET/PUT `/api/orders/{order_number}/snapshot/`

세관 제출용 구매 상품 사본 생성·조회 (어드민).

**PUT Request Body:**

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `product_name` | string | ✅ | 상품명 (한국어) |
| `product_name_en` | string | △ | 영문 품목명 (세관 Invoice 필수) |
| `purchase_price` | float | ✅ | 실제 구매 금액 |
| `product_price_at_purchase` | float | ✅ | 구매 완료 시점 상품가격 |
| `options` | array | ❌ | 옵션 [{name, value}] |
| `quantity` | integer | ❌ | 수량 (기본 1) |
| `seller` | string | ❌ | 판매처 |
| `site_domain` | string | ❌ | 쇼핑몰 도메인 |
| `product_url` | string | ❌ | 원본 URL |
| `images` | array | ❌ | 이미지 URL 목록 (링크 저장, 파일 저장 X) |
| `html_content` | string | ❌ | 크롤링 시점 HTML 원본 (선택) |

**PUT Response Body:** `_snap_data` (아래 ProductSnapshot 모델 참조)

> 스냅샷 저장 시 `Order.product_copy_url`이 `{SITE_BASE_URL}/snapshots/{snapshot_uuid}/`로 자동 업데이트된다.

### GET `/api/orders/snapshots/{snapshot_uuid}/` — JSON

UUID 기반 공개 사본 JSON (세관 제출용 링크).
- 인증 불필요
- `snapshot_uuid`는 UUID v4 형식

### GET `/api/orders/snapshots/{snapshot_uuid}/html/` — HTML 페이지

세관 제출용 HTML 렌더링 페이지.
- 인증 불필요
- 브라우저에서 직접 열거나 PDF 인쇄 가능
- Shipper(주식회사 DK) / Consignee / 상품 명세 / 이미지 포함

---

### DB 모델: ProductSnapshot

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | BigAutoField | PK |
| `order_number` | CharField(50) | 주문번호 (unique) |
| `snapshot_uuid` | UUIDField | 공개 URL용 식별자 (unique, editable=False) |
| `product_name` | CharField(500) | 한국어 품목명 |
| `product_name_en` | CharField(500) | 영문 품목명 (세관 Invoice 필수) |
| `purchase_price` | FloatField | 실제 구매 금액 |
| `product_price_at_purchase` | FloatField | 구매 완료 시점 상품가격 |
| `options` | JSONField\|null | 옵션 [{name, value}] |
| `quantity` | IntegerField | 수량 |
| `seller` | CharField(255) | 판매처 |
| `site_domain` | CharField(255) | 쇼핑몰 도메인 |
| `product_url` | URLField(1000) | 원본 URL |
| `images` | JSONField\|null | 이미지 URL 목록 |
| `html_content` | TextField | 크롤링 시점 HTML 원본 |
| `created_at` | DateTimeField | 생성 시각 |
