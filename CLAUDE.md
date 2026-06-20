# CLAUDE.md — 프로젝트 규칙

## 필수 후속 작업

### 1. Django 모델/API 수정 시

Django 앱(`backend/apps/`)에서 다음 중 하나라도 변경했으면 **반드시** 아래 두 가지를 수행한다.

#### a) Migration 실행

```powershell
# backend/ 디렉토리에서
python manage.py makemigrations
python manage.py migrate
```

- 모델 필드 추가/삭제/변경이 있으면 `makemigrations` 먼저 실행
- 이미 수동으로 migration 파일을 작성한 경우 `migrate`만 실행
- migration 파일은 커밋에 포함

#### b) API 문서 업데이트

`backend/docs/` 아래 해당 앱의 `*_api.md` 파일을 수정한다.

| 앱 | 문서 파일 |
|----|-----------|
| `apps.scraping` | `backend/docs/scraping_api.md` |
| `apps.products` | `backend/docs/products_api.md` |
| `apps.cart` | `backend/docs/cart_api.md` |
| `apps.pricing` | `backend/docs/pricing_api.md` |
| `apps.shipping` | `backend/docs/shipping_api.md` |
| `apps.tariff` | `backend/docs/tariff_api.md` |
| `apps.scrape_template` | `backend/docs/scrape_template_api.md` |

문서에 반영해야 할 항목:
- 엔드포인트 목록 테이블
- Request / Response Body 필드
- 허용값 목록 (choices 등)
- DB 모델 구조 테이블

---

## 배포 아키텍처

```
고객사 서버                          우리 서버 (Boltlab)
┌─────────────────────┐             ┌─────────────────────────┐
│  Django 백엔드       │             │  scraper-agent (Node.js) │
│  - 템플릿 코드 DB    │  크롤 요청  │  - Stateless 크롤 API    │
│  - 상품 DB           │ ──────────▶ │  - Claude AI 분석        │
│  - 각종 설정         │ ◀────────── │  - Python 템플릿 실행    │
└─────────────────────┘  결과 반환  └─────────────────────────┘
```

- **scraper-agent**는 상태를 저장하지 않는 라이브러리처럼 동작
- **Django 백엔드**가 고객사별 템플릿 코드를 자체 DB(`SiteTemplate`)에 보관
- 크롤 시 Django가 DB의 템플릿 코드를 scraper-agent 요청에 포함 → Claude 없이 빠른 실행
- 새 템플릿 빌드 시 scraper-agent의 `save_template` 툴 호출을 캡처 → Django DB 저장
- scraper-agent 로컬 파일시스템 템플릿은 개발·직접 사용 시 폴백용으로만 유지

## 프로젝트 구조 요약

```
koom/
├── backend/              # Django REST API (포트 8000)
│   ├── apps/
│   │   ├── scraping/     # URL 분석 요청 관리
│   │   ├── products/     # 상품 목록·카테고리·뱃지(prima/한정)·상세 크롤 상태
│   │   ├── cart/         # 고객별 장바구니
│   │   ├── pricing/      # 환율·DK 견적
│   │   ├── shipping/     # 배송비 계산
│   │   ├── tariff/       # 관세 조회
│   │   └── common/       # 전역 설정
│   └── docs/             # API 문서 (Markdown)
│
└── scraper-agent/        # Node.js+TypeScript (포트 3000)
    ├── src/
    │   ├── api-server.ts           # Express 서버
    │   ├── products/
    │   │   └── prefetch-queue.ts  # 백그라운드 상세 크롤 큐
    │   └── modules/shopping/      # 크롤러 모듈
    ├── collector/                  # Python Flask (포트 18080)
    └── web/                        # React + Vite 프론트엔드
```

## 작업 방식

- 확인 없이 쭉 진행한다. 중간에 "계속할까요?", "진행할까요?" 같은 yes/no 질문을 하지 않는다.
- migration, 파일 생성/수정, django check 등 모든 후속 작업을 알아서 완료한다.
- 작업 완료 후 결과만 간결하게 보고한다.

---

## 화면 기반 백엔드 개발 방식

사용자가 화면(UI/UX)을 설명하면, 그에 맞는 Django 백엔드(모델, API, migration, 문서)를 만든다.

### 작업 순서

1. **화면 분석** — 화면 설명에서 필요한 데이터 구조와 동작(CRUD, 조회 조건 등)을 파악한다.
2. **모델 설계** — `backend/apps/` 하위 적절한 앱(또는 새 앱)에 Django 모델을 작성한다.
3. **API 설계** — DRF ViewSet / APIView + Serializer로 엔드포인트를 구현한다.
4. **Migration 실행** — `python manage.py makemigrations && python manage.py migrate`
5. **API 문서 업데이트** — 해당 앱의 `backend/docs/*_api.md` 파일에 반영한다.

### 판단 기준

- 화면에 보이는 데이터 항목 → 모델 필드
- 화면에서 발생하는 사용자 동작 → API 엔드포인트
- 목록/필터/정렬 → 쿼리 파라미터 및 ORM 최적화
- 생략된 세부사항은 기존 앱 컨벤션(upsert 키, 포트 등)을 따른다.

---

## 주요 규칙

- Django 백엔드 포트: `8000`
- scraper-agent 포트: `3000`
- Python Flask collector 포트: `18080`
- `DJANGO_BASE_URL` 환경변수로 scraper-agent → Django 주소 변경 가능 (기본 `http://localhost:8000`)
- Products upsert 키: `url` 필드 (같은 URL이면 업데이트)
- 상품 상세 크롤은 `prefetch-queue.ts`가 직렬로 처리 (한 번에 하나씩)
