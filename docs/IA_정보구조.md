# KOOM 정보 구조 (IA)

> 앱 진입 → 로그인 → 화면 분기 흐름을 단계별로 정의합니다. 각 노드에는 **진입 조건 / 필요 데이터 / 다음 화면(분기)** 을 명시합니다.
> 시각화: [ia.html](./ia.html) · 관련 문서: [화면 명세서](./화면명세서.md) · [요구사항 추적표](./요구사항추적표.md)

- 액터: **고객**(앱) / **CS**(현장 실행) / **본사**(관리) / **시스템**(백그라운드)
- 표기: `→` 다음 화면, `⎇` 조건 분기, `↺` 비동기/폴링, `[필요]` 진입에 필요한 데이터

---

## 0. 진입 플로우 (앱 시작 → 로그인 → 분기)

```
[앱 실행]
   │
   ▼
 토큰 보유?
   │
   ├─ 아니오 ─▶ S-01 LINE 로그인 ──(OAuth code)──▶ JWT 발급 ─┐
   │                                                          │
   └─ 예(JWT 유효) ───────────────────────────────────────────┤
                                                              ▼
                                                       S-02 홈 (메인)
                                                              │
        ┌───────────────┬───────────────┬──────────────┬─────┴──────┬───────────────┬──────────────┐
        ▼               ▼               ▼              ▼            ▼               ▼              ▼
   S-01b URL입력    S-03 상품목록    S-05 쇼핑몰     S-06 장바구니   S-09 주문목록   S-14 마이페이지  S-16~18 콘텐츠
        │               │               │              │            │               │
        ▼               ▼               ▼              ▼            ▼               ├─ S-14a 배송지
   (스크래핑)       S-04 상품상세 ◀──────┘         S-07 결제       S-10 주문상세    ├─ S-14b 포인트
        │               │                              │            │               ├─ S-14c 쿠폰
        └──▶ S-04 상품상세                             ▼            ├─ S-11 문의      ├─ S-14d 알림설정
                        │                         S-08 주문완료    ├─ S-12 취소      └─ S-14e 위시리스트
                        ▼                              │            └─ S-13 환불
                   S-06 장바구니 ◀────────────────────┘
```

---

## 0-1. 화면 전환표 (연결 검증)

> 각 화면의 **들어오는 경로(in)** 와 **나가는 경로(out)** 를 하나하나 확인한 표입니다. 공통 화면(S-04·S-06·S-10)은 **1개 노드**이며, 여러 곳에서 들어와도 나가는 출구는 항상 동일합니다.

### 고객 앱
| 화면 | 들어옴 (in) | 나감 (out) |
|------|-------------|------------|
| S-01 로그인 | 앱 실행(토큰 없음) | → S-02 |
| S-02 홈(허브) | S-01, 토큰 유효 진입 | → S-01b · S-03 · S-05 · S-09 · S-14 · S-16~18 / (하단탭) S-06 |
| S-01b URL 입력 | S-02 | → **S-04** |
| S-03 상품 목록 | S-02 | → **S-04** |
| S-05 쇼핑몰 | S-02 | → **S-04** |
| **S-04 상품 상세** | **S-01b · S-03 · S-05** (수렴) | → S-06(담기) · S-14e(위시) |
| S-06 장바구니 | S-04, (하단탭) S-02 | → S-07(선택 결제) |
| S-07 결제 | S-06 | → S-08 |
| S-08 주문 완료 | S-07 | → S-10 / S-02 |
| S-09 주문 목록 | S-02 | → S-10 |
| **S-10 주문 상세** | **S-08 · S-09** (수렴) | → S-11 · S-12 · S-13 · P-01 |
| S-11~13 문의·취소·환불 | S-10 | → (처리 후 상태 조회) |
| S-14 마이(a~e) | S-02 | (내부 서브: 배송지·포인트·쿠폰·알림·위시) |
| S-16~18 콘텐츠 | S-02 | (조회) |
| P-01 세관 스냅샷 | S-10, H-04(링크 발급) | (공개 페이지, 종단) |

### CS 콘솔 (process 체인)
| 화면 | 들어옴 (in) | 나감 (out) |
|------|-------------|------------|
| C-05 담당 추적(허브) | CS 로그인 | → C-01 · C-02 · C-03 · C-04 (드릴다운) |
| C-01 대리구매 | C-05, 결제완료(paid) 주문 | → C-02 (구매완료·입고 후) |
| C-02 검수 | C-01(입고), C-05 | → C-03 (검수완료 후) |
| C-03 FastBox 인계 | C-02(검수완료), C-05 | → (국제배송, 시스템 추적) |
| C-04 CS 응대 | C-05 | → H-03 (환불 승인 인계) |

### 본사 어드민 (radial)
| 화면 | 들어옴 (in) | 나감 (out) |
|------|-------------|------------|
| H-11 모니터링(허브) | 본사 로그인 | → H-01·02 / H-03·04 / H-05~10 (드릴다운) |
| H-03 결제·정산 | H-11, C-04(환불 인계) | → (Capture·환불 실행, 종단) |
| H-04 스냅샷·영문명 | H-11 | → P-01 (공개 링크 발급) |

---

## 1. 고객 앱 — 화면별 진입 조건 / 필요 데이터 / 분기

### S-01 · LINE 로그인  `[필요: 없음(비인증)]`
- **진입**: 토큰 없음 / 만료
- **흐름**: `GET /api/auth/line/login/` → LINE 동의 → `callback/?code=` → JWT + `customer_id, display_name, picture_url, is_new`
- **→ 분기**: 성공 → **S-02 홈** / `is_new=true` → (선택) 온보딩

### S-02 · 홈(메인)  `[필요: JWT(customer_id)]`
- **표시 데이터**:
  - 이벤트 배너 — `EventBanner(image_url, link_url, starts_at~ends_at)` 활성분
  - 추천 쇼핑몰 카테고리 — `FeaturedCategory(mall, category_name, display_title)`
  - 카테고리 칩 — `Product.category` distinct
  - 추천 상품 — `Product(is_recommended=true)`
  - 최근 본 URL — `UrlVisit(customer_id)`
- **⎇ 분기**: URL 입력바 → **S-01b** · 카테고리/추천 → **S-03** · 몰 → **S-05** · 배너 link_url → 외부/이벤트 · 하단탭 → 장바구니/주문/마이/콘텐츠

### S-01b · URL 입력 → 즉석 스크래핑  `[필요: JWT, 상품 URL]`
- **입력**: `url`(상품 링크), (내부) `customer_id, category=shopping, page_type=auto`
- **처리**: `POST /api/scraping/analyze/` → `ScrapeRequest.status: pending→processing→completed/failed` → `ScrapeResult.raw_data`
- **표시**: 스크래핑 진행 상태, 결과 상품 카드(title·images·price), 미지원 사이트 안내
- **⎇ 분기**: 결과 카드 → **S-04 상품상세** · 담기 → **S-06**

### S-03 · 상품 목록(카탈로그)  `[필요: JWT, (선택) category/mall 필터]`
- **표시(목록 카드)**: `Product` → title, images[0], price_original/price_discounted, currency, brand, 뱃지(is_limited/is_recommended), detail_status, rating, review_count
- **조회**: `GET /api/products/?category=&mall=&is_recommended=`
- **⎇ 분기**: 카드 → **S-04** · 정렬/필터 변경 → 재조회

### S-04 · 상품 상세  `[필요: JWT, product_id]`
- **조회**: `GET /api/products/{id}/page/` → 상품 + **가격 계산(JPY 환산+배송+관세+소비세)** + 배송 소요일 + 결제수단
- **표시**: images 갤러리, title/brand, options(detail_data), price 내역, availability, 배송 단계, detail_status(pending이면 크롤 대기)
- **동작**: detail_status=failed/오래됨 → `POST /{id}/refresh/`
- **⎇ 분기**: 장바구니 담기 → **S-06** · 위시 → **S-14e** · 구매 → **S-07**

### S-05 · 쇼핑몰별 탐색  `[필요: JWT, (선택) slug]`
- **표시**: 활성 몰 목록 `KoreanMall(name, logo_url)`; 몰 상세 → 카테고리별 상품수 `MallCategory(category_name, products_count)`; 추천 상품
- **조회**: `/api/malls/`, `/{slug}/`, `/{slug}/products/?category=`, `/{slug}/recommended/`
- **⎇ 분기**: 상품 → **S-04**

### S-06 · 장바구니(선택)  `[필요: JWT, customer_id]`
- **조회**: `GET /api/cart/{cid}/page/` → items + 브랜드/사이트명 + **JPY 환산가** + 포인트 적립 예상 + 배송 예상
- **항목 데이터**: `CartItem` → product_url, title, brand, options[], price_final, currency, quantity
- **동작**: 추가 `POST items/`, 수정 `PATCH items/{id}/`(quantity/options/price), 삭제 `DELETE`, 전체비우기 `DELETE /cart/{cid}/`
- **⎇ 분기**: **선택 항목** 체크 → 결제 → **S-07**

### S-07 · 결제(체크아웃)  `[필요: JWT, 선택된 cart item, 배송지]`
- **통합 조회**: `GET /api/cart/{cid}/checkout/` → items, **addresses(UserAddress)**, points(balance), coupons(UserCoupon), order summary, policies
- **입력/선택**: 배송지 선택, 쿠폰 적용, 포인트 사용액, 결제수단(카드/PayPay)
- **결제 처리**:
  - 카드 — `POST /api/payment/entry/` (access_id/pass) → 프론트 토크나이즈 → `POST /api/payment/execute/`
  - PayPay — `POST /api/payment/paypay/entry/` (QR URL) → `paypay/execute/`
- **주문 생성**: `POST /api/orders/groups/create/` → `OrderGroup(group_number, customer_id, items, coupon_discount, point_discount, total_paid)`
- **⎇ 분기**: 성공 → **S-08 주문완료** → **S-10 주문상세**

### S-08 · 주문 완료  `[필요: group_number]`
- **표시**: group_number, 결제 금액, 예상 배송일
- **→**: **S-10 주문상세** / 계속 쇼핑 → **S-02**

### S-09 · 주문 목록  `[필요: JWT, customer_id]`
- **조회**: `GET /api/orders/?customer_id=` / `GET /api/orders/groups/?customer_id=`
- **표시**: 주문 카드 — order/group number, status, 대표 상품, 금액, 진행단계
- **⎇ 분기**: 카드 → **S-10**

### S-10 · 주문 상세(13단계 추적)  `[필요: group_number]`
- **조회**: `GET /api/orders/groups/{group_number}/` + `/{order}/status-log/` + `/{order}/pg/`
- **표시**: 13단계 타임라인(OrderStatusLog.stage), 상품별 가격 내역, PG 상태, 배송 추적(fb_invoice_no, tracking_number, delay)
- **⎇ 분기**: 문의 → **S-11** · 취소 → **S-12** · 환불 → **S-13** · 스냅샷 → **P-01**

### S-11 / S-12 / S-13 · 문의 / 취소 / 환불  `[필요: JWT, (선택) order_number]`
- **S-11 문의**: `POST /api/cs/inquiries/` — inquiry_type(9종), title, content, images[]
- **S-12 취소**: `POST /api/cs/cancel/` — order_number, reason → 상태 기반 가능 검증
- **S-13 환불**: `POST /api/cs/refund/` — order_number, reason, requested_amount
- **→**: 접수 후 상태 조회(open→in_progress→resolved / pending→approved→completed)

### S-14 · 마이페이지 (5 서브)  `[필요: JWT, customer_id]`
- **S-14a 배송지** `/api/mypage/{cid}/addresses/` — **필수 입력**: name(한자), name_kana(가타카나), name_en(영문), date_of_birth, phone, zipcode, address1/2, country, is_default
- **S-14b 포인트** `GET /api/mypage/{cid}/points/` — balance + PointLog(delta, reason, balance_after)
- **S-14c 쿠폰** `GET /api/mypage/{cid}/coupons/` — UserCoupon(coupon, is_used, used_at)
- **S-14d 알림설정** `/api/mypage/{cid}/notifications/` — order_status_push/email, marketing_push/email
- **S-14e 위시리스트** `/api/wishlist/{cid}/` — product_url, title, images, price_snapshot, options

### S-16 / S-17 / S-18 · FAQ / 공지 / 정책  `[필요: 없음~JWT]`
- **S-16 FAQ** `GET /api/content/faq/` — category, question, answer, sort_order
- **S-17 공지** `GET /api/content/notices/` — title, content, is_pinned, published_at
- **S-18 정책** `GET /api/content/policies/{type}/` — privacy/terms/shipping/refund/guide, version, is_current

### P-01 · 세관 스냅샷 공개 페이지  `[필요: snapshot_uuid (비인증)]`
- **조회**: `GET /api/orders/snapshots/{uuid}/` (+ `/html/`)
- **표시**: product_name(KO), product_name_en, quantity, purchase_price, product_url, images

---

## 2. CS 콘솔 — 현장 실행 흐름

```
[CS 로그인] ─▶ C-05 내 담당 건 추적(대시보드)
                  │
   ┌──────────────┼───────────────┬───────────────┐
   ▼              ▼               ▼               ▼
C-01 대리구매   C-02 검수       C-03 FastBox    C-04 CS응대
(paid 주문)    (arrived 주문)   인계            (문의/취소/환불)
   │              │               │               │
   ▼              ▼               ▼               ▼
purchasing   inspection      shipping_intl    resolved/approved
```

### C-05 · 내 담당 건 추적  `[필요: cs_user]`
- **조회**: `GET /api/stats/monitoring/overview/?scope=mine&cs_user=` + `/api/logistics/stagnated/`
- **표시**: 본인 담당 주문의 단계별 카운트, 배송 지연(24/48h), 검수 이슈, 오차
- **⎇ 분기**: 지연/이슈 클릭 → 해당 작업 화면(C-01/02/03)

### C-01 · 대리구매 작업  `[필요: cs_user, status=paid 주문]`
- **목록**: `GET /api/cs/purchase-tasks/?state=pending` — order_number, **product_url(원본)**, options, quantity, expected_price
- **입력**: `POST /api/cs/purchase-tasks/{order}/complete/` — **purchase_account, collection_address(국내 집하지), actual_price, domestic_shipping_fee**, cs_user, memo
- **처리**: PurchaseRecord 생성 → `status: paid→purchasing` → 가격 오차 평가(ErrorCriteria) → ErrorInfo
- **→**: 입고 대기 → **C-02**

### C-02 · 상품 검수  `[필요: cs_user, 입고 주문]`
- **입력**: `POST /api/logistics/{order}/inspection/` — result(pass/issue), components_match, has_defect, issue_reason, inspection_photos[], inspector
- **처리**: LogisticsInfo upsert → `status→inspection` → issue 시 **CS Inquiry(inspection_issue) 자동 생성**
- **→**: pass → **C-03**

### C-03 · FastBox(DHUB) 인계  `[필요: cs_user, 검수완료 주문]`
- **등록**: `POST /api/logistics/{order}/dhub/register/` — address(미입력 시 **기본 UserAddress 자동 채움**) → fb_invoice_no 채번, ShippingTracking 생성, log preparing_dispatch
- **배송지시**: `POST /api/logistics/dhub/instruct/` — fb_invoice_nos[](≤200), requester, arrival_due_date → dhub_instruction_no, 대상 주문 `→shipping_intl`
- **↺**: 이후 `tracking/sync/` 폴링으로 통관→일본배송 추적

### C-04 · CS 응대  `[필요: cs_user]`
- **문의** `PATCH /api/cs/inquiries/{id}/` — admin_reply, status
- **취소** `PATCH /api/cs/cancel/{id}/` — status, shipping_fee_burden
- **환불(1차)** `PATCH /api/cs/refund/{id}/` — status(approved/partial_approved), approved_amount → 본사 실행으로 인계(**H-03**)

---

## 3. 본사 어드민 — 관리 흐름

```
[본사 로그인] ─▶ H-11 실시간 모니터링(전체)
   │
   ├─ 상품/콘텐츠 ── H-01 상품·뱃지 / H-02 지원사이트·템플릿 / H-05 콘텐츠
   ├─ 정산/세관 ──── H-03 결제·정산(Capture·환불승인) / H-04 스냅샷·영문명
   ├─ 정책/설정 ──── H-06 사이트설정 / H-07 쿠폰 / H-08 금지품목 / H-09 오차기준
   └─ 감독 ───────── H-10 주문·액션 이력
```

### H-11 · 실시간 모니터링(전체)  `[필요: 본사 권한]`
- `GET /api/stats/monitoring/overview/` → order_status_counts, purchase_tasks_pending, shipping(delay_24h/48h), inspection_issues, price_error
- 보조: `/api/stats/dk-burden/`, `/error-rate/`, `/cs-conversion/`, `/site-parsing/`

### H-01 · 상품·뱃지 관리
- `PATCH /api/products/{id}/badges/` (is_limited), `/category/`, `/inbound/`, arrival-photos
- 입고 추적: inbound_order_number, inbound_tracking_number, arrival_status(ordered→in_transit→arrived→inspected)

### H-02 · 지원사이트·AI 템플릿
- `/api/sites/`(SupportedSite, url patterns), `/api/templates/`(SiteTemplate, build, build-logs), 몰 크롤잡 `/api/malls/{slug}/jobs/`

### H-03 · 결제·정산  `[필요: 본사 권한]`
- Capture `POST /api/payment/capture/` / 취소 `cancel/` / 환불 `refund/`
- **CS 환불요청 승인-실행**: `POST /api/cs/refund/{id}/execute/` (approved → GMO 환불 → Order/PG/RefundRequest 동기화)

### H-04 · 스냅샷·영문명(CI)
- `PUT /api/orders/{order}/snapshot/` — product_name_en(세관 영문 품목명), purchase_price, images → P-01 공개 링크

### H-05 · 콘텐츠 관리  🟦 Django Admin
- FAQ / Notice / EventBanner / Policy 등록·정렬·고정·버전 (고객 조회는 `/api/content/*`)

### H-06 · 사이트 설정  🟦 Django Admin + 조회 API
- 환율(ExchangeRateLog) / 배송요율(ShippingRateTable·Entry) / 배송모드(ShippingModeConfig) / 유류할증(FuelSurcharge) / 카테고리 무게(CategoryWeightPreset) / 관세

### H-07 · 쿠폰 생성·발급
- `/api/mypage/coupons/`(생성), `/{id}/issue/`(고객별 UserCoupon 발급)

### H-08 · 금지 품목 키워드  ✅🟦
- `GET /api/prohibited/`, `POST /check/` (risk_level, is_active) / 관리는 Admin

### H-09 · 가격 오차 기준
- `/api/operations/error-criteria/` (small/large threshold, 원인별 handling), history, log

### H-10 · 주문·액션 이력(감사)
- `/api/orders/admin/dashboard/`, `/admin/list/`, `/{order}/action-log/`, `/status-log/`, `/error/`

---

## 4. 시스템(백그라운드) — 화면 없음

| 처리 | 트리거 | 관련 |
|------|--------|------|
| 상품 일괄 저장(upsert) | scraper-agent → `POST /api/products/batch/` | PRD-05 |
| 상세 비동기 크롤 | prefetch-queue → `POST /api/products/{id}/detail/` | PRD-06 |
| 그룹 상태 동기화 | 주문 상태 변경 시 | ORD-03 |
| 가격 오차 평가 | 대리구매 완료 시 | ORD-04 |
| 배송 추적 폴링 | 주기/수동 `tracking/sync/` | LOG-03 |
| 지연 감지 | 폴링 시 24/48h 계산 | LOG-04 |
| 단계별 알림 | 상태 변경 시 `/api/notify/send/` | NTF-01 |
| 환율 캐싱 | `/api/pricing/exchange-rate/` | PRC-01 |
| 가격 계산 | `/api/pricing/quote/` | PRC-02 |
| 관세 조회 | `/api/tariff/lookup/` | PRC-04 |
| 번역 캐시 | `/api/translate/` | I18N-01 |
| 파일 저장 | `/api/storage/upload/` | FILE-01 |
