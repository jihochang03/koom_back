# Operations API

운영 기준 관리 (오차 처리 기준).

Base URL: `/api/operations/`

---

## 엔드포인트 목록

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/operations/error-criteria/` | 현재 오차 기준 조회 |
| POST | `/api/operations/error-criteria/` | 새 오차 기준 버전 생성 |
| PATCH | `/api/operations/error-criteria/` | 현재 기준 수정 + 변경 이력 기록 |
| GET | `/api/operations/error-criteria/history/` | 기준 변경 이력 전체 |
| GET | `/api/operations/error-criteria/{id}/log/` | 특정 버전 변경 로그 |

---

## ErrorCriteria 필드

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `small_error_threshold_pct` | float | 2.0 | 소오차 % 기준 |
| `small_error_threshold_abs` | float | 500 | 소오차 절대금액 기준 (원) |
| `small_error_per_item` | boolean | true | 상품별(true) / 묶음별(false) |
| `large_error_threshold_pct` | float | 5.0 | 대오차 % 기준 (CS 전환) |
| `handling_ai_error` | string | `company_burden` | AI/크롤링 오류 처리 방식 |
| `handling_price_change` | string | `cs_review` | 상품가 변동 처리 방식 |
| `handling_shipping_extra` | string | `company_burden` | 배송비 추가 처리 방식 |
| `handling_tax` | string | `cs_review` | 세금/관세 추가 처리 방식 |
| `handling_prima_risk` | string | `cs_review` | 프리마 리스크 처리 방식 |
| `handling_exchange_rate` | string | `company_burden` | 환율 차이 처리 방식 |
| `note` | string | | 변경 메모 |
| `created_by` | string | | 생성자 |

**handling_* 허용값:** `company_burden` / `cs_review` / `additional_charge` / `cancel` / `partial_refund`

---

## PATCH `/api/operations/error-criteria/`

변경할 필드만 포함. `changed_by` 필드로 변경자 기록.

```json
{
  "small_error_threshold_pct": 3.0,
  "handling_prima_risk": "additional_charge",
  "changed_by": "admin@boltlab.co.kr"
}
```

변경 이력은 `ErrorCriteriaLog`에 자동 기록.

---

## DB 모델 구조

### ErrorCriteria
소오차 기준(pct/abs/per_item), 대오차 기준(pct), 원인별 처리 방식 6종, is_current, note, created_by

### ErrorCriteriaLog
FK(ErrorCriteria), changed_field, old_value(JSON), new_value(JSON), changed_by, changed_at
