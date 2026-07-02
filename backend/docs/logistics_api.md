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
| GET | `/api/logistics/{order_number}/timeline/` | **배송 추적 타임라인** (4단계 진행 바 + 날짜별 이벤트 로그 + 최종 배송정보) |
| POST | `/api/logistics/{order_number}/timeline/` | 추적 이벤트 적재 (description 기반 단계 분류 — 폴백) |
| GET | `/api/logistics/{order_number}/tracking/` | 배송 추적 정보 조회 |
| PUT | `/api/logistics/{order_number}/tracking/` | 배송 추적 정보 수동 수정 |
| POST | `/api/logistics/{order_number}/dhub/register/` | DHUB 주문 등록 → FB 송장번호 채번 |
| POST | `/api/logistics/{order_number}/tracking/sync/` | DHUB 배송추적 동기화 |
| POST | `/api/logistics/dhub/instruct/` | DHUB 배송지시 (창고 → 국제 발송) |
| GET | `/api/logistics/stagnated/` | 지연 감지된 배송 목록 |
| GET | `/api/logistics/{order_number}/customs/` | 통관 결과 조회 |
| POST | `/api/logistics/{order_number}/customs/` | 통관 결과 등록 (거절 시 고객 안내 + 응답기한 설정) |
| POST | `/api/logistics/{order_number}/customs/respond/` | 고객 응답 기록 (자동 부분환불 대상 제외) |
| POST | `/api/logistics/{order_number}/customs/refund/` | 해당 상품만 부분환불 실행 (CS 수동) |
| GET | `/api/logistics/customs/refund-due/` | 부분환불 처리 대기 목록 (미응답·기한경과) |

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
| `address.hs_code` | | HS 코드 (생략 시 검수 확정값 → `621790` 기본값 순) |
| `address.prd_category` | | 통관 카테고리 (생략 시 검수 확정값 → `Order.product_category` 순) |
| `address.material` | △ | 소재 (일본 배송 필수) |
| `address.cloth_material` | △ | 옷감 (일본 배송 필수) |

나머지 주문 데이터(`ord_bundle_no`, `selling_price`, `quantity` 등)는 `Order` 모델에서 자동 매핑.

**배송지 자동 채움:** `address`를 생략하거나 일부만 보내면 고객 기본 배송지(`mypage.UserAddress` — `is_default` 우선)에서 `receiver_name`·`receiver_name_voice`(가타카나)·`receiver_name_en`·`receiver_cell`·`receiver_zipcode`·`receiver_address1/2`·`date_of_birth`를 자동 채운다. body로 보낸 값이 우선한다. `receiver_email`은 UserAddress에 없으므로 별도로 전달해야 한다.

**HS코드·통관 카테고리 자동 채움:** `address.hs_code`를 생략하면, 검수 담당자가 확정한 상품 HS 분류(`tariff.ProductHsClassification`, `status=confirmed`)를 자동으로 끌어다 쓴다. 연결은 `Order.product_url == Product.url` 기준이며, 확정 레코드의 `final_hs_code`/`final_category`가 각각 `hs_code`/`prd_category`로 주입된다. body로 `hs_code`를 명시하면 그 값이 우선한다. 확정 분류가 없고 body도 없으면 기본값 `621790`(여성 의류). 어떤 출처가 쓰였는지는 응답의 `hs_code_source`로 확인할 수 있다. (HS 분류 추천·확정은 `tariff_api.md`의 `/api/tariff/products/{pk}/classification/` 참고)

### Response (201)

```json
{
  "fb_invoice_no": "FB20250001234",
  "ord_no": "ORD20250001",
  "delivery_type": "FB",
  "hs_code": "6109100000",
  "hs_code_source": "inspection_confirmed"
}
```

| 필드 | 설명 |
|------|------|
| `fb_invoice_no` | FastBox 송장번호 → `ShippingTracking.fb_invoice_no` 저장됨 |
| `ord_no` | DHUB 출고지시번호 |
| `delivery_type` | `FB`(FastBox) / `SD`(자체물류) |
| `hs_code` | 실제 등록에 사용된 HS코드 |
| `hs_code_source` | `inspection_confirmed`(검수 확정값) / `request_body`(요청 명시) / `default`(기본값 621790) |

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

## 통관 결과 / 통관 거절 → 해당 상품만 부분환불

통관결과(거절 사유 포함)는 **FastBox 문서 API 로는 수신되지 않으므로**, 통관업자→CS 가 받은 정보를 **수기 등록**한다. 거절 시 CS 가 고객에게 "해당 상품만 부분환불"을 안내하고, **미응답인 채 응답기한(기본 7일)이 지나면** CS 가 처리 대기 목록에서 **해당 Order 금액만** 부분환불한다.

- 기한: `SiteConfig` 키 `CUSTOMS_REFUND_NO_RESPONSE_DAYS` (기본 `7`, 달력일)
- 실행: **CS 수동** (자동 배치 없음) — `refund-due` 목록에서 건별 실행
- 컷오프(FastBox 인계) 환불 차단과 무관 — 이건 **통관 귀책** 환불이므로 단계와 무관하게 실행

### POST `/api/logistics/{order_number}/customs/`

통관 결과 등록. `result=rejected`(또는 `returned`)이면 고객 안내 발송 + 응답기한 설정.

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `result` | string | ✅ | `pending` / `cleared` / `rejected` / `returned` |
| `customs_type` | string | ❌ | `list`(목록통관) / `general`(일반통관) |
| `reject_reason` | string | ❌ | 거절 사유 (rejected 시) |
| `operator` | string | ❌ | 등록 담당 CS (감사 로그) |

거절 등록 시 부수효과: `partial_refund_amount`(해당 Order 실청구액) 산정, `notified_at`·`response_deadline`(=now+N일) 설정, **고객 안내 알림 발송**(`notify` 이벤트 `customs_rejected`, NotificationLog 기록), `OrderStatusLog(cancelled_or_refunded)` + `AdminActionLog(customs_result)` 기록.

**Response (200)**

```json
{ "customs": { "...": "CustomsClearance" }, "notified": true, "no_response_days": 7 }
```

### POST `/api/logistics/{order_number}/customs/respond/`

고객(또는 CS 대행)이 통관 거절 안내에 응답했음을 기록 → `customer_responded_at` 설정 → **자동 부분환불 대상(refund-due)에서 제외**. (응답 후 재발송/추가서류 등은 CS 가 개별 처리)

### GET `/api/logistics/customs/refund-due/`

부분환불 **처리 대기 목록**. 조건: `result ∈ {rejected, returned}` + 고객 미응답(`customer_responded_at` null) + 응답기한 경과(`response_deadline ≤ now`) + 미환불(`refund_processed_at` null). `response_deadline` 오름차순.

### POST `/api/logistics/{order_number}/customs/refund/`

CS 수동 확인 후 **해당 상품만** 부분환불 실행. PG(그룹 단위)를 `order→group→PGTransaction`으로 해소해 `execute_pg_refund(pg, amount)` 호출.

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `amount` | number | ❌ | 환불 금액. 생략 시 `partial_refund_amount` 사용 |
| `hq_user` | string | ❌ | 실행 담당자 (감사 로그) |

성공 시: `CustomsClearance.refund_processed_at`·`refund_amount` 기록, `Order.status=partial_refund`·`refund_amount`·`refund_reason`, `OrderStatusLog(cancelled_or_refunded)` + `AdminActionLog(customs_partial_refund)`, 환불완료 알림(`refund_complete`).

| 상태 | 조건 |
|------|------|
| 409 | rejected/returned 아님 / 이미 환불됨 |
| 400 | 환불 금액 확인 불가 |
| 404 | 통관 레코드/PG 없음 |
| 502 | PG 환불 실패 (`provider_code`, `detail`) |

---

## GET `/api/logistics/{order_number}/timeline/`

고객 **배송 추적 화면** 페이로드. 상단 4단계 진행 바 + 시간순(날짜별) 이벤트 로그 + 최종 배송정보.

### 배송 4단계

진행 바는 **FastBox(DHUB) `status_code` 를 권위 소스로 직접 구동**한다 (코드→단계 매핑: `dhub_client.DHUB_STATUS_MAP['stage']`).

| 순서 | `key` | 라벨 | 의미 | FastBox status_code |
|------|-------|------|------|---------------------|
| 1 | `shipment_sent` | 상품발송 | 주문접수·발송준비 | `ORE`, `RPE` |
| 2 | `intl_transit` | 국제운송 | 국제 운송 중 | `RFI`, `InTransit` |
| 3 | `domestic_delivery` | 현지배송 | 현지 택배사 배달 | `OutForDelivery`, `AttemptFail` |
| 4 | `delivered` | 배송완료 | 고객 수령 완료 | `Delivered` |

> **"통관" 단계는 제거됨.** FastBox 는 통관 전용 status_code 를 주지 않고(현지측 일본어 이벤트라 한국어 키워드 분류도 신뢰 불가), 통관 데이터를 넣어줄 자동 피드도 없어 추측 단계가 된다. 향후 통관 자동 피드가 생기면 단계로 승격 가능. `description` 기반 키워드 분류기(`stages.classify_tracking_stage`)는 수동 `POST /timeline/` 적재용 폴백으로만 남는다.

### Response (200)

| 필드 | 타입 | 설명 |
|------|------|------|
| `order_number` | string | 주문번호 |
| `current_stage` | string | 현재 단계 `key` |
| `current_stage_index` | int | 현재 단계 인덱스 (0~3) |
| `stages` | array | 4단계 배열 — `{key, label, status, reached_at}` |
| `stages[].status` | string | `completed`(지난 단계) / `current`(현재) / `pending`(예정) |
| `stages[].reached_at` | datetime\|null | 해당 단계 최초 도달 시각 (이벤트 없으면 null) |
| `events_by_date` | array | 날짜별 이벤트 그룹 — `{date, items[]}` |
| `events_by_date[].items[]` | object | `{occurred_at, time, stage, stage_label, description, location, source}` |
| `delivery` | object | `{delivered_at, region, carrier, tracking_number, delivery_type}` |

```json
{
  "order_number": "ORD-20260617-AB12CD",
  "current_stage": "delivered",
  "current_stage_index": 3,
  "stages": [
    {"key": "shipment_sent",     "label": "상품발송", "status": "completed", "reached_at": "2026-06-17T09:10:00+09:00"},
    {"key": "intl_transit",      "label": "국제운송", "status": "completed", "reached_at": "2026-06-18T11:00:00+09:00"},
    {"key": "domestic_delivery", "label": "현지배송", "status": "completed", "reached_at": "2026-06-19T08:00:00+09:00"},
    {"key": "delivered",         "label": "배송완료", "status": "current",   "reached_at": "2026-06-19T15:04:00+09:00"}
  ],
  "events_by_date": [
    {"date": "2026-06-18", "items": [
      {"time": "11:00:00", "stage": "intl_transit", "stage_label": "국제운송", "description": "국제 배송 중", "location": "仁川国際空港", "source": "carrier", "occurred_at": "2026-06-18T11:00:00+09:00"}
    ]},
    {"date": "2026-06-19", "items": [
      {"time": "08:00:00", "stage": "domestic_delivery", "stage_label": "현지배송", "description": "배달 예정", "location": "ヤマト運輸", "source": "carrier", "occurred_at": "2026-06-19T08:00:00+09:00"},
      {"time": "15:04:00", "stage": "delivered", "stage_label": "배송완료", "description": "배송 완료", "location": "", "source": "carrier", "occurred_at": "2026-06-19T15:04:00+09:00"}
    ]}
  ],
  "delivery": {
    "delivered_at": "2026-06-19T15:04:00+09:00",
    "region": "",
    "carrier": "ヤマト運輸",
    "tracking_number": "123456789",
    "delivery_type": "FB"
  }
}
```

---

## POST `/api/logistics/{order_number}/timeline/`

원천 추적 이벤트(택배 등)를 적재한다. 각 이벤트는 설명 텍스트로 **4단계 자동 분류**되고(`stage` 직접 지정 시 그 값 사용),
현재 단계·배송완료 시각·배송 지역이 재계산된다. 중복 이벤트(`occurred_at`+`description` 동일)는 무시.
DHUB 동기화(`tracking/sync/`)는 FastBox 이벤트에 status_code 기반 `description`·`stage`를 주입해 이 적재를 자동 호출하므로,
이 엔드포인트는 별도 택배/통관 소스를 직접 밀어 넣을 때만 사용한다.

### Request Body

```json
{
  "source": "carrier",
  "events": [
    {"occurred_at": "2026-06-18 09:00:00", "description": "국제 배송 중"},
    {"occurred_at": "2026-06-19 08:00:00", "description": "배달 예정"},
    {"occurred_at": "2026-06-19 15:04:00", "description": "여의도 배송 완료", "location": "여의도"}
  ]
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `events` | array | ✅ | 이벤트 목록 |
| `events[].occurred_at` | datetime | ✅ | 발생 시각 (ISO 또는 `YYYY-MM-DD HH:MM:SS` 등 관용 파싱) |
| `events[].description` | string | ✅ | 이벤트 내용 (4단계 분류 기준) |
| `events[].location` | string | | 위치 (배송완료 시 배송 지역 추출에 사용) |
| `events[].stage` | string | | 단계 직접 지정 (생략 시 설명으로 자동 분류) |
| `events[].source` | string | | `seller`/`intl`/`customs`/`carrier`/`system` |
| `source` | string | | 이벤트별 `source` 미지정 시 기본값 (기본 `carrier`) |

> `occurred_at`/`description` 외에도 `datetime`·`reg_date`·`status`·`status_name`·`status_code` 등 다양한 원천 키를 관용적으로 인식한다.

### Response (200)

```json
{
  "ingested": {"total": 15, "current_stage": "delivered", "delivered_at": "...", "delivery_region": "여의도"},
  "timeline": { "...": "GET timeline 과 동일 구조" }
}
```

---

## DB 모델 구조

### CustomsClearance

| 필드 | 타입 | 설명 |
|------|------|------|
| `order_number` | CharField(unique) | 주문번호 |
| `customs_type` | CharField | `list`(목록통관) / `general`(일반통관) |
| `result` | CharField | `pending` / `cleared` / `rejected` / `returned` |
| `reject_reason` | TextField | 거절 사유 |
| `partial_refund_amount` | FloatField\|null | 해당 상품 부분환불 예정액 (해당 Order 실청구액) |
| `notified_at` | DateTimeField\|null | 고객 안내(CS 발송) 시각 |
| `response_deadline` | DateTimeField\|null | 고객 응답 기한 (`notified_at` + N일) |
| `customer_responded_at` | DateTimeField\|null | 고객 응답 시각 (null=미응답) |
| `refund_processed_at` | DateTimeField\|null | 부분환불 실행 시각 |
| `refund_amount` | FloatField\|null | 실제 환불액 |

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
| `current_stage` | CharField | 현재 배송 단계 (4단계 `key`, FastBox status_code 기반 자동 갱신) |
| `delivered_at` | DateTimeField | 배송완료 시각 (배송완료 이벤트에서 추출) |
| `delivery_region` | CharField | 배송 지역 (배송완료 이벤트 위치/설명에서 추출) |

### TrackingEvent

배송 추적 타임라인의 개별 이벤트. 설명 텍스트로 4단계 자동 분류(`stages.classify_tracking_stage`, FastBox 경로는 status_code 기반 `stage` 주입).

| 필드 | 타입 | 설명 |
|------|------|------|
| `order_number` | CharField(indexed) | 주문번호 |
| `occurred_at` | DateTimeField(indexed) | 발생 시각 |
| `stage` | CharField | 4단계 `key` (`shipment_sent`/`intl_transit`/`domestic_delivery`/`delivered`) |
| `description` | CharField(500) | 이벤트 내용 |
| `location` | CharField(255) | 위치 |
| `source` | CharField | `seller`/`intl`/`customs`/`carrier`/`system` |
| `raw_code` | CharField(50) | 원천 상태코드 |
| `raw` | JSONField | 원천 데이터 원본 |

> 유니크 제약 `(order_number, occurred_at, description)` 으로 중복 이벤트 적재 방지.
