# CS API

고객 문의·취소 요청·환불 요청 관리.

Base URL: `/api/cs/`

---

## 엔드포인트 목록

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/cs/inquiries/` | 문의 목록 |
| POST | `/api/cs/inquiries/` | 문의 등록 |
| GET | `/api/cs/inquiries/{id}/` | 문의 상세 |
| PATCH | `/api/cs/inquiries/{id}/` | 답변 등록 (어드민) |
| GET | `/api/cs/cancel/` | 취소 요청 목록 |
| POST | `/api/cs/cancel/` | 취소 요청 등록 |
| GET | `/api/cs/cancel/{id}/` | 취소 요청 상세 |
| PATCH | `/api/cs/cancel/{id}/` | 취소 처리 (어드민) |
| GET | `/api/cs/refund/` | 환불 요청 목록 |
| POST | `/api/cs/refund/` | 환불 요청 등록 |
| GET | `/api/cs/refund/{id}/` | 환불 요청 상세 |
| PATCH | `/api/cs/refund/{id}/` | 환불 1차 처리 (CS — 승인/반려/금액) |
| POST | `/api/cs/refund/{id}/execute/` | 환불 승인-실행 (본사 — GMO 환불) |
| GET | `/api/cs/purchase-tasks/` | 대리구매 작업 목록 (CS) |
| POST | `/api/cs/purchase-tasks/{order_number}/complete/` | 대리구매 완료·내역 입력 (CS) |

---

## 환불 승인-실행 (FR-CS-03·FR-PAY-04, 화면 H-03)

환불은 **CS 접수·1차 처리 → 본사 최종 승인·실행** 2단계로 분리된다.

1. `PATCH /api/cs/refund/{id}/` (CS) — `status`를 `approved` / `partial_approved` 로, `approved_amount` 설정
2. `POST /api/cs/refund/{id}/execute/` (본사) — 실제 GMO 환불 실행

### POST `/api/cs/refund/{id}/execute/`

`status`가 `approved` / `partial_approved` 일 때만 호출 가능(아니면 `409`). 실행 시:
- GMO 환불 실행(`execute_pg_refund`) → `PGTransaction` 갱신
- `RefundRequest.status=completed`, `approved_amount`=실제 환불액, `processed_at` 기록
- `Order.refund_amount`·`refund_reason` 기록, `Order.status` → 전액이면 `refunded`, 부분이면 `partial_refund`
- `OrderStatusLog(stage=cancelled_or_refunded)` + `AdminActionLog(changed_field=refund_execute)` 기록

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `hq_user` | string | ❌ | 실행 본사 담당자 식별자 (감사 로그) |

환불 금액은 `approved_amount`(없으면 `requested_amount`)를 사용. PG는 그룹 단위이므로 `order_number`→그룹→`PGTransaction` 으로 해소한다.

**Response**

```json
{ "status": "completed", "refund_amount": 4000, "pg_status": "refunded", "order_status": "partial_refund" }
```

---

## 대리구매 작업 (FR-ORD-07, 화면 C-01)

### GET `/api/cs/purchase-tasks/`

CS가 직접 대리구매할 주문 목록. 원본 URL·옵션·예상가를 포함한다.

| 쿼리 | 설명 |
|------|------|
| `state` | `pending`(기본, 결제완료·미처리) / `done`(처리완료) |
| `cs_user` | `state=done` 일 때 담당 CS 필터 |

응답 항목: `order_number, group_number, customer_id, site_domain, product_url, title, options, quantity, expected_price, price_total, currency, status, purchase_record`

### POST `/api/cs/purchase-tasks/{order_number}/complete/`

대리구매 완료 후 구매 내역 입력. `PurchaseRecord` upsert → `Order.status` `paid→purchasing`, 가격 오차 검사(FR-ORD-04), `OrderStatusLog(purchase_complete)` + `AdminActionLog` 기록.

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `actual_price` | float | ✅ | 실제 구매가 |
| `purchase_account` | string | ❌ | 구매에 사용한 계정 |
| `collection_address` | string | ❌ | 쇼핑몰이 보낼 국내 집하 주소 (고객 일본주소와 별개) |
| `domestic_shipping_fee` | float | ❌ | 국내 배송비 (기본 0) |
| `currency` | string | ❌ | 통화 (기본 KRW) |
| `cs_user` | string | ❌ | 담당 CS 식별자 |
| `memo` | string | ❌ | 메모 |
| `purchased_at` | datetime | ❌ | 구매 시각 (기본 현재) |

**Response**

```json
{
  "purchase_record": { "order_number": "ORD-...", "purchase_account": "buyer01", "collection_address": "...", "actual_price": 12000, "domestic_shipping_fee": 2500, "cs_user": "cs-kim", "purchased_at": "..." },
  "order_status": "purchasing",
  "price_error": { "error_rate": 20.0, "error_amount": 2000, "handling_method": "cs_review", "auto_processed": false }
}
```

`price_error.handling_method`: 오차율 ≤ 소오차 기준(또는 절대금액 이하) → `company_burden`(auto_processed=true), 대오차 기준 초과 → `cs_review`. 기준은 `ErrorCriteria(is_current=True)`에서 동적으로 읽는다.

---

## POST `/api/cs/inquiries/`

### Request Body

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `customer_id` | string | ✅ | 고객 식별자 |
| `title` | string | ✅ | 문의 제목 |
| `content` | string | ✅ | 문의 내용 |
| `inquiry_type` | string | ❌ | 문의 유형 (기본 `general`) |
| `order_number` | string | ❌ | 관련 주문번호 |

**`inquiry_type` 허용값**

| 값 | 설명 |
|----|------|
| `general` | 일반 문의 |
| `cancel` | 취소 문의 |
| `refund` | 환불 문의 |
| `exchange` | 교환 문의 |
| `return` | 반품 문의 |
| `shipping` | 배송 문의 |
| `shipping_delay` | 배송 지연 |
| `price_error` | 가격 오차 |
| `inspection_issue` | 검수 이슈 (검수 API가 자동 생성) |
| `other` | 기타 |

---

## PATCH `/api/cs/inquiries/{id}/` (어드민)

### Request Body

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `admin_reply` | string | ✅ | 답변 내용 |
| `status` | string | ✅ | 변경할 상태 |

**`status` 허용값:** `open` / `in_progress` / `resolved` / `closed`

---

## POST `/api/cs/cancel/`

### Request Body

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `customer_id` | string | ✅ | 고객 식별자 |
| `order_number` | string | ✅ | 주문번호 |
| `reason` | string | ✅ | 취소 사유 |

**취소 가능 여부 (주문 상태 기준)**

| 단계 | 취소 가능 여부 |
|------|--------------|
| `pending` | 취소 가능 |
| `paid` / `purchasing` | 조건부 취소 (배송비 부담 가능) |
| `shipping_intl` 이후 | 취소 불가 |

---

## PATCH `/api/cs/cancel/{id}/` (어드민)

| 필드 | 타입 | 설명 |
|------|------|------|
| `status` | string | `pending` / `approved` / `rejected` / `completed` |
| `shipping_fee_burden` | boolean | 고객 배송비 부담 여부 |
| `admin_notes` | string | 어드민 메모 |

---

## POST `/api/cs/refund/`

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `customer_id` | string | ✅ | 고객 식별자 |
| `order_number` | string | ✅ | 주문번호 |
| `reason` | string | ✅ | 환불 사유 |
| `requested_amount` | float | ✅ | 환불 요청 금액 |

---

## PATCH `/api/cs/refund/{id}/` (어드민)

| 필드 | 타입 | 설명 |
|------|------|------|
| `status` | string | `pending` / `approved` / `partial_approved` / `rejected` / `completed` |
| `approved_amount` | float | 실제 환불 금액 |
| `admin_notes` | string | 어드민 메모 |

---

## DB 모델 구조

### Inquiry

| 필드 | 타입 | 설명 |
|------|------|------|
| `customer_id` | CharField(255) | 고객 식별자 |
| `order_number` | CharField(50) | 관련 주문번호 (선택) |
| `inquiry_type` | CharField(20) | 문의 유형 |
| `title` | CharField(255) | 제목 |
| `content` | TextField | 내용 |
| `status` | CharField(20) | 상태 |
| `admin_reply` | TextField | 어드민 답변 |
| `replied_at` | DateTimeField\|null | 답변 시각 |

### CancelRequest

| 필드 | 타입 | 설명 |
|------|------|------|
| `order_number` | CharField(50) | 주문번호 (unique) |
| `customer_id` | CharField(255) | 고객 식별자 |
| `reason` | TextField | 취소 사유 |
| `status` | CharField(20) | 상태 |
| `shipping_fee_burden` | BooleanField | 고객 배송비 부담 여부 |
| `admin_notes` | TextField | 어드민 메모 |
| `processed_at` | DateTimeField\|null | 처리 시각 |

### RefundRequest

| 필드 | 타입 | 설명 |
|------|------|------|
| `order_number` | CharField(50) | 주문번호 (unique) |
| `customer_id` | CharField(255) | 고객 식별자 |
| `reason` | TextField | 환불 사유 |
| `requested_amount` | FloatField | 요청 금액 |
| `approved_amount` | FloatField\|null | 승인 금액 |
| `status` | CharField(20) | 상태 |
| `admin_notes` | TextField | 어드민 메모 |
| `processed_at` | DateTimeField\|null | 처리 시각 |

### PurchaseRecord (`apps.orders` 모델 — CS 대리구매 내역)

| 필드 | 타입 | 설명 |
|------|------|------|
| `order_number` | CharField(50) | 주문번호 (unique) |
| `purchase_account` | CharField(255) | 구매에 사용한 계정 |
| `collection_address` | TextField | 쇼핑몰이 보낼 국내 집하 주소 (고객 일본주소와 별개) |
| `actual_price` | FloatField\|null | 실제 구매가 |
| `domestic_shipping_fee` | FloatField | 국내 배송비 |
| `currency` | CharField(10) | 통화 (기본 KRW) |
| `cs_user` | CharField(255) | 담당 CS |
| `memo` | TextField | 메모 |
| `purchased_at` | DateTimeField\|null | 구매 시각 |
