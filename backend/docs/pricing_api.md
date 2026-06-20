# Pricing API

실시간 환율 조회 및 DK 구매대행 최종 견적(수수료 + 관세 + 환율 마진)을 계산하는 앱.

Base URL: `/api/pricing/`

---

## 엔드포인트 목록

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/pricing/exchange-rate/` | 실시간 환율 조회 |
| POST | `/api/pricing/quote/` | DK 구매대행 견적 계산 |
| GET | `/api/pricing/logs/` | 견적 이력 조회 |

---

## GET `/api/pricing/exchange-rate/`

실시간 환율을 조회한다. 기본 1시간 캐시를 사용한다.

### Query Parameters

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `base` | string | `JPY` | 기준 통화 (`JPY`, `USD`, `EUR`) |
| `target` | string | `KRW` | 대상 통화 (`KRW`, `JPY`, `USD`) |
| `use_cache` | boolean | `true` | 최근 1시간 이내 캐시 사용 여부 |

### Request 예시

```
GET /api/pricing/exchange-rate/
GET /api/pricing/exchange-rate/?base=JPY&target=KRW
GET /api/pricing/exchange-rate/?use_cache=false
```

### Response Body (200 OK)

| 필드 | 타입 | 설명 |
|------|------|------|
| `base` | string | 기준 통화 |
| `target` | string | 대상 통화 |
| `rate` | float | 환율 (1 기준통화당 대상통화) |
| `cached` | boolean | 캐시에서 반환된 결과인지 여부 |
| `cache_ttl_minutes` | integer | 캐시 유효 시간 (분) |

### Response 예시

```json
{
  "base": "JPY",
  "target": "KRW",
  "rate": 9.12,
  "cached": true,
  "cache_ttl_minutes": 60
}
```

### 에러 응답

| 상태 코드 | 조건 |
|-----------|------|
| `503 Service Unavailable` | 외부 환율 API 모두 응답 없음 |

---

## POST `/api/pricing/quote/`

DK 구매대행 최종 견적을 계산한다.  
환율은 직접 입력하거나 자동 조회하며, 관세율도 직접 지정하거나 상품명으로 자동 조회할 수 있다.

### Request Body

#### 상품 가격

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|------|------|------|--------|------|
| `discounted_price` | float\|null | 가격 중 하나 필수 | `null` | 할인가 (이 값을 기준으로 계산) |
| `original_price` | float\|null | 가격 중 하나 필수 | `null` | 정가 (`discounted_price`가 없을 때 사용) |
| `currency` | string | ❌ | `KRW` | 가격 통화 (`KRW` 또는 `JPY`) |

#### 환율

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|------|------|------|--------|------|
| `krw_per_jpy_market` | float\|null | ❌ | `null` | 시장 환율 (원/엔). 미입력 시 자동 조회 |

> 자동 조회 시 `GET /api/pricing/exchange-rate/`와 동일한 캐시 로직 사용.

#### 배송비

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|------|------|------|--------|------|
| `shipping_krw` | float | ❌ | `0.0` | 국내 배송비 (KRW). 마진 없이 통관 CIF에 포함 |
| `intl_shipping_jpy` | float | ❌ | `0.0` | 국제 배송비 (JPY). 원가 기준. 40% 마크업 적용해 청구 |

#### 관세

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|------|------|------|--------|------|
| `tariff_rate` | float\|null | ❌ | `null` | 관세율 직접 지정 (0~1). 최우선 적용 |
| `product_title` | string | ❌ | `""` | 관세율 자동 조회 시 사용할 상품명 |
| `use_tariff_lookup` | boolean | ❌ | `false` | `product_title`로 관세율 자동 조회 여부 |

> 관세율 결정 우선순위: `tariff_rate` 직접 지정 → `use_tariff_lookup` 조회 결과 → 기본값 5%

#### 수량 및 부가 옵션

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|------|------|------|--------|------|
| `quantity` | integer | ❌ | `1` | 수량 (종량세·혼합세 계산용) |
| `bundle_consolidation` | boolean | ❌ | `false` | 합배송 처리 (+200엔) |
| `photo_inspection` | boolean | ❌ | `false` | 사진 검수 서비스 (+300엔) |
| `speed_shipping` | boolean | ❌ | `false` | 스피드 출하 서비스 (+500엔) |

### Request 예시 — 기본

```json
{
  "discounted_price": 15000,
  "original_price": 20000,
  "currency": "KRW",
  "shipping_krw": 3000
}
```

### Request 예시 — 환율 직접 입력 + 관세율 조회

```json
{
  "discounted_price": 3500,
  "currency": "JPY",
  "krw_per_jpy_market": 9.15,
  "intl_shipping_jpy": 690,
  "use_tariff_lookup": true,
  "product_title": "블루투스 무선 이어폰",
  "quantity": 1
}
```

### Request 예시 — 부가 옵션 포함

```json
{
  "discounted_price": 8000,
  "currency": "JPY",
  "intl_shipping_jpy": 780,
  "bundle_consolidation": true,
  "photo_inspection": true,
  "tariff_rate": 0.0
}
```

### Response Body (200 OK)

| 필드 | 타입 | 설명 |
|------|------|------|
| `schema_version` | integer | 응답 스키마 버전 (현재 `1`) |
| `product_currency` | string | 상품 통화 |
| `product_jpy_nominal_market` | float | 시장 환율 기준 상품 JPY 명목가 |
| `tariff_policy` | object | 관세 정책 정보 |
| `exchange` | object | 환율 정보 |
| `lines` | object[] | 항목별 비용 명세 (고객 노출) |
| `lines_hidden` | object[] | 내부 환율 마진 등 숨김 항목 |
| `domestic_shipping_krw` | float | 국내 배송비 (KRW) |
| `domestic_shipping_jpy` | float\|null | 국내 배송비 (시장 환율 환산 JPY) |
| `subtotal_jpy` | float | JPY 소계 |
| `subtotal_krw` | float | KRW 소계 |
| `subtotal_krw_ceil_won` | integer | KRW 소계 올림 (원 단위) |
| `total_jpy_estimated` | float | JPY 합계 |
| `total_jpy_estimated_ceil` | integer | JPY 합계 올림 |
| `total_krw_estimated` | float | KRW 합계 |
| `total_krw_estimated_ceil_won` | integer | KRW 합계 올림 (원 단위) |
| `customs` | object | 통관 추정 정보 |
| `points_earn_krw` | float | 포인트 적립 예상액 (KRW, 합계 미포함) |
| `points_note` | string | 포인트 안내 |
| `disclaimer` | string | 면책 고지 |
| `_meta` | object | API 메타 정보 |

**`tariff_policy` 객체**

| 필드 | 타입 | 설명 |
|------|------|------|
| `uses_tariff_table_lookup` | boolean | 관세율표 조회 사용 여부 |
| `non_physical` | boolean | 비실물 품목 여부 |
| `matched_item` | string\|null | 매칭된 관세율표 품명 |
| `rate_source` | string | 세율 출처 (`request`/`lookup_rcep`/`default` 등) |
| `duty_type` | string | 세율 유형 |
| `applied_rate` | float | 최종 적용 세율 |
| `fallback_reason` | string\|null | 기본값 사용 이유 |
| `note` | string\|null | 안내 메시지 |

**`exchange` 객체**

| 필드 | 타입 | 설명 |
|------|------|------|
| `krw_per_jpy_market` | float | 시장 환율 (원/엔) |
| `krw_per_jpy_customer` | float | 고객 청구 환율 = 시장환율 / 1.04 |
| `margin_rate_pct` | float | 환율 마진율 (%) = `4.0` |

**`lines` 항목 구조**

| 필드 | 타입 | 설명 |
|------|------|------|
| `code` | string | 항목 코드 |
| `label` | string | 표시 명칭 |
| `jpy` | float | JPY 금액 |
| `krw` | float | KRW 금액 (고객 환율 적용) |
| `visible` | boolean | 고객 노출 여부 |
| `note` | string | 비고 (선택) |

**`lines`에 포함되는 항목 코드**

| code | 설명 | 조건 |
|------|------|------|
| `product` | 상품가 (할인가 기준) | 항상 |
| `domestic_shipping` | 국내 배송비 | 항상 (0원이어도 표시) |
| `agency_fee` | 구매대행 수수료 | 항상 |
| `intl_shipping` | 국제 배송비 (마크업 적용) | `intl_shipping_jpy > 0` |
| `bundle_consolidation` | 합배송 처리비 | `bundle_consolidation=true` |
| `photo_inspection` | 사진 검수 서비스 | `photo_inspection=true` |
| `speed_shipping` | 스피드 출하 서비스 | `speed_shipping=true` |
| `customs_duty_vat` | 통관 추정 (관세 + 부가세) | 과세 추정 시 |

**`customs` 객체**

| 필드 | 타입 | 설명 |
|------|------|------|
| `duty_free` | boolean | 면세 여부 |
| `rule` | string | 면세/과세 판단 기준 |
| `cif_times_60pct_jpy` | float | (상품가+국내배송+국제배송) × 60% (JPY) |
| `approx_exempt_product_jpy_max` | float | 면세 적용 가능 최대 상품가 (JPY) ≈ 16,667엔 |
| `duty_jpy` | float | 관세 (과세 시) |
| `vat_jpy` | float | 부가세 (과세 시) |
| `tax_subtotal_jpy` | float | 세금 소계 = 관세 + 부가세 |

> 면세 기준: `(상품가 + 국내배송 + 국제배송) × 60% ≤ 10,000엔`

**`_meta` 객체**

| 필드 | 타입 | 설명 |
|------|------|------|
| `krw_per_jpy_market_used` | float | 실제 적용된 시장 환율 |
| `exchange_rate_cached` | boolean\|null | 환율 캐시 사용 여부 (`null`: 직접 입력) |
| `tariff_lookup_used` | boolean | 관세율 조회 사용 여부 |

### Response 예시

```json
{
  "schema_version": 1,
  "product_currency": "KRW",
  "product_jpy_nominal_market": 1639.34,
  "tariff_policy": {
    "uses_tariff_table_lookup": false,
    "non_physical": false,
    "matched_item": null,
    "rate_source": "default",
    "duty_type": "ad_valorem",
    "applied_rate": 0.0,
    "fallback_reason": null,
    "note": null
  },
  "exchange": {
    "krw_per_jpy_market": 9.15,
    "krw_per_jpy_customer": 8.798,
    "margin_rate_pct": 4.0
  },
  "lines": [
    {
      "code": "product",
      "label": "상품 (할인가 기준)",
      "jpy": 1639.34,
      "krw": 15000.0,
      "visible": true
    },
    {
      "code": "domestic_shipping",
      "label": "국내 배송비",
      "jpy": 327.87,
      "krw": 3000.0,
      "visible": true,
      "note": "마진 없음 · 과세 CIF에 포함"
    },
    {
      "code": "agency_fee",
      "label": "구매대행 수수료",
      "jpy": 300,
      "krw": 2639.34,
      "visible": true,
      "note": "상품가 10,000엔 이하 300엔 / 초과 500엔"
    }
  ],
  "lines_hidden": [ ... ],
  "domestic_shipping_krw": 3000.0,
  "subtotal_jpy": 2267.21,
  "subtotal_krw": 20639.34,
  "subtotal_krw_ceil_won": 20640,
  "total_jpy_estimated": 2267.21,
  "total_jpy_estimated_ceil": 2268,
  "total_krw_estimated": 20639.34,
  "total_krw_estimated_ceil_won": 20640,
  "customs": {
    "duty_free": true,
    "rule": "(상품가+국내배송비+국제배송비) × 60% ≤ 10,000엔 → 면세 추정",
    "cif_times_60pct_jpy": 1178.53,
    "approx_exempt_product_jpy_max": 16666.67
  },
  "points_earn_krw": 150.0,
  "points_note": "할인가(표시 통화) 기준 1% 적립 안내 — 고객 환율(일본 청구 기준, 마진 반영) 적용",
  "disclaimer": "추정 금액입니다. 실제 관세·환율은 결제(송금) 시점 및 품목·신고에 따라 달라질 수 있습니다.",
  "_meta": {
    "krw_per_jpy_market_used": 9.15,
    "exchange_rate_cached": null,
    "tariff_lookup_used": false
  }
}
```

### 에러 응답

| 상태 코드 | 조건 |
|-----------|------|
| `400 Bad Request` | `discounted_price`와 `original_price` 모두 `null` |
| `503 Service Unavailable` | `krw_per_jpy_market` 미입력 + 환율 자동 조회 실패 |

---

## GET `/api/pricing/logs/`

최근 50건의 견적 이력을 반환한다.

### Response Body (200 OK)

```json
[
  {
    "id": 3,
    "original_price": 20000.0,
    "discounted_price": 15000.0,
    "currency": "KRW",
    "krw_per_jpy_market": 9.15,
    "result": { ... },
    "created_at": "2026-06-01T10:30:00+09:00"
  }
]
```

---

## DB 모델 구조

### ExchangeRateLog

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | AutoField | PK |
| `base_currency` | CharField(5) | 기준 통화 |
| `target_currency` | CharField(5) | 대상 통화 |
| `rate` | FloatField | 환율 |
| `source` | CharField(100) | 데이터 출처 URL |
| `fetched_at` | DateTimeField | 조회 시각 |

### PricingQuoteLog

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | AutoField | PK |
| `original_price` | FloatField\|null | 정가 |
| `discounted_price` | FloatField\|null | 할인가 |
| `currency` | CharField(5) | 통화 |
| `krw_per_jpy_market` | FloatField | 적용 시장 환율 |
| `result` | JSONField | 계산 결과 전체 |
| `created_at` | DateTimeField | 생성 시각 |

---

## 환경 변수

| 변수명 | 기본값 | 설명 |
|--------|--------|------|
| `EXCHANGE_CACHE_MINUTES` | `60` | 환율 캐시 유효 시간 (분) |
| `ANTHROPIC_API_KEY` | — | 관세율 자동 조회 시 필요 |
| `DK_AGENCY_FEE_LOW_JPY` | `300` | 구매대행 수수료 (10,000엔 이하) |
| `DK_AGENCY_FEE_HIGH_JPY` | `500` | 구매대행 수수료 (10,000엔 초과) |
| `DK_AGENCY_THRESHOLD_JPY` | `10000` | 수수료 구간 기준 (엔) |
| `DK_CUSTOMS_RATIO` | `0.6` | 통관 면세 판정 비율 (60%) |
| `DK_CUSTOMS_EXEMPT_JPY` | `10000` | 통관 면세 기준선 (엔) |
| `DK_CONSUMPTION_TAX_RATE` | `0.10` | 일본 소비세율 (10%) |
| `DK_DEFAULT_TARIFF_RATE` | `0.05` | 기본 관세율 (5%) |
| `DK_TAX_ADVANCE_FEE_RATE` | `0.05` | 세금 대납 수수료율 (5%, 숨김) |
| `DK_EXCHANGE_MARGIN_RATE` | `0.04` | 환율 마진율 (4%) |
| `DK_INTL_SHIPPING_MARKUP_RATE` | `1.4` | 국제 배송비 마크업 배율 (40%) |
| `DK_POINTS_RATE` | `0.01` | 포인트 적립율 (1%) |
| `DK_BUNDLE_FEE_JPY` | `200` | 합배송 수수료 (엔) |
| `DK_PHOTO_INSPECTION_JPY` | `300` | 사진 검수 수수료 (엔) |
| `DK_SPEED_SHIP_JPY` | `500` | 스피드 출하 수수료 (엔) |
