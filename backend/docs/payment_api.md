# Payment API

멀티 PG 프로바이더 구조. 현재 GMO Payment Gateway(カード + PayPay) 지원.
신규 PG(Stripe, Adyen 등) 추가 시 `apps/payment/providers/` 에 프로바이더 클래스 구현 후 `registry.py`에 등록하면 뷰 변경 없이 연동 가능.

Base URL: `/api/payment/`

---

## 엔드포인트 목록

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/payment/entry/` | 거래 등록 (access token 발급) |
| POST | `/api/payment/execute/` | 결제 실행 (카드 토큰 + access token) |
| POST | `/api/payment/capture/` | 매출 확정 (admin) |
| POST | `/api/payment/cancel/` | 결제 취소 |
| POST | `/api/payment/refund/` | 환불 |
| GET | `/api/payment/status/<order_id>/` | 거래 현황 조회 |
| POST | `/api/payment/paypay/entry/` | PayPay 거래 등록 → QR URL 발급 |
| POST | `/api/payment/paypay/execute/` | PayPay 결제 확정 (고객 스캔 완료 후) |
| GET | `/api/payment/paypay/status/<order_id>/` | PayPay 거래 현황 조회 |

---

## 프로바이더 구조

```
apps/payment/providers/
├── base.py       # BasePaymentProvider ABC, EntryResult / ExecuteResult / AlterResult / ProviderError
├── gmo.py        # GmoProvider  (카드 결제)
├── paypay.py     # PayPayProvider  (PayPay QR)
└── registry.py   # get_provider(name), register_provider(name, instance)
```

### 새 PG 추가 방법

```python
# providers/stripe.py
class StripeProvider(BasePaymentProvider):
    name = 'stripe'
    def entry(...): ...
    def execute(...): ...
    # ...

# providers/registry.py에 등록
_REGISTRY['stripe'] = StripeProvider()
```

---

## 결제 흐름 (카드)

```
[프론트엔드]                   [Django]              [GMO-PG]
     │                             │                      │
     │  1. POST /entry/            │                      │
     │  { order_group_id } ───────▶│  EntryTran ─────────▶│
     │                             │  ◀── AccessID/Pass ──│
     │  ◀── { provider_order_id,   │                      │
     │        access_id,           │                      │
     │        access_pass }        │                      │
     │                             │                      │
     │  2. JS 토크나이저            │                      │
     │  Multipayment.getToken(card)│                      │
     │  → token                    │                      │
     │                             │                      │
     │  3. POST /execute/          │                      │
     │  { token, access_id, ... } ▶│  ExecTran ──────────▶│
     │                             │  ◀── TranID/Approve ─│
     │  ◀── { status, transaction_id } │                  │
     │                             │                      │
     │            [주문 처리 → 검수 완료]                   │
     │                             │                      │
     │                             │  4. POST /capture/   │  ← admin 호출
     │                             │  AlterTran(SALES) ──▶│
```

---

## POST `/api/payment/entry/`

### Request Body

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `order_group_id` | integer | ✅ | OrderGroup PK |

### Response (200 OK)

| 필드 | 타입 | 설명 |
|------|------|------|
| `provider` | string | `gmo` |
| `provider_order_id` | string | PG 측 주문 ID (group_number 기반, 27자 이내) |
| `access_id` | string | execute 호출에 사용 |
| `access_pass` | string | execute 호출에 사용 |
| `amount` | integer | 결제 금액 |
| `currency` | string | 통화 코드 (`JPY`) |

### 에러 응답

| 상태 | 조건 |
|------|------|
| 400 | order_group_id 미지정 / 금액 0 |
| 404 | OrderGroup 없음 |
| 502 | PG 통신 오류 (`provider_code`, `detail` 포함) |

---

## POST `/api/payment/execute/`

### Request Body

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `order_group_id` | integer | ✅ | OrderGroup PK |
| `provider_order_id` | string | ✅ | entry에서 받은 값 |
| `access_id` | string | ✅ | entry에서 받은 값 |
| `access_pass` | string | ✅ | entry에서 받은 값 |
| `token` | string | ✅ | `Multipayment.getToken()` 발급 토큰 |
| `method` | string | ❌ | `1`=일시불(기본), `2`=할부, `3`=보너스, `4`=보너스할부, `5`=리볼빙 |
| `pay_times` | integer | 조건부 | 할부 회수 (method=2,4 시 필수) |

### Response (200 OK)

| 필드 | 타입 | 설명 |
|------|------|------|
| `status` | string | `auth_complete` |
| `transaction_id` | string | PG 거래 ID |
| `approve` | string | 승인 번호 |
| `forward` | string | 카드사 코드 |
| `tran_date` | string | 거래 일시 (YYYYMMDDHHmmss) |
| `pg_id` | integer | PGTransaction PK |

OrderGroup.status → `paid`, paid_at 업데이트됨.

### 에러 응답

| 상태 | 조건 |
|------|------|
| 400 | 필수 파라미터 누락 |
| 402 | 결제 거절 (`provider_code`, `detail` 포함) |
| 404 | OrderGroup 없음 |
| 502 | PG 통신 오류 |

---

## POST `/api/payment/capture/`

AUTH 거래를 매출 확정(SALES). 검수 완료 후 admin이 호출.

### Request Body

| 필드 | 타입 | 필수 |
|------|------|------|
| `order_group_id` | integer | ✅ |

### Response (200 OK)

```json
{ "status": "captured", "transaction_id": "..." }
```

---

## POST `/api/payment/cancel/`

결제 취소. SALES 확정 전에만 가능.

### Request Body

| 필드 | 타입 | 필수 |
|------|------|------|
| `order_group_id` | integer | ✅ |

### Response (200 OK)

```json
{ "status": "cancelled" }
```

OrderGroup.status → `cancelled` 업데이트됨.

---

## POST `/api/payment/refund/`

환불(RETURN). SALES 확정 이후 사용.

### Request Body

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `order_group_id` | integer | ✅ | |
| `amount` | integer | ❌ | 환불 금액 (생략 시 전액) |

### Response (200 OK)

```json
{ "status": "refunded", "refund_amount": 1200 }
```

부분 환불(`amount` < 전액)이면 `OrderGroup.status` → `partial`, 전액이면 `cancelled`.

> 이 엔드포인트는 **그룹 단위 직접 환불**(본사 운영 도구)이다. 고객 환불 요청(`RefundRequest`) 기반의 승인-실행 흐름은 `POST /api/cs/refund/{id}/execute/`(본사) 를 사용하며, 두 경로 모두 내부적으로 동일한 `execute_pg_refund()` 서비스를 호출한다.

---

## GET `/api/payment/status/<order_id>/`

PG 거래 현황 실시간 조회. `order_id`는 entry에서 받은 `provider_order_id`.

### Response (200 OK)

| 필드 | 타입 | 설명 |
|------|------|------|
| `provider_order_id` | string | |
| `status` | string | PG 상태 (UNPROCESSED/AUTH/SALES/CANCEL/RETURN 등) |
| `job_cd` | string | 현재 JobCd |
| `amount` | string | 결제 금액 |
| `process_date` | string | 처리 일시 |
| `transaction_id` | string | PG 거래 ID |
| `approve` | string | 승인 번호 |
| `forward` | string | 카드사 코드 |
| `card_no` | string | 마스킹 카드 번호 |
| `local_status` | string\|null | 로컬 PGTransaction.auth_status |

---

## PayPay QR 결제

### POST `/api/payment/paypay/entry/`

#### Request Body

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `order_group_id` | integer | ✅ | |
| `return_url` | string | ✅ | 고객 결제 완료 후 리다이렉트 URL |

#### Response (200 OK)

| 필드 | 타입 | 설명 |
|------|------|------|
| `provider` | string | `gmo_paypay` |
| `provider_order_id` | string | PG 측 주문 ID |
| `access_id` | string | execute 호출에 사용 |
| `access_pass` | string | execute 호출에 사용 |
| `qr_url` | string | 고객에게 표시할 PayPay QR 결제 URL |
| `amount` | integer | 결제 금액 |
| `currency` | string | `JPY` |

---

### POST `/api/payment/paypay/execute/`

고객 QR 스캔 완료 후 서버에서 결제 확정.

#### Request Body

| 필드 | 타입 | 필수 |
|------|------|------|
| `order_group_id` | integer | ✅ |
| `provider_order_id` | string | ✅ |
| `access_id` | string | ✅ |
| `access_pass` | string | ✅ |

#### Response (200 OK)

| 필드 | 타입 | 설명 |
|------|------|------|
| `status` | string | `captured` |
| `transaction_id` | string | |
| `forward` | string | |
| `tran_date` | string | |
| `pg_id` | integer | PGTransaction PK |

---

## DB 모델 구조 (PGTransaction)

`apps.orders.PGTransaction`

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | BigAutoField | PK |
| `order_number` | CharField(50) | OrderGroup.group_number |
| `provider` | CharField(20) | PG 프로바이더 (`gmo`, `gmo_paypay`, `stripe`, `adyen`) |
| `currency` | CharField(3) | 통화 코드 (`JPY`, `USD` 등) |
| `provider_order_id` | CharField(100) | PG 측 주문 ID (PG 공통 조회 키) |
| `pg_transaction_id` | CharField(255) | PG 거래 ID (ExecTran 후 설정) |
| `auth_status` | CharField(30) | 내부 상태 (아래 표) |
| `refund_amount` | FloatField\|null | 환불 금액 |
| `refund_requested_at` | DateTimeField\|null | |
| `refund_completed_at` | DateTimeField\|null | |
| `failure_reason` | TextField | 실패 사유 |
| `raw_payload` | JSONField | PG 원본 응답 누적 |
| `gmo_order_id` | CharField(50) | GMO OrderID (레거시 호환) |
| `gmo_access_id` | CharField(255) | GMO EntryTran AccessID |
| `gmo_access_pass` | CharField(255) | GMO EntryTran AccessPass |
| `gmo_forward` | CharField(50) | 카드사 Forward 코드 |
| `gmo_approve` | CharField(50) | 승인 번호 |
| `gmo_job_cd` | CharField(20) | 현재 GMO JobCd |
| `amount_jpy` | IntegerField | 결제 금액 (통화 단위) |

**auth_status 허용값**

| 값 | 설명 |
|----|------|
| `pending` | 인증 대기 |
| `auth_complete` | 결제 인증 완료 (AUTH) |
| `capture_pending` | 매출 확정 대기 |
| `captured` | 매출 확정 완료 (SALES) |
| `cancel_in_progress` | 취소/환불 진행 중 |
| `cancelled` | 취소 완료 |
| `refunded` | 환불 완료 |
| `failed` | 실패 |

---

## 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `GMO_SHOP_ID` | — | GMO 쇼핑몰 ID |
| `GMO_SHOP_PASS` | — | GMO 쇼핑몰 패스워드 |
| `GMO_SANDBOX` | `true` | `false`로 변경 시 production |
| `GMO_TIMEOUT` | `30` | 요청 타임아웃(초) |
