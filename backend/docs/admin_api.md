# Admin API

어드민 운영 대시보드 및 주문 관리.

Base URL: `/api/orders/`

---

## 엔드포인트 목록

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/orders/admin/dashboard/` | 운영 대시보드 집계 |
| GET | `/api/orders/admin/list/` | 어드민 주문 목록 (탭+필터) |

---

## GET `/api/orders/admin/dashboard/`

### Response Body (200 OK)

```json
{
  "manual_review": {
    "inspection_issues": 3,
    "refunds_pending": 2
  },
  "delays": {
    "shipping_stalled": 5
  },
  "cs_open": 12,
  "order_status_counts": {
    "pending": 10,
    "paid": 5,
    "purchasing": 3,
    "shipping_domestic": 8,
    "inspection": 2,
    "shipping_intl": 7,
    "delivered": 120
  }
}
```

| 필드 | 설명 |
|------|------|
| `manual_review.inspection_issues` | 검수 이슈 메모가 있는 주문 수 |
| `manual_review.refunds_pending` | 부분 환불 처리 중인 주문 수 |
| `delays.shipping_stalled` | 3일 이상 배송 상태 미변경 주문 수 |
| `cs_open` | CS 앱 미해결 건 합계 (문의+취소+환불 요청) |
| `order_status_counts` | 상태별 주문 수 |

---

## GET `/api/orders/admin/list/`

### Query Parameters

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `tab` | string | `all` / `in_progress` / `completed` / `refund` / `error` |
| `date_from` | string | 시작일 (YYYY-MM-DD) |
| `date_to` | string | 종료일 (YYYY-MM-DD) |
| `status` | string | 주문 상태 필터 |
| `has_refund` | boolean | 환불 건만 (`true`) |
| `has_error` | boolean | 검수 이슈 건만 (`true`) |

### tab 설명

| 값 | 포함 상태 |
|----|----------|
| `all` | 전체 |
| `in_progress` | paid / purchasing / shipping_domestic / inspection / shipping_intl |
| `completed` | delivered |
| `refund` | refunded / partial_refund |
| `error` | inspection_notes가 있는 건 |
