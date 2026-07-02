# Tariff API

상품명으로 일본 관세율표(SQLite DB)를 조회하고, Claude AI로 최적 항목을 선택하는 앱.  
조회 결과는 24시간 캐시하여 Claude API 중복 호출을 방지한다.

Base URL: `/api/tariff/`

---

## 엔드포인트 목록

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/tariff/lookup/` | 관세율 조회 (가격 견적용, 단일 결과) |
| POST | `/api/tariff/classify/` | HS코드 분류 + **선정 사유** + **대안 후보** (검수자용) |
| GET | `/api/tariff/products/{pk}/classification/` | 상품 HS 분류 추천 조회/생성 |
| POST | `/api/tariff/products/{pk}/classification/` | 검수 담당자 HS코드·통관 카테고리 확정/수정 |
| GET | `/api/tariff/logs/` | 조회 이력 목록 |

---

## POST `/api/tariff/lookup/`

상품명으로 일본 관세율표를 조회한다.

### 처리 흐름

1. `use_cache=true`이고 최근 24시간 이내 동일 상품명 조회 이력이 있으면 캐시 반환
2. OpenAI 임베딩 가능 시 벡터 검색, 불가능 시 Claude로 검색어 확장 후 FTS5 검색
3. 후보 항목 중 Claude(Haiku)가 가장 적합한 항목 번호 선택
4. RCEP → 잠정 → WTO → 기본 순서로 가장 낮은 세율 적용
5. 결과를 DB에 저장 후 반환

### Request Body

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|------|------|------|--------|------|
| `product_title` | string | ✅ | — | 관세율을 조회할 상품명 (최대 500자) |
| `use_cache` | boolean | ❌ | `true` | 24시간 캐시 사용 여부 |

### Request 예시

```json
{
  "product_title": "블루투스 무선 이어폰 노이즈캔슬링"
}
```

```json
{
  "product_title": "면 100% 반소매 티셔츠",
  "use_cache": false
}
```

### Response Body (200 OK)

| 필드 | 타입 | 설명 |
|------|------|------|
| `rate` | float\|null | 종가세율 (0~1, 예: `0.085` = 8.5%). 종량세만 있으면 `null` |
| `rate_source` | string\|null | 세율 출처 |
| `duty_type` | string\|null | 세율 유형 |
| `specific_yen_per_unit` | float\|null | 종량세 단위 금액 (엔). `duty_type`이 `specific`/`compound`일 때만 존재 |
| `specific_unit` | string\|null | 종량세 단위 (예: `kg`, `each`) |
| `matched_item` | string\|null | 매칭된 관세율표 한글 품명 |
| `순번` | integer\|null | 관세율표 순번 (HS코드) |
| `full_path` | string\|null | 분류 전체 경로 (`대분류 > 중분류 > ... > 품목`) |
| `depth_path` | string[] | `full_path`를 단계별로 분해한 배열 |
| `candidates_found` | integer | 검색된 후보 항목 수 |
| `selection_method` | string | 선택 방법 |
| `search_expansion` | string | Claude가 확장한 검색어 (있을 때만) |
| `non_physical` | boolean | 비실물 품목 여부 (서비스·티켓 등) |
| `cached` | boolean | 캐시에서 반환된 결과인지 여부 |

**`rate_source` 허용값**

| 값 | 설명 |
|----|------|
| `rcep` | RCEP(한-일 FTA) 세율 |
| `temp` | 잠정세율 |
| `wto` | WTO 협정세율 |
| `basic` | 기본세율 |
| `unparseable` | 파싱 불가 |
| `none` | 후보 없음 |

**`duty_type` 허용값**

| 값 | 설명 |
|----|------|
| `free` | 무관세 |
| `advalorem` | 종가세 (상품가 대비 %) |
| `specific` | 종량세 (수량·중량 기준 고정액) |
| `compound` | 혼합세 (종가 + 종량) |
| `unknown` | 파싱 불가 |

### Response 예시 — 종가세

```json
{
  "rate": 0.0,
  "rate_source": "rcep",
  "duty_type": "free",
  "specific_yen_per_unit": null,
  "specific_unit": null,
  "matched_item": "헤드폰, 이어폰 및 이와 유사한 것",
  "순번": 8518300000,
  "candidates_found": 12,
  "selection_method": "llm",
  "search_expansion": "헤드폰, 이어폰, 음향기기, 수신기",
  "non_physical": false,
  "cached": false
}
```

### Response 예시 — 혼합세

```json
{
  "rate": 0.25,
  "rate_source": "basic",
  "duty_type": "compound",
  "specific_yen_per_unit": 63.0,
  "specific_unit": "kg",
  "matched_item": "가죽제 의류",
  "순번": 4203100000,
  "candidates_found": 8,
  "selection_method": "llm",
  "non_physical": false,
  "cached": false
}
```

### Response 예시 — 비실물 품목

```json
{
  "rate": null,
  "rate_source": "none",
  "duty_type": null,
  "specific_yen_per_unit": null,
  "specific_unit": null,
  "matched_item": null,
  "순번": null,
  "candidates_found": 0,
  "non_physical": true,
  "cached": false
}
```

### 에러 응답

| 상태 코드 | 조건 |
|-----------|------|
| `400 Bad Request` | `product_title` 누락 또는 유효하지 않은 파라미터 |

> **참고**: ANTHROPIC_API_KEY 미설정이나 DB 파일 없음 등의 내부 오류는 `rate: null`, `candidates_found: 0`으로 응답하며 예외를 던지지 않는다.

---

## GET `/api/tariff/logs/`

최근 50건의 관세율 조회 이력을 반환한다.

### Response Body (200 OK)

```json
[
  {
    "id": 10,
    "product_title": "블루투스 무선 이어폰 노이즈캔슬링",
    "result": { ... },
    "rate": 0.0,
    "duty_type": "free",
    "matched_item": "헤드폰, 이어폰 및 이와 유사한 것",
    "created_at": "2026-06-01T10:00:00+09:00"
  }
]
```

**응답 필드**

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | integer | 이력 ID |
| `product_title` | string | 조회한 상품명 |
| `result` | object | 조회 결과 전체 (lookup 반환 dict) |
| `rate` | float\|null | 최종 세율 |
| `duty_type` | string | 세율 유형 |
| `matched_item` | string | 매칭된 품명 |
| `created_at` | string (ISO 8601) | 조회 시각 |

---

## POST `/api/tariff/classify/`

검수 담당자가 fastbox 통관 등록 전에 HS코드·통관 카테고리를 **확인·선택**할 수 있도록,
AI가 고른 분류와 **선정 사유**, 그리고 채택될 여지가 있는 **대안 후보**를 함께 반환한다.
관세 분류는 `대분류 → 중분류 → 세부품목`으로 좁혀지는 트리(depth)이므로, 각 후보마다
`full_path`/`depth_path`로 어떤 경로로 도달했는지 보여 준다. (상태 저장 안 함)

`/lookup/`과의 차이: `/lookup/`은 가격 견적용 **단일 세율**만 반환하지만,
`/classify/`는 **여러 후보 + 사유**를 반환해 검수자가 다른 분류를 고를 수 있게 한다.

### Request Body

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|------|------|------|--------|------|
| `product_title` | string | ✅ | — | 분류할 상품명 |
| `top_n` | integer | ❌ | `5` | 제시할 대안 후보 개수 (0~10) |

### Response Body (200 OK)

| 필드 | 타입 | 설명 |
|------|------|------|
| `product_title` | string | 요청한 상품명 |
| `non_physical` | boolean | 비실물 품목 여부 |
| `search_expansion` | string\|null | AI 검색 확장어 |
| `candidates_found` | integer | 검색된 후보 수 |
| `selected` | object\|null | AI가 고른 최적 분류 (아래 후보 객체 + `reason`) |
| `alternatives` | object[] | 대안 후보 목록 (후보 객체 + `rank`) |

**후보 객체 (`selected` / `alternatives[]`)**

| 필드 | 타입 | 설명 |
|------|------|------|
| `hs_code` | integer\|null | 관세율표 순번(HS코드) |
| `matched_item` | string\|null | 한글 품명 |
| `full_path` | string\|null | 분류 전체 경로 |
| `depth_path` | string[] | 단계별 분류 배열 |
| `rate` | float\|null | 종가세율 (0~1) |
| `rate_source` | string\|null | 세율 출처 (`rcep`/`temp`/`wto`/`basic`/…) |
| `duty_type` | string\|null | 세율 유형 (`free`/`advalorem`/`specific`/`compound`) |
| `specific_yen_per_unit` | float\|null | 종량세 단위 금액 |
| `specific_unit` | string\|null | 종량세 단위 |
| `reason` | string | (`selected`만) AI가 이 분류를 고른 이유 |
| `rank` | integer | (`alternatives`만) 적합 순위 |

### Response 예시

```json
{
  "product_title": "면 100% 반소매 티셔츠 남성",
  "non_physical": false,
  "search_expansion": "면 편직물 의류, 티셔츠, 메리야스 상의, 면제",
  "candidates_found": 18,
  "selected": {
    "hs_code": 6109100000,
    "matched_item": "티셔츠ㆍ싱글릿과 그 밖의 조끼류(메리야스 편물ㆍ뜨개질 편물로 한정한다)",
    "full_path": "방직용 섬유제품 > 의류 > 티셔츠ㆍ싱글릿 > 면제",
    "depth_path": ["방직용 섬유제품", "의류", "티셔츠ㆍ싱글릿", "면제"],
    "rate": 0.0,
    "rate_source": "rcep",
    "duty_type": "free",
    "specific_yen_per_unit": null,
    "specific_unit": null,
    "reason": "면 편직물로 만든 반소매 상의이므로 '티셔츠ㆍ싱글릿(면제)' 분류 경로와 정확히 일치한다."
  },
  "alternatives": [
    {
      "hs_code": 6105100000,
      "matched_item": "남성용 셔츠(메리야스 편물ㆍ뜨개질 편물로 한정한다)",
      "full_path": "방직용 섬유제품 > 의류 > 셔츠 > 면제",
      "depth_path": ["방직용 섬유제품", "의류", "셔츠", "면제"],
      "rate": 0.0, "rate_source": "rcep", "duty_type": "free",
      "specific_yen_per_unit": null, "specific_unit": null,
      "rank": 1
    }
  ]
}
```

---

## GET `/api/tariff/products/{pk}/classification/`

상품의 HS 분류 추천을 조회한다. 분류 레코드가 없으면 상품 제목으로 AI 분류
(`/classify/` 로직)를 생성·저장한 뒤 반환한다.

### Query Parameters

| 파라미터 | 설명 |
|----------|------|
| `refresh` | `1`/`true`이면 미확정(pending) 레코드의 AI 추천을 재계산 |

### Response Body (200 OK)

저장된 분류 레코드(아래 DB 모델 필드) + 신규 생성/refresh 시 `classify` 키에
최신 분류 결과(`/classify/` 응답 구조)를 포함한다.

```json
{
  "id": 3,
  "product": 42,
  "ai_suggested": { "hs_code": 6109100000, "matched_item": "...", "reason": "..." },
  "ai_alternatives": [ { "hs_code": 6105100000, "rank": 1, "...": "..." } ],
  "ai_search_expansion": "면 편직물 의류, 티셔츠",
  "final_hs_code": "",
  "final_category": "",
  "final_full_path": "",
  "status": "pending",
  "decision_source": "",
  "inspector": "",
  "inspector_note": "",
  "created_at": "2026-06-22T10:00:00+09:00",
  "confirmed_at": null,
  "updated_at": "2026-06-22T10:00:00+09:00",
  "classify": { "...": "/classify/ 응답 구조" }
}
```

---

## POST `/api/tariff/products/{pk}/classification/`

검수 담당자가 HS코드·통관 카테고리를 **확정**하거나 **수정**하고 피드백을 남긴다.
확정 시 `status=confirmed`, `confirmed_at` 자동 기록. 확정값(`final_*`)이 fastbox
통관 등록에 사용된다.

### Request Body

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|------|------|------|--------|------|
| `final_hs_code` | string | ❌ | `''` | 확정 HS코드(순번) |
| `final_category` | string | ❌ | `''` | 확정 통관 카테고리(한글품명) |
| `final_full_path` | string | ❌ | `''` | 확정 분류 경로 |
| `decision_source` | string | ❌ | `manual` | `ai_confirmed`/`alternative`/`manual` |
| `inspector` | string | ❌ | `''` | 검수 담당자 |
| `inspector_note` | string | ❌ | `''` | 검수 피드백/메모 |

**`decision_source` 허용값**

| 값 | 설명 |
|----|------|
| `ai_confirmed` | AI 추천을 그대로 확정 |
| `alternative` | 제시된 대안 후보 중 선택 |
| `manual` | 검수자가 직접 입력해 수정 |

### Request 예시

```json
{
  "final_hs_code": "6105100000",
  "final_category": "남성용 셔츠(메리야스 편물)",
  "final_full_path": "방직용 섬유제품 > 의류 > 셔츠 > 면제",
  "decision_source": "alternative",
  "inspector": "김검수",
  "inspector_note": "실물 확인 결과 티셔츠가 아니라 카라 있는 셔츠라 셔츠 분류로 변경"
}
```

응답은 확정된 분류 레코드(위 GET 응답의 `classify` 제외) 전체.

---

## DB 모델 구조

### TariffLookupLog

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | AutoField | PK |
| `product_title` | CharField(500) | 조회 상품명 |
| `result` | JSONField | 조회 결과 전체 |
| `rate` | FloatField | 최종 세율 (빠른 필터용) |
| `duty_type` | CharField(20) | 세율 유형 |
| `matched_item` | CharField(500) | 매칭된 품명 |
| `created_at` | DateTimeField | 생성 시각 |

### ProductHsClassification

상품별 HS코드·통관 카테고리 확정 레코드 (`products.Product`와 1:1).

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | AutoField | PK |
| `product` | OneToOneField(products.Product) | 대상 상품 |
| `ai_suggested` | JSONField | AI 추천 스냅샷 (`/classify/`의 `selected`) |
| `ai_alternatives` | JSONField | AI 대안 후보 목록 |
| `ai_search_expansion` | CharField(500) | AI 검색 확장어 |
| `final_hs_code` | CharField(30) | 확정 HS코드(순번) |
| `final_category` | CharField(500) | 확정 통관 카테고리(품명) |
| `final_full_path` | TextField | 확정 분류 경로 |
| `status` | CharField(12) | `pending`/`confirmed` |
| `decision_source` | CharField(15) | `ai_confirmed`/`alternative`/`manual` |
| `inspector` | CharField(100) | 검수 담당자 |
| `inspector_note` | TextField | 검수 피드백/메모 |
| `created_at` | DateTimeField | 생성 시각 |
| `confirmed_at` | DateTimeField | 확정 시각 |
| `updated_at` | DateTimeField | 수정 시각 |

---

## 검색 정확도 개선 (오분류 방지)

고객이 입력한 상품 제목에서 HS코드를 뽑을 때 오류를 줄이기 위해:

1. **분류 경로(full_path) 컨텍스트** — 후보를 Claude에 넘길 때 `대분류 > ... > 품목`
   경로를 함께 제공. 기존의 rowid 역추적(취약·부정확) 방식을 DB의 `full_path`
   컬럼으로 대체해 같은 실물 품목을 정확히 고르게 한다.
2. **LIKE 폴백 강화** — 후보가 부족하면(`< limit/2`) 2글자 이상 키워드까지
   부분 문자열 매칭을 더 적극적으로 수행.
3. **한글 bigram 폴백** — 키워드 추출이 모두 빗나가 후보가 3건 미만일 때,
   긴 키워드를 2글자 조각으로 쪼개 매칭 → 완전 무후보 상황 감소.

---

## 환경 변수

| 변수명 | 기본값 | 설명 |
|--------|--------|------|
| `ANTHROPIC_API_KEY` | — | Claude API 키 (필수) |
| `OPENAI_API_KEY` | — | OpenAI 임베딩 키 (선택, 없으면 FTS 검색) |
| `TARIFF_CACHE_TTL_HOURS` | `24` | 조회 결과 캐시 유효 시간 (시간) |
| `TARIFF_EXPAND_MODEL` | `claude-sonnet-4-6` | 검색어 확장 모델 |
| `TARIFF_ANTHROPIC_MODEL` | `claude-haiku-4-5-20251001` | 항목 선택 모델 |
| `TARIFF_EMBED_MODEL` | `text-embedding-3-small` | OpenAI 임베딩 모델 |
