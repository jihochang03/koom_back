이재운

1. 앞으로의 확장성을 고려한, db system과 탐색 알고리즘 설계.

ai agent를 만드는 sdk는 이미 너무 추상화가 잘 되어 있어서 새로만드는게 의미가 없음. 조금만 커스텀하거나 wrapper씌워서 권한 level system만 만들면 될 것 같음. (이 ai agent가 할 수 있는 tools, 읽을 수 있는 db를 미리 다 넣어주기보다는 level로 간편하게 관리. 특히 db level권한은 기존 코드로 구현 불가능)

그래서 db system과, 무결성을 위한 탐색 알고리즘 설계가 더 중요한 부분.

앞으로 수많은 다양한 데이터와 관계를 표현하기 위해서는 json을 저장하는 형식이 좋을듯함. 그리고 요즘 https://aisparkup.com/posts/8192
https://arxiv.org/abs/2605.15184
이런 글이 나오는 걸 보면 LLM모델들이 filesystem과 같은 환경에서 매우 강력한 것을 알 수 있음.
https://aisparkup.com/posts/8653
물론 명확한 스키마다 있는 환경에서 “수정”과 같은 작업을 할 땐 sql이 더욱 강력함.

그래서 나온 결론은 json 탐색에 특화된 db system을 사용하면서, filesystem과 같은 tree구조와, path column를 심어주면 매우 좋지 않을까 하는 생각…

https://duckdb.org/
duckdb라는 것을 찾았는데, 얘는 native grep이 매우 빠른 이유인 SIMD를 db에서 지원하고 오히려 json을 그냥 varchar로 저장해서 grep용으로는 더 빠름.

```markdown
1. 데이터 모델 – JSON base + 그래프 ✅

- 원본(source of truth) = JSON 문서. 관계형(타입 너무 많음) ×, 생짜 JSON(난장판) ×
- 난장판 방지 = 타입별 스키마 검증, 단 증분식. 문서가 "나 회의록이야" 선언 → 그 타입 스키마로만 검증. 새 타입은 그때 등록, 마이그레이션 없음.
- 관계 = 1급 엣지(그래프). parent/child + cross-edge(transitions·calls 등). 엣지는 문서 안 FK가 아니라 별도.
- 그래프→트리 핵심 통찰: 관계 하나(containment)를 백본으로 정하면 그 방향은 트리 = 디렉터리 depth. → materialized path(ltree류)로 표현.
  나머지 관계는 전부 노드 안의 링크.

2. 검색 – grep-first, 에스컬레이션 ✅

1차 crank.grep ← 텍스트/구조 검색 (custom rg over JSON)
2차 crank.search ← 의미/벡터 (1차가 단어 못 맞출 때만 fallback)(이건 보류)
3차 crank.traverse ← 그래프 (관계·"왜"·역방향)

- "custom rg" = 텍스트 스캔 ×.
  - DuckDB over JSON/Parquet 파일 – read_json('glob/\*\*') + regexp_matches/구조술어, 벡터화·병렬 SIMD 스캔, glob=디렉터리 스코프. 너무 규모(MB~low GB, 쿼리 빈도 낮음)엔 brute-force 스캔이 이김 (인덱스 유지 0, 항상 최신). → 유력

3. 구조 가독성 – "한눈에 보임"을 의도적으로 재현 ✅

raw 그래프는 filesystem의 glance-able 지도를 자동으로 안 줌. 그래서 강제로:

- 백본 관계 1개 지정 + 의미있는 path/이름(UUID ×) + crank.map() 트리 렌더러(body 안 읽고 백본 + cross-edge 주석)
- → filesystem보다 나음(트리 개요 + cross-edge 쿼리 가능)
- 에이전트 루프: map → grep/read → traverse

4. 수정 전파 완결성 – 차별화 기능 ✅

노드 수정 시 영향 노드를 빠짐없이, 에이전트가 하나씩 무조건 보게 강제.

- impact set = 타입별 전파 규칙(어떤 엣지가 어느 방향·몇 hop) 따라 reachability
- 강제 = dirty 마킹 + 리뷰 원장 + commit gate. 각 노드를 수정 or 이유 달고 기각 둘 중 하나, 전부 resolve 전엔 edit close 불가 (Make/Bazel dirty-propagation 모델)
- 알고리즘 = change-gated BFS 큐 (바뀐 노드만 이웃 펼침). 그래프용 보정 3개:
  a. 종료 = 큐 empty (depth 전부 무작정 ×)
  b. 통과(pass-through) 엣지는 무수정이어도 펼침 (안 그럼 누락)
  c. 위상순서로 상류 먼저, 사이클이면 fixpoint
- 정직한 한계: 구조적 완결성(기록된 엣지 기준) + 리뷰 강제지 의미적 정확성 ×. 엣지 품질이 천장.
```

ai agent oauth 뚫어서 codex처럼 api쓰는건 opencode 코드 가져오면 됨

1. 기획 에이전트란 무엇을 해야하는가?

지금 생각하는건 요구사항 정의서, 유저 인터뷰, 뭐든지의 context를 받아서 디자이너, 백엔드개발자, 프론트개발자가 모두가 Ground Truth라고 생각하는 화면, transition, api, db가 연결된 IA문서를 생성하는게 목표.

여기서 나오는 유저플로우, 요구사항 정의서는 다 IA문서의 투영이라고 볼 수 있음.

!image.png

저니맵은 좀 다른 듯? 저니맵은 요구사항 정의서 더 전단계에서 사업에 대한 설계 + 핵심 기능을 정의하는 느낌이고, 이번에 만들려는 IA는 진짜 서비스 제작을 위한 상세 기획서에 더 가까운 듯.

!image.png

---

IA : 프로덕트의 모든 구조적 정보를 연결한 그래프

기획 에이전트는 **Context를 구조화하여 하나의 IA(Graph)를 생성·관리하는 시스템**

입력으로는 사용자 인터뷰, 회의록, 요구사항 메모, 기존 문서 등 어떤 형태의 Context라도 받을 수 있으며, 이를 분석해 화면(Screen), 전이(Transition), API, 데이터 모델(DB), 권한(Permission), 비즈니스 규칙(Business Rule) 등의 노드와 관계를 가진 하나의 IA를 구축한다.
이 IA가 프로젝트의 Ground **Truth**가 되고 이후 요구사항 정의서, User Flow, Wireframe, API 명세, DB 스키마, 테스트 케이스 등은 각각 IA를 특정 관점에서 **투영(Projection)** 한 결과물.

output : 이해관계자 지도, 전이맵, 유저플로우, 서비스 블루프린트, 플로우차트, 데이터 모델(ERD), API 명세, IA, 와이어프레임

IA 데이터 모델에 들어갈 것들 : Node, Edge

```jsx
Node -
  screen -
  component -
  api -
  db_table / data_model -
  requirement -
  user_flow -
  business_rule -
  permission -
  state -
  validation -
  error_case;
```

| column         | 역할                               |
| -------------- | ---------------------------------- |
| id             | 유일한 식별자                      |
| project_id     | 프로젝트                           |
| type           | 객체 종류                          |
| name           | 사람이 읽는 이름                   |
| path           | 그래프 내 위치                     |
| origin_context | 노드가 어떤 context에서 비롯됐는지 |
| payload        | 객체의 모든 의미                   |
| version        | 변경 추적                          |
| schema_version | payload 검증                       |
| created_at     | 생성                               |
| updated_at     | 수정                               |

```jsx
Edge;
(contains,
  calls,
  reads,
  writes,
  transitions_to,
  requires,
  governed_by,
  derived_from,
  impacts);
```

# Node Types

## 1. Screen

사용자가 인지하는 하나의 화면.

예시

```
Login

Signup

Home

Checkout

Product Detail
```

왜 필요한가?

프로젝트의 대부분은 결국 화면 중심으로 연결된다.

Screen은

- Component를 포함하고
- API를 호출하며
- State를 표현하고
- 다른 Screen으로 이동하며
- Permission을 요구하고
- Business Rule을 따른다.

주요 속성

```
route

purpose

status

platform

owner

actor

permission
```

---

## 2. Component

Screen을 구성하는 최소 UI 단위.

예시

```
Button

SearchBar

Modal

Header

Table
```

왜 필요한가?

Component는 재사용의 단위이다. Component 하나를 수정하면 여러 Screen이 영향을 받을 수 있다.

주요 속성

```
kind

props

design_system

reusable
```

---

## 3. Actor

시스템을 사용하는 주체.

예시

```
Guest

User

Admin

Manager

Driver
```

왜 필요한가?

Permission은 Actor를 기준으로 정의된다.

또한 User Flow 역시 Actor마다 달라질 수 있다.

주요 속성

```
role

description

organization
```

---

## 4. Data Model

시스템이 관리하는 도메인 객체. 중요한 점은 Data Model ≠ Database Table 이다.

예시

```
User

Order

Product

Project

Review
```

DB는 구현체일 뿐이며, Data Model이 Ground Truth이다.

주요 속성

```
fields

relationships

constraints

status
```

---

## 5. API

시스템 간 Contract. Frontend와 Backend가 만나는 경계이다.

예시

```
POST /login

GET /products

PATCH /users
```

주요 속성

```
method

path

request

response

authentication

version

actor 별 permission list
```

---

## 6. Business Rule

비즈니스가 반드시 만족해야 하는 규칙.

예시

```
이메일 인증 후 로그인 가능

재고가 없으면 구매 불가

관리자는 모든 프로젝트 조회 가능
```

왜 필요한가?

Business Rule은

Screen

API

Data Model

모두에 영향을 준다.

주요 속성

```
priority

severity

description

source
```

---

## 7. Validation Rule

입력값 검증 규칙.

Business Rule과는 별개이다.

예시

```
password >= 8

email format

phone regex
```

왜 필요한가?

Validation은

Frontend

Backend

QA

가 동일하게 공유해야 하는 규칙이다.

주요 속성

```
field

condition

message

error_code
```

---

## 8. Permission

누가 무엇을 할 수 있는가.

Permission은

Actor

Action

Resource

세 요소를 연결한다.

예시

```
Admin

↓

Delete User

Guest

↓

Read Product
```

주요 속성

```
role

action

condition

resource
```

---

## 9. Context

모든 설계의 근거(Evidence).

예시

```
Meeting

Slack

User Interview

Notion

PRD

Figma
```

왜 필요한가? 모든 Node는 "왜 존재하는가?"를 설명할 수 있어야 한다. Context는 Agent의 추론 근거를 저장한다.

주요 속성

```
author

source_type

created_at

raw_text

attachments
```

---

# Edge

Node가 객체라면,

Edge는 관계이다.

```
Edge

from

to

relation

metadata
```

예시

```
{
  "from":"screen.login",
  "to":"api.post_login",
  "relation":"calls"
}
```

---

# Edge Ontology

## Structural

구조를 나타낸다.

```
contains

belongs_to
```

예시

```
Screen

contains

Component
```

---

## Navigation

화면 이동.

```
transitions_to
```

예시

```
Login

↓

Home
```

User Flow는

Navigation Edge만 추출한 Projection이다.

---

## Dependency

의존성.

```
calls

reads

writes

updates
```

예시

```
Screen

↓

calls

↓

API

↓

writes

↓

Data Model
```

---

## Constraint

규칙 적용.

```
requires

validated_by

governed_by
```

예시

```
Signup Screen

↓

validated_by

↓

Password Rule
```

---

## Provenance

설계 근거.

```
derived_from

mentioned_in
```

예시

```
Business Rule

↓

derived_from

↓

Meeting Note
```

---

## Impact

변경 영향.

```
impacts

depends_on
```

예시

```
API

↓

impacts

↓

Screen

↓

impacts

↓

Test Case
```

Agent는 이를 이용하여

Change Propagation을 수행한다.

---

# Projection

다음은 Node가 아니다.

```
Requirement

User Flow

API Spec

DB Schema

Wireframe

Test Case
```

이들은 모두

IA를 특정 관점에서 표현한 Projection이다.

예시

```
Screen + transitions_to

↓

User Flow
```

```
API + Data Model

↓

API Spec
```

```
Data Model

↓

DB Schema
```

```
Business Rule + Validation

↓

Requirement
```
