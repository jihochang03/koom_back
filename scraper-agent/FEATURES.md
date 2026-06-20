# scraper-agent 기능 설명서

---

## 전체 설계 철학: 범용 코어 + 쇼핑몰 특화 모듈

이 프로그램은 **어떤 웹사이트든 크롤링할 수 있는 공통 기반** 위에, **쇼핑몰 전용 기능**을 별도 레이어로 얹는 구조로 설계되어 있습니다.

```
src/core/          ← 범용 크롤러 기반 (브라우저 제어, 네트워크, 스텔스, 에이전트 루프)
src/agent/         ← 범용 에이전트 (코드 생성 AI)
  tools/           ← 에이전트가 쓰는 도구들 (브라우저, 파일, 실행)
src/modules/
  shopping/        ← 쇼핑몰 특화 레이어 (가격·옵션 추출, 쇼핑몰별 AI 프롬프트)

collector/         ← 범용 수집 서버 (Chrome 관리)
  shopping/        ← 쇼핑몰 특화 수집기 (네이버, 쿠팡, 무신사 등)
```

새로운 도메인(뉴스 사이트, 채용 공고 등)을 추가하려면 `src/modules/<새도메인>/`과 `collector/<새도메인>/`만 만들면 되고, 코어는 건드리지 않아도 됩니다.

---

## 핵심 개념: 템플릿

**템플릿**이란 "이 쇼핑몰에서 데이터를 어떻게 꺼내는지"를 적어둔 파일입니다.
`templates/` 폴더에 쇼핑몰 도메인 이름으로 저장됩니다.

- `smartstore.naver.com_detail.py` → 네이버 스마트스토어 상품 페이지용 Python 스크립트
- `coupang.com_both.py` → 쿠팡용 Python 스크립트 (상품 상세 + 목록 모두 지원)

템플릿이 있으면 AI 없이 바로 실행하고, 없으면 AI가 분석합니다.
→ **가장 중요한 분기점**입니다.

---

## 기능 1: 상품 URL 분석 — 3단계 fallback 체인

URL이 들어오면 빠른 방법부터 순서대로 시도합니다. 앞 단계가 실패해야만 다음 단계로 넘어갑니다.

```
URL 입력
  ↓
[1단계] templates/ 폴더에 이 도메인 템플릿(.py)이 있나?
  있음 → Python으로 바로 실행 → 완료
  없음 ↓
[2단계] Flask 수집 서버(Chrome)로 HTML 수집 → Claude AI가 분석
  성공 → 완료
  실패(수집 서버가 꺼져있음) ↓
[3단계] Playwright(TS 브라우저)로 직접 수집 → Claude AI가 분석
```

### 1단계: 템플릿 실행 (가장 빠름, AI 비용 없음)

`template-runner.ts`가 `templates/` 폴더를 뒤져서 도메인에 맞는 `.py` 파일을 찾습니다.
찾으면 `python <파일명> <URL>` 명령어로 실행합니다. 출력된 JSON을 화면에 보여줍니다.

실패하거나 파일이 없으면 2단계로 넘어갑니다.

### 2단계·3단계: Claude AI 분석

수집 서버(Chrome) 또는 Playwright로 HTML을 가져온 뒤, Claude Sonnet에게 넘깁니다.
Claude는 한국어로 상품을 설명하면서 동시에 구조화된 JSON 데이터를 출력합니다.

자세한 수집 방식은 **기능 3(수집 서버)** 에서 설명합니다.

---

## 기능 2: 템플릿을 만드는 에이전트 (Template Builder Agent)

새 쇼핑몰에 대한 템플릿이 없을 때, AI가 스스로 그 쇼핑몰을 분석해서 Python 스크레이퍼 코드를 만들고 검증까지 합니다.

웹 UI의 **Template 탭**에서 채팅하듯 사용합니다.

### 에이전트란?

보통 AI는 질문에 답만 합니다. 에이전트는 다릅니다. **도구를 직접 사용해서 결과를 확인하고, 그 결과를 보고 다음 행동을 결정하며, 완성할 때까지 반복합니다.**

마치 탐정이 단서를 하나씩 찾아가며 사건을 해결하는 것과 비슷합니다.

### 에이전트 루프 구조 (`agent-core.ts`)

```
Claude 생각
  ↓
도구 선택 + 실행
  ↓
결과 확인
  ↓
Claude 생각 (다시)
  ↓
... (최대 12회 반복)
  ↓
최종 코드 완성
```

이 반복 구조(`runAgentLoop`)는 `agent-core.ts`에 공통으로 구현되어 있어서, 다른 에이전트를 만들 때도 재사용할 수 있습니다.

### 템플릿 빌더가 쓰는 8가지 도구

에이전트가 쓸 수 있는 도구 목록은 미리 정의되어 있고(`template-builder-agent.ts`), Claude는 필요한 도구를 골라서 사용합니다.

---

**collect_page** — 페이지 수집

Flask 수집 서버에 "이 URL 열어줘"라고 요청합니다.
결과(HTML + 네트워크 로그)를 서버 메모리의 **세션**에 저장해둡니다.
이후 grep_html, inspect_network 등 도구들이 이 세션 데이터를 참조합니다.

---

**grep_html** — HTML에서 검색

세션에 저장된 HTML을 줄 단위로 쪼개서 정규식(패턴 문자열)으로 검색합니다.
예: `option|variant|color` 로 검색하면 옵션 관련 줄들을 전후 문맥과 함께 꺼냅니다.
워드 문서에서 Ctrl+F 검색과 같은 개념입니다.

---

**get_html_section** — HTML 특정 부분 추출

CSS 셀렉터(HTML 요소를 가리키는 주소)로 원하는 HTML 블록만 잘라냅니다.
예: `.option-wrap` 이라고 하면 옵션 컨테이너 부분만 꺼내줍니다.
전체 HTML을 보는 대신 필요한 부분만 확인하는 용도입니다.

---

**inspect_network** — API 응답 확인

세션의 네트워크 로그(페이지가 로드되면서 백그라운드로 호출한 API 응답들)를 URL로 필터링해 보여줍니다.
많은 쇼핑몰이 옵션 데이터를 별도 API로 불러오기 때문에, HTML만 보면 놓치는 옵션 데이터를 찾을 수 있습니다.

---

**run_code** — Python 코드 실제 실행

Claude가 작성한 Python 스크레이퍼 코드를 임시 파일로 저장하고 실제로 실행합니다.
출력이 JSON이면 화면에 미리보기로 표시합니다. "잘 동작하는지" 확인하는 단계입니다.

---

**save_template** — 템플릿 저장

검증된 코드를 `templates/도메인_detail.py` 형식으로 저장합니다.
이후 같은 쇼핑몰 URL이 들어오면 1단계에서 이 파일을 바로 실행합니다.

---

**click_and_capture** — 클릭 실험

"이 버튼을 클릭하면 새 옵션이 나오나?" 실험합니다.
클릭 전후 옵션 관련 요소 개수를 비교해서 새 옵션이 나타났는지 확인합니다.
탭, 아코디언, 더보기 버튼 등 클릭해야만 보이는 옵션을 찾을 때 씁니다.

---

**save_site_knowledge** — 수집 힌트 저장

"이 쇼핑몰은 이 버튼을 클릭해야 옵션이 나온다" 같은 정보를 `site_knowledge/도메인.json`에 영구 저장합니다.
다음에 같은 쇼핑몰을 방문하면 자동으로 재사용합니다.

---

### 실제 탐색 흐름 예시

```
사용자: "https://example.com/product/123 으로 스크레이퍼 만들어줘"

Claude → collect_page 실행
  결과: HTML 45KB, 네트워크 로그 12개

Claude → inspect_network(url_filter="option") 실행
  결과: /api/v2/option?id=123 응답 발견, 색상 3개·사이즈 5개 JSON 확인

Claude → click_and_capture(selectors=["[role='tab']"]) 실행
  결과: 옵션 신호 +6 증가 → 탭 클릭이 효과 있음

Claude → (Python 코드 작성)

Claude → run_code 실행
  결과: {"title": "...", "options": [...]} 출력 확인

Claude → save_template 실행 → templates/example.com_detail.py 저장
Claude → save_site_knowledge(extra_clicks=["[role='tab']"]) 실행
```

### 히스토리 압축

대화가 길어지면 토큰(AI가 처리하는 글자 단위) 비용이 올라갑니다.
오래된 도구 실행 결과(400자 초과)는 `[N자 결과 — 이전 턴 처리됨]`으로 요약 압축합니다.
최근 8개 메시지는 원본 그대로 유지합니다.

---

## 기능 3: CLI 에이전트 (TypeScript 핸들러 생성)

터미널에서 직접 사용하는 에이전트입니다. 웹 UI의 템플릿 빌더와는 다르게, **TypeScript 핸들러 파일**을 생성하는 것이 목적입니다. (`src/modules/shopping/apis/` 아래에 `.ts` 파일로 저장)

`agent.ts`가 `agent-core.ts`의 공통 루프를 가져다 쓰고, 아래 도구들을 조합합니다.

### browser-tools.ts (브라우저 조작 도구)

Playwright(MS가 만든 브라우저 자동화 라이브러리)를 써서 실제 Chrome을 조종합니다.

| 도구 | 기능 |
|------|------|
| `navigate_browser` | URL로 이동 |
| `take_screenshot` | 현재 화면 스크린샷 → Claude가 이미지를 직접 보고 판단 |
| `get_page_html` | 페이지 HTML 전체 또는 CSS 셀렉터로 특정 부분만 |
| `grep_html` | 현재 페이지 HTML에서 패턴 검색 |

스크린샷 도구는 특이하게 텍스트가 아닌 이미지를 반환합니다. Claude가 이미지를 받으면 화면을 눈으로 보듯 분석할 수 있습니다.

### file-tools.ts (파일 읽기/쓰기 도구)

| 도구 | 기능 |
|------|------|
| `read_file` | 프로젝트 파일 읽기 (기존 코드 스타일 학습용) |
| `list_files` | glob 패턴으로 파일 목록 조회 |
| `write_file` | 생성한 핸들러 코드를 파일로 저장 |

에이전트가 코드를 쓰기 전에 먼저 기존 파일들을 읽어서 "이 프로젝트가 어떤 코드 스타일을 쓰는지" 파악합니다.

### run-tools.ts (코드 실행 도구)

| 도구 | 기능 |
|------|------|
| `run_api` | 생성한 TypeScript 핸들러를 실제로 실행해서 결과 확인 |

내부적으로 임시 runner 파일을 만들어 `ts-node`로 실행합니다.

### ask_user (사용자 확인)

코드를 파일에 쓰기 전에 사용자에게 "이렇게 만들어도 될까요? [y/n]"을 물어봅니다.
허락 없이 파일을 변경하지 않습니다.

### CLI 에이전트 워크플로우

```
1. list_files로 기존 코드 파일 목록 확인
2. read_file로 기존 코드 스타일 학습
3. navigate_browser로 목표 페이지 이동
4. take_screenshot + grep_html로 페이지 구조 파악
5. CAPTCHA가 있으면 solve_captcha로 자동 해결
6. ask_user로 계획 확인
7. write_file로 핸들러 코드 저장
8. run_api로 실제 실행 테스트
```

---

## 기능 4: 수집 서버 (Flask + Chrome, 포트 18080)

웹사이트에서 HTML을 가져오는 전담 서버입니다. `collector/server.py`가 Flask(Python 웹 서버 라이브러리)로 구동됩니다.

### 왜 별도 서버로 분리했나?

쿠팡, 네이버 같은 대형 쇼핑몰은 자동화 프로그램이 접속하면 막습니다. 이를 우회하려면 실제 Chrome에 특수 설정이 필요한데, 이 Chrome을 계속 띄워두고 재사용하는 게 훨씬 빠릅니다.

TypeScript 서버가 "이 URL 수집해줘"를 HTTP 요청으로 보내면, Python 서버가 Chrome으로 수집해서 HTML을 돌려주는 구조입니다.

### 봇 탐지 우회 방법들

**undetected_chromedriver 사용**
일반 자동화 Chrome에는 `navigator.webdriver = true`라는 표식이 있어서 쇼핑몰이 봇임을 알아챕니다. `undetected_chromedriver`는 이 표식을 제거합니다.

**영구 Chrome 프로필**
매번 새 Chrome을 열지 않고, 같은 프로필 폴더를 재사용합니다. 방문 기록·쿠키가 쌓여 "단골 사용자"처럼 보입니다.

**Warm-up 방문**
쿠팡 상품 페이지를 바로 열기 전에 쿠팡 홈페이지를 먼저 방문합니다. 홈에서 검색해서 들어온 것처럼 보이게 합니다.

**JS 네비게이션**
`driver.get(url)` (자동화 표준 방식) 대신 JavaScript로 `window.location.href = url`을 실행합니다. 사용자가 주소창에 직접 입력하거나 링크를 클릭한 것과 동일한 방식입니다.

**Referer 위장**
서버에 접속할 때 "구글에서 검색해서 왔습니다"라는 정보를 함께 보냅니다.
(HTTP 헤더: `Referer: https://www.google.com/search?q=쇼핑몰도메인`)

### 네트워크 로그 캡처

많은 쇼핑몰은 옵션(색상, 사이즈) 데이터를 별도 API로 불러옵니다. HTML만 보면 옵션이 없는 것처럼 보이지만, 실제로는 페이지가 열리면서 백그라운드 요청이 날아갑니다.

Chrome이 시작될 때 CDP(Chrome 개발자 도구 프로토콜)로 다음을 심어둡니다:
- 모든 `fetch`(최신 네트워크 요청 방식) 응답을 몰래 가로채서 저장
- 모든 `XHR`(구형 네트워크 요청 방식) 응답도 동일하게 저장
- 이미지·CSS·폰트는 제외, JSON 데이터만 저장

페이지 수집 후 이 데이터를 꺼내서 HTML과 함께 AI에게 전달합니다.

### 쇼핑몰별 특화 수집

범용 수집 로직 위에 쇼핑몰별 특화 처리가 추가됩니다.

| 쇼핑몰 | 특화 처리 |
|--------|---------|
| 네이버 스마트스토어 | `NaverCollector` (별도 Chrome 슬롯), `__PRELOADED_STATE__` JSON 파싱 |
| 쿠팡 | `undetected_chromedriver`, 영구 프로필, 홈 warm-up |
| 무신사 | 드롭다운 버튼 자동 클릭 후 재수집 |
| 지마켓 | 옵션 셀렉트박스·버튼 자동 클릭 |
| 올리브영 | 옵션 버튼 자동 클릭 |
| 그 외 (SSG, 롯데온, 에이블리, 지그재그, 29CM 등) | HTML 파서로만 처리 |

### 슬롯 풀

Chrome 인스턴스를 동시에 1~4개까지 운영합니다. (기본 1개, 환경변수 `COLLECTOR_MAX_WORKERS`로 설정)
요청이 들어오면 여유 슬롯을 라운드로빈(순서대로 배정)으로 할당합니다.
모든 슬롯이 사용 중이면 `503 Busy`를 반환합니다.

### 자동 복구

120초마다 Watchdog 스레드가 모든 Chrome이 살아있는지 확인합니다. 죽어있으면 자동으로 재시작합니다.

---

## 기능 5: CAPTCHA 자동 해결

쇼핑몰이 "로봇이 아닌지 확인"하는 CAPTCHA를 자동으로 풀어줍니다.

챌린지 페이지 감지 조건:
- 수집된 HTML이 5,000자 미만 (정상 상품 페이지는 훨씬 큼)
- "상품 접근 확인", "captcha", "비정상적인 접근" 같은 단어 포함

### KnownPatternHandler — 기억해둔 패턴 재사용

이전에 이 쇼핑몰의 CAPTCHA를 푼 기록이 `site_knowledge/도메인.json`에 있으면 그 방법을 바로 씁니다. AI 호출 없이 즉시 처리.

### VisionCaptchaHandler — Claude Haiku 비전 분석

처음 보는 CAPTCHA일 때 사용합니다.
1. 현재 화면 스크린샷 촬영
2. Claude Haiku(작고 빠른 모델)에게 이미지 + HTML 전송
3. Haiku가 "수학 문제 17+3=?" 같은 CAPTCHA를 분석해 정답·입력창 위치 반환
4. Selenium이 정답을 입력하고 제출

성공하면 패턴을 `site_knowledge`에 저장해 다음번엔 KnownPatternHandler가 처리합니다.

---

## 기능 6: 숨겨진 옵션 자동 탐색 (OptionRevealer)

탭·아코디언·더보기 버튼 뒤에 숨은 옵션을 자동으로 펼칩니다.

### 동작 방식

1. **옵션 신호 개수 측정** — `option`, `swatch`, `color`, `size` 등 단어가 포함된 요소 개수 합산
2. **이미 알고 있는 패턴 먼저** — `site_knowledge.extra_clicks`에 저장된 셀렉터를 클릭
3. **후보 30여 개 순서대로 시도** — `[role="tab"]`, 아코디언 버튼, 더보기 버튼, 색상 스워치 등
4. **클릭 전후 비교** — 옵션 신호가 늘었으면 "효과 있음"으로 판단
5. **새로 찾은 패턴 저장** — 다음번 같은 사이트에서 재사용

---

## 기능 7: HTML 전용 파서 (Claude 없이 선처리)

Chrome 수집 결과를 Claude에게 넘기기 전에, Python BeautifulSoup(HTML 파싱 도구)으로 먼저 가격·옵션을 추출합니다. Claude가 놓쳤을 때 보완 역할도 합니다.

**추출 우선순위:**

1. **JSON-LD 스키마** — `<script type="application/ld+json">` 태그에 기계가 읽기 쉬운 형식으로 정리된 상품 데이터
2. **OG 메타태그** — SNS 공유 미리보기용 태그. 상품명·이미지·가격 포함
3. **가격 정규식** — `12,000원`, `₩15,000` 패턴 텍스트에서 추출
4. **h1/h2 제목** — 모두 실패 시 가장 큰 제목 태그를 상품명으로

**네이버 전용:** `window.__PRELOADED_STATE__` (페이지 HTML에 심어진 상품 전체 JSON)를 정규식으로 추출·파싱.

**우선순위 규칙:** 네트워크 API 응답에서 더 많은 옵션 그룹이 발견되면 HTML 파서 결과를 API 결과로 교체합니다.

---

## 기능 8: Site Knowledge (사이트 학습 저장소)

각 쇼핑몰에 대한 "경험"을 파일로 저장합니다. 위치: `collector/site_knowledge/도메인.json`

```json
{
  "captcha": {
    "type": "math",
    "input_selector": "input#captchaAnswer",
    "submit_selector": "button.confirm",
    "solved_count": 5
  },
  "collection": {
    "extra_clicks": ["[role='tab']:first-child", ".size-toggle"],
    "wait_for_selector": ".product-options",
    "network_patterns": ["/api/v2/products/"]
  }
}
```

이 파일은 세 곳에서 자동으로 업데이트됩니다:
- CAPTCHA 해결 성공 시
- OptionRevealer가 새 클릭 패턴 발견 시
- 템플릿 빌더 에이전트가 `save_site_knowledge` 도구 사용 시

---

## 기능 9: React 화면 3개

### Analyze 탭 (상품 분석)

URL 입력 → 분석 결과가 실시간으로 타이핑 효과로 나타납니다.

SSE(Server-Sent Events) 방식을 씁니다. SSE는 서버가 작업하면서 중간 결과를 실시간으로 클라이언트에 밀어주는 기술입니다. Claude가 단어를 생성할 때마다 즉시 화면에 표시되는 이유입니다.

상태 메시지("페이지 수집 중...", "Claude가 읽고 있어요...")도 같은 방식으로 전달됩니다.

### Template 탭 (템플릿 빌더)

채팅 UI. 메시지를 보낼 때마다 지금까지의 전체 대화 내역을 서버에 함께 전송합니다. 서버는 상태를 저장하지 않고 매번 전달받은 내역 기준으로 처리합니다.

화면에 표시되는 것들:
- Claude 설명 텍스트 (실시간 타이핑)
- 🔧 어떤 도구를 실행했는지
- Python 코드 블록 (색상 강조)
- 코드 실행 결과 미리보기

### Knowledge 탭 (지식 관리)

저장된 모든 도메인의 site_knowledge와 템플릿 파일을 관리합니다.

목록에서 도메인 클릭 → 우측 패널:
- CAPTCHA 패턴 JSON 직접 편집·저장
- 수집 힌트 JSON 직접 편집·저장
- `.py` 템플릿 파일 내용 보기·복사·삭제
