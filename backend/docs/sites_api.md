# Sites API

지원 사이트 목록과 URL 분류 기능.

Base URL: `/api/sites/`

---

## 엔드포인트 목록

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/sites/` | 지원 사이트 목록 |
| POST | `/api/sites/classify/` | URL 유형 분류 |

---

## GET `/api/sites/`

활성화된 지원 사이트 목록 반환.

### Response Body (200 OK)

배열. 각 항목:

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | integer | PK |
| `name` | string | 사이트명 |
| `domain` | string | 도메인 |
| `icon_url` | string | 파비콘 URL |
| `sort_order` | integer | 정렬 순서 |
| `product_url_patterns` | string[] | 상품 URL 판별 path 패턴 |
| `search_url_patterns` | string[] | 검색 URL 판별 path 패턴 |

---

## POST `/api/sites/classify/`

URL을 입력받아 사이트와 URL 유형을 반환한다.

### Request Body

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `url` | string | ✅ | 분류할 URL |

### Response Body (200 OK)

| 필드 | 타입 | 설명 |
|------|------|------|
| `url_type` | string | `product` / `search` / `unknown` |
| `domain` | string | 추출된 도메인 |
| `site` | object\|null | 매칭된 SupportedSite (없으면 null) |

### url_type 허용값

| 값 | 설명 |
|----|------|
| `product` | 상품 상세 URL → 상품 상세 페이지로 이동 |
| `search` | 검색/목록 URL → 사이트 검색 결과 이동 |
| `unknown` | 분류 불가 → URL 확인 요청 안내 |

---

## DB 모델 구조

### SupportedSite

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | BigAutoField | PK |
| `name` | CharField(100) | 사이트명 |
| `domain` | CharField(255) | 도메인 (unique) |
| `icon_url` | URLField | 파비콘 URL |
| `is_active` | BooleanField | 활성화 여부 (인덱스) |
| `sort_order` | PositiveIntegerField | 정렬 순서 (인덱스) |
| `product_url_patterns` | JSONField | 상품 URL path 패턴 목록 |
| `search_url_patterns` | JSONField | 검색 URL path 패턴 목록 |
| `created_at` | DateTimeField | 생성 시각 |
| `updated_at` | DateTimeField | 수정 시각 |

### 사전 등록 사이트

| 사이트 | 도메인 |
|--------|--------|
| 쿠팡 | coupang.com |
| 올리브영 | oliveyoung.co.kr |
| 무신사 | musinsa.com |
| 네이버 스마트스토어 | smartstore.naver.com |
| G마켓 | gmarket.co.kr |
| 11번가 | 11st.co.kr |
| 마켓컬리 | kurly.com |
| 위메프 | wemakeprice.com |
