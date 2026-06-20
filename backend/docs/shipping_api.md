# Shipping API

한국 → 일본 B2C 국제 배송비를 계산하는 앱.  
KSE(해상/항공/SDEX), CJL(Door-to-Door), FastBox(항공특송), EMS를 지원한다.  
배송사·무게기준은 Admin에서 동적 설정.

Base URL: `/api/shipping/`

---

## 엔드포인트 목록

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/shipping/quote/` | 배송비 견적 계산 (수동 1건) |
| GET | `/api/shipping/logs/` | 견적 이력 조회 |
| POST | `/api/shipping/intl-estimate/` | 국제 배송비 자동 견적 (무게 기반 다배송사) |

---

## POST `/api/shipping/quote/`

배송비 견적을 계산한다.

### Request Body

#### 필수 파라미터

| 필드 | 타입 | 설명 |
|------|------|------|
| `service_provider` | string | 배송 서비스 (`KSE` 또는 `CJL`) |
| `transport_mode` | string | 운송 수단 |
| `actual_weight_kg` | float | 실제 무게 (kg, 최소 0.001) |

**`service_provider` + `transport_mode` 유효 조합**

| service_provider | transport_mode | 설명 |
|------------------|----------------|------|
| `KSE` | `SEA` | KSE 해상 |
| `KSE` | `AIR` | KSE 항공 |
| `KSE` | `SDEX` | KSE SDEX |
| `CJL` | `DOOR_TO_DOOR` | CJL Door to Door |

#### 치수 (선택, 부피무게 계산에 사용)

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `width_cm` | float\|null | `null` | 가로 (cm) |
| `length_cm` | float\|null | `null` | 세로 (cm) |
| `height_cm` | float\|null | `null` | 높이 (cm) |
| `thickness_cm` | float\|null | `null` | 두께 (cm) — KSE Light 판정용 |
| `longest_side_cm` | float\|null | `null` | 가장 긴 변 (cm) |
| `girth_sum_cm` | float\|null | `null` | 세 변의 합 (cm). 미입력 시 `width+length+height` 자동 계산 |

> KSE Light (YU-PACKET) 판정: `girth_sum ≤ 60cm` AND `longest_side ≤ 34cm` AND `thickness ≤ 3cm` AND `weight ≤ 1kg`  
> KSE Standard (YU-PACK) 판정: `girth_sum ≤ 160cm` AND `weight ≤ 30kg`  
> KSE 부피무게: `(width × length × height) / 6000`  
> 과금무게: `max(실제무게, 부피무게)`

#### 통관/지역

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `invoice_value_jpy` | float | `0.0` | 신고 금액 (JPY) |
| `destination_region` | string | `EAST_JAPAN` | 배송 지역 |
| `export_declaration_type` | string | `NONE` | 수출신고 유형 |
| `vat_rate` | float\|null | `null` | 수출신고비 VAT율 (`SIMPLIFIED`/`LIST_CONVERSION` 선택 시 필수) |

**`destination_region` 허용값**

| 값 | 설명 |
|----|------|
| `EAST_JAPAN` | 동일본 (기본값) |
| `WEST_JAPAN` | 서일본 |
| `JEJU` | 제주 |

**`export_declaration_type` 허용값**

| 값 | 비용 | 설명 |
|----|------|------|
| `NONE` | 0원 | 신고 없음 (기본값) |
| `MANIFEST` | 0원 | 목록통관 (수출실적 불인정) |
| `SIMPLIFIED` | 200원 + VAT | 간이수출신고 (수출실적 인정) |
| `LIST_CONVERSION` | 150원 + VAT | 수출목록변환신고 |

#### 서비스 옵션

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `box_count` | integer | `1` | 박스 수 (CJL 지역추가비 계산용) |
| `item_count` | integer | `1` | 아이템 수 (3PL 피킹비 계산용) |
| `fsc_amount_jpy` | float\|null | `null` | AIR FSC 금액 (JPY). KSE AIR 선택 시 입력 권장 |
| `requested_service_class` | string\|null | `null` | KSE 서비스 클래스 힌트. 미지정 시 자동 판정 |

**`requested_service_class` 허용값**

| 값 | 설명 |
|----|------|
| `LIGHT` | Light(YU-PACKET) 강제 요청. 규격 미충족 시 STANDARD로 자동 변경 |
| `STANDARD` | Standard(YU-PACK) 강제 지정 |
| `null` | 자동 판정 (기본) |

#### 화물 특성

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `has_battery` | boolean | `false` | 배터리 포함 여부 |
| `is_alcohol` | boolean | `false` | 주류 여부 |
| `is_tobacco` | boolean | `false` | 담배 여부 |
| `is_food_or_quarantine` | boolean | `false` | 식검 대상 여부 |
| `is_dangerous_goods` | boolean | `false` | 위험물 여부 |

> 화물 특성이 `true`이면 `requires_manual_review: true` 및 `warnings` 항목 추가. 즉시 거절되지는 않는다.

#### 3PL (선택)

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `inbound_type` | string\|null | `null` | 입고 유형 (`PALLET` 또는 `BOX`) |
| `storage_type` | string\|null | `null` | 보관 유형 (`PALLET` 또는 `SHELF`) |
| `label_work_count` | integer | `0` | 라벨 작업 수량 |
| `return_processing_count` | integer | `0` | 반품 처리 수량 |

### Request 예시 — KSE 해상

```json
{
  "service_provider": "KSE",
  "transport_mode": "SEA",
  "actual_weight_kg": 1.2,
  "width_cm": 25,
  "length_cm": 20,
  "height_cm": 15
}
```

### Request 예시 — KSE 항공 + 수출신고

```json
{
  "service_provider": "KSE",
  "transport_mode": "AIR",
  "actual_weight_kg": 0.8,
  "width_cm": 20,
  "length_cm": 15,
  "height_cm": 5,
  "thickness_cm": 5,
  "longest_side_cm": 20,
  "fsc_amount_jpy": 200,
  "export_declaration_type": "SIMPLIFIED",
  "vat_rate": 0.1,
  "invoice_value_jpy": 5000
}
```

### Request 예시 — CJL

```json
{
  "service_provider": "CJL",
  "transport_mode": "DOOR_TO_DOOR",
  "actual_weight_kg": 2.5,
  "invoice_value_jpy": 8000,
  "destination_region": "WEST_JAPAN"
}
```

### Response Body (200 OK)

| 필드 | 타입 | 설명 |
|------|------|------|
| `request_id` | string (UUID) | 요청 고유 ID |
| `calculated_at` | string (ISO 8601) | 계산 시각 |
| `is_available` | boolean | 배송 가능 여부 |
| `requires_manual_review` | boolean | 수동 검토 필요 여부 (주의 품목 등) |
| `is_estimate_complete` | boolean | 견적 완전 여부 (FSC 미입력 등이면 `false`) |
| `rejection_reasons` | object[] | 즉시 거절 사유 목록 |
| `warnings` | object[] | 경고 목록 |
| `selected_rate_table` | string\|null | 적용된 요율표 키 (예: `SEA_STANDARD`) |
| `selected_service_class` | string\|null | 적용된 서비스 클래스 |
| `selected_service_provider` | string | 서비스 제공사 |
| `selected_transport_mode` | string | 운송 수단 |
| `dimension_check` | object\|null | 치수 검증 결과 |
| `customs_check` | object\|null | 통관 기준 체크 |
| `freight_breakdown` | object\|null | 운임 명세 |
| `export_declaration_breakdown` | object\|null | 수출신고비 명세 (KSE만) |
| `fulfillment_breakdown` | object\|null | 3PL 비용 명세 (KSE만) |
| `lead_time_estimate` | object\|null | 예상 리드타임 |
| `notes` | string[] | 주의사항 |

**`rejection_reasons` / `warnings` 항목 구조**

```json
{
  "code": "KSE_LIGHT_DOWNGRADED_TO_STANDARD",
  "message": "Light 규격 미충족 → Standard로 자동 변경"
}
```

**`freight_breakdown` (KSE)**

```json
{
  "provider": "KSE",
  "kse": {
    "is_available": true,
    "service_class": "STANDARD",
    "selected_rate_table": "SEA_STANDARD",
    "actual_weight_kg": 1.2,
    "volumetric_weight_kg": 1.25,
    "chargeable_weight_kg": 1.25,
    "weight_break_applied_kg": 1.25,
    "base_freight_jpy": 740,
    "fsc_jpy": 0,
    "total_freight_jpy": 740,
    "currency": "JPY"
  }
}
```

**`freight_breakdown` (CJL)**

```json
{
  "provider": "CJL",
  "cjl": {
    "is_available": true,
    "actual_weight_kg": 2.5,
    "chargeable_weight_kg": 2.5,
    "weight_break_applied_kg": 2.5,
    "base_freight_krw": 11500,
    "regional_fee_jpy": 1800,
    "total_freight_krw": 11500,
    "is_tax_exempt": true,
    "is_estimate_complete": true,
    "currency_note": "기본 운임: KRW / 지역추가비: JPY — 혼합 통화"
  }
}
```

### Response 예시 — KSE SEA 성공

```json
{
  "request_id": "a1b2c3d4-...",
  "calculated_at": "2026-06-01T10:00:00Z",
  "is_available": true,
  "requires_manual_review": false,
  "is_estimate_complete": true,
  "rejection_reasons": [],
  "warnings": [],
  "selected_rate_table": "SEA_STANDARD",
  "selected_service_class": "STANDARD",
  "selected_service_provider": "KSE",
  "selected_transport_mode": "SEA",
  "dimension_check": {
    "girth_sum_cm": 60,
    "longest_side_cm": 25,
    "thickness_cm": null,
    "passed_light_check": false,
    "passed_standard_check": true
  },
  "customs_check": {
    "invoice_value_jpy": 0,
    "tax_exempt_threshold_jpy": 10000,
    "is_tax_exempt": true,
    "max_invoice_limit_jpy": 300000
  },
  "freight_breakdown": {
    "provider": "KSE",
    "kse": {
      "is_available": true,
      "service_class": "STANDARD",
      "actual_weight_kg": 1.2,
      "volumetric_weight_kg": 1.25,
      "chargeable_weight_kg": 1.25,
      "weight_break_applied_kg": 1.25,
      "base_freight_jpy": 740,
      "fsc_jpy": 0,
      "total_freight_jpy": 740,
      "currency": "JPY"
    }
  },
  "export_declaration_breakdown": { "type": "NONE", "total_fee_krw": 0 },
  "fulfillment_breakdown": { "total_fulfillment_krw": 900 },
  "lead_time_estimate": { "min_days": 3, "max_days": 5, "delay_risks": ["..."] },
  "notes": ["KSE 운송요금: JPY 기준 / 통관·3PL 비용: KRW 기준 (혼합 통화)"]
}
```

### 에러 응답

| 상태 코드 | 조건 |
|-----------|------|
| `400 Bad Request` | 잘못된 파라미터 또는 계산 중 예외 |

---

## GET `/api/shipping/logs/`

최근 50건의 배송비 견적 이력을 반환한다.

### Response Body (200 OK)

```json
[
  {
    "id": 7,
    "service_provider": "KSE",
    "transport_mode": "SEA",
    "actual_weight_kg": 1.2,
    "result": { ... },
    "is_available": true,
    "created_at": "2026-06-01T10:00:00+09:00"
  }
]
```

---

## POST `/api/shipping/intl-estimate/`

무게(또는 카테고리별 수량)를 입력하면, Admin에서 설정한 **배송 방식 규칙**에 따라 운송 방식을 자동 결정하고, 해당 mode의 모든 활성 배송사 견적을 반환한다.

### Request Body

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `weight_kg` | float | 둘 중 하나 | 과금 무게 (kg) 직접 입력 |
| `items` | object[] | 둘 중 하나 | 카테고리별 수량 배열 |
| `mode` | string | 선택 | `AIR` / `SEA` / `EMS` — 지정 시 Admin 규칙 무시 |

`items` 항목 구조: `{"category": "의류", "quantity": 2}`

### Response Body (200 OK)

| 필드 | 타입 | 설명 |
|------|------|------|
| `total_weight_kg` | float | 적용된 무게 |
| `weight_source` | string | `direct` (직접 입력) / `estimated` (카테고리 추정) |
| `mode_applied` | string | 실제 적용된 운송 방식 (`AIR` / `SEA` / `EMS`) |
| `carriers` | object[] | 배송사별 견적 목록 |

`carriers` 항목:

| 필드 | 타입 | 설명 |
|------|------|------|
| `profile_id` | int | 배송사 프로필 ID |
| `name` | string | 배송사명 |
| `engine` | string | 계산 엔진 (`FB` / `KSE_AIR` / `TABLE` 등) |
| `mode` | string | 운송 방식 |
| `is_default` | boolean | 기본 배송사 여부 |
| `is_available` | boolean | 배송 가능 여부 |
| `freight_krw` | int\|null | KRW 운임 (`null` = JPY 기준 또는 미계산) |
| `quote` | object\|null | 상세 견적 (엔진별 상이) |

### Request 예시

```json
{ "weight_kg": 1.5 }
```

```json
{
  "items": [{"category": "의류", "quantity": 2}, {"category": "신발", "quantity": 1}],
  "mode": "AIR"
}
```

### 운송 방식 자동 결정 규칙 (ShippingModeConfig)

Admin > 배송 방식 규칙에서 `is_current=True` 인 레코드가 기준:

| mode_selection | 동작 |
|----------------|------|
| `AUTO` | `weight_kg ≤ air_max_weight_kg` → AIR, 초과 → SEA (기본 3.0 kg) |
| `AIR_ONLY` | 항상 AIR |
| `SEA_ONLY` | 항상 SEA |

API에서 `mode`를 직접 전달하면 Admin 규칙 무시.

---

## DB 모델 구조

### ShippingQuoteLog

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | AutoField | PK |
| `service_provider` | CharField(10) | 서비스 제공사 |
| `transport_mode` | CharField(20) | 운송 수단 |
| `actual_weight_kg` | FloatField | 실제 무게 |
| `result` | JSONField | 계산 결과 전체 |
| `is_available` | BooleanField | 배송 가능 여부 |
| `created_at` | DateTimeField | 생성 시각 |

---

## 요율표 요약

### KSE 운임 (JPY)

| 구간 | SEA Standard | AIR Standard | SDEX Standard |
|------|-------------|--------------|---------------|
| 0.10 kg | 440 | 475 | 515 |
| 0.50 kg | 570 | 610 | 645 |
| 1.00 kg | 690 | 720 | 715 |
| 2.00 kg | 890 | 920 | 865 |
| 5.00 kg | 1,260 | 1,554 | 1,215 |
| 10.00 kg | 2,040 | 2,616 | 2,616 |
| 17.50 kg | 3,170 | 4,163 | 4,163 |

### KSE Light (YU-PACKET) 운임 (JPY)

동일 요율 (SEA/AIR/SDEX 공통):

| 구간 | 운임 |
|------|------|
| 0.10 kg | 350 |
| 0.30~0.25 kg | 400 |
| 0.55 kg | 460 |
| 0.75 kg | 490 |
| 1.00 kg | 530 |

### CJL 운임 (KRW)

| 구간 | 운임 |
|------|------|
| 0.5 kg | 8,500 |
| 1.0 kg | 9,100 |
| 2.0 kg | 10,100 |
| 5.0 kg | 14,300 |
| 10.0 kg | 20,500 |
| 20.0 kg | 34,900 |

---

## Admin 설정 모델

### ShippingCarrierProfile — 배송사 프로필

| 필드 | 타입 | 설명 |
|------|------|------|
| `name` | CharField(60) | 배송사명 (자유 입력) |
| `engine` | CharField(15) | 계산 엔진 (아래 허용값 참조) |
| `mode` | CharField(10) | 운송 방식 (`AIR` / `SEA` / `EMS`) |
| `rate_table` | FK(ShippingRateTable) | TABLE 엔진 시 연결할 요율표 |
| `currency` | CharField(5) | TABLE 엔진 통화 (`KRW` / `JPY`) |
| `fb_tier` | CharField(10) | FB 등급 (`STANDARD` / `VIP` / `SVIP` / `SSVIP`) |
| `fb_tax_mode` | CharField(5) | FB 세금 납부 (`DDU` / `DDP`) |
| `is_default` | BooleanField | 같은 mode 내 기본 배송사 |
| `is_active` | BooleanField | 활성화 |
| `sort_order` | IntegerField | 정렬 순서 |

**engine 허용값**

| 값 | 설명 |
|----|------|
| `FB` | FastBox (DHUB) 항공특송 |
| `KSE_AIR` | KSE 항공 |
| `KSE_SEA` | KSE 해운 |
| `KSE_SDEX` | KSE SDEX |
| `CJL` | CJL Door to Door |
| `EMS` | 한국우편 EMS |
| `TABLE` | 커스텀 요율표 직접 조회 (신규 배송사) |

### ShippingModeConfig — 배송 방식 규칙

| 필드 | 타입 | 설명 |
|------|------|------|
| `mode_selection` | CharField | `AUTO` / `AIR_ONLY` / `SEA_ONLY` |
| `air_max_weight_kg` | FloatField | AUTO일 때 항공 최대 무게 (기본 3.0 kg) |
| `is_current` | BooleanField | 현재 적용 규칙 |

### FuelSurcharge — 월별 유류할증료

| 필드 | 타입 | 설명 |
|------|------|------|
| `carrier_name` | CharField(60) | 배송사명 (ShippingCarrierProfile.name 과 일치) |
| `year_month` | CharField(7) | 적용 월 (`YYYY-MM`) |
| `amount` | IntegerField | 유류할증료 금액 |
| `currency` | CharField(5) | `KRW` / `JPY` |
| unique_together | — | `(carrier_name, year_month)` |

FSC는 자동 견적 시 현재 월 기준으로 조회되어 FB 운임에 포함된다.
