# Logistics API

물류 입고·검수 및 배송 추적 정보. DHUB(FastBox) 국제 물류 API 연동 포함.

Base URL: `/api/logistics/`

---

## 엔드포인트 목록

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/logistics/{order_number}/` | 물류/검수 정보 조회 |
| PUT | `/api/logistics/{order_number}/` | 물류/검수 정보 등록·수정 (단순 저장, 상태전이 없음) |
| POST | `/api/logistics/{order_number}/inspection/` | 검수 등록 (상태전이·CS 티켓 자동) |
| GET | `/api/logistics/{order_number}/tracking/` | 배송 추적 정보 조회 |
| PUT | `/api/logistics/{order_number}/tracking/` | 배송 추적 정보 수동 수정 |
| POST | `/api/logistics/{order_number}/dhub/register/` | DHUB 주문 등록 → FB 송장번호 채번 |
| POST | `/api/logistics/{order_number}/tracking/sync/` | DHUB 배송추적 동기화 |
| POST | `/api/logistics/dhub/instruct/` | DHUB 배송지시 (창고 → 국제 발송) |
| GET | `/api/logistics/stagnated/` | 지연 감지된 배송 목록 |

---

## PUT `/api/logistics/{order_number}/`

물류 입고·검수 정보 **단순 등록/수정**. 상태 전이·로그·CS 티켓 부수효과 없음. 검수 확정은 아래 `inspection/` 사용.

| 필드 | 타입 | 설명 |
|------|------|------|
| `expected_arrival` | datetime | 예상 입고 시각 |
| `arrived_at` | datetime | 실제 입고 시각 — 입력 후 배송지시(`dhub/instruct/`) 가능 |
| `inspection_result` | string | `pending` / `pass` / `issue` |
| `inspection_photos` | array | 검수 사진 URL 목록 |
| `components_match` | boolean\|null | 구성품 일치 여부 |
| `has_defect` | boolean\|null | 하자 여부 |
| `issue_reason` | string | 문제 발생 사유 |
| `post_inspection_action` | string | 검수 후 처리 결과 |

---

## POST `/api/logistics/{order_number}/inspection/`  (FR-LOG-05, 화면 C-02)

CS 검수 확정. `LogisticsInfo` upsert(미입력 시 `arrived_at`=현재) + 부수효과:
- `Order.status` → `inspection`
- `OrderStatusLog(stage=inspection_complete)` + `AdminActionLog(changed_field=inspection, actor_type=logistics)` 기록
- `result=issue` 이면 `Order.inspection_notes` 기록 + **CS Inquiry 자동 생성**(type `other`, title `[검수이슈] {order_number}`)

### Request Body

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `result` | string | ✅ | `pass`(검수 완료) / `issue`(이슈) |
| `components_match` | boolean\|null | ❌ | 구성품 일치 여부 |
| `has_defect` | boolean\|null | ❌ | 하자 여부 |
| `issue_reason` | string | ❌ | 이슈 사유 (issue 시 CS 티켓 내용) |
| `post_inspection_action` | string | ❌ | 검수 후 처리 |
| `inspection_photos` | array | ❌ | 검수 사진 URL |
| `inspector` | string | ❌ | 검수 담당 CS |

### Response

```json
{
  "logistics": { "order_number": "ORD-...", "inspection_result": "issue", "arrived_at": "..." },
  "inquiry_id": 12,
  "order_status": "inspection"
}
```

`inquiry_id`: `result=pass` 이면 `null`, `issue` 이면 생성된 CS 문의 ID.

---

## PUT `/api/logistics/{order_number}/tracking/`

배송 추적 정보 수동 수정. 자동 동기화는 `tracking/sync/` 사용.

| 필드 | 타입 | 설명 |
|------|------|------|
| `tracking_number` | string | 실 배송사(일본 택배) 운송장 번호 |
| `carrier` | string | 배송사명 |
| `carrier_status` | string | DHUB status_code 원본 |
| `customer_status` | string | 고객 표시 상태 |
| `last_status_changed_at` | datetime | 마지막 상태 변경 시각 |
| `last_api_checked_at` | datetime | 마지막 DHUB API 확인 시각 |
| `next_check_at` | datetime | 다음 확인 예정 시각 |
| `is_untrackable_segment` | boolean | 조회 불가 구간 여부 (FastBox 내부·세관 구간) |
| `delay_detected` | boolean | 지연 감지 여부 |
| `delay_type` | string | `none` / `24h` / `48h` / `extended` |
| `delay_hours` | integer | 정체 경과 시간 |
| `stagnation_detected_at` | datetime | 정체 감지 시각 |
| `events` | array | DHUB `trace[]` 원본 이벤트 목록 |

---

## POST `/api/logistics/{order_number}/dhub/register/`

DHUB(FastBox)에 주문 등록 → FB 송장번호(`fb_invoice_no`) 채번.  
**연동 시점:** 주문 `purchase_complete` 단계 전환 시 호출.

### Request Body

```json
{
  "address": {
    "receiver_name":     "홍길동",
    "receiver_name_voice": "ホンギルドン",
    "receiver_cell":     "010-1234-5678",
    "receiver_email":    "user@example.com",
    "receiver_zipcode":  "100-0001",
    "receiver_address1": "東京都千代田区",
    "receiver_address2": "1-1-1",
    "delivery_message":  "부재 시 문 앞에 두세요",
    "hs_code":           "621790",
    "material":          "면 100%",
    "cloth_material":    "Cotton"
  }
}
```

| 필드 | 필수 | 설명 |
|------|------|------|
| `address.receiver_name` | ✅ | 수령자명 |
| `address.receiver_cell` | ✅ | 수령자 연락처 |
| `address.receiver_email` | ✅ | 수령자 이메일 |
| `address.receiver_zipcode` | ✅ | 배송지 우편번호 |
| `address.receiver_address1` | ✅ | 배송지 주소 |
| `address.receiver_name_voice` | △ | 수령자명 가타카나 (일본 배송 필수) |
| `address.hs_code` | | HS 코드 (미입력 시 `621790` 기본값) |
| `address.material` | △ | 소재 (일본 배송 필수) |
| `address.cloth_material` | △ | 옷감 (일본 배송 필수) |

나머지 주문 데이터(`ord_bundle_no`, `selling_price`, `quantity` 등)는 `Order` 모델에서 자동 매핑.

**배송지 자동 채움:** `address`를 생략하거나 일부만 보내면 고객 기본 배송지(`mypage.UserAddress` — `is_default` 우선)에서 `receiver_name`·`receiver_name_voice`(가타카나)·`receiver_name_en`·`receiver_cell`·`receiver_zipcode`·`receiver_address1/2`·`date_of_birth`를 자동 채운다. body로 보낸 값이 우선한다. `receiver_email`은 UserAddress에 없으므로 별도로 전달해야 한다.

### Response (201)

```json
{
  "fb_invoice_no": "FB20250001234",
  "ord_no": "ORD20250001",
  "delivery_type": "FB"
}
```

| 필드 | 설명 |
|------|------|
| `fb_invoice_no` | FastBox 송장번호 → `ShippingTracking.fb_invoice_no` 저장됨 |
| `ord_no` | DHUB 출고지시번호 |
| `delivery_type` | `FB`(FastBox) / `SD`(자체물류) |

**부수효과:** 등록 성공 시 `OrderStatusLog(stage=preparing_dispatch)` + `AdminActionLog(changed_field=dhub_register)` 기록. (주문 상태는 배송지시 시점에 전이)

---

## POST `/api/logistics/{order_number}/tracking/sync/`

DHUB 배송추적 API(`GET /api/Tracking`) 호출 → `ShippingTracking` 자동 업데이트.  
**연동 시점:** 주기적 폴링 또는 어드민 수동 동기화.

`ShippingTracking.fb_invoice_no`가 없으면 400 반환.

### Response (200)

```json
{
  "carrier_status": "InTransit",
  "customer_status": "국제 배송 중",
  "tracking_number": "123456789",
  "events_count": 5,
  "delay_detected": false,
  "last_api_checked_at": "2025-06-08T10:00:00+09:00"
}
```

**DHUB 상태코드 매핑:**

| DHUB `status_code` | `customer_status` |
|--------------------|------------------|
| `ORE` | 주문 접수 |
| `RPE` | 국제 배송 준비 |
| `RFI` | 일본 배송사 인계 |
| `InTransit` | 국제 배송 중 |
| `OutForDelivery` | 배달 예정 |
| `Delivered` | 배송 완료 |
| `AttemptFail` | 배달 시도 실패 |

---

## POST `/api/logistics/dhub/instruct/`

FastBox 창고에서 국제 발송 지시.  
**연동 시점:** `LogisticsInfo.arrived_at` 입력(입고 완료) 후 어드민이 수동 호출.

### Request Body

```json
{
  "fb_invoice_nos":   ["FB20250001234", "FB20250001235"],
  "requester_name":   "담당자명",
  "requester_phone":  "02-000-0000",
  "arrival_due_date": "2025-06-10"
}
```

| 필드 | 필수 | 설명 |
|------|------|------|
| `fb_invoice_nos` | ✅ | FB 송장번호 배열 (최대 200개) |
| `arrival_due_date` | ✅ | 창고 도착 예정일 (YYYY-MM-DD) |
| `requester_name` | | 배송지시 요청자명 |
| `requester_phone` | | 요청자 연락처 |

### Response (200)

```json
{
  "instruction_no": "INST20250001",
  "result": [
    { "fb_invoice_no": "FB20250001234", "result": true }
  ],
  "transitioned_orders": ["ORD-20250001-ABC123"]
}
```

`instruction_no`는 해당 `fb_invoice_no`들의 `ShippingTracking.dhub_instruction_no`에 자동 저장됨.

**부수효과:** 배송지시 = 국제 발송 개시 → 대상 주문들의 `Order.status` → `shipping_intl` 전이, `OrderStatusLog(stage=intl_shipping)` + `AdminActionLog(changed_field=dhub_instruction)` 기록. 전이된 주문번호는 `transitioned_orders`로 반환.

---

## GET `/api/logistics/stagnated/?hours=24`

Query: `?hours=` — 정체 기준 시간 (기본 24시간)

`delay_detected=true`이고 미배송인 건 목록 반환.

---

## DB 모델 구조

### LogisticsInfo

| 필드 | 타입 | 설명 |
|------|------|------|
| `order_number` | CharField(unique) | 주문번호 |
| `expected_arrival` | DateTimeField | 예상 입고 시각 |
| `arrived_at` | DateTimeField | 실제 입고 시각 |
| `inspection_result` | CharField | `pending` / `pass` / `issue` |
| `inspection_photos` | JSONField | 검수 사진 URL 목록 |
| `components_match` | BooleanField | 구성품 일치 여부 |
| `has_defect` | BooleanField | 하자 여부 |
| `issue_reason` | TextField | 문제 발생 사유 |
| `post_inspection_action` | TextField | 검수 후 처리 결과 |

### ShippingTracking

| 필드 | 타입 | 설명 |
|------|------|------|
| `order_number` | CharField(unique) | 주문번호 |
| `tracking_number` | CharField | 실 배송사(일본 택배) 운송장 번호 |
| `carrier` | CharField | 배송사명 |
| `carrier_status` | CharField | DHUB status_code 원본 |
| `customer_status` | CharField | 고객 표시 상태 |
| `last_status_changed_at` | DateTimeField | 마지막 상태 변경 시각 |
| `last_api_checked_at` | DateTimeField | 마지막 DHUB API 확인 시각 |
| `next_check_at` | DateTimeField | 다음 확인 예정 시각 |
| `is_untrackable_segment` | BooleanField | 조회 불가 구간 여부 |
| `delay_detected` | BooleanField | 지연 감지 여부 |
| `delay_type` | CharField | `none` / `24h` / `48h` / `extended` |
| `delay_hours` | IntegerField | 정체 경과 시간 |
| `stagnation_detected_at` | DateTimeField | 정체 감지 시각 |
| `fb_invoice_no` | CharField(indexed) | **FastBox 송장번호** (DHUB API 키) |
| `dhub_ord_bundle_no` | CharField | DHUB 합포번호 |
| `dhub_instruction_no` | CharField | DHUB 배송지시번호 |
| `dhub_delivery_type` | CharField | `FB` / `SD` |
| `events` | JSONField | DHUB `trace[]` 원본 이벤트 목록 |
