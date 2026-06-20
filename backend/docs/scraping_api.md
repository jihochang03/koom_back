# Scraping API

URL 분석을 scraper-agent에 위임하고 결과를 DB에 저장·조회하는 앱.

Base URL: `/api/scraping/`

---

## 엔드포인트 목록

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/scraping/analyze/` | URL 분석 요청 |
| GET | `/api/scraping/requests/` | 스크래핑 요청 목록 조회 |
| GET | `/api/scraping/requests/{id}/` | 스크래핑 요청 단건 조회 |
| GET | `/api/scraping/visits/recent/` | 사용자 최근 방문 URL |
| GET | `/api/scraping/visits/popular/` | 인기 URL (전체 기준) |

---

## POST `/api/scraping/analyze/`

scraper-agent에 URL 분석을 요청하고, 완료되면 결과를 DB에 저장 후 반환한다.

### Request Body

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|------|------|------|--------|------|
| `url` | string (URL) | ✅ | — | 분석할 페이지 URL |
| `category` | string | ❌ | `shopping` | 사이트 카테고리 |
| `page_type` | string | ❌ | `auto` | 페이지 유형 힌트 |
| `max_items` | integer | ❌ | `null` | list 타입에서 수집할 최대 아이템 수 (최소 1) |
| `collect_detail` | boolean | ❌ | `true` | list 타입에서 각 아이템 상세 정보까지 수집 여부 |
| `customer_id` | string | ❌ | `""` | 방문 기록 저장용 고객 ID (있을 때만 UrlVisit 생성) |

**`category` 허용값**

| 값 | 설명 |
|----|------|
| `shopping` | 쇼핑몰 상품 (기본값) |
| `news` | 뉴스/블로그 기사 |
| `real_estate` | 부동산 매물 |
| `jobs` | 채용 공고 |
| `general` | 기타 범용 |

**`page_type` 허용값**

| 값 | 설명 |
|----|------|
| `auto` | scraper-agent가 자동 판단 (기본값) |
| `list` | 목록 페이지 — 페이지 내 모든 항목 수집 |
| `detail` | 상세 페이지 — 단일 항목 수집 |

### Request 예시

```json
{
  "url": "https://www.coupang.com/vp/products/123456",
  "category": "shopping",
  "page_type": "detail"
}
```

```json
{
  "url": "https://www.zigbang.com/home/apt/items",
  "category": "real_estate",
  "page_type": "list",
  "max_items": 20
}
```

### Response Body (201 Created)

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | integer | 요청 ID |
| `url` | string | 요청한 URL |
| `domain` | string | URL에서 추출한 도메인 |
| `category` | string | 카테고리 |
| `page_type` | string | 페이지 유형 |
| `status` | string | 처리 상태 |
| `error_message` | string | 실패 시 에러 메시지 |
| `result` | object\|null | 수집 결과 (아래 참조) |
| `created_at` | string (ISO 8601) | 요청 생성 시각 |
| `updated_at` | string (ISO 8601) | 마지막 업데이트 시각 |

**`status` 허용값**

| 값 | 설명 |
|----|------|
| `pending` | 대기 중 |
| `processing` | 처리 중 |
| `completed` | 완료 |
| `failed` | 실패 |

**`result` 객체**

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | integer | 결과 ID |
| `raw_data` | object | scraper-agent가 반환한 원시 데이터 (카테고리별 형태 상이) |
| `template_used` | string | 사용된 템플릿 파일명 (없으면 빈 문자열) |
| `items_count` | integer | 수집된 아이템 수 (list 타입: 전체 수, detail: 1) |
| `created_at` | string (ISO 8601) | 결과 생성 시각 |

### Response 예시

```json
{
  "id": 42,
  "url": "https://www.coupang.com/vp/products/123456",
  "domain": "coupang.com",
  "category": "shopping",
  "page_type": "detail",
  "status": "completed",
  "error_message": "",
  "result": {
    "id": 38,
    "raw_data": {
      "title": "무선 블루투스 이어폰",
      "price": { "original": 29000, "discounted": 19900, "currency": "KRW" },
      "options": [{ "name": "색상", "values": ["블랙", "화이트"] }],
      "availability": "in_stock"
    },
    "template_used": "coupang.com_detail.py",
    "items_count": 1,
    "created_at": "2026-06-01T10:30:00+09:00"
  },
  "created_at": "2026-06-01T10:29:55+09:00",
  "updated_at": "2026-06-01T10:30:02+09:00"
}
```

### 에러 응답

| 상태 코드 | 조건 | 예시 |
|-----------|------|------|
| `400 Bad Request` | 유효하지 않은 요청 파라미터 | `{"url": ["이 필드는 필수 항목입니다."]}` |
| `502 Bad Gateway` | scraper-agent 서버 연결 실패 또는 오류 | `{"error": "scraper-agent 서버에 연결할 수 없습니다."}` |

---

## GET `/api/scraping/requests/`

저장된 스크래핑 요청 목록을 페이지네이션으로 조회한다.

### Query Parameters

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `domain` | string | 도메인으로 필터링 (예: `coupang.com`) |
| `category` | string | 카테고리로 필터링 |
| `page` | integer | 페이지 번호 (기본 1) |

### Request 예시

```
GET /api/scraping/requests/?domain=coupang.com&category=shopping
GET /api/scraping/requests/?page=2
```

### Response Body (200 OK)

```json
{
  "count": 150,
  "next": "http://localhost:8000/api/scraping/requests/?page=2",
  "previous": null,
  "results": [
    {
      "id": 42,
      "url": "https://www.coupang.com/vp/products/123456",
      "domain": "coupang.com",
      "category": "shopping",
      "page_type": "detail",
      "status": "completed",
      "error_message": "",
      "result": { ... },
      "created_at": "2026-06-01T10:29:55+09:00",
      "updated_at": "2026-06-01T10:30:02+09:00"
    }
  ]
}
```

---

## GET `/api/scraping/requests/{id}/`

특정 스크래핑 요청과 결과를 단건 조회한다.

### Path Parameters

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `id` | integer | 스크래핑 요청 ID |

### Response Body (200 OK)

`POST /api/scraping/analyze/` 응답과 동일한 구조.

### 에러 응답

| 상태 코드 | 조건 |
|-----------|------|
| `404 Not Found` | 해당 ID의 요청이 없음 |

---

---

## GET `/api/scraping/visits/recent/`

특정 사용자의 최근 방문 URL 목록. 최신순 정렬.

### Query Parameters

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `customer_id` | string | ✅ | 고객 ID |
| `limit` | integer | ❌ | 최대 반환 수 (기본 10, 최대 50) |

### Response

```json
[
  {"id": 1, "url": "https://oliveyoung.co.kr/...", "title": "", "visited_at": "2026-06-09T10:00:00+09:00"},
  {"id": 2, "url": "https://coupang.com/...", "title": "", "visited_at": "2026-06-09T09:50:00+09:00"}
]
```

---

## GET `/api/scraping/visits/popular/`

전체 사용자 기준 방문 횟수 많은 URL 순.

### Query Parameters

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `limit` | integer | 최대 반환 수 (기본 10, 최대 50) |

### Response

```json
[
  {"url": "https://oliveyoung.co.kr/...", "visit_count": 142},
  {"url": "https://coupang.com/...", "visit_count": 87}
]
```

---

## DB 모델 구조

### UrlVisit

| 필드 | 타입 | 설명 |
|------|------|------|
| `customer_id` | CharField(255) | 고객 ID (인덱스) |
| `url` | URLField(2048) | 방문한 URL |
| `title` | CharField(1024) | 페이지 제목 (선택) |
| `visited_at` | DateTimeField | 방문 시각 (복합 인덱스: customer_id + visited_at) |

### ScrapeRequest

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | AutoField | PK |
| `url` | URLField(2048) | 요청 URL |
| `domain` | CharField(255) | 추출된 도메인 (인덱스) |
| `category` | CharField(20) | 카테고리 (인덱스) |
| `page_type` | CharField(10) | 페이지 유형 |
| `status` | CharField(20) | 처리 상태 |
| `error_message` | TextField | 오류 메시지 |
| `created_at` | DateTimeField | 생성 시각 |
| `updated_at` | DateTimeField | 수정 시각 |

### ScrapeResult

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | AutoField | PK |
| `scrape_request` | OneToOneField | ScrapeRequest FK |
| `raw_data` | JSONField | 수집 원시 데이터 |
| `template_used` | CharField(255) | 사용된 템플릿명 |
| `items_count` | IntegerField | 수집 아이템 수 |
| `created_at` | DateTimeField | 생성 시각 |
