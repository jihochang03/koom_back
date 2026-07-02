# -*- coding: utf-8 -*-
"""
KOOM IA Graph generator.

Produces koom_ia.json: an Information Architecture graph (Nodes + Edges)
following the schema described in ia_example.md.

Sources of truth synthesized into this graph:
  - Figma blueprint "주문/배송 과정" (order/shipping service blueprint)
  - "DK 어드민 프로토타입.html" (admin prototype: 9 pages + 3 roles)
  - backend/docs/*_api.md (24 API docs: endpoints, models, enums, rules)
  - docs/화면명세서.md, docs/IA_정보구조.md, docs/요구사항추적표.md
"""
import json, os

TODAY = "2026-06-29T00:00:00+09:00"
PROJECT = "koom"

NODES = []
EDGES = []
_seen = set()

def node(nid, ntype, name, path, origin, payload=None, schema_version=1):
    assert nid not in _seen, f"dup node {nid}"
    _seen.add(nid)
    NODES.append({
        "id": nid,
        "project_id": PROJECT,
        "type": ntype,
        "name": name,
        "path": path,
        "origin_context": origin,
        "payload": payload or {},
        "version": 1,
        "schema_version": schema_version,
        "created_at": TODAY,
        "updated_at": TODAY,
    })

def edge(frm, to, rel, meta=None):
    e = {"from": frm, "to": to, "relation": rel}
    if meta:
        e["metadata"] = meta
    EDGES.append(e)

# ---------------------------------------------------------------------------
# 0. Project root + organizational surfaces (containment backbone)
# ---------------------------------------------------------------------------
node("project.koom", "project", "KOOM 구매대행 플랫폼", "koom",
     "backend_docs",
     {"summary": "일본 고객이 한국 쇼핑몰 상품을 대행 구매·국제배송 받는 크로스보더 커머스. "
                 "고객 앱(LINE) + CS 콘솔 + 본사 어드민 + 백그라운드 시스템.",
      "platforms": ["LINE WebApp(고객)", "Admin Web(CS/본사)", "WMS Mobile(입고/검수)"],
      "backbone_relation": "contains"})

SURFACES = [
    ("surface.customer_app", "고객 앱 (S)",   "koom/customer-app", "LINE 로그인 기반 고객용 모바일 웹앱"),
    ("surface.cs_console",   "CS 콘솔 (C)",   "koom/cs-console",   "대리구매·검수·물류·CS 현장 실행 콘솔"),
    ("surface.hq_admin",     "본사 어드민 (H)", "koom/hq-admin",    "정산·정책·콘텐츠·모니터링 관리 콘솔"),
    ("surface.public",       "공개 (P)",      "koom/public",       "비인증 공개 페이지(세관 스냅샷 등)"),
    ("surface.system",       "시스템 (SYS)",  "koom/system",       "화면 없는 백그라운드 처리"),
    ("surface.data",         "데이터 모델",    "koom/data",         "도메인 객체(Ground Truth) — DB는 구현체"),
    ("surface.api",          "API",          "koom/api",          "프론트·백엔드 계약(엔드포인트)"),
    ("surface.actors",       "액터",          "koom/actors",       "시스템을 사용하는 주체"),
    ("surface.rules",        "비즈니스 규칙",  "koom/rules",        "반드시 만족해야 하는 정책"),
    ("surface.validations",  "검증 규칙",      "koom/validations",  "입력값 검증"),
    ("surface.permissions",  "권한",          "koom/permissions",  "Actor×Action×Resource"),
    ("surface.contexts",     "컨텍스트",       "koom/contexts",     "설계 근거(Evidence)"),
    ("surface.states",       "상태 머신",      "koom/states",       "상태/전이 모음"),
]
for sid, name, path, desc in SURFACES:
    node(sid, "surface", name, path, "ia_doc", {"description": desc})
    edge("project.koom", sid, "contains")

# ---------------------------------------------------------------------------
# 1. Actors
# ---------------------------------------------------------------------------
ACTORS = [
    ("actor.guest",     "Guest(비인증)",   "고객(미로그인)", "JWT 없음·만료. 공개 페이지만 접근.", "surface.customer_app"),
    ("actor.customer",  "고객(회원)",      "고객", "LINE 로그인 회원. 등급(웰컴/첫구매10%/재구매5%/VIP15%)·포인트·쿠폰 보유.", "surface.customer_app"),
    ("actor.cs",        "CS 운영자",       "operator", "대리구매·검수·HS분류·FastBox 인계·CS 응대. 본인 담당 건만(데이터 격리).", "surface.cs_console"),
    ("actor.wms",       "입고/WMS 담당",   "operator", "물류센터 입고 스캔·검수(모바일 화면). 프로토타입 'wms' 롤.", "surface.cs_console"),
    ("actor.hq",        "본사 관리자",     "admin", "통계·정책·정산·환불 실행·콘텐츠. 전 화면 접근.", "surface.hq_admin"),
    ("actor.system",    "시스템",          "system", "환율 캐싱·가격계산·관세조회·배송추적·알림 등 백그라운드.", "surface.system"),
    ("actor.gmo",       "GMO-PG (외부)",   "external", "카드·PayPay 결제 게이트웨이. Auth/Capture/Cancel/Return.", "surface.system"),
    ("actor.dhub",      "DHUB/FastBox (외부)", "external", "한국→일본 국제배송 중개. 송장 채번·배송지시·추적.", "surface.system"),
    ("actor.seller",    "판매처 (외부)",   "external", "한국 쇼핑몰/판매자. 품절·가격변동·반품 승인 주체.", "surface.system"),
]
for aid, name, role, desc, surface in ACTORS:
    node(aid, "actor", name, f"koom/actors/{aid.split('.')[1]}", "prototype" if aid in ("actor.cs","actor.wms","actor.hq") else "backend_docs",
         {"role": role, "description": desc})
    edge("surface.actors", aid, "contains")

# actor → operates → surface
for aid, surf in [("actor.guest","surface.public"),("actor.customer","surface.customer_app"),
                  ("actor.cs","surface.cs_console"),("actor.wms","surface.cs_console"),
                  ("actor.hq","surface.hq_admin"),("actor.system","surface.system")]:
    edge(aid, surf, "operates")

# ---------------------------------------------------------------------------
# 2. APIs  (id, method, path, app, actors, summary)
# ---------------------------------------------------------------------------
APIS = [
    # auth / scraping / products
    ("api.auth_line_login",  "GET",  "/api/auth/line/login/",                 "auth_social", ["guest"], "LINE OAuth 로그인 시작"),
    ("api.auth_verify",      "POST", "/api/auth/verify/",                     "auth_social", ["customer","system"], "JWT 검증→customer_id"),
    ("api.scraping_analyze", "POST", "/api/scraping/analyze/",                "scraping",    ["customer"], "URL 분석 요청(scraper-agent 위임)"),
    ("api.products_list",    "GET",  "/api/products/",                        "products",    ["guest","customer"], "상품 목록(필터·페이지네이션)"),
    ("api.products_page",    "GET",  "/api/products/{id}/page/",              "products",    ["guest","customer"], "상품상세 통합(상품+가격+배송+결제수단)"),
    ("api.products_batch",   "POST", "/api/products/batch/",                  "products",    ["system"], "상품 일괄 저장(url upsert)"),
    ("api.products_detail",  "POST", "/api/products/{id}/detail/",            "products",    ["system"], "상세 비동기 크롤 결과 저장(webhook)"),
    ("api.products_badges",  "PATCH","/api/products/{id}/badges/",            "products",    ["hq"], "뱃지(is_limited) 토글"),
    ("api.products_inbound", "PATCH","/api/products/{id}/inbound/",           "products",    ["hq"], "입고 추적 정보 갱신"),
    ("api.malls_list",       "GET",  "/api/malls/",                           "malls",       ["guest","customer"], "활성 쇼핑몰 목록"),
    ("api.featured_cats",    "GET",  "/api/malls/featured-categories/",       "malls",       ["guest","customer"], "메인 추천 카테고리"),
    # cart / checkout
    ("api.cart_items",       "POST", "/api/cart/{cid}/items/",                "cart",        ["customer"], "장바구니 항목 추가/수정/삭제"),
    ("api.cart_page",        "GET",  "/api/cart/{cid}/page/",                 "cart",        ["customer"], "장바구니 화면(JPY 환산·포인트·배송)"),
    ("api.cart_checkout",    "GET",  "/api/cart/{cid}/checkout/",             "cart",        ["customer"], "결제 통합 조회(주소·쿠폰·포인트·정책)"),
    # payment
    ("api.pay_entry",        "POST", "/api/payment/entry/",                   "payment",     ["customer"], "거래 등록(AccessID/Pass)"),
    ("api.pay_execute",      "POST", "/api/payment/execute/",                 "payment",     ["customer"], "결제 실행(카드 토큰)"),
    ("api.paypay_entry",     "POST", "/api/payment/paypay/entry/",            "payment",     ["customer"], "PayPay 거래 등록→QR"),
    ("api.pay_capture",      "POST", "/api/payment/capture/",                 "payment",     ["hq"], "매출 확정(AUTH→SALES)"),
    ("api.pay_refund",       "POST", "/api/payment/refund/",                  "payment",     ["hq"], "결제 환불(부분/전액)"),
    # orders
    ("api.orders_create",    "POST", "/api/orders/groups/create/",            "orders",      ["customer"], "주문 그룹 생성(장바구니→주문)"),
    ("api.orders_group",     "GET",  "/api/orders/groups/{group_number}/",    "orders",      ["customer","cs","hq"], "그룹 상세"),
    ("api.orders_detail",    "GET",  "/api/orders/{order_number}/",           "orders",      ["customer","cs","hq"], "주문 상세(+cancel_eligibility)"),
    ("api.orders_status",    "PATCH","/api/orders/{order_number}/status/",    "orders",      ["cs","hq","system"], "상태 업데이트"),
    ("api.orders_statuslog", "GET",  "/api/orders/{order_number}/status-log/","orders",      ["customer","cs","hq"], "13단계 진행 이력"),
    ("api.orders_actionlog", "GET",  "/api/orders/{order_number}/action-log/","orders",      ["hq"], "어드민 액션 감사 로그"),
    ("api.orders_error",     "PUT",  "/api/orders/{order_number}/error/",     "orders",      ["cs","system"], "오차 정보 upsert"),
    ("api.orders_snapshot",  "PUT",  "/api/orders/{order_number}/snapshot/",  "orders",      ["hq"], "세관 스냅샷·영문명 편집"),
    ("api.orders_snap_pub",  "GET",  "/api/orders/snapshots/{uuid}/",         "orders",      ["guest"], "세관 스냅샷 공개 조회(비인증)"),
    ("api.orders_admin_dash","GET",  "/api/orders/admin/dashboard/",          "admin",       ["hq"], "운영 대시보드 집계"),
    # cs
    ("api.cs_inquiries",     "POST", "/api/cs/inquiries/",                    "cs",          ["customer"], "1:1 문의 등록(9유형)"),
    ("api.cs_inquiry_reply", "PATCH","/api/cs/inquiries/{id}/",               "cs",          ["cs"], "문의 답변·상태"),
    ("api.cs_cancel",        "POST", "/api/cs/cancel/",                       "cs",          ["customer"], "취소 요청(1주문1요청)"),
    ("api.cs_refund",        "POST", "/api/cs/refund/",                       "cs",          ["customer"], "환불 요청"),
    ("api.cs_refund_patch",  "PATCH","/api/cs/refund/{id}/",                  "cs",          ["cs"], "환불 1차 승인(CS)"),
    ("api.cs_refund_exec",   "POST", "/api/cs/refund/{id}/execute/",          "cs",          ["hq"], "환불 승인-실행(본사·GMO)"),
    ("api.cs_purchase_tasks","GET",  "/api/cs/purchase-tasks/",               "cs",          ["cs"], "대리구매 작업 목록"),
    ("api.cs_purchase_done", "POST", "/api/cs/purchase-tasks/{order}/complete/","cs",        ["cs"], "대리구매 완료·실구매내역 입력"),
    # logistics
    ("api.log_inspection",   "POST", "/api/logistics/{order}/inspection/",    "logistics",   ["cs","wms"], "검수 등록(pass/issue·사진)"),
    ("api.log_dhub_register","POST", "/api/logistics/{order}/dhub/register/", "logistics",   ["cs"], "DHUB 주문 등록→FB 송장 채번"),
    ("api.log_dhub_instruct","POST", "/api/logistics/dhub/instruct/",         "logistics",   ["cs"], "배송지시 일괄(≤200)"),
    ("api.log_tracking_sync","POST", "/api/logistics/{order}/tracking/sync/", "logistics",   ["system"], "DHUB 배송추적 동기화"),
    ("api.log_timeline",     "GET",  "/api/logistics/{order}/timeline/",      "logistics",   ["customer"], "배송 추적 타임라인(4단계+이벤트)"),
    ("api.log_timeline_post","POST", "/api/logistics/{order}/timeline/",      "logistics",   ["system"], "추적 이벤트 적재·단계 자동분류"),
    ("api.log_stagnated",    "GET",  "/api/logistics/stagnated/",             "logistics",   ["cs","hq"], "지연 감지 배송 목록(24/48h)"),
    ("api.log_customs",      "POST", "/api/logistics/{order}/customs/",       "logistics",   ["cs"], "통관 결과 등록(거절시 응답기한)"),
    ("api.log_customs_refund","POST","/api/logistics/{order}/customs/refund/","logistics",   ["cs"], "통관 불가 부분환불(수동)"),
    # tariff / pricing / shipping
    ("api.tariff_lookup",    "POST", "/api/tariff/lookup/",                   "tariff",      ["system"], "관세율 조회(견적용)"),
    ("api.tariff_classify",  "POST", "/api/tariff/classify/",                 "tariff",      ["cs"], "HS코드 분류+선정사유+대안"),
    ("api.tariff_classification","POST","/api/tariff/products/{id}/classification/","tariff",["cs"], "검수자 HS코드 확정"),
    ("api.pricing_quote",    "POST", "/api/pricing/quote/",                   "pricing",     ["customer","system"], "구매대행 견적 계산"),
    ("api.pricing_fx",       "GET",  "/api/pricing/exchange-rate/",           "pricing",     ["system"], "실시간 환율(캐시)"),
    ("api.shipping_quote",   "POST", "/api/shipping/quote/",                  "shipping",    ["system"], "국제 배송비 견적"),
    # mypage / content / notify / stats / ops / prohibited / sites
    ("api.mypage_addresses", "POST", "/api/mypage/{cid}/addresses/",          "mypage",      ["customer"], "배송지 CRUD"),
    ("api.mypage_points",    "GET",  "/api/mypage/{cid}/points/",             "mypage",      ["customer"], "포인트 잔액·내역"),
    ("api.mypage_coupons",   "GET",  "/api/mypage/{cid}/coupons/",            "mypage",      ["customer"], "보유 쿠폰"),
    ("api.coupon_issue",     "POST", "/api/mypage/coupons/{id}/issue/",       "mypage",      ["hq"], "쿠폰 고객 발급"),
    ("api.content_banners",  "GET",  "/api/content/banners/",                 "content",     ["guest","customer"], "활성 이벤트 배너"),
    ("api.notify_send",      "POST", "/api/notify/send/",                     "notify",      ["system"], "단계별 알림 발송(LINE/Email/SMS)"),
    ("api.stats_monitoring", "GET",  "/api/stats/monitoring/overview/",       "stats",       ["hq","cs"], "실시간 운영 모니터링(scope all/mine)"),
    ("api.ops_error_criteria","PATCH","/api/operations/error-criteria/",      "operations",  ["hq"], "가격 오차 기준 수정(+이력)"),
    ("api.prohibited_check", "POST", "/api/prohibited/check/",                "prohibited",  ["guest","system"], "금지품목 키워드 매칭"),
    ("api.templates_build",  "POST", "/api/templates/build/",                 "scrape_template",["hq"], "AI 스크래퍼 템플릿 빌드→DB 저장"),
]
api_ids = set()
# group APIs into per-app subcontainers under surface.api for a tidy tree
api_apps = {}
for aid, method, path, app, actors, summary in APIS:
    api_apps.setdefault(app, [])
    api_apps[app].append(aid)
for app, ids in api_apps.items():
    cid = f"surface.api.{app}"
    node(cid, "surface", f"/api/{app}", f"koom/api/{app}", "backend_docs", {"app": app})
    edge("surface.api", cid, "contains")
for aid, method, path, app, actors, summary in APIS:
    api_ids.add(aid)
    node(aid, "api", f"{method} {path}", f"koom/api/{app}/{aid.split('.')[1]}", "backend_docs",
         {"method": method, "path": path, "app": app, "summary": summary,
          "actor_permissions": actors})
    edge(f"surface.api.{app}", aid, "contains")

# ---------------------------------------------------------------------------
# 3. Data models  (id, name, key fields, key enums, origin)
# ---------------------------------------------------------------------------
DATA = [
    ("dm.product", "Product", "상품(목록 크롤 결과·상세·입고)",
     ["url(upsert key)","title","price_original","price_discounted","images","brand","category",
      "is_limited","is_recommended","detail_status","arrival_status","inspection_required"],
     {"detail_status":["pending","prefetching","ready","failed"],
      "arrival_status":["ordered","in_transit","arrived","inspected"]}),
    ("dm.cart", "Cart", "고객별 장바구니(customer_id unique)",
     ["customer_id(unique)","item_count","total_price"], {}),
    ("dm.cart_item", "CartItem", "장바구니 항목",
     ["product_url","title","brand","options[{name,value}]","price_final","currency","quantity(>=1)"], {}),
    ("dm.order_group", "OrderGroup", "결제 묶음(그룹)",
     ["group_number(unique GRP-…)","customer_id","status","bundle_fee","coupon_discount",
      "point_discount","total_paid","paid_at"], {}),
    ("dm.order", "Order", "개별 주문(상품 단위) — 커머스 그래프의 허브",
     ["order_number(unique ORD-…)","group(FK)","product_url","title","options","quantity",
      "price_product","price_intl_shipping","price_tariff","price_total","price_actual",
      "price_dk_burden","status","tracking_number","inspection_notes","refund_amount"],
     {"status":["pending","paid","purchasing","shipping_domestic","inspection",
                "shipping_intl","delivered","cancelled","refunded","partial_refund"]}),
    ("dm.order_status_log", "OrderStatusLog", "13단계 진행 이력(불변)",
     ["order_number(FK)","stage","changed_at","responsible_party","memo","available_actions"],
     {"responsible_party":["dk","seller","logistics","carrier","system","customer"]}),
    ("dm.admin_action_log", "AdminActionLog", "어드민 액션 감사 로그(불변)",
     ["changed_field","old_value","new_value","actor_type","actor_id","reason"],
     {"actor_type":["system","operator","logistics","pg","carrier_api"]}),
    ("dm.error_info", "ErrorInfo", "주문 오차(예상 vs 실제)",
     ["error_rate","error_amount","error_causes[]","handling_method","auto_processed"],
     {"handling_method":["company_burden","cs_review","additional_charge","cancel","partial_refund"],
      "error_causes":["price_change","ai_parsing_error","domestic_shipping_extra",
                      "intl_shipping_weight_diff","tax_tariff_extra","exchange_rate_diff"]}),
    ("dm.pg_transaction", "PGTransaction", "PG 결제 거래(그룹 단위)",
     ["provider","provider_order_id","auth_status","refund_amount","gmo_job_cd","amount_jpy"],
     {"provider":["gmo","gmo_paypay","stripe","adyen"],
      "auth_status":["pending","auth_complete","captured","cancelled","refunded","failed"]}),
    ("dm.purchase_record", "PurchaseRecord", "CS 대리구매 실구매 내역",
     ["order_number(unique)","purchase_account","collection_address","actual_price",
      "domestic_shipping_fee","cs_user","purchased_at"], {}),
    ("dm.logistics_info", "LogisticsInfo", "입고·검수 정보",
     ["order_number(unique)","arrived_at","inspection_result","inspection_photos[]",
      "components_match","has_defect","issue_reason","post_inspection_action"],
     {"inspection_result":["pending","pass","issue"]}),
    ("dm.shipping_tracking", "ShippingTracking", "국제 배송 추적(DHUB)",
     ["order_number(unique)","fb_invoice_no","dhub_instruction_no","carrier_status",
      "customer_status","current_stage","delay_type","delivered_at","delivery_region","events[]"],
     {"delay_type":["none","24h","48h","extended"],
      "dhub_delivery_type":["FB","SD"]}),
    ("dm.tracking_event", "TrackingEvent", "추적 이벤트(단계 자동분류)",
     ["order_number","occurred_at","stage","description","location","source",
      "unique(order_number,occurred_at,description)"],
     {"stage":["shipment_sent","intl_transit","domestic_delivery","delivered"],
      "source":["seller","intl","customs","carrier","system"]}),
    ("dm.customs_clearance", "CustomsClearance", "통관 결과",
     ["order_number(unique)","customs_type","result","reject_reason",
      "partial_refund_amount","response_deadline","customer_responded_at"],
     {"customs_type":["list","general"],"result":["pending","cleared","rejected","returned"]}),
    ("dm.product_snapshot", "ProductSnapshot", "세관 제출용 상품 사본(공개 UUID)",
     ["order_number(unique)","snapshot_uuid","product_name","product_name_en",
      "purchase_price","quantity","seller","product_url","images"], {}),
    ("dm.product_hs", "ProductHsClassification", "HS코드 통관 분류(AI 추천→검수 확정)",
     ["product(1:1)","ai_suggested","ai_alternatives","final_hs_code","final_category",
      "status","decision_source","inspector","inspector_note"],
     {"status":["pending","confirmed"],"decision_source":["ai_confirmed","alternative","manual"]}),
    ("dm.inquiry", "Inquiry", "1:1 문의(CS 티켓)",
     ["customer_id","order_number","inquiry_type","title","content","status","admin_reply"],
     {"inquiry_type":["general","cancel","refund","exchange","return","shipping",
                      "shipping_delay","price_error","inspection_issue","other"],
      "status":["open","in_progress","resolved","closed"]}),
    ("dm.cancel_request", "CancelRequest", "취소 요청(1주문1요청)",
     ["order_number(unique)","reason","reason_type","status","shipping_fee_burden"],
     {"reason_type":["change_of_mind","defect","mis_ship","inspection","other"],
      "status":["pending","approved","rejected","completed"]}),
    ("dm.refund_request", "RefundRequest", "환불 요청(CS 1차→본사 실행)",
     ["order_number(unique)","reason","reason_type","requested_amount","approved_amount","status"],
     {"reason_type":["change_of_mind","defect","mis_ship","inspection","other"],
      "status":["pending","approved","partial_approved","rejected","completed"]}),
    ("dm.user_address", "UserAddress", "고객 배송지(통관 다국어 필드)",
     ["customer_id","name(한자)","name_kana(가타카나)","name_en(영문)","date_of_birth",
      "phone","country(ISO)","zipcode","address1","address2","is_default"], {}),
    ("dm.coupon", "Coupon", "쿠폰 템플릿",
     ["code(unique)","name","discount_type","discount_value","min_order_amount","valid_until"],
     {"discount_type":["fixed","percent"]}),
    ("dm.user_coupon", "UserCoupon", "고객 발급 쿠폰",
     ["customer_id","coupon(FK)","order_number","is_used","used_at"], {}),
    ("dm.point_log", "PointLog", "포인트 원장(1P=1JPY)",
     ["customer_id","delta","reason","balance_after","order_number"],
     {"reason":["earn_order","use_order","refund"]}),
    ("dm.error_criteria", "ErrorCriteria", "가격 오차 처리 기준(버전·이력)",
     ["small_error_threshold_pct","small_error_threshold_abs","large_error_threshold_pct",
      "handling_price_change","handling_exchange_rate","is_current"], {}),
    ("dm.exchange_rate_log", "ExchangeRateLog", "환율 캐시 로그",
     ["base_currency","target_currency","rate","fetched_at"], {}),
    ("dm.shipping_rate", "ShippingRateTable", "배송 요율표(무게 구간)",
     ["table_key","currency","ShippingRateEntry(weight_break_kg, freight)"], {}),
    ("dm.supported_site", "SupportedSite", "지원 사이트(URL 패턴 분류)",
     ["domain(unique)","name","product_url_patterns[]","search_url_patterns[]","is_active"], {}),
    ("dm.site_template", "SiteTemplate", "스크래퍼 템플릿(진실의 원천=Django DB)",
     ["domain(unique)","filename","code(python)","page_type","category"],
     {"page_type":["detail","list","both"]}),
    ("dm.prohibited", "ProhibitedKeyword", "수입 금지·제한 키워드",
     ["keyword(unique)","category","risk_level","customs_reference","is_active"],
     {"risk_level":["prohibited","restricted","warning"]}),
    ("dm.event_banner", "EventBanner", "메인 이벤트 배너",
     ["title","image_url","link_url","sort_order","starts_at","ends_at","is_active"], {}),
    ("dm.social_account", "SocialAccount", "LINE 소셜 계정(provider_uid upsert)",
     ["provider='line'","provider_uid","display_name","picture_url","access_token"], {}),
    ("dm.membership_grade", "MembershipGrade", "회원 등급·혜택 (프로토타입 정의, 백엔드 미구현)",
     ["grade(웰컴/첫구매/재구매/VIP)","discount_rate(10/5/15%)","welcome_coupon(¥500)"], {}),
]
# enum 코드 → 한글 라벨 (IA에 저장 — 렌더러가 아니라 그래프가 보유)
MASTER_LABELS = {
 "pending":"대기","paid":"결제 완료","purchasing":"현지 구매중","shipping_domestic":"현지 배송중",
 "inspection":"검수중","shipping_intl":"국제 배송중","delivered":"배송 완료","cancelled":"취소",
 "refunded":"환불 완료","partial_refund":"부분 환불",
 "prefetching":"수집중","ready":"수집 완료","failed":"실패",
 "ordered":"발주","in_transit":"이동중","arrived":"입고 완료","inspected":"검수 완료",
 "pass":"합격","issue":"이슈 발생","none":"정상","24h":"24시간 지연","48h":"48시간 지연","extended":"장기 지연",
 "open":"접수","in_progress":"처리중","resolved":"해결","closed":"종결",
 "general":"일반 문의","cancel":"취소 문의","refund":"환불 문의","exchange":"교환 문의","return":"반품 문의",
 "shipping":"배송 문의","shipping_delay":"배송 지연","price_error":"가격 오차","inspection_issue":"검수 이슈","other":"기타",
 "approved":"승인","partial_approved":"부분 승인","rejected":"반려","completed":"완료",
 "change_of_mind":"단순변심","defect":"하자/불량","mis_ship":"오배송",
 "fixed":"정액 할인","percent":"정률 할인","prohibited":"수입 금지","restricted":"수입 제한","warning":"주의",
 "list":"목록 통관","cleared":"통관 완료","returned":"반송",
 "dk":"DK","seller":"판매처","logistics":"물류","carrier":"배송사","system":"시스템","customer":"고객",
 "auth_complete":"승인 완료","captured":"매출 확정",
 "shipment_sent":"상품 발송","intl_transit":"국제 운송","domestic_delivery":"현지 배송",
 "detail":"상세","both":"상세+목록","gmo":"GMO 카드","gmo_paypay":"PayPay","stripe":"Stripe","adyen":"Adyen",
 "ai_confirmed":"AI 추천 확정","alternative":"대안 선택","manual":"직접 입력","confirmed":"확정",
 "FB":"패스트박스","SD":"일반 배송","intl":"국제","customs":"통관","operator":"운영자","pg":"PG","carrier_api":"배송사 API",
 "earn_order":"주문 적립","use_order":"주문 사용",
 "company_burden":"회사 부담","cs_review":"CS 검토","additional_charge":"추가 청구",
 "price_change":"가격 변동","ai_parsing_error":"AI 파싱 오류","domestic_shipping_extra":"국내배송 추가",
 "intl_shipping_weight_diff":"국제배송 무게차","tax_tariff_extra":"관세 추가","exchange_rate_diff":"환율 차이",
}
# 같은 코드가 enum 따라 다른 의미를 갖는 경우 (필드 스코프 오버라이드)
OVERRIDES = {
 ("dm.customs_clearance","customs_type","general"):"일반 통관",
 ("dm.cancel_request","reason_type","inspection"):"검수 이슈",
 ("dm.refund_request","reason_type","inspection"):"검수 이슈",
 ("dm.error_info","handling_method","cancel"):"주문 취소",
 ("dm.point_log","reason","refund"):"환불 차감",
 ("dm.site_template","page_type","list"):"목록",
}
# 필드 가이드(무엇/어떻게/예시) — 모델별 스코프로 IA에 저장
FIELD_GUIDE_BY_MODEL = {
 "dm.order":{
   "status":{"what":"주문의 현재 진행 단계. 정해진 보기 중 하나입니다.","howto":"PATCH /status/ 로 갱신되고 13단계 OrderStatusLog와 함께 움직입니다. 화면에서는 코드값을 한글 배지로 매핑해 보여줍니다.","example":"검수중 (inspection)"},
   "order_number":{"what":"개별 주문 번호.","howto":"주문 생성 시 ORD-YYYYMMDD-XXXXXX 형식으로 자동 발번. 대부분 API의 경로 파라미터.","example":"ORD-20260629-A1B2C3"},
   "price_dk_burden":{"what":"가격 오차 중 DK(회사)가 부담하는 금액.","howto":"오차 기준 정책에 따라 소오차는 자동 company_burden 처리.","example":"1,200"}},
 "dm.order_group":{
   "group_number":{"what":"결제 묶음(그룹) 번호.","howto":"주문 생성 시 GRP-YYYYMMDD-XXXXXX 형식으로 자동 발번.","example":"GRP-20260629-A1B2C3"}},
 "dm.logistics_info":{
   "inspection_result":{"what":"입고 상품 검수 결과. 합격/이슈 중 하나.","howto":"검수자가 C-02 화면에서 선택. 'issue' 선택 시 CS 티켓이 자동 생성됩니다.","example":"합격 (pass)"}},
 "dm.shipping_tracking":{
   "delay_type":{"what":"배송 지연 정도. 4가지 중 하나.","howto":"추적 동기화 시 마지막 상태 변경 후 경과 시간으로 자동 판정.","example":"24시간 지연 (24h)"},
   "tracking_number":{"what":"실 배송사(일본 택배) 운송장 번호.","howto":"DHUB 추적 동기화로 자동 채움 또는 어드민 입력.","example":"460012345678"},
   "fb_invoice_no":{"what":"패스트박스(FastBox) 국제 송장번호.","howto":"DHUB 주문 등록(C-03) 응답으로 채번되어 저장.","example":"FB2026062900123"}},
 "dm.inquiry":{
   "inquiry_type":{"what":"문의 유형. 9가지 중 하나.","howto":"고객이 문의 등록 시 선택. inspection_issue는 검수 API가 자동 부여.","example":"배송 문의 (shipping)"}},
 "dm.cancel_request":{
   "reason_type":{"what":"취소 사유 구분. 단순변심 여부가 정책을 가릅니다.","howto":"change_of_mind은 출고 준비 이후 취소 불가. 하자/오배송은 단계 무관 접수 가능.","example":"단순변심 (change_of_mind)"}},
 "dm.refund_request":{
   "reason_type":{"what":"환불 사유 구분.","howto":"하자/오배송/검수이슈는 귀책 환불로 단계 무관 접수.","example":"하자/불량 (defect)"},
   "requested_amount":{"what":"고객이 요청한 환불 금액.","howto":"본사 실행 시 approved_amount 이하로 확정.","example":"4,000"}},
 "dm.coupon":{
   "discount_type":{"what":"쿠폰 할인 방식.","howto":"fixed=정액(엔), percent=정률(%). discount_value와 함께 사용.","example":"정액 할인 (fixed)"}},
 "dm.prohibited":{
   "risk_level":{"what":"금지/제한 품목 위험도.","howto":"상품명 매칭 시 가장 높은 위험도를 반환해 통관 가능성을 경고.","example":"수입 금지 (prohibited)"}},
 "dm.user_address":{
   "name_kana":{"what":"수취인 가타카나 이름. 일본 배송사(DHUB receiver_name_voice) 필수.","howto":"가타카나로 입력. 누락하면 DHUB 등록 경고.","example":"スズキ アオイ"},
   "name_en":{"what":"수취인 영문명. 세관 서류 필수.","howto":"여권 영문 표기로 입력. 실명만 허용.","example":"Suzuki Aoi"},
   "date_of_birth":{"what":"생년월일. 한국→일본 통관 필수.","howto":"YYYY-MM-DD.","example":"1996-03-12"}},
 "dm.product_snapshot":{
   "product_name_en":{"what":"세관 제출용 영문 품목명.","howto":"실제 품목명 필수. Gift/Present/Goods 등 모호한 표기 금지(세관 반려).","example":"Cotton T-Shirt"}},
 "dm.error_info":{
   "error_rate":{"what":"예상가 대비 실제가 오차율.","howto":"대리구매 완료 시 자동 계산(0.05 = 5%). 기준 초과면 cs_review로 분기.","example":"0.05"}},
}
import re as _re
def _base(f):  # 필드 문자열에서 변수 base 이름만 추출 ("options[{..}]"->"options")
    return _re.split(r'[\(\[\{=]', f)[0].strip()

# 필드 타입을 IA에 명시 저장 (렌더러가 추론하지 않음). 빌드 시 1회 산출.
def _field_type(name, ev):
    if ev: return "enum"
    n = name.lower()
    if _re.search(r'\[\]|images|^options$|photos|^events$|patterns|depth_path|alternatives|ai_suggested|snapshot|^raw$|payload|html_content|available_actions|error_causes', n): return "array/json"
    if _re.search(r'^is_|^has_|components_match|_required|reusable|shipping_fee_burden', n): return "boolean"
    if _re.search(r'date_of_birth|_date$|valid_until|valid_from|effective_date|year_month', n): return "date"
    if _re.search(r'_at$|deadline|fetched_at', n): return "datetime"
    if "email" in n: return "email"
    if _re.search(r'url|_reference$', n): return "url"
    if _re.search(r'(price|amount|_fee$|^fee$|_rate$|^rate$|_pct$|threshold|delta|balance|quantity|weight_break|avg_weight|^freight$|count(?![a-z])|discount_value|min_order|max_discount|rating|_order$|hours$|usage_limit|review_count)', n) and not _re.search(r'number|_no$|_id$', n): return "number"
    return "string"
TYPE_OVERRIDES = {  # 휴리스틱이 틀리는 케이스만 명시
    ("dm.shipping_rate","ShippingRateEntry"):"array/json",
    ("dm.membership_grade","discount_rate"):"string",
    ("dm.membership_grade","welcome_coupon"):"string",
    ("dm.product_hs","final_hs_code"):"string",
}
def field_types_for(did, fields, enums):
    out = {}
    for f in fields:
        b = _base(f)
        ev = enums.get(b) if enums else None
        out[b] = TYPE_OVERRIDES.get((did, b)) or _field_type(b, ev)
    return out

# 일관된 시나리오(고객 '스즈키 아오이'의 패딩 구매대행, 검수중) 기준 예시 데이터 — 전부 IA에 저장
GLOBAL_EXAMPLES = {
 # 식별자
 "order_number":"ORD-20260629-A1B2C3","group_number":"GRP-20260629-9F2K1L","group":"GRP-20260629-9F2K1L",
 "customer_id":"cust_8842","provider_order_id":"GRP202606299F2K1L","pg_transaction_id":"tran_77f12",
 "tracking_number":"460012345678","fb_invoice_no":"FB2026062900123","dhub_ord_bundle_no":"BND-20260629-1",
 "dhub_instruction_no":"INS-20260629-007","snapshot_uuid":"3fa85f64-5717-4562-b3fc-2c963f66afa6",
 "actor_id":"op_jung","cs_user":"cs_han","inspector":"insp_kim","product_id":"77123","provider_uid":"U1a2b3c4d5e",
 "coupon":"웰컴 쿠폰 ¥500","product":"코오롱스포츠 안타티카 패딩","raw_code":"InTransit",
 # 상품/콘텐츠
 "url":"https://www.coupang.com/vp/products/77123","product_url":"https://www.coupang.com/vp/products/77123",
 "source_url":"https://www.coupang.com/np/categories/1029","domain":"coupang.com","slug":"musinsa",
 "title":"코오롱스포츠 안타티카 구스다운 패딩","product_name":"코오롱스포츠 안타티카 패딩",
 "product_name_en":"Kolon Sport Antarctica Down Jacket","brand":"코오롱스포츠","seller":"코오롱몰",
 "category":"아우터","name":"鈴木 葵","display_name":"あおい","keyword":"건강기능식품",
 "images":'["https://img.coupang.com/77123_1.jpg", "…"]',"image_url":"https://cdn.koom.jp/banner_summer.png",
 "link_url":"https://koom.jp/event/summer","picture_url":"https://line.me/p/aoi.jpg",
 "icon_url":"https://logo.clearbit.com/coupang.com","logo_url":"https://logo.clearbit.com/musinsa.com",
 "customs_reference":"https://www.customs.go.jp/mizugiwa/kinshi.htm","code":"WELCOME500","filename":"coupang_com_both.py",
 "table_key":"AIR_STANDARD","rating":4.7,"review_count":1284,"availability":"in_stock",
 # 금액 (JPY 기준, 상품 원가는 KRW)
 "price_original":259000,"price_discounted":189000,"price_product":189000,"price_final":189000,
 "purchase_price":189000,"actual_price":192000,"product_price_at_purchase":189000,
 "price_intl_shipping":1800,"price_tariff":2100,"price_total":21500,"price_actual":21800,"price_dk_burden":300,
 "price_domestic_shipping":0,"total_paid":21500,"total_price":21500,"bundle_fee":200,"coupon_discount":500,
 "point_discount":120,"domestic_shipping_fee":0,"amount_jpy":21500,"refund_amount":4000,"error_amount":300,
 "partial_refund_amount":4000,"requested_amount":4000,"approved_amount":4000,"delta":-120,"balance_after":1380,
 "discount_value":500,"min_order_amount":5000,"max_discount_amount":2000,"small_error_threshold_pct":2.0,
 "small_error_threshold_abs":500,"large_error_threshold_pct":5.0,"error_rate":0.05,"rate":9.12,
 "weight_break_kg":1.0,"freight":690,"avg_weight_kg":1.2,
 # 수량/플래그
 "quantity":1,"item_count":2,"sort_order":1,"is_limited":True,"is_recommended":True,"inspection_required":True,
 "components_match":True,"has_defect":False,"auto_processed":True,"is_default":True,"is_used":False,"is_current":True,
 "is_active":True,"shipping_fee_burden":False,
 # 텍스트
 "options":'[{"name":"색상","value":"블랙"},{"name":"사이즈","value":"100"}]',
 "memo":"검수 사진 추가 확인 요망","reason":"단순 변심으로 취소합니다","admin_reply":"확인 후 부분환불 처리하겠습니다.",
 "content":"배송이 며칠째 그대로인데 확인 부탁드려요","admin_notes":"부분환불 4,000엔 승인","inspection_notes":"우측 소매 봉제 불량",
 "issue_reason":"우측 소매 봉제 불량","post_inspection_action":"고객 통보 후 선택지 제공","refund_reason":"검수 이슈(봉제 불량)",
 "reject_reason":"성분 규제 품목","note":"6월 가격 인상 반영","inbound_note":"분리 입고","reason_display":"주문 적립",
 "changed_field":"status","old_value":"paid","new_value":"purchasing","carrier_status":"InTransit","customer_status":"국제 배송중",
 "delivery_region":"도쿄","location":"중부산 물류센터","description":"한국 세관 통관 완료",
 "purchase_account":"buyer01@dkmall","collection_address":"인천 동구 송림로 108 DK센터","gmo_job_cd":"SALES",
 "final_hs_code":"6201.40","final_category":"우모제 외투","inspector_note":"AI 추천 채택","ai_search_expansion":"down jacket outerwear",
 "currency":"JPY","base_currency":"JPY","target_currency":"KRW","country":"JP","zipcode":"150-0001",
 "address1":"東京都渋谷区神宮前1-2-3","address2":"コーポ青山 402","phone":"080-1234-5678",
 "name_kana":"スズキ アオイ","name_en":"Suzuki Aoi","date_of_birth":"1996-03-12","access_token":"(보안 토큰·미표시)",
 "handling_price_change":"cs_review","handling_exchange_rate":"company_burden","year_month":"2026-06",
 "discount_rate":"15%","welcome_coupon":"¥500","grade":"VIP","source":"https://api.exchangerate.host",
 "status":"검수중","stage":"inspection_complete (검수 완료)","current_stage":"intl_transit (국제 운송)",
 # 배열/JSON
 "inspection_photos":'["https://cdn.koom.jp/insp_77123_1.jpg"]',"events":"[{DHUB trace 원본…}]",
 "available_actions":'["cancel","contact"]',"error_causes":'["price_change"]',"ai_suggested":'{hs_code:6201.40, …}',
 "ai_alternatives":"[{hs_code:6202.40, rank:2}, …]","product_url_patterns":'["/vp/products/"]',
 "search_url_patterns":'["/np/search"]',"html_content":"<html>…세관 제출용…</html>","ShippingRateEntry":"1.0kg → 690엔",
 "unique":"(order_number, occurred_at, description)","raw":"{원본 trace JSON}",
 # 날짜시간
 "paid_at":"2026-06-22 14:05","changed_at":"2026-06-25 09:10","created_at":"2026-06-22 14:05","updated_at":"2026-06-25 09:10",
 "purchased_at":"2026-06-23 11:20","arrived_at":"2026-06-25 08:40","occurred_at":"2026-06-27 06:30",
 "delivered_at":"2026-06-29 15:10","response_deadline":"2026-07-06 23:59","customer_responded_at":"2026-06-30 10:00",
 "fetched_at":"2026-06-29 09:00","used_at":"2026-06-22 14:05","valid_until":"2026-12-31","valid_from":"2026-06-01",
 "starts_at":"2026-06-01 00:00","ends_at":"2026-08-31 23:59","detail_crawled_at":"2026-06-22 13:50",
 "confirmed_at":"2026-06-25 10:00","published_at":"2026-06-20 09:00","effective_date":"2026-06-01",
 "last_status_changed_at":"2026-06-27 06:30","created_by":"hq_choi",
}
# 같은 base 이름이 모델별로 다른 값이어야 하는 경우
EXAMPLE_OVERRIDES = {
 ("dm.coupon","name"):"웰컴 쿠폰 ¥500",("dm.supported_site","name"):"쿠팡",
 ("dm.event_banner","title"):"여름맞이 구매대행 프로모션",("dm.inquiry","title"):"색상 오배송 문의",
 ("dm.prohibited","category"):"식품/건강식품",("dm.site_template","category"):"shopping",
 ("dm.site_template","code"):"(파이썬 스크래퍼 코드)",("dm.social_account","provider"):"line",
 ("dm.refund_request","reason_type"):"하자/불량",
 # ── 시나리오 일관성을 위한 enum 예시 (아오이의 패딩 주문: 검수중·검수합격·통관 거절→부분환불) ──
 ("dm.order","status"):"검수중",("dm.logistics_info","inspection_result"):"합격",
 ("dm.product","detail_status"):"수집 완료",("dm.product","arrival_status"):"입고 완료",
 ("dm.inquiry","inquiry_type"):"배송 지연",("dm.inquiry","title"):"배송 지연 문의",
 ("dm.customs_clearance","result"):"거절",("dm.pg_transaction","auth_status"):"매출 확정",
 ("dm.product_hs","status"):"확정",("dm.refund_request","status"):"완료",
 ("dm.admin_action_log","actor_type"):"운영자",("dm.tracking_event","stage"):"국제 운송",
 ("dm.tracking_event","source"):"통관",("dm.prohibited","risk_level"):"수입 제한",
 ("dm.point_log","reason"):"주문 사용",("dm.point_log","reason_display"):"주문 사용",
 ("dm.error_info","handling_method"):"CS 검토",("dm.site_template","page_type"):"상세+목록",
 ("dm.refund_request","reason"):"검수 결과 하자가 확인되었습니다",
}
MISSING_EXAMPLES = []
def field_examples_for(did, fields, enums, elabels):
    out = {}
    for f in fields:
        b = _base(f)
        v = EXAMPLE_OVERRIDES.get((did, b))                 # 시나리오 지정값이 최우선
        if v is None and enums and b in enums:              # enum → 첫 코드의 라벨
            codes = enums[b]; v = elabels[b][codes[0]] if codes else ""
        if v is None: v = GLOBAL_EXAMPLES.get(b)
        if v is None:
            MISSING_EXAMPLES.append(f"{did}.{b}"); v = ""
        out[b] = v
    return out

MISSING_LABELS = []
def enum_labels_for(did, enums):
    out = {}
    for field, codes in enums.items():
        out[field] = {}
        for c in codes:
            lab = OVERRIDES.get((did, field, c)) or MASTER_LABELS.get(c)
            if lab is None:
                MISSING_LABELS.append(f"{did}.{field}={c}")
                lab = c  # honest fallback: show code (no fabricated 한글)
            out[field][c] = lab
    return out

dm_ids = set()
for did, name, desc, fields, enums in DATA:
    dm_ids.add(did)
    origin = "prototype" if did == "dm.membership_grade" else "backend_docs"
    pay = {"description": desc, "fields": fields}
    el = enum_labels_for(did, enums) if enums else {}
    if enums:
        pay["enums"] = enums
        pay["enum_labels"] = el                              # 한글 라벨을 IA에 동봉
    pay["field_types"] = field_types_for(did, fields, enums)            # 필드 타입을 IA에 명시 저장
    pay["field_examples"] = field_examples_for(did, fields, enums, el)  # 예시 데이터를 IA에 동봉
    if did in FIELD_GUIDE_BY_MODEL:
        pay["field_guide"] = FIELD_GUIDE_BY_MODEL[did]      # 필드 가이드를 IA에 동봉
    if did == "dm.membership_grade": pay["status"] = "proposed (스펙 불일치: 프로토타입 only)"
    node(did, "data_model", name, f"koom/data/{name}", origin, pay)
    edge("surface.data", did, "contains")

# data model relationships (belongs_to / depends)
for frm, to, rel, meta in [
    ("dm.cart_item","dm.cart","belongs_to",None),
    ("dm.order","dm.order_group","belongs_to",None),
    ("dm.order_status_log","dm.order","belongs_to",None),
    ("dm.admin_action_log","dm.order","belongs_to",None),
    ("dm.error_info","dm.order","belongs_to",None),
    ("dm.purchase_record","dm.order","belongs_to",None),
    ("dm.logistics_info","dm.order","belongs_to",None),
    ("dm.shipping_tracking","dm.order","belongs_to",None),
    ("dm.tracking_event","dm.shipping_tracking","belongs_to",None),
    ("dm.customs_clearance","dm.order","belongs_to",None),
    ("dm.product_snapshot","dm.order","belongs_to",None),
    ("dm.product_hs","dm.product","belongs_to",None),
    ("dm.pg_transaction","dm.order_group","belongs_to",{"note":"PG는 그룹 단위"}),
    ("dm.user_coupon","dm.coupon","belongs_to",None),
    ("dm.cart_item","dm.product","derived_from",{"note":"느슨한 연결(product nullable)"}),
    ("dm.order","dm.product","derived_from",{"note":"주문 시 스냅샷"}),
]:
    edge(frm, to, rel, meta)

# ---------------------------------------------------------------------------
# 4. Screens  (code, name, surface, primary actor, route, purpose, fr, apis[], transitions[], prototype_page)
# ---------------------------------------------------------------------------
S = lambda c: f"screen.{c.lower().replace('-','_')}"
SCREENS = [
 # code, name, surface, actor, purpose, fr, apis, transitions, proto
 ("S-01","LINE 로그인","surface.customer_app","actor.guest","비인증 진입·LINE OAuth","FR-AUTH-01",
   ["api.auth_line_login","api.auth_verify"],["S-02"],None),
 ("S-01b","URL 입력→즉석 스크래핑","surface.customer_app","actor.customer","상품 URL 붙여넣기 분석","FR-PRD-09",
   ["api.scraping_analyze"],["S-04"],None),
 ("S-02","홈(메인)","surface.customer_app","actor.customer","배너·추천·카테고리 허브","FR-PRD-03,FR-CNT-03",
   ["api.content_banners","api.featured_cats","api.products_list"],
   ["S-01b","S-03","S-05","S-06","S-09","S-14a","S-16"],None),
 ("S-03","상품 목록(카탈로그)","surface.customer_app","actor.customer","필터·정렬 목록","FR-PRD-01",
   ["api.products_list"],["S-04"],None),
 ("S-04","상품 상세","surface.customer_app","actor.customer","상품+가격+배송+결제수단","FR-PRD-02,FR-PRC-02",
   ["api.products_page","api.pricing_quote"],["S-06","S-14e","S-07"],None),
 ("S-05","쇼핑몰별 탐색","surface.customer_app","actor.customer","몰·카테고리 탐색","FR-PRD-04",
   ["api.malls_list"],["S-04"],None),
 ("S-06","장바구니(선택)","surface.customer_app","actor.customer","선택 결제 묶기","FR-CART-01,FR-CART-02",
   ["api.cart_page","api.cart_items"],["S-07"],None),
 ("S-07","결제(체크아웃)","surface.customer_app","actor.customer","주소·쿠폰·포인트·결제수단","FR-CART-03,FR-PAY-01,FR-PAY-02",
   ["api.cart_checkout","api.pay_entry","api.pay_execute","api.paypay_entry","api.orders_create"],["S-08"],None),
 ("S-08","주문 완료","surface.customer_app","actor.customer","group_number·예상배송일","FR-ORD-01",
   [],["S-10","S-02"],None),
 ("S-09","주문 목록","surface.customer_app","actor.customer","내 주문 카드","FR-ORD-06",
   ["api.orders_group"],["S-10"],None),
 ("S-10","주문 상세(13단계 추적)","surface.customer_app","actor.customer","타임라인·가격·결제·배송","FR-ORD-02,FR-ORD-06",
   ["api.orders_group","api.orders_statuslog","api.orders_detail"],
   ["S-10b","S-11","S-12","S-13","P-01"],None),
 ("S-10b","배송 추적 타임라인","surface.customer_app","actor.customer","4단계 진행바·이벤트 로그","FR-LOG-07",
   ["api.log_timeline"],[],None),
 ("S-11","1:1 문의","surface.customer_app","actor.customer","문의 등록·답변 확인","FR-CS-01",
   ["api.cs_inquiries"],[],None),
 ("S-12","취소 요청","surface.customer_app","actor.customer","취소 접수(가능 검증)","FR-CS-02",
   ["api.cs_cancel","api.orders_detail"],[],None),
 ("S-13","환불 요청","surface.customer_app","actor.customer","환불 접수","FR-CS-03",
   ["api.cs_refund"],[],None),
 ("S-14a","마이·배송지","surface.customer_app","actor.customer","통관 다국어 주소","FR-MY-01",
   ["api.mypage_addresses"],["S-14b","S-14c","S-14d","S-14e"],None),
 ("S-14b","마이·포인트","surface.customer_app","actor.customer","잔액·내역","FR-MY-02",
   ["api.mypage_points"],[],None),
 ("S-14c","마이·쿠폰","surface.customer_app","actor.customer","보유 쿠폰","FR-MY-03",
   ["api.mypage_coupons"],[],None),
 ("S-14d","마이·알림설정","surface.customer_app","actor.customer","수신 동의","FR-MY-04",[],[],None),
 ("S-14e","마이·위시리스트","surface.customer_app","actor.customer","찜","FR-MY-05",[],[],None),
 ("S-16","FAQ","surface.customer_app","actor.customer","자주 묻는 질문","FR-CNT-01",[],[],None),
 ("S-17","공지사항","surface.customer_app","actor.customer","공지","FR-CNT-02",[],[],None),
 ("S-18","정책","surface.customer_app","actor.customer","약관·정책","FR-CNT-04",[],[],None),
 ("P-01","세관 스냅샷 공개","surface.public","actor.guest","비인증 품목 사본","FR-ORD-05",
   ["api.orders_snap_pub"],[],None),
 # CS
 ("C-05","내 담당 건 추적","surface.cs_console","actor.cs","담당 대시보드(데이터 격리)","FR-MON-01b",
   ["api.stats_monitoring","api.log_stagnated"],["C-01","C-02","C-06","C-03","C-04"],"dashboard"),
 ("C-01","대리구매 작업","surface.cs_console","actor.cs","원본 URL 구매·실내역 입력","FR-ORD-07,FR-ORD-04",
   ["api.cs_purchase_tasks","api.cs_purchase_done"],["C-02"],"orders"),
 ("C-02","상품 검수","surface.cs_console","actor.wms","pass/issue·사진·실측","FR-LOG-05",
   ["api.log_inspection"],["C-06"],"logistics"),
 ("C-06","HS코드 통관 분류 검수","surface.cs_console","actor.cs","AI 추천 확정/대안/직접","FR-LOG-06",
   ["api.tariff_classify","api.tariff_classification"],["C-03"],"logistics"),
 ("C-03","FastBox(DHUB) 인계","surface.cs_console","actor.cs","송장 채번·배송지시","FR-LOG-01,FR-LOG-02",
   ["api.log_dhub_register","api.log_dhub_instruct"],[],"logistics"),
 ("C-04","CS 응대","surface.cs_console","actor.cs","문의·취소·환불 1차","FR-CS-01,FR-CS-02,FR-CS-03",
   ["api.cs_inquiry_reply","api.cs_refund_patch"],["H-03"],"cs"),
 # HQ
 ("H-11","실시간 모니터링","surface.hq_admin","actor.hq","전체 운영 대시보드(허브)","FR-MON-01",
   ["api.stats_monitoring","api.orders_admin_dash"],
   ["H-01","H-02","H-03","H-04","H-05","H-06","H-07","H-08","H-09","H-10"],"dashboard"),
 ("H-01","상품·뱃지 관리","surface.hq_admin","actor.hq","뱃지·입고 추적","FR-PRD-07",
   ["api.products_badges","api.products_inbound"],[],"content"),
 ("H-02","지원사이트·AI 템플릿","surface.hq_admin","actor.hq","사이트·템플릿 빌드","FR-PRD-08,FR-ADM-05",
   ["api.templates_build"],[],"content"),
 ("H-03","결제·정산","surface.hq_admin","actor.hq","Capture·환불 실행","FR-PAY-03,FR-PAY-04",
   ["api.pay_capture","api.pay_refund","api.cs_refund_exec"],[],"orders"),
 ("H-04","스냅샷·영문명(CI)","surface.hq_admin","actor.hq","세관 영문 품목명 편집","FR-ADM-03,FR-ORD-05",
   ["api.orders_snapshot"],["P-01"],"orders"),
 ("H-05","콘텐츠 관리","surface.hq_admin","actor.hq","FAQ·공지·배너·정책","FR-CNT-01,FR-CNT-04",
   ["api.content_banners"],[],"content"),
 ("H-06","사이트 설정","surface.hq_admin","actor.hq","환율·요율·배송모드","FR-ADM-01,FR-PRC-03",
   ["api.pricing_fx","api.shipping_quote"],[],"criteria"),
 ("H-07","쿠폰 생성·발급","surface.hq_admin","actor.hq","쿠폰 발급","FR-ADM-06",
   ["api.coupon_issue"],[],"content"),
 ("H-08","금지 품목 키워드","surface.hq_admin","actor.hq","금지·제한 관리","FR-ADM-04",
   ["api.prohibited_check"],[],"criteria"),
 ("H-09","가격 오차 기준","surface.hq_admin","actor.hq","임계값·자동처리 정책","FR-ADM-02",
   ["api.ops_error_criteria"],[],"criteria"),
 ("H-10","주문·액션 이력(감사)","surface.hq_admin","actor.hq","감사 로그","FR-ADM-08",
   ["api.orders_actionlog","api.orders_statuslog","api.orders_error"],[],"orders"),
]
screen_ids = {}
for code, name, surface, actor, purpose, fr, apis, trans, proto in SCREENS:
    sid = S(code)
    screen_ids[code] = sid
    surf_path = dict((s[0], s[2]) for s in SURFACES)[surface]
    pay = {"code": code, "purpose": purpose, "primary_actor": actor,
           "requirements": fr.split(","), "status": "implemented"}
    if proto: pay["prototype_page"] = proto
    node(sid, "screen", f"{code} · {name}", f"{surf_path}/{code}", "screen_spec", pay)
    edge(surface, sid, "contains")
    edge(sid, "ctx.screen_spec", "mentioned_in")
    # primary actor link via permission later; also a light edge for visualization
    # API calls
    for ap in apis:
        if ap in api_ids:
            edge(sid, ap, "calls")
    # requirements provenance
# transitions (after all screens created)
for code, name, surface, actor, purpose, fr, apis, trans, proto in SCREENS:
    for t in trans:
        if t in screen_ids:
            edge(screen_ids[code], screen_ids[t], "transitions_to")
# login transition guest -> S-01 handled via actor operates; add explicit
edge("screen.s_08","screen.s_10","transitions_to")  # ensure exists (already) - harmless dup guard? it's allowed

# ---------------------------------------------------------------------------
# 5. Components (reusable) -> contained by a home screen, impacts others
# ---------------------------------------------------------------------------
COMPONENTS = [
 ("comp.admin_sidebar","어드민 사이드바(롤 기반 네비)","screen.h_11",["screen.c_05"],
   {"kind":"navigation","role_aware":True,"note":"hq=9페이지 / cs=5페이지 노출"}),
 ("comp.role_switcher","롤 스위처(본사/CS/WMS)","screen.h_11",["screen.c_05"],
   {"kind":"control","reusable":True}),
 ("comp.order_timeline","주문 13단계 타임라인","screen.s_10",["screen.s_10b","screen.h_10"],
   {"kind":"display","reads":"OrderStatusLog"}),
 ("comp.price_breakdown","가격 내역(견적)","screen.s_04",["screen.s_07","screen.s_10"],
   {"kind":"display","reads":"pricing/quote"}),
 ("comp.inspection_form","검수 입력 폼(사진/실측)","screen.c_02",[],
   {"kind":"form","note":"issue 시 CS 티켓 자동"}),
 ("comp.hs_classifier","HS코드 분류 위젯(추천·대안)","screen.c_06",[],
   {"kind":"form","note":"AI selected + alternatives + reason"}),
 ("comp.ticket_panel","CS 티켓 패널","screen.c_04",[],{"kind":"panel"}),
 ("comp.address_form","배송지 폼(통관 다국어)","screen.s_14a",["screen.s_07"],
   {"kind":"form","required":["name_kana","name_en","date_of_birth"]}),
 ("comp.product_card","상품 카드(뱃지·환산가)","screen.s_03",["screen.s_05","screen.s_02"],
   {"kind":"display","reusable":True}),
]
for cid, name, home, others, pay in COMPONENTS:
    home_node = next(n for n in NODES if n["id"]==home)
    node(cid, "component", name, home_node["path"]+"/"+cid.split('.')[1], "screen_spec", pay)
    edge(home, cid, "contains")
    for o in others:
        edge(cid, o, "impacts", {"reuse":"동일 컴포넌트 재사용"})

# ---------------------------------------------------------------------------
# 6. States (state machines)
# ---------------------------------------------------------------------------
def state_machine(mid, name, desc, states, transitions, owner_model=None):
    node(mid, "state_machine", name, f"koom/states/{mid.split('.')[1]}", "backend_docs",
         {"description": desc})
    edge("surface.states", mid, "contains")
    for sid_, label in states:
        node(sid_, "state", label, f"koom/states/{mid.split('.')[1]}/{sid_.split('.')[-1]}",
             "backend_docs", {"machine": mid})
        edge(mid, sid_, "contains")
    for a,b,meta in transitions:
        edge(a,b,"transitions_to",meta)
    if owner_model:
        edge(owner_model, mid, "governed_by", {"note":"상태 머신"})

ord_stages = [
 ("state.ord.order_received","주문 접수"),("state.ord.purchase_review","구매 검토"),
 ("state.ord.purchase_complete","구매 완료"),("state.ord.pre_arrival","입고 대기"),
 ("state.ord.arrived","입고 완료"),("state.ord.inspection_in_progress","검수 중"),
 ("state.ord.inspection_complete","검수 완료"),("state.ord.preparing_dispatch","출고 준비(FastBox 인계)"),
 ("state.ord.intl_shipping","국제 배송 중"),("state.ord.jp_carrier_handover","일본 배송사 인계"),
 ("state.ord.delivered","배송 완료"),("state.ord.cancelled_or_refunded","취소/반품/환불"),
]
ord_seq = [s[0] for s in ord_stages[:-1]]
ord_trans = [(ord_seq[i],ord_seq[i+1],None) for i in range(len(ord_seq)-1)]
# branches to terminal
for s in ["state.ord.purchase_review","state.ord.inspection_complete","state.ord.intl_shipping"]:
    ord_trans.append((s,"state.ord.cancelled_or_refunded",{"trigger":"취소/환불/이슈"}))
state_machine("sm.order_lifecycle","주문 라이프사이클(13단계)",
              "order_received → … → delivered, 분기 cancelled_or_refunded",
              ord_stages, ord_trans, owner_model="dm.order_status_log")

cs_states=[("state.cs.open","접수"),("state.cs.in_progress","처리중"),
           ("state.cs.resolved","답변완료/해결"),("state.cs.closed","종결")]
state_machine("sm.cs_status","CS 문의 상태","open→in_progress→resolved→closed",
              cs_states,[("state.cs.open","state.cs.in_progress",None),
                         ("state.cs.in_progress","state.cs.resolved",None),
                         ("state.cs.resolved","state.cs.closed",None)],
              owner_model="dm.inquiry")

insp_states=[("state.insp.pending","검수 대기"),("state.insp.pass","합격"),("state.insp.issue","이슈 발생")]
state_machine("sm.inspection","검수 결과","pending→pass/issue",
              insp_states,[("state.insp.pending","state.insp.pass",None),
                           ("state.insp.pending","state.insp.issue",{"effect":"CS 티켓 자동 생성"})],
              owner_model="dm.logistics_info")

delay_states=[("state.delay.none","정상"),("state.delay.d24","24h 지연"),
              ("state.delay.d48","48h 지연"),("state.delay.ext","장기 지연")]
state_machine("sm.delay","배송 지연","none→24h→48h→extended",
              delay_states,[("state.delay.none","state.delay.d24",None),
                            ("state.delay.d24","state.delay.d48",None),
                            ("state.delay.d48","state.delay.ext",None)],
              owner_model="dm.shipping_tracking")

# ---------------------------------------------------------------------------
# 7. Business Rules
# ---------------------------------------------------------------------------
RULES = [
 ("rule.cancel_cutoff","단순변심 취소 컷오프","🔴",
   "단순변심(change_of_mind) 취소는 FastBox 인계(preparing_dispatch) 이후 차단(409). "
   "하자·오배송 등 귀책 사유는 단계 무관 항상 접수 가능.",
   ["ctx.figma_blueprint","ctx.backend_docs"],
   {"governs":["screen.s_12","api.cs_cancel","state.ord.preparing_dispatch","dm.cancel_request"]}),
 ("rule.refund_two_step","환불 2단계 승인","🔴",
   "환불은 CS 1차 승인(approved/partial_approved) → 본사 GMO 실행. RefundRequest=completed 시 "
   "Order.status refunded/partial_refund + 로그 기록.",
   ["ctx.backend_docs"],
   {"governs":["api.cs_refund_patch","api.cs_refund_exec","screen.c_04","screen.h_03","dm.refund_request"]}),
 ("rule.price_error","가격 오차 자동/수동 처리","🔴",
   "실제가 vs 예상가 비교: 소오차(≤기준 pct/abs, 누적)→company_burden 자동, 대오차(>기준)→cs_review.",
   ["ctx.figma_blueprint","ctx.backend_docs"],
   {"governs":["dm.error_info","dm.error_criteria","api.cs_purchase_done","screen.c_01","screen.h_09"]}),
 ("rule.auto_cancel_7d","미응답 7일 자동 취소","🟡",
   "품절·가격변동·통관 등으로 고객 확인 필요 시 CS 발송 → 7일 이내 미응답이면 자동 취소.",
   ["ctx.figma_blueprint"],
   {"governs":["dm.cancel_request","dm.customs_clearance"]}),
 ("rule.inspection_autoticket","검수 이슈 자동 티켓","🔴",
   "검수 result=issue 시 CS Inquiry(inspection_issue) 자동 생성 → C-04로 인계.",
   ["ctx.backend_docs"],
   {"governs":["api.log_inspection","dm.inquiry","screen.c_02","state.insp.issue"]}),
 ("rule.customs_partial_refund","통관 불가 부분환불","🔴",
   "통관 거절 시 해당 상품만 부분환불(DK 부담), 고객 응답기한(기본 7일). 미응답 시 수동 처리.",
   ["ctx.figma_blueprint","ctx.backend_docs"],
   {"governs":["dm.customs_clearance","api.log_customs","api.log_customs_refund"]}),
 ("rule.delivery_failure","배송 실패(주소 오류)","🟡",
   "주소 오류(고객 귀책)→통관 불가/반송. 5일 내 FastBox 반송, 재배송·반송비 고객 부담. 보관기간 안내.",
   ["ctx.figma_blueprint"],
   {"governs":["dm.shipping_tracking","screen.s_10b"]}),
 ("rule.duty_free","면세 기준(CIF×60%)","🔴",
   "(상품가+국내배송+국제배송)×60% ≤ 10,000엔 이면 관세·소비세 면제.",
   ["ctx.backend_docs"],
   {"governs":["api.pricing_quote","api.tariff_lookup"]}),
 ("rule.exchange_margin","환율 4% 마진","🟡",
   "고객 청구 환율 = 시장환율 / 1.04 (4% 마진).",
   ["ctx.backend_docs"],{"governs":["api.pricing_quote","dm.exchange_rate_log"]}),
 ("rule.intl_markup","국제배송 40% 마크업","🟡",
   "국제 배송비 원가에 40% 마크업 적용해 청구. 국내 배송비는 마진 없이 통관 CIF에 포함.",
   ["ctx.backend_docs"],{"governs":["api.pricing_quote","api.shipping_quote"]}),
 ("rule.points_earn","포인트 적립(배송완료 후)","⚪",
   "1포인트=1JPY. delivered 후 표시통화 기준 1% 적립.",
   ["ctx.backend_docs"],{"governs":["dm.point_log","state.ord.delivered"]}),
 ("rule.card_not_stored","카드정보 미저장(PCI)","🔴",
   "카드번호 DB·로그 미저장, GMO 토큰만 전달, 3D Secure 2.0 적용.",
   ["ctx.backend_docs"],{"governs":["api.pay_entry","api.pay_execute","dm.pg_transaction"]}),
 ("rule.data_isolation","데이터 격리","🔴",
   "customer_id / cs_user 스코프로 타인 데이터 미노출(CS는 본인 담당 건만).",
   ["ctx.backend_docs"],{"governs":["api.stats_monitoring","screen.c_05","api.orders_group"]}),
 ("rule.snapshot_en","세관 영문 품목명 필수","🔴",
   "ProductSnapshot.product_name_en 은 실제 품목명 필수(Gift/Present/Goods 금지). 일본 세관 심사 대상.",
   ["ctx.figma_blueprint","ctx.backend_docs"],
   {"governs":["dm.product_snapshot","api.orders_snapshot","screen.h_04"]}),
 ("rule.hs_priority","HS코드 우선순위","🟡",
   "HS코드: request body → 검수 확정값(C-06) → 기본 621790. fastbox 등록 시 자동 주입.",
   ["ctx.backend_docs"],{"governs":["dm.product_hs","api.log_dhub_register"]}),
 ("rule.audit_immutable","감사 로그 불변","🔴",
   "OrderStatusLog/AdminActionLog/ErrorCriteriaLog 삭제 불가(전체 이력 보존).",
   ["ctx.backend_docs"],{"governs":["dm.order_status_log","dm.admin_action_log"]}),
 ("rule.price_change","가격 변동 대응","🟡",
   "인상 시 고객 추가비용 요청 or 취소. 인상 폭 큰/작은 범위 설정 필요(미정). 7일 미응답 자동취소.",
   ["ctx.figma_blueprint"],{"governs":["dm.error_info","screen.c_01"], "open_question":True}),
]
for rid,name,prio,desc,ctxs,extra in RULES:
    node(rid,"business_rule",name,f"koom/rules/{rid.split('.')[1]}","figma" if "ctx.figma_blueprint" in ctxs else "backend_docs",
         {"priority":prio,"description":desc, **{k:v for k,v in extra.items() if k!="governs"}})
    edge("surface.rules", rid, "contains")
    for c in ctxs:
        edge(rid, c, "derived_from")
    for g in extra.get("governs",[]):
        edge(g, rid, "governed_by")

# ---------------------------------------------------------------------------
# 8. Validation rules
# ---------------------------------------------------------------------------
VALS = [
 ("val.address_customs","통관 필수 주소 필드","name_kana(가타카나)·name_en(영문)·date_of_birth 필수",
   "일본 통관/배송사 서류 누락","DHUB_REQUIRED",["dm.user_address","api.mypage_addresses","screen.s_14a"]),
 ("val.cart_qty","수량 최소값","quantity ≥ 1","수량은 1 이상","CART_QTY_MIN",["dm.cart_item","api.cart_items"]),
 ("val.cancel_unique","취소 요청 유일성","order_number unique (1주문 1취소요청)","이미 취소요청 존재(409)","CANCEL_DUP",
   ["dm.cancel_request","api.cs_cancel"]),
 ("val.refund_amount","승인 금액 한도","approved_amount ≤ requested_amount","환불 승인액 초과","REFUND_AMT",
   ["dm.refund_request","api.cs_refund_patch"]),
 ("val.dhub_batch","배송지시 건수","fb_invoice_nos ≤ 200","일괄 배송지시 200건 초과","DHUB_BATCH_MAX",
   ["api.log_dhub_instruct"]),
 ("val.pg_orderid","PG 주문 ID 길이","provider_order_id ≤ 27자(영숫자·-)","GMO OrderID 형식","PG_ORDERID_LEN",
   ["api.pay_entry","dm.pg_transaction"]),
 ("val.weight_min","배송 무게 최소","actual_weight_kg ≥ 0.001","무게 입력 필요","WEIGHT_MIN",
   ["api.shipping_quote"]),
 ("val.snapshot_en_real","영문 품목명 실명","product_name_en 실제 품목(Gift 등 금지)","세관 반려 위험","SNAPSHOT_EN",
   ["dm.product_snapshot","api.orders_snapshot"]),
]
for vid,name,cond,msg,code,targets in VALS:
    node(vid,"validation",name,f"koom/validations/{vid.split('.')[1]}","backend_docs",
         {"condition":cond,"message":msg,"error_code":code})
    edge("surface.validations", vid, "contains")
    for t in targets:
        edge(t, vid, "validated_by")

# ---------------------------------------------------------------------------
# 9. Permissions (role × action × resource)
# ---------------------------------------------------------------------------
PERMS = [
 ("perm.hq_full","본사 전 화면 접근","actor.hq","access","hq-admin(9 pages)",
   ["screen.h_11","screen.h_01","screen.h_03","screen.h_09"]),
 ("perm.cs_scope","CS 5화면(담당 격리)","actor.cs","access","dashboard/orders/customers/logistics/cs",
   ["screen.c_05","screen.c_01","screen.c_02","screen.c_04"]),
 ("perm.wms_inspection","WMS 입고·검수(모바일)","actor.wms","inspect","logistics",
   ["screen.c_02","api.log_inspection"]),
 ("perm.refund_exec_hq","환불 실행=본사 전용","actor.hq","execute_refund","RefundRequest/GMO",
   ["api.cs_refund_exec","api.pay_refund"]),
 ("perm.refund_approve_cs","환불 1차 승인=CS","actor.cs","approve_refund","RefundRequest",
   ["api.cs_refund_patch"]),
 ("perm.purchase_cs","대리구매=CS","actor.cs","purchase","Order(paid)",
   ["api.cs_purchase_tasks","api.cs_purchase_done"]),
 ("perm.public_snapshot","스냅샷 공개 조회(비인증)","actor.guest","read","ProductSnapshot",
   ["api.orders_snap_pub","screen.p_01"]),
 ("perm.customer_own","고객 본인 데이터만","actor.customer","read_own","Order/Cart/Address",
   ["api.orders_group","api.cart_page","api.mypage_addresses"]),
 ("perm.content_hq","콘텐츠/정책 관리=본사","actor.hq","manage","FAQ/Notice/Banner/Policy",
   ["screen.h_05","api.content_banners","api.coupon_issue"]),
 ("perm.badge_hq","상품 뱃지/입고=본사","actor.hq","manage","Product",
   ["api.products_badges","api.products_inbound"]),
]
for pid,name,actor,action,resource,targets in PERMS:
    node(pid,"permission",name,f"koom/permissions/{pid.split('.')[1]}","prototype" if "hq" in pid or "cs" in pid or "wms" in pid else "backend_docs",
         {"role":actor,"action":action,"resource":resource})
    edge("surface.permissions", pid, "contains")
    edge(pid, actor, "requires")          # permission requires a role(actor)
    for t in targets:
        edge(t, pid, "requires")          # screen/api requires permission

# ---------------------------------------------------------------------------
# 10. Contexts (provenance / evidence)
# ---------------------------------------------------------------------------
CTX = [
 ("ctx.figma_blueprint","Figma · 주문/배송 과정 블루프린트","Figma",
   "단계별 정보 수급 방식·담당자·취소/반품/이슈 정책 서비스 블루프린트. 미정 항목(가격인상 범위 등) 다수 주석."),
 ("ctx.admin_prototype","DK 어드민 프로토타입(HTML)","Prototype",
   "9 페이지(대시보드/주문/고객/물류/CS/직원/통계/기준/콘텐츠) + 3 롤(본사/CS/WMS) 인터랙티브 데모."),
 ("ctx.backend_docs","backend/docs · 24개 API 문서","PRD",
   "엔드포인트·DB 모델·enum·비즈니스 규칙의 1차 구현 기준."),
 ("ctx.screen_spec","화면명세서.md","PRD",
   "41화면 진입조건·API·표시/입력 필드·전이 명세(디자이너용 자연어 + 백엔드 변수)."),
 ("ctx.rtm","요구사항추적표.md","PRD","FR 61건 → 화면 → API → 테스트케이스 추적(RTM)."),
 ("ctx.ia_doc","IA_정보구조.md","PRD","앱 진입→로그인→분기 화면 전환표(연결 검증)."),
]
for cid,name,stype,desc in CTX:
    node(cid,"context",name,f"koom/contexts/{cid.split('.')[1]}",stype.lower(),
         {"source_type":stype,"description":desc})
    edge("surface.contexts", cid, "contains")

# external dependency edges (depends_on)
for api_, actor_, meta in [
    ("api.pay_entry","actor.gmo",{"protocol":"GMO EntryTran"}),
    ("api.pay_execute","actor.gmo",{"protocol":"GMO ExecTran"}),
    ("api.pay_capture","actor.gmo",{"protocol":"GMO AlterTran(SALES)"}),
    ("api.log_dhub_register","actor.dhub",{"protocol":"DHUB /order/add"}),
    ("api.log_dhub_instruct","actor.dhub",{"protocol":"DHUB /delivery/instruction"}),
    ("api.log_tracking_sync","actor.dhub",{"protocol":"DHUB /Tracking"}),
    ("api.scraping_analyze","actor.system",{"service":"scraper-agent"}),
    ("api.tariff_classify","actor.system",{"service":"Claude AI"}),
]:
    edge(api_, actor_, "depends_on", meta)

# seller involvement in issue rules
edge("rule.price_change","actor.seller","derived_from",{"note":"판매처 가격변동 주체"})
edge("rule.delivery_failure","actor.seller","mentioned_in")

# ---------------------------------------------------------------------------
# 10b. API ⇄ Data Model dependency edges (reads / writes)
# ---------------------------------------------------------------------------
RW = [
 ("api.auth_verify","dm.social_account","reads"),
 ("api.auth_line_login","dm.social_account","writes"),
 ("api.products_list","dm.product","reads"),
 ("api.products_page","dm.product","reads"),
 ("api.products_batch","dm.product","writes"),
 ("api.products_detail","dm.product","writes"),
 ("api.products_badges","dm.product","writes"),
 ("api.products_inbound","dm.product","writes"),
 ("api.cart_items","dm.cart_item","writes"),
 ("api.cart_items","dm.cart","writes"),
 ("api.cart_page","dm.cart","reads"),
 ("api.cart_checkout","dm.user_address","reads"),
 ("api.cart_checkout","dm.user_coupon","reads"),
 ("api.cart_checkout","dm.point_log","reads"),
 ("api.orders_create","dm.order_group","writes"),
 ("api.orders_create","dm.order","writes"),
 ("api.orders_group","dm.order_group","reads"),
 ("api.orders_detail","dm.order","reads"),
 ("api.orders_status","dm.order","writes"),
 ("api.orders_status","dm.order_status_log","writes"),
 ("api.orders_statuslog","dm.order_status_log","reads"),
 ("api.orders_actionlog","dm.admin_action_log","reads"),
 ("api.orders_error","dm.error_info","writes"),
 ("api.orders_snapshot","dm.product_snapshot","writes"),
 ("api.orders_snap_pub","dm.product_snapshot","reads"),
 ("api.pay_entry","dm.pg_transaction","writes"),
 ("api.pay_execute","dm.pg_transaction","writes"),
 ("api.pay_capture","dm.pg_transaction","writes"),
 ("api.pay_refund","dm.pg_transaction","writes"),
 ("api.cs_inquiries","dm.inquiry","writes"),
 ("api.cs_inquiry_reply","dm.inquiry","writes"),
 ("api.cs_cancel","dm.cancel_request","writes"),
 ("api.cs_refund","dm.refund_request","writes"),
 ("api.cs_refund_patch","dm.refund_request","writes"),
 ("api.cs_refund_exec","dm.refund_request","writes"),
 ("api.cs_refund_exec","dm.pg_transaction","writes"),
 ("api.cs_refund_exec","dm.order","writes"),
 ("api.cs_purchase_tasks","dm.order","reads"),
 ("api.cs_purchase_done","dm.purchase_record","writes"),
 ("api.cs_purchase_done","dm.order","writes"),
 ("api.cs_purchase_done","dm.error_info","writes"),
 ("api.log_inspection","dm.logistics_info","writes"),
 ("api.log_inspection","dm.inquiry","writes"),
 ("api.log_dhub_register","dm.shipping_tracking","writes"),
 ("api.log_dhub_register","dm.product_hs","reads"),
 ("api.log_dhub_instruct","dm.shipping_tracking","writes"),
 ("api.log_tracking_sync","dm.shipping_tracking","writes"),
 ("api.log_timeline","dm.tracking_event","reads"),
 ("api.log_timeline_post","dm.tracking_event","writes"),
 ("api.log_stagnated","dm.shipping_tracking","reads"),
 ("api.log_customs","dm.customs_clearance","writes"),
 ("api.log_customs_refund","dm.customs_clearance","writes"),
 ("api.tariff_classify","dm.product_hs","reads"),
 ("api.tariff_classification","dm.product_hs","writes"),
 ("api.pricing_quote","dm.exchange_rate_log","reads"),
 ("api.pricing_fx","dm.exchange_rate_log","writes"),
 ("api.shipping_quote","dm.shipping_rate","reads"),
 ("api.mypage_addresses","dm.user_address","writes"),
 ("api.mypage_points","dm.point_log","reads"),
 ("api.mypage_coupons","dm.user_coupon","reads"),
 ("api.coupon_issue","dm.coupon","reads"),
 ("api.coupon_issue","dm.user_coupon","writes"),
 ("api.content_banners","dm.event_banner","reads"),
 ("api.ops_error_criteria","dm.error_criteria","writes"),
 ("api.prohibited_check","dm.prohibited","reads"),
 ("api.templates_build","dm.site_template","writes"),
 ("api.scraping_analyze","dm.site_template","reads"),
 ("api.stats_monitoring","dm.order","reads"),
 ("api.stats_monitoring","dm.shipping_tracking","reads"),
 ("api.orders_admin_dash","dm.order","reads"),
 ("api.malls_list","dm.supported_site","reads"),
]
for a,d,rel in RW:
    if a in api_ids and d in dm_ids:
        edge(a,d,rel)

# ---------------------------------------------------------------------------
# 11. Projections (descriptive — not nodes; documented in output meta)
# ---------------------------------------------------------------------------
PROJECTIONS = [
 {"name":"User Flow","derive":"screen + transitions_to","desc":"화면 전이만 추출한 사용자 플로우"},
 {"name":"ERD","derive":"data_model + belongs_to/derived_from","desc":"도메인 모델 관계도"},
 {"name":"API Spec","derive":"api + reads/writes(data_model)","desc":"엔드포인트 계약"},
 {"name":"Requirement(RTM)","derive":"screen.requirements + business_rule + validation","desc":"요구사항 추적"},
 {"name":"State Machine","derive":"state + transitions_to","desc":"상태 전이도(주문/CS/검수/지연)"},
 {"name":"Permission Matrix","derive":"actor × permission × resource","desc":"권한 매트릭스"},
 {"name":"Impact Map","derive":"governed_by/impacts/depends_on","desc":"변경 전파 영향 집합"},
]

# ---------------------------------------------------------------------------
# write out
# ---------------------------------------------------------------------------
counts = {}
for n in NODES:
    counts[n["type"]] = counts.get(n["type"],0)+1
rel_counts = {}
for e in EDGES:
    rel_counts[e["relation"]] = rel_counts.get(e["relation"],0)+1

doc = {
 "schema": "koom-ia/1.0",
 "generated_at": TODAY,
 "project": {
   "id": PROJECT,
   "name": "KOOM 구매대행 플랫폼",
   "description": "일본 고객 대상 한국 상품 구매대행·국제배송 크로스보더 커머스 IA",
   "backbone_relation": "contains",
   "node_types": sorted(counts.keys()),
   "edge_relations": sorted(rel_counts.keys()),
   "sources": [c[0] for c in CTX],
 },
 "stats": {"nodes": len(NODES), "edges": len(EDGES),
           "by_node_type": counts, "by_relation": rel_counts},
 "glossary": {
   "note": ("문서 렌더링에 쓰이는 모든 한글 라벨·예시·가이드는 IA에 저장됨 — "
            "enum 라벨/필드 가이드는 각 data_model 노드의 payload.enum_labels / payload.field_guide, "
            "경로 파라미터 라벨은 아래 param_labels. 렌더러는 별도 도메인 지식을 갖지 않음."),
   "param_labels": {
     "group_number":"그룹번호","order_number":"주문번호","order":"주문번호","id":"리소스 ID","pk":"리소스 ID",
     "cid":"고객 ID","customer_id":"고객 ID","uuid":"스냅샷 UUID","snapshot_uuid":"스냅샷 UUID",
     "slug":"몰 slug","domain":"도메인","policy_type":"정책유형","addr_id":"주소 ID","item_id":"항목 ID","photo_id":"사진 ID",
   },
 },
 "projections": PROJECTIONS,
 "nodes": NODES,
 "edges": EDGES,
}

# validate edge endpoints
ids = set(n["id"] for n in NODES)
bad = [(e["from"],e["to"],e["relation"]) for e in EDGES if e["from"] not in ids or e["to"] not in ids]
if bad:
    print("WARNING: dangling edges:", bad[:20], "...", len(bad))

out_dir = os.path.dirname(os.path.abspath(__file__))
out_path = os.path.join(out_dir, "koom_ia.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(doc, f, ensure_ascii=False, indent=2)

print("nodes:", len(NODES), "edges:", len(EDGES))
print("by type:", counts)
print("by relation:", rel_counts)
if MISSING_LABELS:
    print("WARNING: enum codes without a 한글 label (would render as raw code):", MISSING_LABELS)
else:
    print("integrity OK: 모든 enum 코드에 IA 한글 라벨 존재")
if MISSING_EXAMPLES:
    print("WARNING: fields without an IA example value:", sorted(set(MISSING_EXAMPLES)))
else:
    print("integrity OK: 모든 data_model 필드에 IA 예시 데이터 존재")
print("wrote", out_path)

# ---------------------------------------------------------------------------
# Self-contained interactive visualization (vanilla JS canvas force graph)
# ---------------------------------------------------------------------------
data_json = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
HTML = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>KOOM IA · 정보구조 그래프</title>
<style>
:root{--bg:#0b1020;--panel:#121a2f;--panel2:#0f1729;--line:#26324d;--txt:#e7ecf5;--mut:#8a97b3;--acc:#4f8cff}
*{box-sizing:border-box}html,body{margin:0;height:100%}
body{background:var(--bg);color:var(--txt);font:13px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Noto Sans KR",sans-serif;overflow:hidden}
#app{display:flex;height:100vh}
#side{width:300px;flex:none;background:var(--panel);border-right:1px solid var(--line);display:flex;flex-direction:column}
#side header{padding:14px 16px;border-bottom:1px solid var(--line)}
#side header h1{margin:0;font-size:15px;letter-spacing:.2px}
#side header .sub{color:var(--mut);font-size:11px;margin-top:3px}
#scroll{overflow:auto;padding:12px 14px;flex:1}
.sec{margin-bottom:16px}
.sec h2{font-size:11px;text-transform:uppercase;letter-spacing:.8px;color:var(--mut);margin:0 0 8px}
.preset{display:flex;flex-wrap:wrap;gap:6px}
.preset button{background:var(--panel2);color:var(--txt);border:1px solid var(--line);border-radius:7px;padding:6px 9px;font-size:11.5px;cursor:pointer}
.preset button:hover{border-color:var(--acc)}
.preset button.on{background:var(--acc);border-color:var(--acc);color:#fff}
.chk{display:flex;align-items:center;gap:7px;padding:3px 4px;border-radius:6px;cursor:pointer;font-size:12px}
.chk:hover{background:var(--panel2)}
.chk input{accent-color:var(--acc)}
.dot{width:10px;height:10px;border-radius:3px;flex:none}
.cnt{margin-left:auto;color:var(--mut);font-size:11px}
#search{width:100%;padding:8px 10px;background:var(--panel2);border:1px solid var(--line);border-radius:8px;color:var(--txt);font-size:12px}
#main{flex:1;position:relative}
canvas{display:block;width:100%;height:100%}
#detail{position:absolute;top:12px;right:12px;width:330px;max-height:calc(100% - 24px);overflow:auto;background:rgba(15,23,41,.96);border:1px solid var(--line);border-radius:12px;padding:14px 16px;display:none;backdrop-filter:blur(6px)}
#detail.show{display:block}
#detail .x{float:right;cursor:pointer;color:var(--mut);font-size:16px}
#detail h3{margin:0 6px 2px 0;font-size:14px}
#detail .tag{display:inline-block;font-size:10px;padding:2px 7px;border-radius:20px;margin:6px 0;color:#fff}
#detail .path{color:var(--mut);font-size:11px;word-break:break-all;margin-bottom:8px}
#detail .desc{font-size:12px;margin:8px 0;color:#cdd6ea}
#detail table{width:100%;border-collapse:collapse;font-size:11.5px}
#detail td{padding:3px 4px;vertical-align:top;border-top:1px solid var(--line)}
#detail td:first-child{color:var(--mut);white-space:nowrap;width:34%}
#detail .edges li{font-size:11.5px;margin:2px 0;color:#cdd6ea;list-style:none}
#detail .edges{padding-left:0}
#detail .rel{color:var(--acc);font-weight:600}
.kv{font-size:11px;color:var(--mut)}
#legend2{position:absolute;left:12px;bottom:12px;background:rgba(15,23,41,.9);border:1px solid var(--line);border-radius:10px;padding:8px 10px;font-size:11px;color:var(--mut);max-width:520px}
#hud{position:absolute;left:12px;top:12px;background:rgba(15,23,41,.9);border:1px solid var(--line);border-radius:10px;padding:8px 11px;font-size:11px;color:var(--mut)}
#hud b{color:var(--txt)}
.btny{background:var(--panel2);color:var(--txt);border:1px solid var(--line);border-radius:7px;padding:5px 9px;font-size:11px;cursor:pointer}
.row{display:flex;gap:6px;margin-top:8px}
small.note{color:var(--mut)}
a{color:var(--acc)}
</style></head><body>
<div id="app">
  <div id="side">
    <header>
      <h1>KOOM · IA 그래프</h1>
      <div class="sub">기획 에이전트 산출물 예시 — Node/Edge 그래프</div>
    </header>
    <div id="scroll">
      <div class="sec">
        <h2>투영 (Projection)</h2>
        <div class="preset" id="presets"></div>
      </div>
      <div class="sec">
        <h2>검색</h2>
        <input id="search" placeholder="이름·코드·경로 검색…">
      </div>
      <div class="sec">
        <h2>노드 타입</h2>
        <div id="types"></div>
      </div>
      <div class="sec">
        <h2>관계 (Edge)</h2>
        <div id="rels"></div>
      </div>
      <div class="sec">
        <div class="row"><button class="btny" id="resetView">뷰 리셋</button>
        <button class="btny" id="allOn">모두 표시</button>
        <button class="btny" id="freeze">정지/재생</button></div>
        <small class="note" id="srcnote"></small>
      </div>
    </div>
  </div>
  <div id="main">
    <canvas id="cv"></canvas>
    <div id="hud"></div>
    <div id="legend2"></div>
    <div id="detail"></div>
  </div>
</div>
<script id="ia-data" type="application/json">__DATA__</script>
<script>
const DOC = JSON.parse(document.getElementById('ia-data').textContent);
const NODES = DOC.nodes, EDGES = DOC.edges;
const byId = {}; NODES.forEach(n=>byId[n.id]=n);

const TYPE_COLOR = {
  project:'#f5d76e', surface:'#5b6b8c', actor:'#ff7ab6', screen:'#4f8cff',
  component:'#7cc7ff', data_model:'#2dd4bf', api:'#a78bfa', business_rule:'#fb7185',
  validation:'#fbbf24', permission:'#f97316', context:'#94a3b8', state_machine:'#34d399',
  state:'#86efac'
};
const TYPE_LABEL = {project:'프로젝트',surface:'그룹',actor:'액터',screen:'화면',component:'컴포넌트',
  data_model:'데이터모델',api:'API',business_rule:'비즈니스규칙',validation:'검증',permission:'권한',
  context:'컨텍스트',state_machine:'상태머신',state:'상태'};
const REL_COLOR = {contains:'#3a4a6b',transitions_to:'#4f8cff',calls:'#a78bfa',reads:'#2dd4bf',
  writes:'#14b8a6',requires:'#f97316',validated_by:'#fbbf24',governed_by:'#fb7185',
  derived_from:'#94a3b8',mentioned_in:'#64748b',impacts:'#f43f5e',depends_on:'#eab308',
  belongs_to:'#22d3ee',operates:'#ff7ab6'};
const relColor = r => REL_COLOR[r] || '#3a4a6b';

const PRESETS = {
 '전체 IA':{types:'*',rels:'*'},
 'User Flow':{types:['screen','actor'],rels:['transitions_to','operates']},
 '화면→API→데이터':{types:['screen','api','data_model'],rels:['calls','reads','writes']},
 'ERD (데이터)':{types:['data_model'],rels:['belongs_to','derived_from']},
 'API ↔ 데이터':{types:['api','data_model'],rels:['reads','writes']},
 '상태 머신':{types:['state_machine','state'],rels:['transitions_to','contains']},
 '권한 매트릭스':{types:['actor','permission','screen','api'],rels:['requires','operates']},
 '규칙·영향(Impact)':{types:['business_rule','validation','screen','api','data_model','state'],rels:['governed_by','validated_by','impacts','depends_on']},
 '근거(Provenance)':{types:['context','business_rule','screen'],rels:['derived_from','mentioned_in']},
 '컨테인먼트 트리':{types:'*',rels:['contains']},
};

const allTypes = [...new Set(NODES.map(n=>n.type))];
const allRels  = [...new Set(EDGES.map(e=>e.relation))];
const typeCount = {}; NODES.forEach(n=>typeCount[n.type]=(typeCount[n.type]||0)+1);
const relCount = {}; EDGES.forEach(e=>relCount[e.relation]=(relCount[e.relation]||0)+1);

let activeTypes = new Set(allTypes), activeRels = new Set(allRels), query='';

// ---- positions / physics ----
const W0=()=>cv.clientWidth, H0=()=>cv.clientHeight;
NODES.forEach((n,i)=>{ const a=i/NODES.length*Math.PI*2; n.x=Math.cos(a)*300+Math.random()*40; n.y=Math.sin(a)*300+Math.random()*40; n.vx=0; n.vy=0; });
// seed by type bands
const typeBand={}; allTypes.forEach((t,i)=>typeBand[t]=i);
NODES.forEach(n=>{ n.x += (typeBand[n.type]-allTypes.length/2)*40; });

const adj={}; NODES.forEach(n=>adj[n.id]=[]);
EDGES.forEach(e=>{ if(adj[e.from]&&adj[e.to]){adj[e.from].push(e.to);adj[e.to].push(e.from);} });

let frozen=false;
function visibleNode(n){
  if(!activeTypes.has(n.type)) return false;
  if(query){ const q=query.toLowerCase();
    return (n.name||'').toLowerCase().includes(q)||(n.id||'').toLowerCase().includes(q)||(n.path||'').toLowerCase().includes(q)
      || adjMatchesQuery(n); }
  return true;
}
function adjMatchesQuery(n){ return false; }
function visEdges(){ return EDGES.filter(e=>activeRels.has(e.relation)&&isVis(byId[e.from])&&isVis(byId[e.to])); }
const _visCache={v:null};
function isVis(n){ return n && n.__vis; }
function recomputeVis(){
  NODES.forEach(n=>n.__vis=false);
  // base: type filter + query
  NODES.forEach(n=>{ if(activeTypes.has(n.type)){ if(!query){n.__vis=true;} else {
     const q=query.toLowerCase();
     if((n.name||'').toLowerCase().includes(q)||(n.id||'').toLowerCase().includes(q)||(n.path||'').toLowerCase().includes(q)) n.__vis=true;
  }}});
  if(query){ // include direct neighbors of matches (any type within activeTypes)
    const matched=NODES.filter(n=>n.__vis).map(n=>n.id);
    matched.forEach(id=>adj[id].forEach(nb=>{ if(activeTypes.has(byId[nb].type)) byId[nb].__vis=true; }));
  }
}

// ---- physics step ----
function step(){
  const vis=NODES.filter(n=>n.__vis);
  const k=0.02, rep=2600, cl=0.86;
  for(let i=0;i<vis.length;i++){ const a=vis[i];
    for(let j=i+1;j<vis.length;j++){ const b=vis[j];
      let dx=a.x-b.x, dy=a.y-b.y, d2=dx*dx+dy*dy+0.01; let d=Math.sqrt(d2);
      if(d>360) continue; let f=rep/d2; let fx=dx/d*f, fy=dy/d*f;
      a.vx+=fx;a.vy+=fy;b.vx-=fx;b.vy-=fy;
    }
    a.vx += -a.x*0.0009; a.vy += -a.y*0.0009; // gravity to center
  }
  visEdges().forEach(e=>{ const a=byId[e.from],b=byId[e.to];
    let dx=b.x-a.x, dy=b.y-a.y, d=Math.sqrt(dx*dx+dy*dy)+.01;
    const L = e.relation==='contains'?70:120;
    let f=(d-L)*k; let fx=dx/d*f, fy=dy/d*f;
    a.vx+=fx;a.vy+=fy;b.vx-=fx;b.vy-=fy;
  });
  vis.forEach(n=>{ if(n===drag) return; n.x+=n.vx*=cl; n.y+=n.vy; n.vy*=cl; });
}

// ---- canvas / camera ----
const cv=document.getElementById('cv'), ctx=cv.getContext('2d');
let cam={x:0,y:0,z:0.85}, drag=null, pan=false, last=null, sel=null, hover=null;
function resize(){ const r=devicePixelRatio||1; cv.width=cv.clientWidth*r; cv.height=cv.clientHeight*r; ctx.setTransform(r,0,0,r,0,0); }
addEventListener('resize',resize);
function toScreen(n){ return {x:(n.x*cam.z)+W0()/2+cam.x, y:(n.y*cam.z)+H0()/2+cam.y}; }
function toWorld(px,py){ return {x:(px-W0()/2-cam.x)/cam.z, y:(py-H0()/2-cam.y)/cam.z}; }

function radius(n){ return n.type==='project'?13:n.type==='surface'?9:n.type==='screen'?7:n.type==='state_machine'?8:6; }

function draw(){
  ctx.clearRect(0,0,W0(),H0());
  const ve=visEdges();
  // edges
  ctx.lineWidth=1;
  ve.forEach(e=>{ const a=toScreen(byId[e.from]), b=toScreen(byId[e.to]);
    const hot = sel && (e.from===sel.id||e.to===sel.id);
    ctx.strokeStyle = hot? '#ffffff' : (relColor(e.relation)+ (cam.z<0.6?'55':'33'));
    ctx.globalAlpha = hot?0.95:(sel?0.12:0.5);
    ctx.beginPath();ctx.moveTo(a.x,a.y);
    if(e.relation==='contains'){ctx.lineTo(b.x,b.y);} else {
      const mx=(a.x+b.x)/2,my=(a.y+b.y)/2-((b.x-a.x)*0.08);
      ctx.quadraticCurveTo(mx,my,b.x,b.y);
    }
    ctx.stroke();
    if(hot){ // arrow
      const ang=Math.atan2(b.y-a.y,b.x-a.x); ctx.fillStyle='#fff';
      ctx.beginPath();ctx.moveTo(b.x,b.y);
      ctx.lineTo(b.x-9*Math.cos(ang-.4),b.y-9*Math.sin(ang-.4));
      ctx.lineTo(b.x-9*Math.cos(ang+.4),b.y-9*Math.sin(ang+.4));ctx.fill();
    }
  });
  ctx.globalAlpha=1;
  // nodes
  const vis=NODES.filter(n=>n.__vis);
  vis.forEach(n=>{ const p=toScreen(n), r=radius(n)*(cam.z<1?1:cam.z*0.9);
    const dim = sel && sel!==n && !adj[sel.id].includes(n.id);
    ctx.globalAlpha = dim?0.22:1;
    ctx.beginPath();ctx.arc(p.x,p.y,r,0,7);ctx.fillStyle=TYPE_COLOR[n.type]||'#888';ctx.fill();
    if(n===sel){ctx.lineWidth=2.5;ctx.strokeStyle='#fff';ctx.stroke();}
    else if(n===hover){ctx.lineWidth=2;ctx.strokeStyle='#fff9';ctx.stroke();}
    // labels
    if(cam.z>0.95 || n.type==='surface'||n.type==='project'||n===hover||n===sel || vis.length<70){
      ctx.globalAlpha=dim?0.3:0.92;ctx.fillStyle='#dde6f7';
      ctx.font=(n.type==='surface'||n.type==='project'?'700 ':'')+(11)+'px sans-serif';
      const lbl=(n.name||n.id);
      ctx.fillText(lbl.length>26?lbl.slice(0,25)+'…':lbl, p.x+r+3, p.y+4);
    }
  });
  ctx.globalAlpha=1;
}

function loop(){ if(!frozen){ for(let i=0;i<2;i++) step(); } draw(); requestAnimationFrame(loop); }

// ---- interaction ----
function pick(px,py){ let best=null,bd=14; const vis=NODES.filter(n=>n.__vis);
  for(const n of vis){ const p=toScreen(n); const d=Math.hypot(p.x-px,p.y-py); if(d<bd+radius(n)){bd=d;best=n;} } return best; }
cv.addEventListener('mousedown',e=>{ const n=pick(e.offsetX,e.offsetY); if(n){drag=n;} else {pan=true;} last={x:e.offsetX,y:e.offsetY}; });
addEventListener('mousemove',e=>{ const rect=cv.getBoundingClientRect(); const px=e.clientX-rect.left,py=e.clientY-rect.top;
  if(drag){ const w=toWorld(px,py); drag.x=w.x;drag.y=w.y;drag.vx=0;drag.vy=0; }
  else if(pan&&last){ cam.x+=px-last.x;cam.y+=py-last.y;last={x:px,y:py}; }
  else { hover=pick(px,py); cv.style.cursor=hover?'pointer':'default'; }
});
addEventListener('mouseup',e=>{ if(drag&&last){ const moved=Math.hypot(e.offsetX-last.x,e.offsetY-last.y); if(moved<4) select(drag); }
  else if(pan&&last){ const moved=Math.hypot((e.offsetX||0)-last.x,(e.offsetY||0)-last.y); }
  drag=null;pan=false;last=null; });
cv.addEventListener('click',e=>{ const n=pick(e.offsetX,e.offsetY); if(!n){ select(null);} });
cv.addEventListener('wheel',e=>{ e.preventDefault(); const f=e.deltaY<0?1.1:1/1.1;
  const w=toWorld(e.offsetX,e.offsetY); cam.z=Math.max(0.2,Math.min(3,cam.z*f));
  const w2=toWorld(e.offsetX,e.offsetY); cam.x+=(w2.x-w.x)*cam.z; cam.y+=(w2.y-w.y)*cam.z; },{passive:false});

function select(n){ sel=n; const d=document.getElementById('detail');
  if(!n){ d.classList.remove('show'); return; }
  const ins=EDGES.filter(e=>e.to===n.id), outs=EDGES.filter(e=>e.from===n.id);
  const pl=n.payload||{};
  let rows='';
  for(const[k,v] of Object.entries(pl)){
    let val = Array.isArray(v)? v.join(', ') : (typeof v==='object'? JSON.stringify(v): String(v));
    rows+=`<tr><td>${k}</td><td>${esc(val)}</td></tr>`;
  }
  const eList = es => es.slice(0,40).map(e=>{ const other = e.from===n.id?e.to:e.from; const dir=e.from===n.id?'→':'←';
     return `<li><span class="rel">${e.relation}</span> ${dir} ${esc((byId[other]||{}).name||other)}</li>`; }).join('');
  d.innerHTML = `<span class="x" onclick="select(null)">×</span>
    <span class="tag" style="background:${TYPE_COLOR[n.type]}">${TYPE_LABEL[n.type]||n.type}</span>
    <h3>${esc(n.name)}</h3>
    <div class="path">${esc(n.path)}</div>
    <div class="kv">id: ${esc(n.id)} · origin: ${esc(n.origin_context)} · v${n.version}</div>
    ${pl.description?`<div class="desc">${esc(pl.description)}</div>`:''}
    ${pl.summary?`<div class="desc">${esc(pl.summary)}</div>`:''}
    ${rows?`<table>${rows}</table>`:''}
    <div style="margin-top:10px"><b style="font-size:11px;color:var(--mut)">나가는 관계 (${outs.length})</b>
      <ul class="edges">${eList(outs)}</ul></div>
    <div><b style="font-size:11px;color:var(--mut)">들어오는 관계 (${ins.length})</b>
      <ul class="edges">${eList(ins)}</ul></div>`;
  d.classList.add('show');
}
const esc=s=>String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

// ---- UI build ----
function buildUI(){
  const pr=document.getElementById('presets');
  Object.keys(PRESETS).forEach(name=>{ const b=document.createElement('button'); b.textContent=name;
    b.onclick=()=>applyPreset(name,b); pr.appendChild(b); });
  pr.firstChild.classList.add('on');

  const tw=document.getElementById('types');
  allTypes.sort((a,b)=>typeCount[b]-typeCount[a]).forEach(t=>{
    const l=document.createElement('label'); l.className='chk';
    l.innerHTML=`<input type=checkbox checked><span class=dot style="background:${TYPE_COLOR[t]}"></span>${TYPE_LABEL[t]||t}<span class=cnt>${typeCount[t]}</span>`;
    l.querySelector('input').onchange=ev=>{ ev.target.checked?activeTypes.add(t):activeTypes.delete(t); recomputeVis(); };
    tw.appendChild(l);
  });
  const rw=document.getElementById('rels');
  allRels.sort((a,b)=>relCount[b]-relCount[a]).forEach(r=>{
    const l=document.createElement('label'); l.className='chk';
    l.innerHTML=`<input type=checkbox checked><span class=dot style="background:${relColor(r)}"></span>${r}<span class=cnt>${relCount[r]}</span>`;
    l.querySelector('input').onchange=ev=>{ ev.target.checked?activeRels.add(r):activeRels.delete(r); };
    l.dataset.rel=r; rw.appendChild(l);
  });
  document.getElementById('search').oninput=e=>{ query=e.target.value.trim(); recomputeVis(); };
  document.getElementById('resetView').onclick=()=>{cam={x:0,y:0,z:0.85};};
  document.getElementById('freeze').onclick=()=>{frozen=!frozen;};
  document.getElementById('allOn').onclick=()=>{ applyPreset('전체 IA', document.querySelector('#presets button')); };
  document.getElementById('srcnote').innerHTML='출처: '+DOC.project.sources.length+'개 컨텍스트 · 노드 '+DOC.stats.nodes+' · 엣지 '+DOC.stats.edges;
  // legend + hud
  document.getElementById('legend2').innerHTML = allTypes.map(t=>`<span style="margin-right:10px"><span class="dot" style="display:inline-block;background:${TYPE_COLOR[t]}"></span> ${TYPE_LABEL[t]||t}</span>`).join('');
}
function applyPreset(name,btn){ document.querySelectorAll('#presets button').forEach(b=>b.classList.remove('on')); if(btn)btn.classList.add('on');
  const p=PRESETS[name];
  activeTypes = new Set(p.types==='*'?allTypes:p.types);
  activeRels  = new Set(p.rels==='*'?allRels:p.rels);
  // sync checkboxes
  document.querySelectorAll('#types .chk').forEach(l=>{ const t=l.textContent.replace(/[0-9]/g,'').trim(); });
  document.querySelectorAll('#types .chk input').forEach((inp,i)=>{});
  syncChecks(); recomputeVis();
  cam={x:0,y:0,z:0.85}; sel=null; document.getElementById('detail').classList.remove('show');
}
function syncChecks(){
  document.querySelectorAll('#types .chk').forEach(l=>{ const lbl=l.childNodes; });
  const typeLabels={}; Object.entries(TYPE_LABEL).forEach(([k,v])=>typeLabels[v]=k);
  document.querySelectorAll('#types .chk').forEach(l=>{ const name=l.querySelector('.cnt').previousSibling.textContent.trim();
     const t = typeLabels[name]||name; l.querySelector('input').checked=activeTypes.has(t); });
  document.querySelectorAll('#rels .chk').forEach(l=>{ l.querySelector('input').checked=activeRels.has(l.dataset.rel); });
}
function hud(){ const v=NODES.filter(n=>n.__vis).length, e=visEdges().length;
  document.getElementById('hud').innerHTML=`표시 노드 <b>${v}</b> · 엣지 <b>${e}</b> · 줌 ${cam.z.toFixed(2)}× <br><span style="opacity:.7">드래그=이동 · 휠=줌 · 노드클릭=상세</span>`; }
setInterval(hud,200);

resize(); buildUI(); recomputeVis(); loop();
</script></body></html>"""
HTML = HTML.replace("__DATA__", data_json)
html_path = os.path.join(out_dir, "koom_ia.html")
with open(html_path, "w", encoding="utf-8") as f:
    f.write(HTML)
print("wrote", html_path, "(", round(len(HTML)/1024), "KB )")
