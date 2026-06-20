# Malls API

한국 쇼핑몰 목록 관리 및 메인 페이지 상품 노출 API.

## 엔드포인트 목록

| Method | URL | 설명 |
|--------|-----|------|
| GET | `/api/malls/` | 활성 쇼핑몰 목록 |
| POST | `/api/malls/` | 쇼핑몰 등록 (admin) |
| GET | `/api/malls/<slug>/` | 쇼핑몰 상세 + 카테고리 목록 |
| PATCH | `/api/malls/<slug>/` | 쇼핑몰 수정 (admin) |
| GET | `/api/malls/<slug>/products/` | 쇼핑몰 상품 목록 (카테고리 필터 가능) |
| GET | `/api/malls/<slug>/recommended/` | 추천 상품 목록 |
| GET | `/api/malls/<slug>/jobs/` | 크롤 작업 목록 (admin) |
| POST | `/api/malls/<slug>/jobs/` | 크롤 작업 생성 (admin) |
| POST | `/api/malls/<slug>/jobs/<id>/crawl/` | 크롤 실행 (admin) |
| GET | `/api/malls/featured-categories/` | 메인 페이지 노출 카테고리 목록 |
| POST | `/api/malls/featured-categories/` | 카테고리 추가 (admin) |
| PATCH | `/api/malls/featured-categories/<id>/` | 카테고리 수정 (admin) |
| DELETE | `/api/malls/featured-categories/<id>/` | 카테고리 삭제 (admin) |

---

## 상세

### GET `/api/malls/`
활성화된 쇼핑몰 목록 반환.

**Response**
```json
[
  {
    "id": 1,
    "slug": "oliveyoung",
    "name": "올리브영",
    "domain": "oliveyoung.co.kr",
    "logo_url": "https://...",
    "is_active": true,
    "display_order": 0
  }
]
```

### GET `/api/malls/<slug>/`
쇼핑몰 상세 + 해당 몰에 등록된 카테고리별 상품 수.

**Response**
```json
{
  "id": 1,
  "slug": "oliveyoung",
  "name": "올리브영",
  "domain": "oliveyoung.co.kr",
  "logo_url": "...",
  "categories": [
    {"category_name": "스킨케어", "products_count": 45},
    {"category_name": "선케어", "products_count": 32}
  ]
}
```

### GET `/api/malls/<slug>/products/`
해당 몰의 상품 목록. 카테고리 필터 지원. 페이지네이션 적용 (20개).

**Query Params**
| 파라미터 | 타입 | 설명 |
|---------|------|------|
| `category` | string | 카테고리 이름으로 필터 |

**Response**: `ProductSerializer` 배열 (paginated)

### GET `/api/malls/<slug>/recommended/`
`is_recommended=True`인 상품 목록.

### POST `/api/malls/<slug>/jobs/`
카테고리 크롤 작업 생성.

**Request Body**
```json
{
  "category_url": "https://www.oliveyoung.co.kr/store/main/getBestList.do",
  "category_name": "베스트"
}
```

### POST `/api/malls/<slug>/jobs/<id>/crawl/`
scraper-agent를 통해 `category_url`을 크롤하고 상품을 DB에 저장.

- `SiteTemplate`에 해당 도메인 템플릿이 있으면 Claude 없이 빠르게 실행
- 성공 시 Job `status=completed`, `products_count` 업데이트

---

## DB 모델

### KoreanMall

| 필드 | 타입 | 설명 |
|------|------|------|
| `slug` | SlugField unique | URL 식별자 (예: oliveyoung) |
| `name` | CharField | 한글 이름 |
| `domain` | CharField | 도메인 (예: oliveyoung.co.kr) |
| `logo_url` | URLField | 로고 이미지 URL |
| `is_active` | BooleanField | 메인 페이지 노출 여부 |
| `display_order` | IntegerField | 정렬 순서 |

### MallCrawlJob

| 필드 | 타입 | 설명 |
|------|------|------|
| `mall` | FK(KoreanMall) | 쇼핑몰 |
| `category_url` | URLField | 크롤할 목록 URL |
| `category_name` | CharField | 카테고리 표시명 |
| `status` | choices | pending / processing / completed / failed |
| `products_count` | IntegerField | 저장된 상품 수 |
| `error_message` | TextField | 실패 사유 |
| `last_crawled_at` | DateTimeField | 마지막 크롤 시각 |

### FeaturedCategory

| 필드 | 타입 | 설명 |
|------|------|------|
| `mall` | FK(KoreanMall) | 쇼핑몰 |
| `category_name` | CharField | `Product.category`와 일치해야 함 |
| `display_title` | CharField | 화면 표시명 (비워두면 category_name 사용) |
| `display_order` | IntegerField | 정렬 순서 |
| `is_active` | BooleanField | 메인 페이지 노출 여부 |

### Product (추가 필드)

| 필드 | 타입 | 설명 |
|------|------|------|
| `mall` | FK(KoreanMall) null | 소속 쇼핑몰 |
| `is_recommended` | BooleanField | 추천 상품 여부 |

---

## 어드민 사용 흐름

1. **Admin** → `KoreanMall` 생성 (slug: oliveyoung, domain: oliveyoung.co.kr)
2. **Admin** → `SiteTemplate` 생성 (domain: oliveyoung.co.kr, page_type: list) — 크롤 템플릿
3. **Admin** → `POST /api/malls/oliveyoung/jobs/` 로 카테고리 URL 등록
4. **Admin** → `POST /api/malls/oliveyoung/jobs/<id>/crawl/` 크롤 실행
5. **사용자** → 메인 페이지에서 올리브영 클릭 → `GET /api/malls/oliveyoung/` 로 카테고리 목록
6. **사용자** → 카테고리 선택 → `GET /api/malls/oliveyoung/products/?category=베스트`
