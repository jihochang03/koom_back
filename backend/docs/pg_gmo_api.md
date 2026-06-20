# GMO Payment Gateway (PG マルチペイメントサービス) API

> 프로토콜 타입(idPass 방식) 기준으로 정리. 공개된 SDK·구현체를 리버스 엔지니어링한 내용이며,
> 계약 후 수령하는 공식 仕様書와 세부 항목이 다를 수 있음.

---

## 연동 방식 선택

GMO는 두 가지 연동 방식을 제공한다. **코렉스는 OpenAPI Type 사용.**

| 항목 | OpenAPI Type | Link Type Plus |
|------|-------------|----------------|
| 카드정보 처리 | Token 방식 | Redirect 방식 |
| 결제 UI | 직접 구현 | GMO 화면 사용 |
| 개발 자유도 | 높음 | 낮음 |
| 구현 난이도 | 높음 | 낮음 |
| PCI 부담 | 낮음 (토크나이저) | 매우 낮음 |
| 비고 | 실서비스 표준 | Stripe Checkout과 유사 |

---

## 도입 전 확인 체크리스트

계약·Sandbox 발급 전에 반드시 확인할 항목.

| # | 항목 | 상태 | 비고 |
|---|------|------|------|
| 1 | OpenAPI Type 계약 가능 여부 | - | Link Type Plus만 허용하는 플랜 존재 |
| 2 | Sandbox 계정 발급 | 계약 진행 중 | 조만간 어카운트 획득 예정 |
| 3 | 결제 생성 API 테스트 | - | EntryTran + ExecTran |
| 4 | Auth→Capture 분리 방식 | **✅ 확인** | Auth 보유기간 **60일** |
| 4-1 | 부분 환불·부분 취소 | **✅ 확인** | 결제일로부터 **180일 이내** API·관리화면 가능 |
| 5 | Member ID 저장 구조 확인 | - | SaveMember / SaveCard API 제공 여부 |
| 6 | 결제 상태 API 연동 | **✅ 확인** | 결제완료·취소·환불·매출확정 API 연동 가능. Webhook 자동통지 별도 확인 필요 |
| 7 | 3D Secure 2.0 | **✅ 필수 확인** | 3DS 2.0 적용 필수. 인증 실패 = 부정거래 차단 기준 |
| 8 | 정기결제(Subscription) 필요 여부 | - | Advanced 라이선스 별도 계약 |
| 9 | 가상계좌·편의점 결제 필요 여부 | - | 별도 계약·Webhook 연동 필요 |
| 10 | 결제 결과 조회 API | - | SearchTrade |
| 11 | 수수료 DK 부담 비율 | **답변 대기** | 거래 처리료 10엔·카드수수료 2.75% DK 부담 여부 |
| 12 | 차지백 배송증빙 효력 | **확인 필요** | 배송완료 증빙으로 차지백 취소 가능한지 |
| 13 | 부정탐지 API→WMS 연동 | **확인 필요** | 리스크 스코어 수신 후 출고 보류 연동 가능 여부 |

---

## 지원 결제수단 (OpenAPI 기준)

| 분류 | 수단 |
|------|------|
| 카드 | Visa / Mastercard / JCB / Amex / Diners / Discover |
| Wallet | Apple Pay / Google Pay |
| 일본 간편결제 | PayPay / d払い / 楽天ペイ / Amazon Pay / メルペイ / au PAY / AEON Pay |
| 현금성 | 편의점 결제 / 은행 계좌이체 / 가상계좌 |

> 편의점·가상계좌는 비동기(입금 확인 후 Webhook) 방식이므로 Webhook 수신 엔드포인트 별도 구현 필요.

---

## 기본 정보

| 항목 | Sandbox | Production |
|------|---------|------------|
| Host | `pt01.mul-pay.jp` | `p01.mul-pay.jp` |
| Protocol | HTTPS POST (application/x-www-form-urlencoded) | 동일 |
| 인증 | ShopID + ShopPass (모든 요청에 포함) | 동일 |
| 응답 포맷 | URL-encoded key=value 문자열 | 동일 |

### 계정 구조

| 자격증명 | 용도 |
|---------|------|
| `ShopID` / `ShopPass` | 쇼핑몰 인증 (거래 처리 전반) |
| `SiteID` / `SitePass` | 회원·카드 토큰 저장 (선택적) |
| `AccessID` / `AccessPass` | EntryTran 응답으로 받음 — 이후 API 호출에 필요 |

---

## 결제 전체 흐름

```
[프론트엔드]                     [Django 백엔드]              [GMO-PG]
    │                                 │                          │
    │  1. JS 토크나이저 로드           │                          │
    │  Multipayment.init(ShopID)      │                          │
    │  Multipayment.getToken(card)    │                          │
    │  → token                        │                          │
    │                                 │                          │
    │  2. POST /api/payment/entry/    │                          │
    │  { order_group_id }  ──────────▶│  EntryTran ────────────▶ │
    │                                 │  ◀─── AccessID/Pass ──── │
    │  ◀── { access_id, access_pass } │                          │
    │                                 │                          │
    │  3. POST /api/payment/execute/  │                          │
    │  { token, access_id, ... } ────▶│  ExecTran ─────────────▶ │
    │                                 │  ◀─── TranID/Approve ─── │
    │  ◀── { status, tran_id }        │                          │
    │                                 │                          │
    │  [주문 처리 → 검수 완료]         │                          │
    │                                 │                          │
    │                                 │  4. AlterTran(SALES) ──▶ │  ← admin 캡처
    │                                 │  5. AlterTran(RETURN) ─▶ │  ← 환불 시
```

### 코렉스 비즈니스 플로우 (GMO 확인 완료)

```
주문 접수
    ↓
카드 Auth (승인) — JobCd=AUTH
    ↓              ← 여기서 결제 UI 완료, 고객에게 주문 확정 안내
한국 상품 확보
    ↓
일본 물류 입고
    ↓
출고 준비 완료
    ↓
Capture (매출 확정) — AlterTran JobCd=SALES   ← Auth로부터 60일 이내
    ↓
배송 진행
```

- Auth 단계에서 고객 카드에 승인만 잡힘 (실제 청구 X)
- 상품 확보 실패 시 AlterTran(CANCEL)로 승인 취소 → 고객 미청구
- 출고 준비 완료 후 Capture → 이 시점에 실제 카드 청구

---

## API 엔드포인트 상세

### 1. EntryTran — 거래 등록

`POST https://pt01.mul-pay.jp/payment/EntryTran.idPass`

거래 슬롯을 생성하고 AccessID/AccessPass를 발급받는다.

#### Request Parameters

| 파라미터 | 필수 | 타입 | 설명 |
|---------|------|------|------|
| `ShopID` | ✅ | string(13) | 쇼핑몰 ID |
| `ShopPass` | ✅ | string(10) | 쇼핑몰 패스워드 |
| `OrderID` | ✅ | string(27) | 주문 ID (영숫자·`-` 만 허용, 재사용 불가) |
| `JobCd` | ✅ | string | 처리 구분 (아래 표 참조) |
| `Amount` | ✅ | integer | 결제 금액 (JPY) |
| `Tax` | ❌ | integer | 세금·배송비 별도 표시 금액 |
| `TdFlag` | ❌ | `0`\|`1` | 3D Secure 사용 여부 |

**JobCd 허용값**

| 값 | 의미 | 설명 |
|----|------|------|
| `AUTH` | 仮売上 | 승인만 — 나중에 AlterTran(SALES)로 확정. **보유기간 60일 (GMO 확인)** |
| `CAPTURE` | 即時売上 | 즉시 매출 확정 |
| `SALES` | 実売上 | AlterTran에서 AUTH→SALES 전환 시 사용 |
| `SAUTH` | 簡易オーソリ | 간이 승인 |

> **코렉스 운영 방침**: 결제 시 `AUTH`로 승인만 잡고, 출고 준비 완료 시 `SALES`(Capture)로 매출 확정. Auth 보유기간 60일 이내에 Capture 처리 필요.

#### Response Fields

| 필드 | 설명 |
|------|------|
| `AccessID` | 이후 API 호출에 사용 |
| `AccessPass` | 이후 API 호출에 사용 |
| `ErrCode` | 에러 코드 (없으면 빈 문자열) |
| `ErrInfo` | 에러 상세 코드 |

---

### 2. ExecTran — 결제 실행

`POST https://pt01.mul-pay.jp/payment/ExecTran.idPass`

카드 정보(토큰)로 실제 결제를 실행한다.

#### Request Parameters

| 파라미터 | 필수 | 타입 | 설명 |
|---------|------|------|------|
| `AccessID` | ✅ | string | EntryTran 응답값 |
| `AccessPass` | ✅ | string | EntryTran 응답값 |
| `OrderID` | ✅ | string(27) | EntryTran과 동일 |
| `Method` | ✅ | `1`-`5` | 결제 방법 (아래 표) |
| `PayTimes` | 조건부 | integer | 할부 회수 (Method=2,4 시 필수) |
| `Token` | △ | string | JS 토크나이저 발급 토큰 **(권장)** |
| `CardNo` | △ | string(10-16) | 카드 번호 (Token 미사용 시) |
| `Expire` | △ | string(4) | 유효기간 YYMM 형식 |
| `SecurityCode` | ❌ | string(3-4) | CVV |
| `HolderName` | ❌ | string(50) | 카드 명의자 |
| `ClientField1` | ❌ | string(100) | 가맹점 메타데이터 1 |
| `ClientField2` | ❌ | string(100) | 가맹점 메타데이터 2 |
| `ClientField3` | ❌ | string(100) | 가맹점 메타데이터 3 |
| `HttpAccept` | 조건부 | string | TdFlag=1 시 필수 |
| `HttpUserAgent` | 조건부 | string | TdFlag=1 시 필수 |

**Method 허용값**

| 값 | 의미 |
|----|------|
| `1` | 一括 (일시불) |
| `2` | 分割 (할부) |
| `3` | ボーナス一括 (보너스 일시불) |
| `4` | ボーナス分割 (보너스 할부) |
| `5` | リボ (리볼빙) |

#### Response Fields

| 필드 | 설명 |
|------|------|
| `ACS` | 3D Secure 리다이렉트 필요 여부 (`0`=불필요, `1`=필요) |
| `OrderID` | 주문 ID |
| `Forward` | 仕向け先コード (카드사 코드) |
| `Method` | 결제 방법 |
| `PayTimes` | 할부 회수 |
| `Approve` | 承認番号 (승인 번호) |
| `TranID` | GMO 거래 ID |
| `TranDate` | 거래 일시 (YYYYMMDDHHmmss) |
| `CheckString` | 위변조 검증용 해시 |
| `ClientField1-3` | 가맹점 메타데이터 (echo) |
| `ErrCode` | 에러 코드 |
| `ErrInfo` | 에러 상세 |

---

### 3. AlterTran — 거래 변경 (캡처·취소·환불)

`POST https://pt01.mul-pay.jp/payment/AlterTran.idPass`

#### Request Parameters

| 파라미터 | 필수 | 타입 | 설명 |
|---------|------|------|------|
| `ShopID` | ✅ | string | |
| `ShopPass` | ✅ | string | |
| `AccessID` | ✅ | string | EntryTran/ExecTran 응답값 |
| `AccessPass` | ✅ | string | |
| `JobCd` | ✅ | string | SALES / CANCEL / RETURN / RETURNX |
| `Amount` | 조건부 | integer | RETURN 시 환불 금액 |
| `Tax` | ❌ | integer | |

**AlterTran JobCd 허용값**

| 값 | 의미 | 조건 |
|----|------|------|
| `SALES` | 매출 확정 | AUTH 상태에서만 |
| `CANCEL` | 취소 | SALES 전에만 (당일) |
| `RETURN` | 반품·환불 | SALES 이후 |
| `RETURNX` | 월말 반품 | 월 넘긴 SALES |

#### Response Fields

| 필드 | 설명 |
|------|------|
| `AccessID` | |
| `AccessPass` | |
| `Forward` | |
| `Approve` | |
| `TranID` | |
| `TranDate` | |
| `ErrCode` | |
| `ErrInfo` | |

---

### 4. SearchTrade — 거래 조회

`POST https://pt01.mul-pay.jp/payment/SearchTrade.idPass`

#### Request Parameters

| 파라미터 | 필수 | 설명 |
|---------|------|------|
| `ShopID` | ✅ | |
| `ShopPass` | ✅ | |
| `OrderID` | ✅ | |

#### Response Fields

| 필드 | 설명 |
|------|------|
| `OrderID` | |
| `Status` | 거래 상태 (아래 표) |
| `ProcessDate` | 처리 일시 |
| `JobCd` | 현재 처리 구분 |
| `AccessID` / `AccessPass` | |
| `Amount` / `Tax` | |
| `CardNo` | 마스킹된 카드 번호 (`****...****1234`) |
| `Expire` | 유효기간 |
| `Method` / `PayTimes` | |
| `Forward` / `TranID` / `Approve` | |
| `ClientField1-3` | |
| `ErrCode` / `ErrInfo` | |

**Status 허용값**

| 값 | 의미 |
|----|------|
| `UNPROCESSED` | 未処理 |
| `AUTHENTICATED` | 3DS 인증 완료 |
| `AUTH` | 仮売上 (승인) |
| `SALES` | 実売上 (매출 확정) |
| `CANCEL` | 取消 |
| `RETURN` | 返品 |
| `RETURNX` | 月跨返品 |

---

## JS 토크나이저 (PCI DSS 준수)

카드 번호를 서버에 전달하지 않고 클라이언트에서 토큰으로 변환.

```html
<!-- Sandbox -->
<script src="https://stg.mul-pay.jp/ext/js/token.js"></script>
<!-- Production -->
<script src="https://p01.mul-pay.jp/ext/js/token.js"></script>

<script>
Multipayment.init("SHOP_ID");
Multipayment.getToken(
  { cardno: "4111111111111111", expire: "2512", securitycode: "123", holdername: "TARO YAMADA" },
  function(response) {
    if (response.resultCode === "000") {
      // response.tokenObject.token → 서버로 전송
    }
  }
);
</script>
```

---

## 주요 에러 코드

### 입력 유효성 오류 (E01xxxxx)

| 코드 | 의미 |
|------|------|
| `E01010001` | ShopID 미지정 |
| `E01020001` | ShopPass 미지정 |
| `E01030002` | ShopID/ShopPass 불일치 |
| `E01040001` | OrderID 미지정 |
| `E01040010` | OrderID 중복 사용 |
| `E01040013` | OrderID 사용 불가 문자 포함 |
| `E01050001` | JobCd 미지정 |
| `E01050002` | JobCd 값 오류 |
| `E01060001` | Amount 미지정 |
| `E01060010` | 캡처 금액이 승인 금액과 불일치 |
| `E01090001` | AccessID 미지정 |
| `E01100001` | AccessPass 미지정 |
| `E01110002` | AccessID/AccessPass 불일치 |
| `E01170001` | CardNo 미지정 |
| `E01170011` | CardNo 자릿수 오류 (10-16자리) |
| `E01180001` | Expire 미지정 |
| `E01180003` | Expire 형식 오류 (YYMM 4자리) |
| `E01260001` | Method 미지정 |
| `E01260002` | Method 값 오류 |

### 거래 상태 오류 (E11xxxxx)

| 코드 | 의미 |
|------|------|
| `E11010001` | 이미 결제 완료된 거래 |
| `E11010002` | 미완료 거래에 변경 불가 |
| `E11010003` | 허용되지 않는 처리 구분 |
| `E11010099` | 카드 사용 불가 |

### 3D Secure 오류 (E21xxxxx)

| 코드 | 의미 |
|------|------|
| `E21010001` | 본인 인증 실패 — 재시도 |
| `E21010201` | 카드가 3D Secure 미지원 |

### 시스템 오류 (E9xxxxxx)

| 코드 | 의미 |
|------|------|
| `E90010001` | 중복 거래 |
| `E91020001` | 통신 타임아웃 |
| `E92000001` | 시스템 처리 불가 — 재시도 |

### 카드사 거절 코드 (42Gxxxxxx)

| 코드 | 의미 |
|------|------|
| `42G020000` | 잔액 부족 |
| `42G030000` | 한도 초과 / CVV 미입력 |
| `42G420000` | PIN 오류 |
| `42G440000` | CVV 오류 |
| `42G650000` | 카드 번호 오류 |
| `42G830000` | 유효기간 오류 |
| `42G950000`-`42G990000` | 카드 사용 불가 |

---

## 보안 (PCI DSS / 3D Secure)

### 카드정보 비보관 원칙

카드 번호(PAN)는 서버를 거치지 않는다. JS 토크나이저가 카드번호를 GMO 서버로 직접 전송하고 token만 반환한다.

```
카드번호 → [JS 토크나이저] → GMO 서버 → token
                                              ↓
                                        우리 백엔드
```

백엔드는 `{ "token": "abc123" }` 만 받아서 처리하므로 PAN을 저장하지 않는다.

### 3D Secure (EMV 3DS)

일본 카드사는 3DS를 거의 필수로 요구한다. EntryTran의 `TdFlag=1` 설정 후 ExecTran 응답의 `ACS` 필드로 리다이렉트 여부를 판단한다.

```
사용자
 │
 ├─ EntryTran (TdFlag=1)
 ├─ ExecTran → ACS=1 이면 카드사 3DS 페이지로 리다이렉트
 ├─ [사용자 인증]
 └─ SecureTran (인증 완료 후 최종 승인)
```

| 파라미터 | 설명 |
|---------|------|
| `TdFlag` | `1` = 3DS 사용 |
| `HttpAccept` | 브라우저 Accept 헤더 (TdFlag=1 시 필수) |
| `HttpUserAgent` | 브라우저 UA (TdFlag=1 시 필수) |
| `ACS` (응답) | `0`=3DS 불필요, `1`=리다이렉트 필요 |

---

## 회원 저장 결제 (会員ID決済)

SiteID/SitePass 자격증명이 별도로 필요하다. 회원 생성 → 카드 등록 → Member ID로 재결제하는 흐름.

### DB 구조 추가 필요

```
users
├── id
└── gmo_member_id   # VARCHAR(60), nullable
```

### API 엔드포인트

#### SaveMember — 회원 등록

`POST .../SaveMember.idPass`

| 파라미터 | 필수 | 설명 |
|---------|------|------|
| `SiteID` | ✅ | 사이트 ID |
| `SitePass` | ✅ | 사이트 패스워드 |
| `MemberID` | ✅ | 가맹점 측 회원 ID (우리 서비스 user.id 등) |
| `MemberName` | ❌ | 회원 이름 |

응답: `MemberID`

#### SearchMember — 회원 조회

`POST .../SearchMember.idPass`

| 파라미터 | 필수 |
|---------|------|
| `SiteID` | ✅ |
| `SitePass` | ✅ |
| `MemberID` | ✅ |

응답: `MemberID`, `MemberName`, `DeleteFlag`

#### SaveCard — 카드 등록

`POST .../SaveCard.idPass`

| 파라미터 | 필수 | 설명 |
|---------|------|------|
| `SiteID` | ✅ | |
| `SitePass` | ✅ | |
| `MemberID` | ✅ | |
| `Token` | ✅ | JS 토크나이저 발급 토큰 |
| `CardSeq` | ❌ | 카드 순번 (갱신 시) |

응답: `CardSeq`, `CardNo`(마스킹), `Expire`

#### SearchCard — 등록 카드 조회

`POST .../SearchCard.idPass`

| 파라미터 | 필수 |
|---------|------|
| `SiteID` | ✅ |
| `SitePass` | ✅ |
| `MemberID` | ✅ |
| `SeqMode` | ✅ | `0`=論理連番, `1`=物理連番 |

응답: `CardSeq`, `DefaultFlag`, `CardName`, `CardNo`, `Expire`, `HolderName`

#### DeleteCard — 카드 삭제

`POST .../DeleteCard.idPass`

| 파라미터 | 필수 |
|---------|------|
| `SiteID` | ✅ |
| `SitePass` | ✅ |
| `MemberID` | ✅ |
| `CardSeq` | ✅ |

### Member ID로 결제하는 흐름

```
EntryTran (ShopID/ShopPass)
    ↓
ExecTran (AccessID/Pass + SiteID/SitePass + MemberID + CardSeq)
    ↓ (Token 대신 MemberID+CardSeq 사용)
결제 완료
```

ExecTran에 `SiteID`, `SitePass`, `MemberID`, `CardSeq` 파라미터를 추가하면 저장된 카드로 결제한다.

---

## 정기결제 (Subscription)

> Advanced 라이선스 별도 계약 필요.

### DB 구조 예시

```
subscriptions
├── id
├── user_id
├── gmo_member_id
├── card_seq
├── amount
├── currency
├── billing_interval       # monthly / yearly
├── next_billing_date
├── status                 # active / paused / cancelled
├── created_at
└── updated_at
```

### 운영 흐름

```
사용자 가입 → SaveMember → SaveCard (MemberID 저장)
         ↓
매월 배치 (Celery Beat 등)
         ↓
EntryTran + ExecTran (MemberID + CardSeq)
         ↓
결제 성공 → next_billing_date += 1개월
결제 실패 → 재시도 로직 / 카드 갱신 확인
```

---

## 카드 갱신 (洗替 / Card Updater)

카드 재발급·만료 시 PG가 자동으로 새 카드번호·유효기간으로 업데이트한다. Stripe Card Updater와 동일한 개념.

- GMO가 카드사와 주기적으로 동기화
- 가맹점 측 DB 변경 불필요 (GMO 내부에서 CardSeq에 매핑된 카드정보 갱신)
- 구독 결제 실패율 감소 효과
- 갱신 결과는 Webhook 또는 SearchCard로 확인 가능

> 사용 여부는 계약 시 GMO 영업팀에 확인.

---

## Webhook (비동기 결제수단용)

> **상태**: 결제완료·취소·환불·매출확정 등 상태 변경은 **API 연동 가능** (GMO 확인). 
> Webhook 자동통지(서버 Push) 지원 여부는 **확인 중** — 지원 안 될 경우 폴링 또는 관리화면 수동 확인으로 대체.

편의점·가상계좌 등 비동기 입금 결제수단에서 입금 완료 시 GMO가 우리 서버로 POST 전송.

### 수신 엔드포인트 예시

`POST /api/payment/webhook/gmo/`

### 검증 필드

| 필드 | 설명 |
|------|------|
| `ShopID` | 요청 출처 검증 |
| `OrderID` | 주문 식별 |
| `Status` | 입금 상태 (`EXPIRED`, `PAIED` 등) |
| `Amount` | 입금 금액 |
| `CheckString` | HMAC 서명 (위변조 방지) |

> Webhook URL은 GMO 관리 콘솔에 등록. HTTPS 필수.

---

## 환불 처리 방식

### 방식 비교

| 구분 | 원카드 환불 (AlterTran RETURN) | GMO 송금서비스 |
|------|-------------------------------|---------------|
| 대상 | 카드 결제 건 | 카드 외 결제 또는 카드 환불 불가 케이스 |
| 처리 방법 | API 또는 관리화면 | 송금 API / 관리화면 / SMS·이메일 송금 |
| 고객 수취 | 카드사 통해 원카드 입금 | 계좌이체 또는 편의점 수령 |
| 수수료 | 없음 (카드사 처리) | 별도 (GMO 송금서비스 약관 기준) |
| 비고 | 1차 도입 시 기본 방식 | 향후 필요 시 추가 도입 검토 |

> **코렉스 1차 방침**: 카드결제만 도입하므로 **원카드 환불(AlterTran RETURN)** 사용.  
> 카드 환불이 불가한 케이스(카드사 기간 초과 등) 발생 시 GMO 송금서비스로 대체 검토.

---

### 부분 환불 / 부분 취소 ✅ GMO 확인

> **확인 완료**: 부분 환불 및 부분 취소 모두 **결제일로부터 180일 이내** 관리화면 또는 API로 가능.  
> 참고: https://mp-faq.gmo-pg.com/s/article/D00016

| 구분 | 방법 | 제한 |
|------|------|------|
| 부분 취소 (CANCEL) | AlterTran JobCd=CANCEL + Amount 지정 | SALES 전 / 180일 이내 |
| 부분 환불 (RETURN) | AlterTran JobCd=RETURN + Amount 지정 | SALES 후 / 180일 이내 |

> AlterTran의 `Amount` 파라미터에 부분 금액을 지정하면 된다. `Amount` 생략 시 전액 처리.  
> 현재 `views.py`의 `PaymentRefundView`는 `amount` 파라미터를 이미 지원함.

---

## 정산 / 입금 주기

> **확인 완료 내용** (GMO 기준)

### 입금 주기 옵션

| 옵션 | 입금 시기 | 비고 |
|------|---------|------|
| 표준 | 결제일로부터 **40일 후** | 기본 계약 |
| 빠른 입금 15일 | 결제일로부터 **15일 후** | 수수료 추가 가능성 |
| 빠른 입금 30일 | 결제일로부터 **30일 후** | |
| 최속 2영업일 | 결제일로부터 **2영업일 후** | 별도 계약 |

### 정산 구조 (표준)

```
월말 마감
    ↓
익월 말 입금
    ↓
송금수수료 200엔 차감
```

### 환불·차지백 발생 시

| 항목 | 처리 방식 |
|------|---------|
| 환불 | 정산금에서 차감 (상세 확인 필요) |
| 차지백 (카드 이의 제기) | 정산금 차감 방식 **추가 확인 필요** |
| 송금수수료 | 입금 건당 200엔 |

> 환불·차지백 발생 시 정산금 차감 세부 방식(시점·단위)은 **계약 진행 중**, GMO 측 추가 확인 예정.

---

## 수수료 / 비용 구조

### 확정 항목 (GMO 확인)

| 항목 | 금액 | 비고 |
|------|------|------|
| 초기비 | 20,000엔 | 계약 시 1회 |
| 월 고정비 | 15,000엔 | 매월 |
| 거래 처리료 | 10엔 / 건 | 결제·취소·환불 모두 발생 |
| 카드수수료 | 2.75% | 결제 금액 기준 |

### 취소·환불 시 수수료 (GMO 확인)

| 상황 | 카드수수료 | 거래 처리료 |
|------|-----------|------------|
| 정상 결제 | 2.75% | 10엔 |
| 취소 (CANCEL) | **없음** | 10엔 |
| 환불 (RETURN) | **없음** | 10엔 |
| 승인 취소 (AUTH→CANCEL) | **없음** | 10엔 |

### 수수료 부담 정책 ✅ 확정

> **초기 운영 방침**: 카드·PayPay 등 GMO PG 결제수수료(카드수수료 2.75%, 거래 처리료 10엔/건)는 **DK(KOOM) 전액 부담**.  
> 고객에게 수수료를 전가하지 않으며, 별도 결제수수료 화면/고지 불필요.

---

## 차지백 / 부정결제 대응

### 차지백 발생 시 책임 구조

| 단계 | 책임 주체 | 내용 |
|------|---------|------|
| 차지백 발생 | **가맹점 (KOOM/DK)** | GMO 정산금 미지급 또는 반환 청구 |
| 분쟁 대응 | **주식회사 DK** | 배송증빙·거래내역으로 카드사 제출 |
| 배송증빙 효력 | 확인 필요 | 배송완료 증빙으로 차지백 취소 가능한지 GMO·카드사 확인 필요 |

> 배송 완료 후 차지백 발생 시 손실은 가맹점(KOOM) 부담.  
> 배송 추적 데이터(운송장 번호, 배송완료 타임스탬프)를 DB에 보관해야 분쟁 대응 가능.

### 배송 보류 기준 (위험 신호)

> **3D Secure 2.0 적용 필수** (GMO 확인) — 3DS 2.0 인증 실패 = 부정거래로 판단.

| 위험 신호 | 대응 |
|---------|------|
| 3DS 2.0 인증 실패 | 결제 거절 (ExecTran 단계에서 차단) |
| 3DS 2.0 인증 완료 | 정상 처리 |
| 배송지·주문 이상 탐지 | 출고 보류 후 수동 검토 (운영 정책 별도 수립 필요) |

#### GMO 제공 부정탐지 솔루션

| 솔루션 | 설명 |
|--------|------|
| EMV 3D Secure 2.0 | **필수 적용**. 본인 인증으로 부정거래 1차 차단 |
| Forter | 행동 기반 부정거래 탐지 (별도 계약) |
| Sift | ML 기반 리스크 스코어링 (별도 계약) |

> **미확인**: 부정탐지 결과(리스크 스코어 등)를 API로 수신하여 KOOM WMS 출고 보류와 연동 가능한지 확인 필요.  
> 확인될 경우 `OrderGroup`에 `fraud_risk_score` 필드 추가 및 출고 보류 플래그 연동 검토.

---

## 환경변수

```
GMO_SHOP_ID=
GMO_SHOP_PASS=
GMO_SITE_ID=          # 회원/카드 저장 사용 시
GMO_SITE_PASS=
GMO_SANDBOX=true      # false 시 production
GMO_TIMEOUT=30        # 초
```
