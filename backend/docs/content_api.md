# Content API

FAQ·공지사항·이벤트 배너·정책 콘텐츠.

Base URL: `/api/content/`

---

## 엔드포인트 목록

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/content/faq/` | FAQ 목록 |
| GET | `/api/content/notices/` | 공지사항 목록 |
| GET | `/api/content/notices/{id}/` | 공지사항 상세 |
| GET | `/api/content/banners/` | 활성 이벤트 배너 목록 |
| GET | `/api/content/policies/{policy_type}/` | 현행 정책 조회 |

---

## FAQ

### GET `/api/content/faq/?category=배송`

Query: `?category=` — 카테고리 필터 (선택)

---

## 공지사항

핀 고정(`is_pinned=true`) 항목이 상단 우선 표시.

---

## 이벤트 배너

현재 시각 기준 `ends_at`이 지나지 않은 배너만 반환.

---

## 정책

### GET `/api/content/policies/{policy_type}/`

**`policy_type` 허용값:** `privacy` / `terms` / `shipping` / `refund` / `guide`

현재 적용 중인(`is_current=true`) 버전 반환.

---

## DB 모델 구조

### FAQ
`category`, `question`, `answer`, `sort_order`, `is_active`

### Notice
`title`, `content`, `is_pinned`, `is_active`, `published_at`

### EventBanner
`title`, `image_url`, `link_url`, `sort_order`, `is_active`, `starts_at`, `ends_at`

### Policy
`policy_type`, `title`, `content`, `version`, `effective_date`, `is_current`

---

## 어드민 CRUD (Section 18)

모든 LIST 엔드포인트: `?all=true` 쿼리 파라미터로 비활성 항목 포함 조회 가능.

### POST `/api/content/faq/`
### PATCH `/api/content/faq/{id}/` — 부분 수정
### DELETE `/api/content/faq/{id}/` — 소프트 삭제 (`is_active=false`)

### POST `/api/content/notices/`
### PATCH `/api/content/notices/{id}/`
### DELETE `/api/content/notices/{id}/` — 소프트 삭제

### POST `/api/content/banners/`

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `title` | string | ✅ | 배너 제목 |
| `image_url` | string | ✅ | 배너 이미지 URL |
| `link_url` | string | ❌ | 클릭 링크 URL |
| `sort_order` | integer | ❌ | 노출 순서 |
| `starts_at` | datetime | ❌ | 노출 시작 |
| `ends_at` | datetime | ❌ | 노출 종료 |

### PATCH `/api/content/banners/{id}/`
### DELETE `/api/content/banners/{id}/` — 소프트 삭제

### GET `/api/content/policies/` — 현행 정책 전체 목록
### POST `/api/content/policies/` — 새 정책 버전 생성
### PATCH `/api/content/policies/{policy_type}/` — 현행 버전 수정
