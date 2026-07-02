# -*- coding: utf-8 -*-
"""
build_ia.py — 이 프로젝트의 IA(정보구조) 그래프를 author 하는 스크립트.

==============================================================================
 사용 흐름 (다른 프로젝트에 복붙한 Claude가 할 일)
==============================================================================
 1) 이 폴더의 ia_engine.py / build_docs.py 는 그대로 둔다(범용).
 2) 프로젝트 자료(요구사항·화면·API 문서·Figma·프로토타입 등)를 읽고,
    아래 예시를 '그 프로젝트 내용'으로 전부 교체한다.
 3) 실행:  python build_ia.py   → <project_id>_ia.json 생성 (무결성 체크 출력)
 4) 실행:  python build_docs.py → <project_id>_ia_docs.html 생성 (브라우저로 열기)

 화면에 표시되는 모든 한글 라벨/예시/타입은 여기(F(...) 스펙)에 적어야 한다.
 렌더러(build_docs.py)는 도메인 지식이 없다 — IA에 없는 정보는 화면에 안 나온다.
==============================================================================

 ↓↓↓ 아래는 동작 확인용 '최소 예시'(작은 배달 주문 앱). 통째로 교체하세요. ↓↓↓
"""
from ia_engine import IA, F, R

ia = IA("demo", "데모 배달앱", "예시용 최소 IA — 실제 프로젝트로 교체하세요")

# --- 컨텍스트(설계 근거) ----------------------------------------------------
ia.context("ctx.prd", "요구사항 정의서", "PRD", "기능요구사항 출처")

# --- UI 표면 (device='phone' → 미리보기 폰 프레임 / 'desktop' → 데스크톱) ----
ia.surface("surface.app", "고객 앱", "주문 고객용 모바일", device="phone")
ia.surface("surface.admin", "관리자", "운영 관리 콘솔", device="desktop")

# --- 액터 -------------------------------------------------------------------
ia.actor("actor.guest", "게스트", role="guest", desc="비로그인", operates="surface.app")
ia.actor("actor.user", "고객", role="user", desc="로그인 사용자", operates="surface.app")
ia.actor("actor.admin", "관리자", role="admin", desc="운영자", operates="surface.admin")

# --- 데이터 모델 (필드마다 타입/필수/예시/enum/가이드를 명시) ----------------
ia.data_model("dm.user", "User", "회원", fields=[
    F("user_id", "string", req=True, ex="usr_1001", note="unique"),
    F("name", "string", req=True, ex="홍길동"),
    F("email", "email", ex="hong@example.com"),
])
ia.data_model("dm.order", "Order", "주문", belongs_to=["dm.user"], fields=[
    F("order_number", "string", req=True, ex="ORD-20260101-0001", note="unique",
      guide=("주문 번호", "생성 시 자동 발번")),
    F("user_id", "string", req=True, ex="usr_1001", note="FK"),
    F("item", "string", req=True, ex="후라이드 치킨"),
    F("quantity", "number", req=True, ex=2),
    F("total_price", "number", req=True, ex=18000),
    F("status", "enum", req=True,
      enum={"pending": "접수", "cooking": "조리중", "delivering": "배달중", "done": "완료", "canceled": "취소"},
      ex="cooking", guide=("주문 진행 상태", "PATCH /status/ 로 갱신, 화면엔 한글 배지로 표시")),
    F("admin_memo", "string", ex="VIP 고객 — 포장 주의", note="관리자 전용"),
    F("created_at", "datetime", ex="2026-01-01 12:30"),
])

# --- API (reads/writes 로 데이터 모델과 연결) -------------------------------
ia.api("api.login", "POST", "/api/login/", app="auth", actors=["guest"],
       summary="로그인", writes=["dm.user"])
ia.api("api.list_orders", "GET", "/api/orders/", app="orders", actors=["user", "admin"],
       summary="주문 목록", reads=["dm.order"])
ia.api("api.create_order", "POST", "/api/orders/", app="orders", actors=["user"],
       summary="주문 생성", writes=["dm.order"])
ia.api("api.update_status", "PATCH", "/api/orders/{order_number}/status/", app="orders",
       actors=["admin"], summary="상태 변경", writes=["dm.order"])

# --- 화면 (surface/actor/calls/transitions/requirements) --------------------
ia.screen("screen.login", "S-1", "로그인", "surface.app", "actor.guest", "로그인",
          requirements=["FR-AUTH-01"], apis=["api.login"], transitions=["screen.list"], context="ctx.prd")
ia.screen("screen.list", "S-2", "주문 목록", "surface.app", "actor.user", "내 주문 목록",
          requirements=["FR-ORD-01"], apis=["api.list_orders"], transitions=["screen.new"], context="ctx.prd",
          access=[
              R("hide", ["actor.guest"], ["self"]),                 # 게스트는 화면 접근 불가
              R("hide", ["actor.user"], ["dm.order.admin_memo"]),   # 고객에겐 관리자 메모 숨김
              R("mask", ["actor.user"], ["dm.order.user_id"]),      # 내부 식별자 마스킹
              R("disable", ["actor.guest"], ["comp.order_card"]),   # (예시) 컴포넌트 비활성
          ])
ia.screen("screen.new", "S-3", "주문하기", "surface.app", "actor.user", "메뉴 담아 주문",
          requirements=["FR-ORD-02"], apis=["api.create_order"], transitions=["screen.list"], context="ctx.prd")
ia.screen("screen.adm_orders", "A-1", "주문 관리", "surface.admin", "actor.admin", "주문 상태 관리",
          requirements=["FR-ADM-01"], apis=["api.list_orders", "api.update_status"], context="ctx.prd",
          access=[R("hide", ["actor.guest", "actor.user"], ["self"])])  # 관리자만

# --- 컴포넌트(재사용 UI; impacts 로 다른 화면 연결) -------------------------
ia.component("comp.order_card", "주문 카드", "screen.list", impacts=["screen.adm_orders"],
             payload={"kind": "display", "reusable": True})

# --- 상태 머신 --------------------------------------------------------------
ia.state_machine("sm.order", "주문 상태", "접수→조리중→배달중→완료(분기 취소)",
    states=[("st.pending", "접수"), ("st.cooking", "조리중"), ("st.delivering", "배달중"),
            ("st.done", "완료"), ("st.canceled", "취소")],
    transitions=[("st.pending", "st.cooking"), ("st.cooking", "st.delivering"),
                 ("st.delivering", "st.done"), ("st.pending", "st.canceled", {"trigger": "고객 취소"})],
    owner="dm.order")

# --- 비즈니스 규칙 / 검증 / 권한 --------------------------------------------
ia.business_rule("rule.cancel_window", "취소 가능 시점", "조리중 이후엔 취소 불가", priority="🔴",
                 derived_from=["ctx.prd"], governs=["api.update_status", "dm.order", "st.cooking"])
ia.validation("val.qty_min", "수량 최소", "quantity >= 1", "수량은 1개 이상", "QTY_MIN",
              targets=["dm.order", "api.create_order"])
# 권한은 별도 node 가 아니라: (1) API 호출 권한 = api(actors=[...]),
#                              (2) UI 노출/비활성 = screen(access=[R(...)]) 으로 표현.

# --- 경로 파라미터 한글 라벨(선택) ------------------------------------------
ia.param_labels.update({"order_number": "주문번호", "user_id": "사용자 ID"})

ia.finalize(__file__)
