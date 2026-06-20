# Stats API

서비스 통계 집계 (Section 15).

Base URL: `/api/stats/`

---

## 엔드포인트 목록

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/stats/dk-burden/` | DK 부담 손실액 통계 |
| GET | `/api/stats/error-rate/` | 견적 오차율 및 오차 금액 통계 |
| GET | `/api/stats/cs-conversion/` | CS 수동 검토 전환율 통계 |
| GET | `/api/stats/site-parsing/` | 사이트별 파싱·오차·취소 통계 |
| GET | `/api/stats/monitoring/overview/` | 실시간 운영 모니터링 (scope=all/mine) |

---

## GET `/api/stats/dk-burden/`

```json
{
  "total_burden": 1250000,
  "tariff_advance": 800000,
  "error_small_burden": 150000,
  "shipping_error_burden": 200000,
  "other_burden": 100000,
  "avg_burden_per_order": 5000,
  "burden_rate_pct": 2.3,
  "order_count": 250
}
```

---

## GET `/api/stats/error-rate/`

```json
{
  "avg_error_rate_pct": 3.2,
  "total_error_amount": 4500000,
  "error_order_count": 87,
  "by_handling_method": {
    "company_burden": 45,
    "cs_review": 30,
    "additional_charge": 12
  },
  "by_cause": {
    "price_change": 20,
    "ai_parsing_error": 15,
    "domestic_shipping_extra": 30
  }
}
```

---

## GET `/api/stats/cs-conversion/`

```json
{
  "total_orders": 500,
  "cs_touched_orders": 87,
  "cs_conversion_rate_pct": 17.4,
  "cs_review_from_error": 30,
  "open_inquiries": 12,
  "resolved_inquiries": 75
}
```

---

## GET `/api/stats/site-parsing/`

Section 17.2 — 사이트/판매처별 파싱·오차·취소 통계.

```json
[
  {
    "site_domain": "coupang.com",
    "total_orders": 200,
    "cancel_refund_rate_pct": 3.5,
    "shipping_extra_rate_pct": 12.0,
    "avg_error_rate_pct": 2.1,
    "error_order_count": 15
  }
]
```

---

## GET `/api/stats/monitoring/overview/`

실시간 운영 모니터링 (FR-MON-01). 화면 H-11(본사 전체) / C-05(CS 담당 건).

| 쿼리 | 설명 |
|------|------|
| `scope` | `all`(기본, 본사 전체) / `mine`(CS 담당 건) |
| `cs_user` | `scope=mine` 일 때 **필수** — 해당 CS가 대리구매한 주문만 집계 (NFR-SEC-02 격리) |

`scope=mine` 인데 `cs_user` 가 없으면 `400`.

```json
{
  "scope": "all",
  "cs_user": null,
  "order_status_counts": { "paid": 12, "purchasing": 5, "shipping_intl": 3, "delivered": 40 },
  "purchase_tasks_pending": 12,
  "shipping": { "tracked_total": 30, "delay_24h": 2, "delay_48h": 1, "delay_extended": 0, "delay_total": 3 },
  "inspection_issues": 1,
  "price_error": { "total": 8, "cs_review": 3, "auto_company": 5 }
}
```

- `purchase_tasks_pending`: 결제완료(`paid`)이고 아직 대리구매 기록(`PurchaseRecord`)이 없는 주문 수
- `shipping`: `ShippingTracking.delay_type` 기준 정체 집계 (FR-LOG-03·04)
- `inspection_issues`: `LogisticsInfo.inspection_result='issue'` (FR-LOG-05)
- `price_error`: `ErrorInfo` 기준 CS 전환·자동 회사부담 집계 (FR-ORD-04)
