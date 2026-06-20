# Tariff API

상품명으로 일본 관세율표(SQLite DB)를 조회하고, Claude AI로 최적 항목을 선택하는 앱.  
조회 결과는 24시간 캐시하여 Claude API 중복 호출을 방지한다.

Base URL: `/api/tariff/`

---

## 엔드포인트 목록

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/tariff/lookup/` | 관세율 조회 |
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
| `순번` | integer\|null | 관세율표 순번 |
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
