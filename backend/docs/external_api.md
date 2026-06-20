# DHUB (FastBox) 외부 API 명세

FastBox(디허브)는 한국→일본 국제 배송 중개 물류 서비스다.  
우리 백엔드는 `apps.logistics`의 `DHubClient`를 통해 이 API를 호출한다.

## 인증

실서버에서는 반드시 **HTTP 헤더**로 인증 정보를 전달한다.

```http
consumerKey: {DHUB_CONSUMER_KEY}
Authorization: Bearer {DHUB_TOKEN}
Content-Type: application/json
```

QA/개발 환경에서는 쿼리 파라미터로도 가능:

```
?mall_id=...&token=...&consumer_key=...
```

| 환경 | Base URL |
|------|----------|
| QA | `https://dhub-api-qa.hanpda.com` |
| Real | `https://dhub-api.cafe24.com` |

환경변수:

| 변수 | 설명 |
|------|------|
| `DHUB_BASE_URL` | Base URL (기본: QA) |
| `DHUB_MALL_ID` | DHUB 몰 아이디 |
| `DHUB_TOKEN` | Bearer 토큰 |
| `DHUB_CONSUMER_KEY` | 컨슈머 키 |
| `DHUB_SELLER_NAME` | 판매사명 (기본: `Boltlab DK`) |

---

## 공통 응답 구조

```json
{
  "meta": {
    "code": 200,
    "message": "성공",
    "trace_id": "abc123"
  },
  "response": [ ... ]
}
```

| code | 설명 |
|------|------|
| 200 | 성공 |
| 440 | 필수 파라미터 오류 |
| 441 | 파라미터 유효성 오류 |
| 500 | 내부 처리 오류 |
| 600 | 알 수 없는 오류 |

---

## 1. 주문 등록 (송장번호 채번)

**연동 시점:** 주문 `purchase_complete` 단계 전환 시  
**담당 코드:** `apps/logistics/dhub_client.py` → `DHubClient.register_order()`  
**연동 엔드포인트:** `POST /api/logistics/{order_number}/dhub/register/`

```
POST /api/order/add?mall_id={mall_id}
```

### Request Body

`request_data`는 JSON 배열. 하나의 요청에 여러 주문 포함 가능.

#### 주문(Order) 레벨 필드

| 필드 | 필수 | 타입 | 설명 | 우리 모델 매핑 |
|------|------|------|------|--------------|
| `seller_name` | ✅ | string(150) | 판매사명 | `DHUB_SELLER_NAME` env |
| `ord_date` | ✅ | string(YYYY-MM-DD) | 주문일자 | `Order.created_at` |
| `ord_bundle_no` | ✅ | string(40) | 합포번호 | `Order.group.group_number` |
| `currency_code` | ✅ | string(3) | 통화 | `JPY` (고정) |
| `country_domain` | ✅ | string(2) | 배송국가 | `JP` (고정) |
| `actual_payment` | | float | 실결제금액 | `Order.price_actual` |
| `coupon_discount_price` | | float | 쿠폰 할인 | `Order.price_discount` |
| `points_spent_amount` | | float | 적립금 사용 | `Order.price_points_used` |
| `receiver_name` | ✅ | string | 수령자명 | `UserAddress.name` |
| `receiver_name_voice` | △ | string | 수령자명(가타카나) — 일본 필수 | 요청 시 수동 입력 |
| `receiver_cell` | ✅ | string | 수령자 휴대전화 | `UserAddress.phone` |
| `receiver_email` | ✅ | string | 수령자 이메일 | 별도 입력 |
| `receiver_zipcode` | ✅ | string | 배송지 우편번호 | `UserAddress.zipcode` |
| `receiver_address1` | ✅ | string | 배송지 주소 | `UserAddress.address1` |
| `receiver_address2` | ✅ | string | 배송지 상세1 | `UserAddress.address2` |
| `receiver_address3` | | string | 배송지 상세2 | 빈 문자열 |
| `ship_fee` | | float | 배송료 | `Order.price_intl_shipping` |
| `delivery_message` | | string | 배송메시지 | 요청 시 입력 |

#### 품목(Item) 레벨 필드 (`item_list` 배열)

| 필드 | 필수 | 타입 | 설명 | 우리 모델 매핑 |
|------|------|------|------|--------------|
| `seller_ord_code` | ✅ | string(40) | 판매사 주문번호 | `Order.order_number` |
| `seller_ord_item_code` | ✅ | string(100) | 판매사 품주번호 | `Order.order_number` |
| `input_prd_name` | ✅ | string(500) | 상품명 | `Order.title` |
| `input_item_name` | ✅ | string(200) | 품목명 | `Order.title` |
| `ord_qty` | ✅ | integer | 수량 | `Order.quantity` |
| `selling_price` | ✅ | float | 판매가 | `Order.price_product` |
| `hs_code` | ✅ | string(6~12) | HS 코드 | `Order.prohibited_review['hs_code']` 또는 기본값 |
| `prd_category` | ✅ | string(200) | 통관용 카테고리명 | `Order.product_category` |
| `prd_category_info` | ✅ | string(380) | 통관용 상품명 | `Order.product_category` |
| `material` | △ | string(255) | 상품소재 — 일본 필수 | 요청 시 수동 입력 |
| `cloth_material` | △ | string(200) | 옷감 — 일본 필수 | 요청 시 수동 입력 |
| `discount_price` | | float | 상품별 할인 | `Order.price_discount` |

### Response

| 필드 | 타입 | 설명 |
|------|------|------|
| `fb_invoice_no` | string | **FB 송장번호** → `ShippingTracking.fb_invoice_no`에 저장 |
| `ord_no` | string | DHUB 출고지시번호 |
| `ord_bundle_no` | string | 합포번호 |
| `result` | bool | 등록 성공 여부 |
| `result_reason` | array | 실패 시 원인 |
| `delivery_type` | string | `FB`(패스트박스) / `SD`(자체물류) |
| `invoice_no` | string | 실 배송사 송장번호 (SD만) |

---

## 2. 배송지시

**연동 시점:** `LogisticsInfo.arrived_at` 입력 후 (입고 완료 → 국제 발송 지시)  
**담당 코드:** `DHubClient.instruct_delivery()`  
**연동 엔드포인트:** `POST /api/logistics/dhub/instruct/`

```
POST /api/delivery/instruction?mall_id={mall_id}
```

### Request Body

| 필드 | 필수 | 타입 | 설명 |
|------|------|------|------|
| `fb_invoice_no` | ✅ | array | FB 송장번호 목록 (최대 200개) |
| `instruction_requester` | ✅ | text | 배송지시 요청자 |
| `requester_phone` | ✅ | text | 요청자 연락처 |
| `packing_status` | ✅ | string(1) | `O` = 주문별 포장 |
| `delivery_type` | ✅ | string(1) | `P`=택배 / `Q`=퀵 / `E`=기타 |
| `parcel_company` | | string(100) | 택배사명 |
| `invoice_no` | | string(100) | 송장번호 |
| `arrival_due_date` | ✅ | string(YYYY-MM-DD) | 창고 도착 예정일 |
| `delivery_memo` | | string(500) | 메모 |

### Response

| 필드 | 설명 |
|------|------|
| `result[].fb_invoice_no` | FB 송장번호 |
| `result[].ord_bundle_no` | 합포번호 |
| `result[].result` | 처리 성공 여부 |
| `result[].result_reason` | 실패 원인 |
| `instruction_no` | **배송지시번호** → `ShippingTracking.dhub_instruction_no`에 저장 |

---

## 3. 주문 상세 조회

**연동 시점:** 상태 동기화 필요 시 (어드민 수동 또는 배경 작업)  
**담당 코드:** `DHubClient.get_order_detail()`

```
GET /api/order/detail?mall_id={mall_id}&fb_invoice_no={fb_invoice_no}
```

### 주요 응답 필드

| 필드 | 설명 | 저장 위치 |
|------|------|----------|
| `ord_status` | 주문 상태 코드 | `ShippingTracking.carrier_status` |
| `invoice_no` | 실 운송장 번호 | `ShippingTracking.tracking_number` |
| `company_name` | 배송사명 | `ShippingTracking.carrier` |
| `instruction_no` | 배송지시번호 | `ShippingTracking.dhub_instruction_no` |

---

## 4. 배송추적

**연동 시점:** 주기적 상태 폴링 또는 어드민 수동 동기화  
**담당 코드:** `DHubClient.get_tracking()`  
**연동 엔드포인트:** `POST /api/logistics/{order_number}/tracking/sync/`

```
GET /api/Tracking?mall_id={mall_id}&fb_invoice_no={fb_invoice_no}
```

### Request

| 파라미터 | 필수 | 설명 |
|----------|------|------|
| `mall_id` | ✅ | DHUB 몰 아이디 |
| `fb_invoice_no` | ✅ | FB 송장번호 |

### Response — `trace` 배열

| 필드 | 타입 | 설명 | 저장 위치 |
|------|------|------|----------|
| `status_code` | string | DHUB 상태 코드 | `ShippingTracking.carrier_status` |
| `status` | string | 상태명 | — |
| `status_msg` | string | 상태 메시지 | — |
| `courier` | string | 배송사명 | `ShippingTracking.carrier` |
| `location` | string | 위치 | — |
| `set_date_time` | string | 상태 일시 | `ShippingTracking.last_status_changed_at` |
| `status_type` | string | `I`=FastBox 내부 / `O`=해외 구간 | — |

### DHUB 상태코드 → 우리 시스템 매핑

| DHUB `status_code` | `carrier_status` | `customer_status` | `OrderStatusLog.stage` |
|--------------------|-----------------|-------------------|-----------------------|
| `ORE` | ORE | 주문 접수 | `order_received` |
| `RPE` | RPE | 국제 배송 준비 | `preparing_dispatch` |
| `RFI` | RFI | 일본 배송사 인계 | `jp_carrier_handover` |
| `InTransit` | InTransit | 국제 배송 중 | `intl_shipping` |
| `OutForDelivery` | OutForDelivery | 배달 예정 | `intl_shipping` |
| `Delivered` | Delivered | **배송 완료** | `delivered` |
| `AttemptFail` | AttemptFail | 배달 시도 실패 | `intl_shipping` |

> ⚠️ `status_type: "I"` (FastBox 내부 구간) 및 한국/일본 세관 구간은 조회 불가.  
> `is_untrackable_segment=true`로 표시.

### 지연 감지 기준

| 기준 | `delay_type` |
|------|-------------|
| 24시간 이상 상태 미변경 | `24h` |
| 48시간 이상 상태 미변경 | `48h` |
| 장기 지연 | `extended` |

---

## 연동 흐름 요약

```
1. 주문 purchase_complete →
   POST /api/logistics/{no}/dhub/register/
   → fb_invoice_no 채번 → ShippingTracking.fb_invoice_no 저장

2. 물류센터 입고 완료(arrived) →
   POST /api/logistics/dhub/instruct/
   → 배송지시 → instruction_no 저장

3. 주기적 추적 폴링 →
   POST /api/logistics/{no}/tracking/sync/
   → trace 이벤트 저장, customer_status·stage 업데이트
   → 지연 감지 시 delay_detected=true

4. 배송 완료(Delivered) →
   OrderStatusLog stage=delivered, Order.status=delivered
```
