# scraper-agent

AI 기반 쇼핑몰 상품 스크래퍼 에이전트.  
Claude를 활용해 쇼핑몰 상품 페이지를 분석하고 구조화된 데이터를 추출합니다.

---

## 작동 방식

```
URL 입력
  │
  ├─ 1순위: Python 수집 서버 (undetected_chromedriver)
  │          └─ 쿠팡·네이버 등 봇 차단이 강한 사이트에 효과적
  │
  └─ 2순위: Playwright (일반 사이트 fallback)

수집된 HTML + 네트워크 응답
  │
  └─ Claude AI 분석
       ├─ 어떤 API가 상품 데이터를 제공하는지 파악
       ├─ 도메인별 템플릿 생성 → templates/<domain>.json 저장
       └─ 상품 데이터 추출 (가격·옵션·스펙·이미지·평점·판매자)

2회차~: 저장된 템플릿 재사용 → 빠른 API 직접 호출
```

---

## 프로젝트 구조

```
scraper-agent/
├── src/
│   ├── index.ts                 ← CLI 진입점 (chat/scrape/agent/template 모드)
│   ├── api-server.ts            ← Express REST API 서버 (포트 3000)
│   ├── core/
│   │   ├── browser.ts           ← Playwright 브라우저 래퍼
│   │   ├── local-collector.ts   ← Python 서버 자동 시작/통신
│   │   ├── network.ts           ← 네트워크 트래픽 레코더
│   │   ├── stealth.ts           ← 봇 탐지 우회 (Playwright용)
│   │   └── captcha-solver.ts    ← 캡차 자동 해결
│   ├── agent/
│   │   ├── agent.ts             ← 범용 에이전트
│   │   ├── template-agent.ts    ← 사이트 분석 → 템플릿 생성
│   │   └── template-builder-agent.ts
│   └── modules/shopping/
│       ├── agent/market-agent.ts ← 챗봇 REPL (chat 모드)
│       ├── apis/
│       │   ├── analyze-site.ts  ← 사이트 분석 + 템플릿 생성
│       │   ├── fetch-product.ts ← 템플릿 기반 빠른 상품 수집
│       │   ├── list-items.ts    ← 상품 목록 수집
│       │   └── get-item.ts      ← 상품 상세 수집
│       └── ai/claude.ts         ← Claude API (분석·파싱)
│
├── collector/
│   ├── server.py                ← Flask 수집 서버 (포트 18080)
│   └── requirements.txt         ← Python 의존성
│
├── web/                         ← React + Vite 웹 UI
├── templates/                   ← 도메인별 API 템플릿 (자동 생성)
└── .profiles/                   ← 도메인별 Chrome 프로필 (쿠키 유지)
```

---

## 사전 요구사항

- **Node.js** 18+
- **Python** 3.10+
- **Google Chrome** (최신 버전 권장)
- **Anthropic API Key**

---

## 설치

### 1. Node.js 의존성

```bash
npm install
```

### 2. 환경 변수

프로젝트 루트에 `.env` 파일을 생성합니다.

```env
ANTHROPIC_API_KEY=sk-ant-api03-...
```

선택 환경 변수:

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `ANTHROPIC_API_KEY` | 필수 | Claude API 키 |
| `WEB_PORT` | `3000` | API 서버 포트 |
| `COLLECTOR_PORT` | `18080` | Python 수집 서버 포트 |
| `COLLECTOR_MAX_WORKERS` | `1` | 동시 Chrome 슬롯 수 (최대 4) |
| `CHROME_PATH` | 자동 탐지 | Chrome 실행 파일 경로 |

### 3. Python 의존성

```bash
pip install -r collector/requirements.txt
```

> Python 수집 서버는 `chat` / `web` 모드 실행 시 **자동으로 시작**됩니다.  
> 별도 pip 환경이 있다면 해당 Python으로 `collector/server.py`를 실행하면 됩니다.

---

## 실행 방법

### 모드 1 — chat (대화형 분석) ← 메인

실제 Chrome을 열고 URL을 입력하면 Claude가 상품 페이지를 실시간 분석합니다.

```bash
npm run chat
```

실행 후 프롬프트에 쇼핑몰 URL을 입력합니다. `q` 입력 시 종료.

```
URL 입력 (q 종료): https://www.coupang.com/vp/products/12345
```

- **첫 방문 도메인** → 전체 분석 → 템플릿 생성 → 상품 데이터 추출
- **재방문 도메인** → 저장된 템플릿 재사용 → 빠른 추출

---

### 모드 2 — scrape (URL 직접 스크래핑)

Playwright로 상품 목록과 상세 페이지를 수집해 JSON으로 저장합니다.

```bash
npx ts-node src/index.ts scrape <URL> [페이지수] [--headless] [--no-details]
```

| 옵션 | 설명 |
|------|------|
| `페이지수` | 수집할 최대 페이지 수 (기본 3) |
| `--headless` | 브라우저를 숨기고 실행 |
| `--no-details` | 상세 페이지 수집 생략 (목록만) |

```bash
# 예시
npx ts-node src/index.ts scrape https://www.coupang.com/np/search?q=노트북 3 --headless
```

결과는 `output/<타임스탬프>/` 디렉토리에 저장됩니다.

```
output/2024-01-15T12-30-00/
├── products.json           # 상품 목록
└── product_details.json    # 상품 상세
```

---

### 모드 3 — agent (AI 에이전트)

자연어로 요청하면 Claude가 새 API 핸들러를 생성·테스트합니다.

```bash
npx ts-node src/index.ts agent "<작업 설명>"
```

```bash
# 예시
npx ts-node src/index.ts agent "쿠팡 검색 스크래퍼 API 만들어줘"
```

---

### 모드 4 — template (사이트 템플릿 생성)

처음 보는 사이트 URL을 분석해 `templates/<도메인>.json`을 자동 생성합니다.

```bash
npx ts-node src/index.ts template <URL>
```

```bash
# 예시
npx ts-node src/index.ts template https://www.rakuten.co.jp/search?q=shoes
```

---

### 모드 5 — web (API 서버 + 웹 UI)

REST API 서버와 React 웹 UI를 실행합니다.

**터미널 1 — API 서버:**

```bash
npm run web
```

**터미널 2 — 웹 UI (개발 서버):**

```bash
cd web
npm install
npm run dev
```

| 서버 | 주소 |
|------|------|
| API 서버 | http://localhost:3000 |
| React 웹 UI (dev) | http://localhost:5174 |

**프로덕션 빌드 (UI + API 단일 서버):**

```bash
npm run web:build   # React 빌드 → web/dist/
npm run web         # http://localhost:3000 에서 UI + API 함께 서빙
```

---

### Python 수집 서버 단독 실행

```bash
python collector/server.py
```

포트 `18080`에서 Flask 서버가 실행됩니다.

---

## 주요 API 엔드포인트 (web 모드)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/api/analyze` | URL 분석 (SSE 스트리밍) |
| `POST` | `/api/template/build` | 템플릿 빌더 멀티턴 대화 |
| `GET` | `/api/templates` | 저장된 템플릿 목록 |
| `DELETE` | `/api/templates/:filename` | 템플릿 삭제 |
| `GET` | `/api/knowledge` | site_knowledge 목록 |
| `GET` | `/api/knowledge/:domain` | 특정 도메인 knowledge |

---

## 지원 쇼핑몰

| 사이트 | 수집 방식 | 옵션 자동 클릭 |
|--------|-----------|----------------|
| 쿠팡 | Python (undetected_chromedriver) | O |
| 네이버 스마트스토어 | Python | O |
| 무신사 | Python + IcArrowDown 클릭 | O |
| 올리브영 | Python + OptionSelector 클릭 | O |
| 지마켓 | Python + 옵션 셀렉트 클릭 | O |
| 지그재그, 29CM, W컨셉, 에이블리, 오늘의집, H몰 | Python | O |
| 기타 일반 사이트 | Playwright fallback | 자동 탐지 |

---

## 템플릿 시스템

첫 방문 시 `templates/<domain>.json`에 저장되며, 이후 방문에서 재사용됩니다.

특정 도메인을 재분석하려면 템플릿 파일을 삭제하고 다시 실행합니다:

```bash
# Windows
del templates\coupang.com.json

# macOS / Linux
rm templates/coupang.com.json
```

---

## 문제 해결

**`ANTHROPIC_API_KEY not set` 오류**  
→ 프로젝트 루트에 `.env` 파일이 있는지, 키가 올바른지 확인합니다.

**Chrome 창이 열리지 않거나 수집 서버 시작 실패**  
→ `pip install -r collector/requirements.txt`로 Python 의존성을 설치합니다.  
→ `.env`에 `CHROME_PATH`를 명시합니다.

```env
CHROME_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe
```

**쿠팡 HTML 0KB / 봇 차단**  
→ Python 수집 서버 로그에 `[슬롯0] Chrome 시작 완료`가 보여야 합니다.  
→ Chrome 프로필을 초기화하려면 `%TEMP%\chrome_profile_coupang_p0` 폴더를 삭제합니다.

**`undetected_chromedriver` 버전 오류**  
→ Chrome 버전과 드라이버 버전 불일치입니다.

```bash
pip install -U undetected-chromedriver
```

**템플릿 오류 / 403 에러**  
→ `templates/<domain>.json` 삭제 후 재실행합니다.
