// 지원 카테고리 레지스트리
// 새 카테고리 추가 시 이 파일에만 내용 추가하면 됩니다.

export type CategoryId = 'shopping' | 'news' | 'real_estate' | 'jobs' | 'general';

export interface CategoryDef {
  id: CategoryId;
  name: string;
  /** narrateAndExtract 에 사용할 Claude 시스템 프롬프트 */
  narrateSystem: string;
  /** 프롬프트 안에 포함될 JSON 출력 스키마 예시 */
  schemaExample: string;
  /** template-builder 가 Python scrape() 에서 반환해야 할 dict 키 목록 설명 */
  templateKeys: string;
  /** template-builder 시스템 프롬프트에 추가되는 카테고리별 지침 */
  templateHints: string;
}

// ─── 카테고리 정의 ────────────────────────────────────────────────────────────

const shopping: CategoryDef = {
  id: 'shopping',
  name: '쇼핑',
  narrateSystem: `당신은 사용자 대신 쇼핑 페이지를 읽어주는 도우미입니다.
HTML 내용을 보고 발견한 상품 정보를 자연스러운 한국어 대화체로 설명해주세요.
상품명·가격·할인·옵션(색상·사이즈·패키지 등)·재고·판매자·평점·브랜드·스펙·배송 도착 예정일 등을 찾아서 이야기해주세요.
없는 정보는 건너뛰고, 있는 정보 위주로 자연스럽게 말해주세요.
"HTML 파서 선추출 데이터" 섹션이 있으면 그 내용을 가장 우선적으로 활용하고, 해당 옵션/가격 정보를 JSON에 그대로 포함하세요.`,
  schemaExample: `{
  "title": "상품명",
  "price": { "original": 숫자, "discounted": 숫자또는null, "currency": "KRW" },
  "options": [{ "name": "옵션명", "values": ["값1", "값2"] }],
  "images": ["url"],
  "brand": null,
  "availability": "in_stock",
  "shipping_fee": 0,
  "shipping_fee_text": "무료배송",
  "delivery_date": "내일(토) 6/27 도착",
  "rating": null,
  "review_count": null,
  "seller": null,
  "specifications": {},
  "size": { "weight_g": 500, "width_cm": null, "length_cm": null, "height_cm": null, "girth_sum_cm": null, "source": "title_guess", "confidence": "LOW" }
}`,
  templateKeys: `title, price_original, price_discounted,
  options (list of {"name": str, "values": list[str], "soldout_values": list[str]}),
  images (list[str]), availability ("in_stock"/"out_of_stock"/"unknown"), seller,
  shipping_fee (int 원 단위, 무료=0, 알수없음=None),
  shipping_fee_text (str, 예: "무료배송" / "2,500원" / "3만원 이상 무료", 없으면 None),
  delivery_date (str, 배송 도착 예정 안내, 예: "내일(토) 6/27 도착", 없으면 None),
  size (dict: {weight_g, width_cm, length_cm, height_cm, girth_sum_cm, source, confidence} — /extract/size 결과를 그대로)`,
  templateHints: `## 배송 도착 예정일 추출 (있으면 필수)
delivery_date는 "언제 도착하는지"를 안내하는 텍스트입니다. 쇼핑몰 상세에 도착 예정 안내가 있으면 반드시 추출하세요.
- 보통 배송 옵션/구매 영역에 라디오·뱃지 형태로 표시됩니다. 선택(기본)된 항목의 도착 안내를 우선 사용합니다.
- 날짜·요일·기준(지역/주문 마감 시각)을 포함한 한 줄 텍스트로 정리합니다. (예: "내일(토) 6/27 도착", "오늘(금) 도착")
- 사이트별 힌트:
  - 쿠팡: .pdd-contents (배송 라디오 .radio-item, 선택됨=.radio.selected). 예: <div class="pdd-contents">…<em>내일(토) 6/27</em><em> 도착</em>…</div> → "내일(토) 6/27 도착"
  - 스마트스토어/일반: "도착" / "배송 예정" / "오늘출발" 등의 키워드 근처 텍스트
- HTML 파서 선추출 결과(product_info)에 shipping_period 가 있으면 그대로 delivery_date 로 사용
- 없으면 None

**쿠팡 .pdd-contents 추출 예시:**
\`\`\`python
def _extract_delivery_date(soup):
    # 선택된 배송 옵션 우선, 없으면 첫 번째 .pdd-contents
    sel = soup.select_one(".radio-item .radio.selected")
    pdd = None
    if sel:
        item = sel.find_parent(class_="radio-item")
        pdd = item.select_one(".pdd-contents") if item else None
    if pdd is None:
        pdd = soup.select_one(".pdd-contents")
    if not pdd:
        return None
    # em 조각을 공백 정리해 한 줄로 합침
    text = " ".join(pdd.get_text(" ", strip=True).split())
    return text or None
\`\`\`

## 필드별 추출 가이드 — "보이는 건 다 뽑는다"

### 이미지(images) — 메인 1장으로 끝내지 말 것
- og:image는 시작점일 뿐. **썸네일 리스트·갤러리 슬라이더·상세 이미지**를 모두 모아 최대 10장.
- 흔한 위치: \`.swiper-slide img\`, \`ul li img\` (썸네일), \`[class*='thumb'] img\`, \`[class*='gallery'] img\`, 상세영역 \`img\`
- 소스 속성: src 외에 \`data-src\`, \`data-original\`, \`srcset\`(가장 큰 것) 확인
- 보정: 썸네일 크기 토큰(예: \`48x48\`, \`100x0\`)을 큰 값으로 치환, \`//\`로 시작하면 \`https:\` 추가, 쿼리스트링 제거 후 중복 제거

### 브랜드(brand)
- \`.brand\`, \`[class*='brand']\`, 제조사/브랜드 레이블 옆 텍스트, JSON-LD \`brand.name\`, og:site_name 순으로 탐색

### 평점·리뷰수(rating, review_count)
- \`[class*='rating']\`, \`[class*='star']\`, \`[class*='review']\`, \`aria-label\`(예: "별점 4.5") 에서 추출
- og:description/meta에 "별점 4.5점, 리뷰 919개" 형태로 들어있는 경우도 많음 → 정규식 추출
- rating은 0~5 float, review_count는 int

### 스펙·필수표기정보(specifications)
- 상품정보고시/필수표기정보/상세 스펙 **표**(table/dl/li "키: 값")를 dict로 전부 수집
- 흔한 위치: \`#itemBrief table\`, \`[class*='detail'] table\`, \`dl\`(dt/dd), "li 안에 콜론(:) 포함 텍스트"

### CSS Module / React 사이트 (올리브영·29CM·무신사 등) — 중요
- 클래스명이 \`Name_part__HASH\` 형태(예: \`DeliveryInfo_text__JLeta\`)면 **HASH는 빌드마다 바뀔 수 있음**.
  → 정확한 클래스명 대신 **부분 일치** \`[class*='DeliveryInfo_text']\` 또는 **\`data-qa-name\`·\`data-*\` 속성**으로 선택할 것.
- 올리브영 배송 예시: \`li[data-qa-name*='delivery']\` 안에서 \`[class*='DeliveryInfo_text']\` 들을 읽어
  - 배송비: "2,500원 (20,000원 이상 무료배송)" → shipping_fee=2500, shipping_fee_text 그대로
  - delivery_date: "평균 3일 이내 도착"
- React SPA라 simple requests로 본문이 비면 chrome 모드로 수집(선추출 product_info 활용).

## 네트워크 API에서 추출 (HTML에 없을 때) — 반드시 템플릿화
이미지 갤러리·리뷰·평점·옵션·재고가 **HTML/product_info에 없으면** JS가 API로 따로 불러온 것입니다.
수집 서버가 페이지를 끝까지 스크롤하며 그 API 응답을 \`network_log\`로 함께 돌려주므로, **그 응답을 템플릿에서 직접 파싱**하세요. (별도 호출·인증 불필요)

**1) inspect_network로 어떤 API에 데이터가 있는지 먼저 확인** (url 패턴·JSON 구조 파악)
**2) 템플릿 코드 패턴 — network_log에서 골라 파싱:**
\`\`\`python
import json, re

def _pick_api(net_log, *keywords):
    """network_log(=[{url, body, ct}])에서 url에 keyword가 포함된 첫 JSON 응답을 dict로 반환."""
    for e in net_log or []:
        u = (e.get("url") or "")
        if any(k in u for k in keywords):
            body = e.get("body") or ""
            try:
                return json.loads(body)
            except Exception:
                continue
    return None

# 예: 리뷰/평점 API (사이트별 url 키워드는 inspect_network로 확인)
review = _pick_api(net_log, "review", "rvw", "comment")
if review:
    rating = review.get("averageScore") or review.get("avgScore")        # 구조는 실제 응답에 맞춰
    review_count = review.get("totalCount") or review.get("reviewCount")
\`\`\`

**3) network_log에 없으면**(스크롤로도 안 터진 경우) URL에서 상품ID를 뽑아 API를 직접 호출(fallback):
\`\`\`python
m = re.search(r'goodscode=(\\d+)', url)         # 사이트별 상품ID 패턴
if m:
    gid = m.group(1)
    rv = requests.get(f"https://.../review/api?goodsNo={gid}", headers=HEADERS, timeout=10).json()
\`\`\`
- 이미지 갤러리도 동일: 상세이미지/썸네일 API 응답(예: itemImage, goodsImage)에 전체 URL 배열이 있으면 그걸 사용.
- **검증**: run_code 결과에서 images가 1장뿐이거나 rating/review가 None이면 → network_log를 의심하고 inspect_network 1회 → API 파싱 코드 추가.

## 클릭형 옵션 감지·처리 (드롭다운/아코디언) — 템플릿화
옵션이 HTML에 안 보이는데 페이지엔 "옵션 선택" UI가 있으면 = **클릭해야 펼쳐지는 옵션**입니다.
- collect_page 결과의 **"클릭형 옵션 트리거 후보(셀렉터)"** 목록을 우선 사용하세요. (수집 서버가 select·aria·옵션류 클릭요소를 미리 감지해 줍니다)
- 처리: \`click_and_capture([트리거_셀렉터])\`로 펼친 뒤 옵션 값을 추출 → 어떤 셀렉터가 옵션을 띄웠는지 확인.
- ★ **템플릿화**: 동작한 셀렉터를 **save_site_knowledge의 \`extra_clicks\`에 저장**하세요. 그러면 수집 서버가 **이후 모든 수집에서 자동으로 그 옵션을 펼쳐** product_info에 옵션을 포함합니다(템플릿 코드 추가 불필요).
- 2단계(선택1→선택2 아코디언)는 \`[선택1_항목_sel, 선택2_헤더_sel]\` 순서로 배열에 담아 click_and_capture.
- 옵션 값/가격이 클릭 시 API로 오면(드롭다운 선택) → 그 API 응답을 **network_log에서 파싱**(위 네트워크 섹션) 또는 click_and_capture 후 net_log 확인.

## iframe 안의 콘텐츠 (상세·리뷰)
일부 사이트는 상세설명·리뷰를 iframe으로 분리합니다 (예: 지마켓 \`/Item/ItemDetailV2\`).
- 수집 서버가 **동일 출처 콘텐츠 iframe을 자동 진입해 HTML을 본문 끝에 \`<!-- IFRAME ... -->\` 뒤로 병합**합니다. 리뷰/평점/상세 텍스트를 그 영역에서 찾으세요.
- 교차출처(다른 도메인) iframe은 접근 불가 → 그 경우 iframe src URL을 requests로 직접 호출해 파싱(fallback).

## 사이즈·무게 추출 (관세·국제배송용) — 항상 size 포함
관세 종량세(yen/kg)·국제배송비(세 변의 합)에 무게·치수가 필요합니다. **모든 템플릿이 size를 채우세요.**
비용 절감 단계로 수집 서버의 \`/extract/size\`를 호출하면 한 번에 처리됩니다:
  ① 작성된 무게·치수 정규식 파싱(무료) → ② 제목/카테고리 키워드 무게 추정(무료) → ③ allow_ocr=true일 때만 이미지 OCR(Claude Haiku, **유료**).

**코드 패턴 (템플릿에 그대로):**
\`\`\`python
size = requests.post("http://localhost:18080/extract/size", json={
    "title": title,
    "category": "",                 # 알면 채우기
    "specs": specifications,         # 위에서 만든 필수표기정보 dict
    "text": soup.get_text(" ", strip=True)[:5000],
    "images": images,
    "allow_ocr": False,              # 기본 무료(작성값+제목추정). 아래 조건에서만 True
}, timeout=30).json()

# 치수가 없고(부피 과금 가능) 무게 신뢰도가 낮으면 → OCR 1회 보강(유료, 선택)
if size.get("girth_sum_cm") is None and size.get("confidence") in ("LOW", "MEDIUM") and images:
    size = requests.post("http://localhost:18080/extract/size", json={
        "title": title, "category": "", "specs": specifications,
        "text": "", "images": images, "allow_ocr": True,
    }, timeout=40).json()
\`\`\`
- 반환 size(weight_g, width_cm, length_cm, height_cm, girth_sum_cm, source, confidence)를 출력 dict의 \`"size"\` 키로 그대로 넣으세요.
- ★ 이 단계는 **템플릿이지만 allow_ocr=True 시 Claude(이미지 OCR) 호출**이 발생합니다. 비용 때문에 기본 false로 두고, 치수가 꼭 필요한 상품(부피 큰 품목)에서만 true.

## 품절 옵션 추출 (soldout_values) — 옵션이 있는 상품 필수
옵션 중 일부만 품절인 경우 **재고 있는 옵션(values)과 품절 옵션(soldout_values)을 분리**해야 합니다.
- **availability**: 전체 품절이면 "out_of_stock", 일부만 품절이면 "in_stock" 유지
- **soldout_values**: 품절 옵션 값 목록. 없으면 빈 리스트 [] 또는 키 생략
- **values**: 재고 있는 옵션 + 품절 옵션 **모두** 포함 (전체 선택지 목록)

**패턴별 추출 방법:**
\`\`\`python
# 패턴 A — 텍스트에 "(품절)" 접미사
# 예: <a>블랙(품절)</a> → values=["블랙"], soldout_values=["블랙"]
soldout = []
available = []
for a in soup.select('.option-list a'):
    raw = a.get_text(strip=True)
    is_soldout = '품절' in raw or 'sold' in raw.lower()
    val = re.sub(r'\\s*\\(품절\\)\\s*|\\s*sold.?out\\s*', '', raw, flags=re.IGNORECASE).strip()
    if val:
        available.append(val)   # values에는 모두 포함
        if is_soldout:
            soldout.append(val)

# 패턴 B — disabled 속성 또는 품절 CSS 클래스
# 예: <option value="S" disabled>S</option>
# 예: <li class="option-item soldout">M</li>
for el in soup.select('select[name^="op"] option'):
    val = el.get_text(strip=True)
    val_clean = re.sub(r'\\s*\\(품절\\)', '', val).strip()
    if val_clean and el.get('value'):
        available.append(val_clean)
        if el.get('disabled') or '품절' in val:
            soldout.append(val_clean)

# 패턴 C — API/JSON에서 soldOut 플래그
# 예: {"optionName": "XL", "soldOut": true}
# network_log에서 옵션 API를 파싱해 soldOut=true인 항목을 soldout_values에 추가

options = [{"name": "사이즈", "values": available, "soldout_values": soldout}]
# soldout이 없으면: {"name": "사이즈", "values": available}
\`\`\`

## 배송비 추출 (쇼핑 필수)
shipping_fee와 shipping_fee_text는 항상 추출해야 합니다.

**추출 우선순위:**
1. HTML 파서 선추출 결과(product_info)에 shipping_fee가 있으면 그대로 사용
2. 없으면 HTML에서 직접 추출

**공통 패턴:**
- 무료배송: "무료배송" 텍스트 → shipping_fee=0, shipping_fee_text="무료배송"
- 유료: "2,500원" → shipping_fee=2500, shipping_fee_text="2,500원"
- **유료+조건부 무료: "2,500원 (2만원 이상 무료배송)" → shipping_fee=2500, shipping_fee_text="2,500원 (2만원 이상 무료배송)"** ← 이 패턴이 가장 흔함
- 순수 조건부 무료 (기본 배송비 미표시): "3만원 이상 무료" → shipping_fee=None, shipping_fee_text="3만원 이상 무료배송"
- 배송비 없음/알수없음: shipping_fee=None, shipping_fee_text=None

**사이트별 힌트:**
- 쿠팡: .price-shipping-fee-info-container 또는 "로켓배송" 텍스트
- 스마트스토어: span.Njct5hT6_B / span.X771s58c2z
- 지마켓/옥션: ul.item-topinfo-sub, span.text__branch
- 일반: "배송비" 키워드 포함 요소에서 가격 패턴 추출

**Python 추출 코드 예시:**
\`\`\`python
import re

def _extract_shipping(soup, html):
    text = soup.get_text(" ", strip=True)
    # "배송비" 또는 "배송" 레이블 근처 300자로 검색 범위 한정 (할부 등 오매칭 방지)
    # "배송비" 우선, 없으면 "배송" (chicor 등은 "배송비" 대신 "배송" 레이블 사용)
    area_m = re.search(r"배송비.{0,300}", text, re.DOTALL) or re.search(r"배송[^비].{0,300}", text, re.DOTALL)
    area = area_m.group(0) if area_m else text

    # 패턴1 (가장 흔함): "2,500원 (2만원 이상 무료배송)" 또는 "2,500원 (30,000원 이상 무료배송)" → fee=2500
    combined = re.search(r"([\d,]+)\s*원[^(]{0,30}\([^)]*[\d,]+\s*만?\s*원\s*이상[^)]*무료[^)]*\)", area)
    if combined:
        fee = int(combined.group(1).replace(",", ""))
        return fee, combined.group(0).strip()

    # 패턴2: 무조건 무료배송
    if re.search(r"무료\s*배송|배송\s*무료", area):
        return 0, "무료배송"

    # 패턴3: 조건부 무료 (기본 배송비 미표시)
    cond = re.search(r"([\d,]+만?\s*원)\s*이상.*?무료", area)
    if cond:
        return None, cond.group(0).strip()

    # 패턴4: 일반 유료
    m = re.search(r"([\d,]+)\s*원", area)
    if m:
        fee = int(m.group(1).replace(",", ""))
        return fee, f"{m.group(1)}원"

    return None, None
\`\`\`

## 연계 옵션 처리 (선택1 → 선택2 아코디언 패턴)
에이블리·스마트스토어 등에서 선택1 항목을 클릭한 뒤 선택2 아코디언을 열어야 하는 패턴이 있습니다.

감지 신호:
- 선택2 listbox/ul이 aria-disabled="true" 또는 비어있음
- 선택2 컨테이너가 collapsed/hidden 상태

처리 전략:
[1단계] 탐색: click_and_capture([선택1_첫번째_항목_sel, 선택2_아코디언_헤더_sel], wait_ms=1500)
[2단계] network_log에 option/combination API가 있으면 Python에서 직접 호출 (패턴 A)
        API 없으면 반환된 HTML에서 선택2 값 파싱 (패턴 B)
- 옵션은 네트워크 API → /collect/click HTML → 기본 HTML 순서로 시도`,
};

const news: CategoryDef = {
  id: 'news',
  name: '뉴스/블로그',
  narrateSystem: `당신은 사용자 대신 뉴스·블로그 페이지를 읽어주는 도우미입니다.
HTML 내용을 보고 발견한 기사/포스트 정보를 자연스러운 한국어 대화체로 설명해주세요.
제목·작성자·발행일·본문 요약·태그·카테고리·대표 이미지를 찾아서 이야기해주세요.
없는 정보는 건너뛰고, 있는 정보 위주로 자연스럽게 말해주세요.`,
  schemaExample: `{
  "title": "기사 제목",
  "author": "작성자 또는 null",
  "published_at": "ISO8601 날짜 또는 null",
  "summary": "본문 첫 200자 요약",
  "content": "본문 전체 텍스트 (최대 3000자)",
  "tags": ["태그1", "태그2"],
  "category": "카테고리 또는 null",
  "thumbnail": "대표 이미지 URL 또는 null",
  "source": "출처 매체명 또는 null"
}`,
  templateKeys: `title, author, published_at (ISO 형식 문자열 또는 None),
  summary (str), content (str, 최대 3000자), tags (list[str]),
  category (str 또는 None), thumbnail (str 또는 None), source (str 또는 None)`,
  templateHints: `## 뉴스/블로그 스크래핑 주의사항
- 날짜는 반드시 ISO 8601 형식으로 통일 (예: "2025-06-01T09:00:00+09:00")
- 날짜를 찾지 못하면 None
- content는 광고·네비게이션·댓글 제외한 순수 본문만 추출
- 목록 페이지(여러 기사 카드)인 경우 각 기사를 items 배열로 반환:
  반환 dict 키: items (list of dict, 각 항목은 title/url/published_at/thumbnail 포함)`,
};

const realEstate: CategoryDef = {
  id: 'real_estate',
  name: '부동산',
  narrateSystem: `당신은 사용자 대신 부동산 매물 페이지를 읽어주는 도우미입니다.
HTML 내용을 보고 발견한 매물 정보를 자연스러운 한국어 대화체로 설명해주세요.
매물명·유형·매매가·전세/보증금·월세·주소·면적·층수·방 개수·특징을 찾아서 이야기해주세요.
없는 정보는 건너뛰고, 있는 정보 위주로 자연스럽게 말해주세요.`,
  schemaExample: `{
  "title": "매물명",
  "type": "아파트/빌라/오피스텔/상가/토지 등",
  "price_sale": 매매가_만원_숫자또는null,
  "price_deposit": 보증금_만원_숫자또는null,
  "price_monthly": 월세_만원_숫자또는null,
  "address": "도로명 또는 지번 주소",
  "district": "구/동 단위 주소",
  "area_exclusive": 전용면적_m2_숫자또는null,
  "area_supply": 공급면적_m2_숫자또는null,
  "floor": "층수 문자열 또는 null",
  "rooms": 방개수_숫자또는null,
  "description": "매물 설명",
  "contact": "연락처 또는 null",
  "images": ["이미지 URL"]
}`,
  templateKeys: `title, type, price_sale (만원 단위 int 또는 None), price_deposit (만원 단위 int 또는 None),
  price_monthly (만원 단위 int 또는 None), address (str), district (str 또는 None),
  area_exclusive (float m² 또는 None), area_supply (float m² 또는 None),
  floor (str 또는 None), rooms (int 또는 None), description (str), contact (str 또는 None),
  images (list[str])`,
  templateHints: `## 부동산 스크래핑 주의사항
- 가격 단위를 만원으로 통일 (억 단위 있으면 변환: 3억5000만 → 35000)
- 면적은 ㎡ 기준으로 통일 (평 있으면 변환: 1평 ≈ 3.3058㎡)
- 목록 페이지인 경우 items 배열 반환 (각 항목: title, url, type, price_sale, price_deposit, area_exclusive)`,
};

const jobs: CategoryDef = {
  id: 'jobs',
  name: '채용/구인',
  narrateSystem: `당신은 사용자 대신 채용 공고 페이지를 읽어주는 도우미입니다.
HTML 내용을 보고 발견한 채용 정보를 자연스러운 한국어 대화체로 설명해주세요.
공고 제목·회사명·근무지·급여·고용 형태·마감일·직무 설명·요구사항·우대사항·복지를 찾아서 이야기해주세요.
없는 정보는 건너뛰고, 있는 정보 위주로 자연스럽게 말해주세요.`,
  schemaExample: `{
  "title": "공고 제목",
  "company": "회사명",
  "location": "근무지",
  "salary": "급여 정보 또는 null",
  "employment_type": "정규직/계약직/인턴/프리랜서 등",
  "deadline": "마감일 ISO8601 또는 null",
  "description": "직무 설명",
  "requirements": ["필수 조건1", "필수 조건2"],
  "preferred": ["우대 사항1"],
  "benefits": ["복지/혜택1"],
  "tech_stack": ["기술스택1"],
  "experience": "경력 요건 또는 null"
}`,
  templateKeys: `title, company, location, salary (str 또는 None), employment_type (str 또는 None),
  deadline (ISO 형식 문자열 또는 None), description (str),
  requirements (list[str]), preferred (list[str]), benefits (list[str]),
  tech_stack (list[str]), experience (str 또는 None)`,
  templateHints: `## 채용 스크래핑 주의사항
- 마감일은 ISO 8601 형식으로 통일
- requirements/preferred/benefits는 각 항목을 개별 문자열로 리스트에 담기
- 목록 페이지인 경우 items 배열 반환 (각 항목: title, url, company, location, deadline, employment_type)`,
};

const general: CategoryDef = {
  id: 'general',
  name: '일반',
  narrateSystem: `당신은 사용자 대신 웹페이지를 읽고 핵심 정보를 구조화하는 도우미입니다.
HTML 내용을 보고 이 페이지의 목적과 주요 정보를 자연스러운 한국어 대화체로 설명해주세요.
페이지 유형(상품/기사/매물/공고/회사소개/이벤트 등)을 먼저 파악한 뒤,
그에 맞는 핵심 필드들을 모두 추출해서 이야기해주세요.
없는 정보는 건너뛰고, 있는 정보 위주로 자연스럽게 말해주세요.`,
  schemaExample: `{
  "title": "페이지 제목",
  "page_type": "이 페이지의 유형 (예: product/article/listing/company 등)",
  "description": "핵심 내용 요약",
  "data": {
    "임의_필드1": "페이지 목적에 맞는 값",
    "임의_필드2": "페이지 목적에 맞는 값"
  },
  "images": ["대표 이미지 URL"],
  "links": ["주요 링크 URL"]
}`,
  templateKeys: `title, page_type (str), description (str),
  data (dict — 페이지 성격에 맞는 임의 필드들),
  images (list[str]), links (list[str])`,
  templateHints: `## 범용 스크래핑 주의사항
- page_type에 이 페이지의 성격을 명시 (product/article/listing/event/company/profile 등)
- data dict에 이 사이트/페이지에서 의미있는 모든 필드를 포함
- 목록 페이지인 경우 items 배열 반환 (각 항목은 title, url, 그리고 사이트별 핵심 필드 포함)`,
};

// ─── 레지스트리 ───────────────────────────────────────────────────────────────

export const CATEGORIES: Record<CategoryId, CategoryDef> = {
  shopping,
  news,
  real_estate: realEstate,
  jobs,
  general,
};

export function getCategory(id?: string | null): CategoryDef {
  if (id && id in CATEGORIES) return CATEGORIES[id as CategoryId];
  return CATEGORIES.general;
}

export function isShoppingCategory(id?: string | null): boolean {
  return (id ?? 'general') === 'shopping';
}
