# Scrape Template API

고객사 Django DB가 Python 스크레이퍼 템플릿의 진실의 원천.  
scraper-agent는 stateless 크롤 라이브러리로만 사용되며, 빌드 완료된 코드는 Django DB에 저장된다.

Base URL: `/api/templates/`

---

## 아키텍처

```
고객사 서버 (Django)                      우리 서버 (scraper-agent)
┌────────────────────────────┐            ┌──────────────────────────┐
│  SiteTemplate DB            │            │  Stateless 크롤 API       │
│  (domain → Python 코드)     │            │                          │
│                             │  크롤 시   │  POST /api/analyze        │
│  ① DB에서 템플릿 코드 조회  │ ──────────▶│  { url, template: code } │
│  ② scraper-agent에 전달     │            │  → 코드 실행 → 결과 반환  │
│  ③ 결과 수신·저장           │ ◀──────────│                          │
│                             │  빌드 시   │  POST /api/template/build │
│  ① scraper-agent 빌드 요청  │ ──────────▶│  SSE: tool_call           │
│  ② save_template 이벤트     │ ◀──────────│  → 코드 생성 스트리밍    │
│     캡처 → DB 저장          │            │                          │
└────────────────────────────┘            └──────────────────────────┘
```

---

## 엔드포인트 목록

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/templates/` | 저장된 템플릿 목록 조회 (DB) |
| POST | `/api/templates/build/` | 새 템플릿 빌드 요청 → DB 저장 |
| GET | `/api/templates/build-logs/` | 템플릿 빌드 이력 조회 |
| GET | `/api/templates/domain/{domain}/` | 도메인별 템플릿 조회 |
| GET | `/api/templates/{domain}/` | 도메인/파일명으로 단건 조회 |
| DELETE | `/api/templates/{domain}/` | 템플릿 삭제 |

---

## GET `/api/templates/`

Django DB에 저장된 전체 템플릿 목록을 반환한다.

### Response Body (200 OK)

```json
{
  "files": [
    {
      "domain": "coupang.com",
      "filename": "coupang_com_both.py",
      "page_type": "both",
      "category": "shopping",
      "updated_at": "2026-06-01T10:30:00+09:00"
    }
  ]
}
```

---

## POST `/api/templates/build/`

scraper-agent에 새 템플릿 빌드를 요청한다.  
SSE 스트림에서 `save_template` 툴 호출을 캡처해 자동으로 Django DB에 저장한다.

### Request Body

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `url` | string (URL) | ✅ | 분석할 페이지 URL |
| `category` | string | ❌ | 카테고리 (기본 `shopping`) |
| `message` | string | ❌ | 추가 지시사항 |

### Response Body (201 Created)

scraper-agent에서 반환된 마지막 SSE data 이벤트 + `merged_from` 목록.  
빌드 성공 시 `SiteTemplate` DB에 코드가 저장된다.

---

## GET `/api/templates/{domain}/`

도메인(또는 파일명)으로 템플릿을 조회한다.

### Path Parameters

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `domain` | string | 도메인명 (e.g. `coupang.com`) 또는 파일명 |

### Response Body (200 OK)

```json
{
  "domain": "coupang.com",
  "filename": "coupang_com_both.py",
  "content": "import requests\n...",
  "page_type": "both"
}
```

### 에러 응답

| 상태 코드 | 조건 |
|-----------|------|
| `404 Not Found` | 해당 도메인 템플릿 없음 |

---

## DELETE `/api/templates/{domain}/`

템플릿을 DB에서 삭제한다.

### Response Body (200 OK)

```json
{"success": true}
```

---

## GET `/api/templates/domain/{domain}/`

도메인에 매칭되는 템플릿 목록(코드 포함)을 반환한다. 빌드 시 기존 템플릿을 병합 컨텍스트로 전달할 때 사용.

### Response Body (200 OK)

```json
[
  {
    "filename": "coupang_com_both.py",
    "content": "import requests\n..."
  }
]
```

---

## DB 모델 구조

### SiteTemplate

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | BigAutoField | PK |
| `domain` | CharField(255) | 도메인 (unique, 인덱스) |
| `filename` | CharField(255) | 파일명 (예: `coupang_com_both.py`) |
| `code` | TextField | Python 스크레이퍼 코드 |
| `page_type` | CharField(20) | `detail` / `list` / `both` |
| `category` | CharField(20) | 카테고리 (인덱스) |
| `created_at` | DateTimeField | 생성 시각 |
| `updated_at` | DateTimeField | 수정 시각 |

### TemplateBuildLog

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | BigAutoField | PK |
| `url` | URLField(2048) | 빌드 요청 URL |
| `domain` | CharField(255) | 도메인 (인덱스) |
| `category` | CharField(20) | 카테고리 |
| `filename` | CharField(255) | 저장된 파일명 |
| `merged_from` | TextField | 병합된 기존 파일명 목록 (콤마 구분) |
| `success` | BooleanField | 성공 여부 |
| `error_message` | TextField | 오류 메시지 |
| `created_at` | DateTimeField | 요청 시각 |

---

## scraping API와의 연동

`POST /api/scraping/analyze/` 호출 시 내부적으로 `SiteTemplate`을 조회한다:
- 해당 도메인 템플릿이 DB에 있으면 → scraper-agent 요청에 `template` 코드를 포함 → Claude 없이 빠른 실행
- 없으면 → scraper-agent가 Claude 분석으로 fallback
