# 디허브(DHUB) / 패스트박스(FastBox) 배송사 외부 API

배송사(패스트박스)가 제공하는 **디허브 웹시스템 API** 스펙.  
우리 Django 백엔드가 이 API를 직접 호출한다 (`apps.logistics.dhub_client.DHubClient`).

> **계약 현황**: 계약 진행 중. 상세 연동 가이드는 계약 완료 후 배송사로부터 별도 제공 예정.  
> 현재 QA 환경(`dhub-api-qa.hanpda.com`) 기준으로 구현되어 있음.

---

## Commercial Invoice (수출신고·통관신고용 송장)

한국→일본 국제특송은 단순 배송지 정보가 아니라 **세관 제출용 Commercial Invoice** 가 필요하다.  
DHUB 주문 등록 시 `item_list`가 이 역할을 하며, 일본 세관이 품목별 세율·수입규제·검역 여부를 판단한다.

### Invoice 3개 영역

```
┌─────────────────────────────────────────────┐
│  SHIPPER (발송인)          — 한국 세관·택배사 확인
│  회사명: 주식회사 DK
│  주소:   인천 동구 송림로 108
│  전화:   070-4710-0021
├─────────────────────────────────────────────┤
│  CONSIGNEE (수취인)        — 일본 세관·배송사 확인
│  이름:   辛東赫 / SHIN DONGHYUK
│  전화:   080-9122-3497
│  우편번호: 547-0024
│  주소:   大阪府大阪市平野区瓜破 1-5-1-3F
├─────────────────────────────────────────────┤
│  INVOICE LIST (품목 명세)  — 일본 세관 심사 대상
│  품목(한국어)   품목(영문)             수량  단가  합계
│  남성 반팔 티셔츠  Men's Cotton T-Shirt   2   20   40 USD
└─────────────────────────────────────────────┘
```

### SHIPPER 정보

고정값 (`SiteConfig` 또는 환경변수로 관리).

| 항목 | 값 |
|------|-----|
| 발송인명 | 주식회사 DK (Boltlab DK) |
| 주소 | 인천 동구 송림로 108 |
| 전화 | 070-4710-0021 |

### CONSIGNEE 정보

`UserAddress` 모델에서 가져온다.

| UserAddress 필드 | Invoice 항목 | 비고 |
|-----------------|-------------|------|
| `name` | 수취인명 (한자) | |
| `name_en` | 수취인명 (영문) | 세관 서류 필수 |
| `name_kana` | 수취인명 (가타카나) | 일본 배송사 필수 |
| `date_of_birth` | 생년월일 | 일본 통관 필수 |
| `phone` | 전화번호 | |
| `zipcode` | 우편번호 | |
| `address1` | 주소 | |

### INVOICE LIST (품목 명세)

`ProductSnapshot` 모델에서 가져온다.

| ProductSnapshot 필드 | Invoice 항목 | 비고 |
|--------------------|-------------|------|
| `product_name` | 품목명 (한국어) | 내부 참조용 |
| `product_name_en` | 품목명 (영문) | **세관 필수** — 반드시 실제 품목명으로 기입 |
| `quantity` | 수량 | |
| `purchase_price` | 단가 (JPY 기준) | USD 환산 필요 |
| `options` | 옵션 상세 | |

> **주의**: 영문 품목명은 실제 품목으로 작성해야 한다.  
> ❌ `Gift`, `Present`, `Goods` → 세관 거부 사유  
> ✅ `Men's Cotton T-Shirt`, `Baseball Cap`, `Photo Card`

### 품목별 세관 처리 차이

| 분류 | 세금 | 수입규제 | 검역 |
|------|------|---------|------|
| 의류 | 과세 | 일반 | 없음 |
| 전자기기 | 과세 | 전파법 인증 확인 | 없음 |
| 화장품 | 과세 | 성분 규제 | 없음 |
| 식품 | 과세 | 식품위생법 | 검역 필요 |
| 의약품 | 과세 | 수입 원칙 금지 | 검역 필요 |

> `apps.prohibited.ProhibitedKeyword`에 수입금지·제한 품목 키워드 관리.  
> 참고: https://www.customs.go.jp/mizugiwa/kinshi.htm

### product_name_en 입력 방법

| 방법 | 비고 |
|------|------|
| 크롤러 추출 | 상품 페이지에 영문 품목명이 있으면 자동 추출 |
| DeepL 번역 | `apps.translate` — 한국어 품목명 자동 번역 |
| 운영자 수동 입력 | 어드민에서 직접 수정 |

미입력(`product_name_en = ''`) 상태로 DHUB 등록 시 `input_prd_name`(한국어)이 그대로 전송되어 세관 문제 발생 가능.

---

## 참고 자료 (배송사 제공)

| 항목 | URL |
|------|-----|
| 일본 관세율 (2026.04.01 기준) | https://www.customs.go.jp/tariff/2026_04_01/index.htm |
| 일본 수입 금지·제한 품목 | https://www.customs.go.jp/mizugiwa/kinshi.htm |
| 항공 탑재 불가 품목 (EMS 기준) | https://ems.epost.go.kr/front.Introduction04New.postal |

> 수입금지품목·항공탑재불가품목은 주문 접수 시 상품 카테고리와 대조하여 사전 필터링 필요.  
> 관련 DB 모델: `apps.prohibited` (`ProhibitedItem`)

---

## 기본 정보

| 항목 | 값 |
|------|-----|
| QA Host | `https://dhub-api-qa.hanpda.com` |
| Production Host | 계약 후 확인 |
| Protocol | HTTPS + JSON |
| 인증 방식 | Bearer Token + Consumer Key 헤더 |

### 인증 헤더

```http
Authorization: Bearer {DHUB_TOKEN}
consumerKey: {DHUB_CONSUMER_KEY}
Content-Type: application/json
```

### 공통 쿼리 파라미터

모든 엔드포인트에 `?mall_id={DHUB_MALL_ID}` 필수.

### 공통 응답 구조

```json
{
  "meta": { "code": 200, "message": "OK" },
  "response": { ... }
}
```

`meta.code != 200` 이면 `DHubError(code, message)` 예외 발생.

---

## 1. 주문 등록

`POST /api/order/add?mall_id={mall_id}`

패스트박스에 국제배송 주문을 등록하고 **FB 송장번호**를 채번한다.  
**호출 시점**: 주문 `purchase_complete` 단계 전환 시.

### Request Body

```json
[
  {
    "seller_name": "Boltlab DK",
    "ord_date": "2026-06-19",
    "ord_bundle_no": "ORD-20260619-ABCD",
    "currency_code": "JPY",
    "country_domain": "JP",
    "actual_payment": 15000,
    "coupon_discount_price": 0,
    "points_spent_amount": 0,
    "receiver_name": "홍길동",
    "receiver_name_voice": "ホンギルドン",
    "receiver_cell": "010-1234-5678",
    "receiver_email": "user@example.com",
    "receiver_zipcode": "100-0001",
    "receiver_address1": "東京都千代田区",
    "receiver_address2": "1-1-1",
    "receiver_address3": "",
    "ship_fee": 3000,
    "delivery_message": "부재 시 문 앞에 두세요",
    "item_list": [
      {
        "seller_ord_code": "ORD-20260619-ABCD",
        "seller_ord_item_code": "ITEM-001",
        "input_prd_name": "나이키 에어맥스",
        "input_item_name": "나이키 에어맥스 270 블랙 270mm",
        "ord_qty": 1,
        "selling_price": 15000,
        "hs_code": "640299",
        "prd_category": "신발",
        "prd_category_info": "운동화",
        "material": "합성섬유 100%",
        "cloth_material": "Synthetic",
        "discount_price": 0
      }
    ]
  }
]
```

### Request 필드

| 필드 | 필수 | 타입 | 설명 |
|------|------|------|------|
| `seller_name` | ✅ | string | 판매자명 (기본값: `Boltlab DK`) |
| `ord_date` | ✅ | string | 주문일 (`YYYY-MM-DD`) |
| `ord_bundle_no` | ✅ | string | 주문번호 (우리 `order_number`) |
| `currency_code` | ✅ | string | `JPY` |
| `country_domain` | ✅ | string | `JP` |
| `actual_payment` | ✅ | float | 실 결제금액 |
| `receiver_name` | ✅ | string | 수령자명 |
| `receiver_cell` | ✅ | string | 수령자 연락처 |
| `receiver_email` | ✅ | string | 수령자 이메일 |
| `receiver_zipcode` | ✅ | string | 배송지 우편번호 |
| `receiver_address1` | ✅ | string | 배송지 주소 1 |
| `receiver_name_voice` | △ | string | 수령자명 가타카나 (일본 배송 필수) |
| `material` | △ | string | 소재 (일본 통관 필수) |
| `cloth_material` | △ | string | 옷감 (일본 통관 필수) |
| `coupon_discount_price` | ❌ | float | 쿠폰 할인액 |
| `points_spent_amount` | ❌ | float | 포인트 사용액 |
| `ship_fee` | ❌ | float | 국제 배송비 |
| `delivery_message` | ❌ | string | 배송 요청사항 |

#### item_list 필드

| 필드 | 필수 | 설명 |
|------|------|------|
| `seller_ord_code` | ✅ | 주문번호 |
| `seller_ord_item_code` | ✅ | 상품 고유코드 |
| `input_prd_name` | ✅ | 상품명 (최대 500자) |
| `input_item_name` | ✅ | 옵션명 (최대 200자) |
| `ord_qty` | ✅ | 수량 |
| `selling_price` | ✅ | 판매가 |
| `hs_code` | ❌ | HS 코드 (기본값: `621790`) |
| `prd_category` | ❌ | 상품 카테고리 |
| `material` | ❌ | 소재 |
| `cloth_material` | ❌ | 옷감 |
| `discount_price` | ❌ | 할인액 |

### Response

```json
{
  "meta": { "code": 200, "message": "OK" },
  "response": [
    {
      "fb_invoice_no": "FB20260619001",
      "ord_no": "ORD20260001",
      "ord_bundle_no": "ORD-20260619-ABCD",
      "result": true,
      "result_reason": "",
      "delivery_type": "FB"
    }
  ]
}
```

| 필드 | 설명 |
|------|------|
| `fb_invoice_no` | **FastBox 송장번호** → `ShippingTracking.fb_invoice_no` 저장 |
| `ord_no` | DHUB 내부 주문번호 |
| `delivery_type` | `FB`(FastBox) / `SD`(자체물류) |
| `result` | 등록 성공 여부 |
| `result_reason` | 실패 사유 |

---

## 2. 배송 추적

`GET /api/Tracking?mall_id={mall_id}&fb_invoice_no={fb_invoice_no}`

FastBox 송장번호로 실시간 배송 이력을 조회한다.  
**호출 시점**: 주기적 폴링 (`next_check_at` 기준) 또는 어드민 수동 동기화.

### Response

```json
{
  "meta": { "code": 200, "message": "OK" },
  "response": {
    "order": {
      "Domestic_Invoice_No": "123456789",
      "Shipping_Company": "ヤマト運輸"
    },
    "trace": [
      {
        "status_code": "InTransit",
        "location": "仁川国際空港",
        "timestamp": "2026-06-19T10:00:00"
      }
    ]
  }
}
```

### 상태코드 매핑

| DHUB `status_code` | 고객 표시 | `Order.status` 연동 |
|--------------------|---------|---------------------|
| `ORE` | 주문 접수 | — |
| `RPE` | 국제 배송 준비 | `shipping_intl` |
| `RFI` | 일본 배송사 인계 | `shipping_intl` |
| `InTransit` | 국제 배송 중 | `shipping_intl` |
| `OutForDelivery` | 배달 예정 | `shipping_intl` |
| `Delivered` | 배송 완료 | `delivered` |
| `AttemptFail` | 배달 시도 실패 | — |

`Domestic_Invoice_No` → `ShippingTracking.tracking_number` (일본 국내 배송 운송장, 차지백 분쟁 시 배송 증빙)

---

## 3. 배송 지시

`POST /api/delivery/instruction?mall_id={mall_id}`

패스트박스 창고에서 국제 발송을 지시한다.  
**호출 시점**: 입고 완료(`arrived_at` 입력) 후 어드민 수동 호출.

### Request Body

```json
{
  "fb_invoice_no": ["FB20260619001", "FB20260619002"],
  "instruction_requester": "담당자명",
  "requester_phone": "02-000-0000",
  "packing_status": "O",
  "delivery_type": "P",
  "arrival_due_date": "2026-06-25"
}
```

| 필드 | 필수 | 설명 |
|------|------|------|
| `fb_invoice_no` | ✅ | FB 송장번호 배열 (최대 200개) |
| `arrival_due_date` | ✅ | 창고 도착 예정일 (`YYYY-MM-DD`) |
| `instruction_requester` | ❌ | 배송지시 요청자명 |
| `requester_phone` | ❌ | 요청자 연락처 |
| `packing_status` | — | 고정값 `O` |
| `delivery_type` | — | 고정값 `P` |

### Response

```json
{
  "meta": { "code": 200, "message": "OK" },
  "response": {
    "instruction_no": "INST20260001",
    "result": [
      { "fb_invoice_no": "FB20260619001", "result": true }
    ]
  }
}
```

`instruction_no` → `ShippingTracking.dhub_instruction_no` 저장됨.

---

## 에러 처리

| `meta.code` | 의미 | 대응 |
|-------------|------|------|
| `200` | 성공 | — |
| `400` | 요청 오류 | 파라미터 검토 |
| `401` | 인증 실패 | TOKEN / CONSUMER_KEY 확인 |
| `404` | 리소스 없음 | fb_invoice_no 확인 |
| `500` | DHUB 서버 오류 | 재시도 또는 배송사 문의 |

`DHubError(code, message)` 예외로 래핑되어 Django 뷰에서 처리됨.

---

## 환경변수

```
DHUB_BASE_URL=https://dhub-api-qa.hanpda.com   # QA. 계약 후 prod URL로 변경
DHUB_MALL_ID=                                   # 디허브 mall 식별자
DHUB_TOKEN=                                     # Bearer 인증 토큰
DHUB_CONSUMER_KEY=                              # 헤더 consumerKey
DHUB_SELLER_NAME=Boltlab DK                     # 주문 등록 시 seller_name 기본값
```

---

## 배송 흐름 전체

```
주문 접수 (Django)
    ↓
카드 Auth (GMO)
    ↓
한국 상품 확보 → 주문 등록 API 호출 → FB 송장번호 채번
    ↓
패스트박스 창고 입고 (물리적)
    ↓
검수 완료 → 배송지시 API 호출
    ↓
Capture (GMO 매출 확정)
    ↓
패스트박스 → 일본 현지 배송사 인계
    ↓
배송 추적 폴링 (fb_invoice_no 기준)
    ↓
배송 완료 (Domestic_Invoice_No = 차지백 증빙)
```
