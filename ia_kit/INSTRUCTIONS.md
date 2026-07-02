# IA Kit — 프로젝트 IA + 자동 문서 생성기

이 폴더를 프로젝트 루트(또는 아무 폴더)에 복붙하고, Claude에게
**"이 폴더의 INSTRUCTIONS.md 대로, 첨부한 자료로 IA를 만들어줘"** 라고 시키면 됩니다.

## 무엇을 만드나
- **IA 그래프**(`<id>_ia.json`) = Node/Edge로 표현한 프로덕트의 단일 진실원천
- **문서 앱**(`<id>_ia_docs.html`) = 그 그래프의 투영. 탭으로 전환:
  - **화면 미리보기**(클릭 가능한 와이어프레임 · 디자이너/개발자 모드 · **역할 선택 시 접근제어 적용**)
  - **IA 그래프(편집)** · **요구사항정의서** · **ERD** · **화면명세서**
- 화면에 보이는 **모든 한글 라벨·예시 데이터·필드 타입**은 IA(JSON)에 저장됩니다.
  렌더러는 도메인 지식이 없어서, **IA에 없는 정보는 화면에 나오지 않습니다.**

## 폴더 구성
| 파일 | 역할 | 수정? |
|------|------|------|
| `ia_engine.py` | IA author 헬퍼(엔진) | ❌ 그대로 |
| `build_docs.py` | 범용 렌더러(JSON→HTML) | ❌ 그대로 |
| `build_ia.py` | **이 프로젝트의 IA 정의** | ✅ 여기를 채운다 |
| `INSTRUCTIONS.md` | 이 문서 | — |

## Claude가 할 일 (워크플로우)
1. 프로젝트 자료(요구사항/화면 목록/API 문서/DB 스키마/Figma/프로토타입 등)를 읽고 구조를 파악한다.
2. `build_ia.py` 안의 예시(데모 배달앱)를 **이 프로젝트 내용으로 전부 교체**한다.
   - 화면, API, 데이터 모델(필드·타입·예시·enum), 액터, 규칙, 검증, 권한, 상태, 컨텍스트를 `ia_engine` API로 선언.
3. `python build_ia.py` 실행 → `<id>_ia.json` 생성. **무결성 경고(WARNING)가 없도록** 채운다.
4. `python build_docs.py` 실행 → `<id>_ia_docs.html` 생성. 브라우저로 열어 확인.

> 요구사항: Python 3. (Node 있으면 `node --check`로 산출 HTML의 JS 검증 가능 — 선택)

## IA 스키마 요약 (ia_engine API)
```python
from ia_engine import IA, F, R
ia = IA("projid", "프로젝트명", "한 줄 설명")

ia.context("ctx.prd","요구사항정의서","PRD","근거")          # 설계 근거
ia.surface("surface.app","고객 앱","설명", device="phone")    # device: phone|desktop
ia.actor("actor.user","고객", role="user", desc="...", operates="surface.app")

ia.data_model("dm.order","Order","주문", belongs_to=["dm.user"], fields=[
    F("order_number","string", req=True, ex="ORD-0001", note="unique"),
    F("status","enum", req=True,
      enum={"pending":"접수","done":"완료"}, ex="pending",      # enum: 코드→한글, ex는 코드
      guide=("무엇인지","어떻게 대입하는지")),                  # 선택
    F("items","array/json", ex=[{"name":"치킨","qty":1}]),     # 리스트/딕트 그대로
])
ia.api("api.create","POST","/api/orders/", app="orders", actors=["user"],   # actors = 호출 권한
       summary="주문 생성", reads=["dm.x"], writes=["dm.order"])
ia.screen("screen.s1","S-1","주문하기","surface.app","actor.user","목적",
          requirements=["FR-ORD-01"], apis=["api.create"],
          transitions=["screen.s2"], context="ctx.prd",
          access=[                                               # ← UI 접근 제어(역할별)
              R("hide",    ["actor.guest"], ["self"]),           # 게스트는 화면 자체 비노출
              R("hide",    ["actor.user"],  ["dm.order.admin_memo"]),  # 특정 필드 숨김
              R("mask",    ["actor.user"],  ["dm.order.user_id"]),     # 값 마스킹(••••)
              R("disable", ["actor.user"],  ["comp.card"]),      # 컴포넌트 비활성
              R("readonly",["actor.user"],  ["dm.order.status"]),# 읽기 전용
          ])
ia.component("comp.card","주문 카드","screen.s1", impacts=["screen.s2"],
             payload={"kind":"display","reusable":True})        # kind: display|form|navigation|control|panel
ia.state_machine("sm.order","주문 상태","설명",
    states=[("st.pending","접수"),("st.done","완료")],
    transitions=[("st.pending","st.done",{"trigger":"…"})], owner="dm.order")
ia.business_rule("rule.x","이름","설명", priority="🔴",
                 derived_from=["ctx.prd"], governs=["api.create","dm.order","st.pending"])
ia.validation("val.x","이름","조건식","메시지","CODE", targets=["dm.order","api.create"])
ia.param_labels.update({"order_number":"주문번호"})              # 경로 파라미터 한글
ia.finalize(__file__)
```

### 권한/접근 제어 — node 로 두지 않는다
`actor` 는 node(흐름·화면 주체로 필수). 하지만 **`permission` node 는 두지 않는다.** 대신:
- **API 호출 권한** → `api(actors=[...])` 의 허용 역할 목록.
- **UI 노출/비활성** → `screen(access=[R(effect, roles, targets)])`.
  - effect: `hide`(숨김) · `disable`(비활성) · `readonly`(읽기전용) · `mask`(값 마스킹)
  - targets: `'self'`(화면 전체) · `'comp.x'`(컴포넌트) · `'dm.x.field'`(필드) · `'dm.x'`(모델 전체)

화면 미리보기 상단의 **역할 선택**으로 즉시 적용된다(숨김 필드 사라짐 / 컴포넌트 회색 / 값 ••• / 화면 차단). 이렇게 하면 "이 화면에서 이 역할은 무엇을 못 보고 무엇이 비활성인지"가 IA 한 곳에 표현되고, permission 노드 폭발 없이 필드 단위까지 제어된다.

### 필드 타입 (`F(type=...)`)
`string · number · enum · datetime · date · boolean · url · email · array/json`

### 노드 타입 / 엣지 관계 (참고)
- 노드: `screen component actor data_model api business_rule validation context state_machine state surface project` (※ permission 노드 없음 — 위 접근제어로 대체)
- 엣지: `contains(백본) transitions_to calls reads writes belongs_to validated_by governed_by derived_from mentioned_in impacts depends_on operates`
- 접근 제어는 엣지가 아니라 `screen.payload.access`(역할별 hide/disable/readonly/mask) + `api.actor_permissions` 로 표현

## 작성 원칙 (중요)
- **예시값(ex)·enum 라벨·타입을 필드마다 반드시 적는다.** 이것이 화면 미리보기·개발자 모드 JSON·ERD에 그대로 쓰인다.
- **하나의 일관된 시나리오**로 예시를 채운다(예: 특정 고객의 한 주문이 화면마다 자연스럽게 이어지도록). enum `ex`는 그 시나리오에 맞는 코드를 고른다(첫 코드가 기본).
- `device="phone"` 표면은 폰 프레임 + 하단 탭, `desktop`은 사이드바 프레임으로 렌더된다.
- `transitions`/`apis`/`governs` 등은 아직 정의 안 된 id를 가리켜도 되지만, 최종적으로 모든 노드를 정의해 **dangling 경고를 0으로** 만든다.
- `build_docs.py`·`ia_engine.py`에 **프로젝트(도메인) 지식을 넣지 말 것**(범용 유지).
  - **예외**: 데모 잔재나 범용 버그 수정은 허용된다 — 특정 프로젝트 값을 박는 게 아니라 *모든* 프로젝트에서 더 잘 동작하게 만드는 수정이면 OK(예: 미리보기 첫 화면을 특정 ID로 고정하지 말고 `DOC.nodes` 의 첫 screen 으로 동적 선택, 파일명을 `DOC.project.id` 기반으로). 이런 수정을 했으면 한 줄로 알려줘서 키트 원본에도 반영되게 할 것.

## 결과 보기
`<id>_ia_docs.html`를 브라우저로 더블클릭. IA 그래프 탭에서 노드를 편집하면 모든 문서 탭이 즉시 다시 그려진다.
