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
상품명·가격·할인·옵션(색상·사이즈·패키지 등)·재고·판매자·평점·브랜드·스펙 등을 찾아서 이야기해주세요.
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
  "rating": null,
  "review_count": null,
  "seller": null,
  "specifications": {}
}`,
  templateKeys: `title, price_original, price_discounted,
  options (list of {"name": str, "values": list[str]}),
  images (list[str]), availability ("in_stock"/"out_of_stock"/"unknown"), seller,
  shipping_fee (int 원 단위, 무료=0, 알수없음=None),
  shipping_fee_text (str, 예: "무료배송" / "2,500원" / "3만원 이상 무료", 없으면 None)`,
  templateHints: `## 배송비 추출 (쇼핑 필수)
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
