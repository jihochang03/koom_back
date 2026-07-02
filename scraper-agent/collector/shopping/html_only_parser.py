"""Claude 없이 HTML/구조화 데이터만으로 상품 정보 파싱.

전략 (사이트별 CSS 클래스 의존 없음):
1. JSON-LD Product 스키마  - 가장 신뢰할 수 있는 기계 가독 소스
2. OG / product 메타태그   - 거의 모든 쇼핑몰이 포함
3. 가격 정규식             - 텍스트에서 가격 패턴 추출
4. h1/h2 제목 fallback

SKIP_CLAUDE=1 환경변수 설정 시 linux_api_server.py에서 이 파서를 사용.
"""
import json
import logging
import re
from typing import Optional

import sys as _sys, os as _os
_COLLECTOR_DIR = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _COLLECTOR_DIR not in _sys.path:
    _sys.path.insert(0, _COLLECTOR_DIR)
from models import ProductInfo, ProductOption

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 공통 유틸
# ---------------------------------------------------------------------------

def _to_num(v) -> Optional[float]:
    if v is None:
        return None
    try:
        cleaned = re.sub(r"[^\d.]", "", str(v).replace(",", ""))
        return float(cleaned) if cleaned else None
    except Exception:
        return None


def _first(*values):
    for v in values:
        if v is not None and str(v).strip():
            return v
    return None


def _extract_meta(soup) -> dict:
    """OG / product / twitter 메타태그를 딕셔너리로 반환."""
    meta = {}
    for tag in soup.find_all("meta"):
        prop = (tag.get("property") or tag.get("name") or "").lower().strip()
        content = (tag.get("content") or "").strip()
        if prop and content:
            meta[prop] = content
    return meta


def _iter_jsonld_objects(soup):
    """모든 JSON-LD 객체를 순회 (@graph·리스트·중첩 평탄화)."""
    for script in soup.find_all("script", type=lambda t: t and "ld+json" in t.lower()):
        raw = script.string or script.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        stack = [data]
        while stack:
            cur = stack.pop()
            if isinstance(cur, list):
                stack.extend(cur)
            elif isinstance(cur, dict):
                g = cur.get("@graph")
                if isinstance(g, list):
                    stack.extend(g)
                yield cur


def _jsonld_type_is(item: dict, *types) -> bool:
    t = item.get("@type")
    if isinstance(t, list):
        return any(x in types for x in t)
    return t in types


def _extract_jsonld_product(soup) -> dict:
    """Product/Offer JSON-LD 객체 반환 (@graph·@type 리스트 대응, 없으면 {})."""
    for item in _iter_jsonld_objects(soup):
        if isinstance(item, dict) and _jsonld_type_is(item, "Product", "IndividualProduct", "Offer"):
            return item
    return {}


def _universal_structured(soup) -> dict:
    """
    JSON-LD(schema.org Product) + OpenGraph + microdata에서 사이트 무관 공통 필드 추출.
    모든 사이트에 1순위로 적용해 site 파서가 못 채운 칸(특히 평점·리뷰·브랜드·이미지)을 메운다.
    """
    out = {
        "title": None, "original_price": None, "discounted_price": None,
        "brand": None, "rating": None, "review_count": None,
        "images": [], "main_image_url": None, "product_weight": None,
    }
    meta = _extract_meta(soup)
    prod = _extract_jsonld_product(soup)

    # ── JSON-LD ──
    if prod:
        out["title"] = prod.get("name")
        offers = prod.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        if isinstance(offers, dict):
            out["discounted_price"] = _to_num(offers.get("price") or offers.get("lowPrice"))
            out["original_price"] = _to_num(offers.get("highPrice"))
        brand = prod.get("brand")
        if isinstance(brand, dict):
            brand = brand.get("name")
        out["brand"] = brand if isinstance(brand, str) else None
        agg = prod.get("aggregateRating") or {}
        if isinstance(agg, dict):
            out["rating"] = _to_num(agg.get("ratingValue"))
            rc = agg.get("reviewCount") or agg.get("ratingCount")
            out["review_count"] = int(_to_num(rc)) if _to_num(rc) is not None else None
        img = prod.get("image")
        imgs: list = []
        if isinstance(img, list):
            imgs = [x.get("url") if isinstance(x, dict) else x for x in img]
        elif isinstance(img, dict):
            imgs = [img.get("url")]
        elif img:
            imgs = [img]
        out["images"] = [str(i) for i in imgs if i]
        w = prod.get("weight")
        if isinstance(w, dict):
            w = w.get("value")
        if w:
            out["product_weight"] = str(w)

    # ── OpenGraph / meta 폴백 ──
    if not out["title"]:
        out["title"] = meta.get("og:title") or meta.get("twitter:title")
    if out["discounted_price"] is None:
        out["discounted_price"] = _to_num(
            meta.get("product:price:amount") or meta.get("og:price:amount")
        )
    if not out["brand"]:
        out["brand"] = meta.get("product:brand") or meta.get("og:brand")
    if not out["images"]:
        ogimg = meta.get("og:image") or meta.get("twitter:image")
        if ogimg:
            out["images"] = [ogimg]
    out["main_image_url"] = out["images"][0] if out["images"] else None

    # ── microdata(itemprop) 폴백 — JSON-LD/OG 둘 다 빈 칸만 ──
    if out["rating"] is None:
        el = soup.find(attrs={"itemprop": "ratingValue"})
        if el:
            out["rating"] = _to_num(el.get("content") or el.get_text(strip=True))
    if out["review_count"] is None:
        el = soup.find(attrs={"itemprop": ["reviewCount", "ratingCount"]})
        if el:
            rc = _to_num(el.get("content") or el.get_text(strip=True))
            out["review_count"] = int(rc) if rc is not None else None
    if not out["brand"]:
        el = soup.find(attrs={"itemprop": "brand"})
        if el:
            out["brand"] = (el.get("content") or el.get_text(strip=True)) or None

    return out


_IMG_BLOCK_PAT = re.compile(
    r"(icon|logo|sprite|btn|button|banner|badge|blank|spacer|1x1|pixel|loading|"
    r"placeholder|emoji|/star|arrow|profile|avatar|sns|share|coupon|^data:)",
    re.I,
)


def _harvest_gallery_images(soup, main_image_url: Optional[str], limit: int = 10) -> list:
    """
    메인 이미지의 CDN host에 앵커링해 같은 host의 상품 이미지를 모은다.
    같은 CDN만 보므로 광고·아이콘·관련상품(다른 host) 노이즈가 거의 없다.
    main_image_url 이 없으면 앵커 불가 → 빈 리스트.
    """
    from urllib.parse import urlparse
    if not main_image_url:
        return []
    try:
        host = urlparse(main_image_url if "//" in main_image_url else "https:" + main_image_url).netloc
    except Exception:
        return []
    if not host:
        return []

    out: list = []
    seen: set = set()

    def _add(u: str):
        if not u or u.startswith("data:"):
            return
        if u.startswith("//"):
            u = "https:" + u
        if _IMG_BLOCK_PAT.search(u):
            return
        try:
            if urlparse(u).netloc != host:
                return
        except Exception:
            return
        base = u.split("?")[0]
        if base in seen:
            return
        seen.add(base)
        out.append(u)

    _add(main_image_url)
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-original") or ""
        srcset = img.get("srcset") or ""
        if srcset:
            parts = [p.strip().split(" ")[0] for p in srcset.split(",") if p.strip()]
            if parts:
                src = parts[-1]  # 가장 큰 해상도
        # 작은 아이콘 크기 필터 (width/height 속성)
        for dim in (img.get("width"), img.get("height")):
            try:
                if dim and int(re.sub(r"\D", "", str(dim)) or "999") < 100:
                    src = ""
                    break
            except Exception:
                pass
        if src:
            _add(src)
        if len(out) >= limit:
            break
    return out


def _extract_shipping_universal(soup) -> tuple:
    """
    텍스트 기반 범용 배송비 추출 (MUI/emotion 등 클래스명 무관 — '무료배송'·'배송비 N원' 텍스트로).
    반환 (shipping_fee: float|None, shipping_fee_text: str|None). 0.0 = 무료.
    """
    text = soup.get_text(" ", strip=True)
    if not text:
        return None, None
    text = re.sub(r"\s+", " ", text)
    # 배송 관련 구간으로 범위 한정 (가격 추출용; 할부·적립 등 오매칭 방지)
    m = re.search(r"배송비.{0,140}", text) or re.search(r"배송\s*안내.{0,140}", text)
    area = m.group(0) if m else text[:2500]
    head = text[:4000]

    # 1) 유료 + 조건부 무료: "2,500원 (2만원 이상 무료배송)"
    combined = re.search(r"([\d,]+)\s*원[^(]{0,30}\([^)]*[\d,]+\s*만?\s*원\s*이상[^)]*무료[^)]*\)", area)
    if combined:
        return _to_num(combined.group(1)), combined.group(0).strip()
    # 2) 순수 조건부 무료(기본 배송비 미표시): "3만원 이상 무료배송" — 무조건 무료보다 먼저 검사
    cond = re.search(r"([\d,]+\s*만?\s*원)\s*이상[^.]{0,25}무료\s*배송?", area)
    if cond:
        return None, cond.group(0).strip()
    # 3) 무조건 무료 (전체 텍스트에서 '무료배송'·'배송비 무료'·'무료 배송')
    if re.search(r"무료\s*배송|배송비?\s*무료|무료배송", head):
        return 0.0, "무료배송"
    # 4) 일반 유료
    m2 = (re.search(r"배송비\s*[:：]?\s*([\d,]+)\s*원", area)
          or re.search(r"([\d,]+)\s*원", area))
    if m2:
        fee = _to_num(m2.group(1))
        if fee and 0 < fee < 100000:
            return fee, f"{m2.group(1)}원"
    return None, None


def _extract_embedded_review(html: str) -> tuple:
    """HTML 내장 JSON의 평점/리뷰수 키 추출 (네이버 averageReviewScore 등). 반환 (rating, review_count)."""
    rating = review_count = None
    for key in ("averageReviewScore", "averageScore", "scoreAverage", "reviewScoreAverage"):
        m = re.search(r'["\']' + key + r'["\']\s*:\s*([0-9]+(?:\.[0-9]+)?)', html)
        if m:
            try:
                v = float(m.group(1))
                if 0 < v <= 5:
                    rating = v
                    break
            except ValueError:
                pass
    for key in ("totalReviewCount", "reviewCount", "reviewAmount", "reviewTotalCount"):
        m = re.search(r'["\']' + key + r'["\']\s*:\s*([0-9]+)', html)
        if m:
            try:
                review_count = int(m.group(1))
                break
            except ValueError:
                pass
    return rating, review_count


def _merge_universal(base: "ProductInfo", soup) -> "ProductInfo":
    """site 파서 결과(base)의 빈 필드를 범용 구조화 데이터로 채운다(비파괴: 기존 값 우선)."""
    try:
        u = _universal_structured(soup)
    except Exception as e:
        logger.debug("[universal] 추출 실패 (무시): %s", e)
        return base
    if not base.title and u["title"]:
        base.title = u["title"]
    if base.discounted_price is None and u["discounted_price"] is not None:
        base.discounted_price = u["discounted_price"]
    if base.original_price is None and u["original_price"] is not None:
        base.original_price = u["original_price"]
    if base.original_price is None and base.discounted_price is not None:
        base.original_price = base.discounted_price
    if not base.brand and u["brand"]:
        base.brand = u["brand"]
    if base.rating is None and u["rating"] is not None:
        base.rating = u["rating"]
    if base.review_count is None and u["review_count"] is not None:
        base.review_count = u["review_count"]
    if not base.main_image_url and u["main_image_url"]:
        base.main_image_url = u["main_image_url"]
    if not base.images and u["images"]:
        base.images = u["images"][:10]
    if not base.product_weight and u["product_weight"]:
        base.product_weight = u["product_weight"]

    # 갤러리 보강: 이미지가 1장 이하면 메인 이미지 CDN host 앵커로 같은 host 갤러리 수집
    if len(base.images or []) <= 1:
        anchor = base.main_image_url or (base.images[0] if base.images else None) or u.get("main_image_url")
        try:
            gallery = _harvest_gallery_images(soup, anchor)
        except Exception:
            gallery = []
        if len(gallery) > len(base.images or []):
            base.images = gallery[:10]
            if not base.main_image_url:
                base.main_image_url = gallery[0]
    return base


def _price_from_text(text: str) -> Optional[float]:
    """텍스트에서 가격 패턴(숫자 + 원/₩) 추출. 가장 큰 값 반환."""
    patterns = [
        r"(\d[\d,]+)\s*원",
        r"₩\s*(\d[\d,]+)",
        r"(\d[\d,]+)\s*₩",
    ]
    found = []
    for pat in patterns:
        for m in re.finditer(pat, text):
            v = _to_num(m.group(1))
            if v and v >= 100:  # 100원 미만은 가격이 아닐 가능성
                found.append(v)
    return max(found) if found else None


def _soup(html: str):
    from bs4 import BeautifulSoup
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")


# ---------------------------------------------------------------------------
# 네이버 전용: PRELOADED_STATE 추가 추출
# ---------------------------------------------------------------------------

def _extract_preloaded(html: str) -> dict:
    m = re.search(r"__PRELOADED_STATE__\s*=\s*(\{)", html)
    if not m:
        return {}
    start = m.start(1)

    # 1차: 직접 파싱
    try:
        obj, _ = json.JSONDecoder().raw_decode(html, start)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    # 2차: 브라켓 매칭으로 JSON 블록 추출 후 undefined→null 치환
    try:
        depth = 0
        in_str = False
        esc = False
        end = -1
        for i in range(start, min(start + 3_000_000, len(html))):
            c = html[i]
            if esc:
                esc = False
                continue
            if c == '\\' and in_str:
                esc = True
                continue
            if c == '"':
                in_str = not in_str
                continue
            if not in_str:
                if c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
        if end > start:
            raw = html[start:end]
            raw = re.sub(r'\bundefined\b', 'null', raw)
            obj = json.loads(raw)
            if isinstance(obj, dict):
                logger.debug("[PRELOADED_STATE] 파싱 성공 (undefined 치환 후)")
                return obj
    except Exception as e:
        logger.warning("[PRELOADED_STATE] JSON 파싱 실패: %s", e)
    return {}


# ─── 네이버 옵션 추출 ─────────────────────────────────────────────────────────
#
# 전략: 신뢰도 높은 구조화 데이터만 사용.
#   1) __PRELOADED_STATE__ JSON — 실제 상품 옵션 키만 탐색
#   2) 일시품절 앵커 — 품절 텍스트로 옵션 그룹 위치 확정
#   3) <select> 드롭다운 — 수량·배송 select 제외 필터 적용
#
# 3-B 형제 패턴(이전 버전)은 오탐이 너무 많아 제거됨.
# ---------------------------------------------------------------------------

# 1단계에서 PRELOADED_STATE 재귀 시 건너뛸 최상위 키
_STATE_SKIP_KEYS = frozenset({
    "review", "reviews", "qna", "questions", "comment", "comments",
    "recommend", "related", "similar", "category", "categories",
    "seller", "store", "brand", "cart", "wish", "wishlist",
    "coupon", "coupons", "benefit", "delivery", "shipping",
    "payment", "search", "filter", "sort", "banner", "ad",
    "analytics", "log", "trace", "config", "setting",
})

# select의 name/id에 이것이 포함되면 수량·정렬 등 → 옵션 아님
_SELECT_SKIP_NAME = re.compile(
    r"qty|quantity|cnt|count|num|sort|order|filter|delivery|ship|pay|region|area",
    re.I,
)

# select 값이 전부 정수면 수량 선택기
_ALL_NUMERIC = re.compile(r"^\d+$")

# 옵션 타입 레이블로 인정할 텍스트 (색상·사이즈 계열)
_OPTION_TYPE_KEYWORDS = re.compile(
    r"색상|컬러|color|사이즈|크기|size|용량|무게|맛|향|타입|종류|소재|재질|모델|버전|패턴",
    re.I,
)


def _find_state_option_groups(obj, depth: int = 0) -> list:
    """PRELOADED_STATE를 재귀 탐색 — 실제 상품 옵션 키만 반환."""
    if depth > 15 or not isinstance(obj, (dict, list)):
        return []

    if isinstance(obj, list):
        for item in obj:
            r = _find_state_option_groups(item, depth + 1)
            if r:
                return r
        return []

    # ── 패턴 B: optionCombinationGroupList ───────────────────────────────────────
    groups_b: list = []
    comb = obj.get("optionCombinationGroupList")
    if isinstance(comb, list) and comb:
        for group_idx, g in enumerate(comb):
            if not isinstance(g, dict):
                continue
            gname = (g.get("groupName") or "옵션").strip()
            combos = g.get("optionCombinations") or []
            # 다차원 옵션: 그룹 인덱스에 맞는 optionNameN 우선, 없으면 optionName1 fallback
            name_key = f"optionName{group_idx + 1}"
            value_total: dict = {}
            value_soldout: dict = {}
            seen_order: list = []
            for c in combos:
                if not isinstance(c, dict):
                    continue
                name = str(c.get(name_key) or "").strip()
                if not name:
                    name = str(c.get("optionName1") or c.get("name") or c.get("value") or "").strip()
                if not name:
                    continue
                if name not in value_total:
                    value_total[name] = 0
                    value_soldout[name] = 0
                    seen_order.append(name)
                value_total[name] += 1
                if (c.get("stockQuantity", 1) == 0
                        or c.get("usable") is False
                        or c.get("soldOutYn") in ("Y", True, "true")):
                    value_soldout[name] += 1
            soldout = [v for v in seen_order if value_total[v] > 0 and value_soldout[v] >= value_total[v]]
            if seen_order:
                groups_b.append({"type": gname, "values": seen_order, "soldout": soldout})

    # ── 패턴 A: productOptionDTOList ─────────────────────────────────────────────
    groups_a: list = []
    dto = obj.get("productOptionDTOList")
    if isinstance(dto, list) and dto:
        # soldout 정보는 B에서 추출
        soldout_by_group: dict = {}
        for group_idx, cg in enumerate((obj.get("optionCombinationGroupList") or [])):
            if not isinstance(cg, dict):
                continue
            gname = (cg.get("groupName") or "").strip()
            name_key = f"optionName{group_idx + 1}"
            for c in (cg.get("optionCombinations") or []):
                if not isinstance(c, dict):
                    continue
                name = str(c.get(name_key) or c.get("optionName1") or "").strip()
                if name and (c.get("stockQuantity", 1) == 0
                             or c.get("usable") is False
                             or c.get("soldOutYn") in ("Y", True, "true")):
                    soldout_by_group.setdefault(gname, set()).add(name)
        for g in dto:
            if not isinstance(g, dict):
                continue
            gname = (g.get("groupName") or g.get("name") or "옵션").strip()
            vals = g.get("optionNameListByProductDetail") or g.get("optionValues") or []
            vals = [str(v).strip() for v in vals if str(v).strip()]
            soldout = [v for v in vals if v in soldout_by_group.get(gname, set())]
            if vals:
                groups_a.append({"type": gname, "values": vals, "soldout": soldout})

    # ── 패턴 C: optionStandards (simpleProductForDetailPage 등에서 사용) ──────────
    groups_c: list = []
    standards = obj.get("optionStandards")
    if isinstance(standards, list) and standards:
        for g in standards:
            if not isinstance(g, dict):
                continue
            gname = (g.get("groupName") or g.get("name") or "옵션").strip()
            vals = (g.get("optionNameListByProductDetail")
                    or g.get("optionValues")
                    or g.get("values") or [])
            vals = [str(v).strip() for v in vals if str(v).strip()]
            if vals:
                groups_c.append({"type": gname, "values": vals, "soldout": []})

    # 세 패턴 중 그룹 수가 가장 많은 것 선택 (같으면 soldout 있는 B 우선)
    all_candidates = [(groups_b, True), (groups_a, False), (groups_c, False)]
    best = max(all_candidates, key=lambda x: len(x[0]))
    if best[0]:
        return best[0]

    # ── 재귀 (노이즈 키 건너뜀) ───────────────────────────────────────────────
    for k, v in obj.items():
        if k.lower() in _STATE_SKIP_KEYS:
            continue
        r = _find_state_option_groups(v, depth + 1)
        if r:
            return r
    return []


def _extract_naver_options_from_state(html: str) -> list:
    """1단계: __PRELOADED_STATE__ JSON에서 상품 옵션 그룹 추출."""
    state = _extract_preloaded(html)
    if not state:
        return []
    # simpleProductForDetailPage.A.optionStandards 직접 확인
    try:
        spf = state.get("simpleProductForDetailPage") or {}
        for prod_id, prod in spf.items():
            if not isinstance(prod, dict):
                continue
            standards = prod.get("optionStandards")
            if standards:
                logger.info("[PRELOADED_STATE] optionStandards[0] 샘플: %s", standards[0] if standards else None)
    except Exception:
        pass
    raw = _find_state_option_groups(state)
    logger.info("[PRELOADED_STATE] 옵션 그룹 %d개: %s", len(raw), [g['type'] for g in raw])
    return [
        ProductOption(
            option_type=g["type"],
            available_values=g["values"],
            selected_value=None,
            soldout_values=g["soldout"] or None,
        )
        for g in raw
    ]


def _extract_naver_options_via_soldout(soup) -> list:
    """2단계: '일시품절' 텍스트를 앵커로 옵션 그룹 추출."""
    _SKIP_RE = re.compile(r"옵션\s*선택|선택하세요|선택\s*해\s*주세요")
    soldout_texts = soup.find_all(string=re.compile(r"^(일시)?품절$"))
    if not soldout_texts:
        return []

    results = []
    seen_groups: set = set()

    for sot in soldout_texts:
        soldout_el = sot.parent
        if not soldout_el:
            continue
        option_item = soldout_el.parent
        if not option_item or option_item.name not in ("span", "div", "li", "button", "a"):
            continue
        group = option_item.parent
        if not group:
            continue
        gid = id(group)
        if gid in seen_groups:
            continue
        seen_groups.add(gid)

        item_tag = option_item.name
        available: list[str] = []
        soldout_vals: list[str] = []
        _SOLDOUT_CLS = re.compile(r"sold.?out|품절|disable", re.I)
        _SOLDOUT_TEXT = re.compile(r"(일시)?품절")

        for child in group.children:
            if not hasattr(child, "name") or child.name != item_tag:
                continue
            first = child.find(True, recursive=False)
            name_from_first = first.get_text(strip=True) if first else ""
            # first 자식이 품절 뱃지 자체인 경우(예: <li>화이트 <span>일시품절</span></li>)
            # → 전체 텍스트에서 품절 부분을 제거해야 함
            if not name_from_first or re.search(r"^(일시)?품절$", name_from_first):
                raw_text = child.get_text(strip=True)
            else:
                raw_text = name_from_first
            name = re.sub(r"\s*[\(\[](품절|일시품절)[)\]]|\s*(일시)?품절$", "", raw_text).strip()
            if not name or len(name) > 60 or _SKIP_RE.search(name):
                continue
            available.append(name)
            is_soldout = bool(
                child.find(string=_SOLDOUT_TEXT)
                or child.get("disabled")
                or any(_SOLDOUT_CLS.search(c) for c in child.get("class", []))
                or re.search(r"(일시)?품절", child.get_text(strip=True))
            )
            if is_soldout:
                soldout_vals.append(name)

        if available:
            # 그룹 레이블 탐색
            opt_type = "옵션"
            for el in (group.find_previous_sibling(), group.parent):
                if not el or not hasattr(el, "get_text"):
                    continue
                t = el.get_text(separator=" ", strip=True)
                m = re.match(r"^([가-힣a-zA-Z0-9 /\-]{1,20})", t)
                if m:
                    lbl = m.group(1).strip()
                    if lbl and lbl not in ("선택", "옵션"):
                        opt_type = lbl
                        break
            results.append(ProductOption(
                option_type=opt_type,
                available_values=available,
                selected_value=None,
                soldout_values=soldout_vals or None,
            ))

    return results


def _extract_naver_options_from_select(soup) -> list:
    """3단계: <select> 드롭다운에서 옵션 추출 (수량·배송·정렬 select 제외)."""
    _PLACEHOLDER = re.compile(r"^(옵션\s*선택|선택하세요|선택\s*해\s*주세요|전체|-- .+ --)$")
    results = []
    seen: set = set()

    for sel in soup.find_all("select"):
        # 수량·정렬 등 select 제외
        sel_id = (sel.get("id") or "") + (sel.get("name") or "")
        if _SELECT_SKIP_NAME.search(sel_id):
            continue

        vals, soldout = [], []
        for opt in sel.find_all("option"):
            text = opt.get_text(strip=True)
            if not text or _PLACEHOLDER.match(text):
                continue
            clean = re.sub(r"\s*[\(\[](품절|일시품절)[)\]]$|\s+(일시)?품절$", "", text).strip()
            if not clean or len(clean) > 60:
                continue
            vals.append(clean)
            if opt.get("disabled") or re.search(r"품절|일시품절", text):
                soldout.append(clean)

        if len(vals) < 2:
            continue

        # 전부 숫자면 수량 선택기
        if all(_ALL_NUMERIC.match(v) for v in vals):
            continue

        # 중복 확인
        key = tuple(vals)
        if key in seen:
            continue
        seen.add(key)

        # 레이블 탐색 — <label>, <dt>, <strong> 등
        opt_type = "옵션"
        prev = sel.find_previous(["label", "strong", "dt", "th"])
        if prev:
            lt = prev.get_text(strip=True)
            if lt and len(lt) <= 20 and not _PLACEHOLDER.match(lt):
                opt_type = lt

        results.append(ProductOption(
            option_type=opt_type,
            available_values=vals,
            selected_value=None,
            soldout_values=soldout or None,
        ))

    return results


def _extract_naver_options_via_shp(soup) -> list:
    """data-shp-contents-id 속성으로 네이버 스마트스토어 옵션 추출.

    <button data-shp-contents-id="초코" data-shp-contents-type="맛" data-shp-contents-grp="form">
    <div   data-shp-contents-id="52g, 5개" data-shp-contents-type="용량, 수량" data-shp-contents-grp="form">
    형태의 요소를 찾아 그룹별로 묶음.
    """
    # data-shp-inventory="grppd" → 상품 옵션 그리드 요소 (버튼/행)
    # data-shp-contents-grp="form" + contents-id/type 있어야 실제 옵션 항목
    items = soup.find_all(attrs={"data-shp-contents-grp": "form"})
    items = [
        el for el in items
        if el.get("data-shp-contents-id")
        and el.get("data-shp-contents-type")
        and el.get("data-shp-inventory") == "grppd"
    ]
    if not items:
        # grppd 필터 없이 재시도 (일부 상품은 inventory 값이 다를 수 있음)
        items = soup.find_all(attrs={"data-shp-contents-grp": "form"})
        items = [el for el in items if el.get("data-shp-contents-id") and el.get("data-shp-contents-type")]
    if not items:
        return []

    _SOLDOUT_RE = re.compile(r"(일시)?품절")
    groups: dict = {}
    group_order: list = []

    for el in items:
        cid = el.get("data-shp-contents-id", "").strip()
        ctype = el.get("data-shp-contents-type", "옵션").strip()
        if not cid:
            continue
        if ctype not in groups:
            groups[ctype] = {"vals": [], "soldout": [], "seen": set()}
            group_order.append(ctype)
        if cid in groups[ctype]["seen"]:
            continue  # 같은 값 중복 제거
        groups[ctype]["seen"].add(cid)
        groups[ctype]["vals"].append(cid)
        # 품절 감지: 텍스트, CSS-disabled input, aria-disabled
        if (el.find(string=_SOLDOUT_RE)
                or el.select_one("input[disabled]")
                or el.get("aria-disabled") == "true"
                or el.get("disabled") is not None):
            groups[ctype]["soldout"].append(cid)

    result = []
    for ctype in group_order:
        g = groups[ctype]
        if g["vals"]:
            result.append(ProductOption(
                option_type=ctype,
                available_values=g["vals"],
                selected_value=None,
                soldout_values=g["soldout"] or None,
            ))
    return result


def _dedup_naver_options(opts: list) -> list:
    """옵션 그룹 내 중복 값 제거 + 동일 타입 그룹 중 값이 더 많은 것으로 합침."""
    merged: dict = {}   # option_type → ProductOption
    order: list = []

    for opt in opts:
        # 값 내 중복 제거 (순서 유지)
        seen: set = set()
        vals: list = []
        for v in opt.available_values:
            if v not in seen:
                seen.add(v)
                vals.append(v)
        soldout = [v for v in (opt.soldout_values or []) if v in seen]

        if opt.option_type not in merged:
            merged[opt.option_type] = ProductOption(
                option_type=opt.option_type,
                available_values=vals,
                selected_value=opt.selected_value,
                soldout_values=soldout or None,
            )
            order.append(opt.option_type)
        else:
            # 같은 타입이 이미 있으면 값이 더 많은 것 유지, soldout은 합집합
            existing = merged[opt.option_type]
            if len(vals) >= len(existing.available_values):
                combined_soldout = list(set((existing.soldout_values or []) + soldout)) or None
                merged[opt.option_type] = ProductOption(
                    option_type=opt.option_type,
                    available_values=vals,
                    selected_value=opt.selected_value or existing.selected_value,
                    soldout_values=combined_soldout,
                )

    return [merged[t] for t in order]


def _extract_naver_options_listbox(soup) -> list:
    """vuCQVdmISZ listbox 기반 네이버 옵션 추출.

    구조:
      div.HGhKRgytBM
        a[data-shp-contents-type]  → 옵션 타입명 (속성값)
        ul.vuCQVdmISZ[role="listbox"]
          li > a[data-shp-contents-id]  → 옵션값 (텍스트)
            텍스트 끝에 " (품절)" 있으면 품절
    """
    _SOLDOUT_SUF = re.compile(r'\s*\(품절\)\s*$')
    result = []

    for group_div in soup.find_all(class_="HGhKRgytBM"):
        type_el = group_div.find(attrs={"data-shp-contents-type": True})
        option_type = (type_el.get("data-shp-contents-type") or "옵션").strip() if type_el else "옵션"

        listbox = group_div.select_one('ul[role="listbox"]')
        if not listbox:
            continue

        values: list[str] = []
        soldout_values: list[str] = []
        selected_value = None

        for li in listbox.find_all("li"):
            a = li.find("a", attrs={"data-shp-contents-id": True})
            if not a:
                continue
            text = a.get_text(strip=True)
            if not text:
                continue
            is_soldout = bool(_SOLDOUT_SUF.search(text))
            name = _SOLDOUT_SUF.sub("", text).strip()
            if not name or len(name) > 80:
                continue
            values.append(name)
            if is_soldout:
                soldout_values.append(name)
            if a.get("aria-selected") == "true":
                selected_value = name

        if values:
            result.append(ProductOption(
                option_type=option_type,
                available_values=values,
                selected_value=selected_value,
                soldout_values=soldout_values or None,
            ))

    return result


def _extract_naver_options(soup, html: str = "") -> list:
    """네이버 스마트스토어 옵션 추출.

    모든 방법을 실행한 뒤 soldout 포함된 결과 우선 반환.
    soldout 있는 결과 없으면 옵션값이라도 있는 첫 번째 반환.
    최종 반환 전 중복 값 제거.
    """
    candidates: list[tuple[str, list]] = []

    # 1. PRELOADED_STATE JSON (optionCombinationGroupList → productOptionDTOList)
    if html:
        r = _extract_naver_options_from_state(html)
        if r:
            candidates.append(("PRELOADED_STATE", r))

    # 2. data-shp-contents-id 속성 (버튼/행 형태)
    r = _extract_naver_options_via_shp(soup)
    if r:
        candidates.append(("data-shp", r))

    # 3. 일시품절 텍스트 앵커
    r = _extract_naver_options_via_soldout(soup)
    if r:
        candidates.append(("일시품절 앵커", r))

    # 4. <select> 드롭다운
    r = _extract_naver_options_from_select(soup)
    if r:
        candidates.append(("select", r))

    # 5. vuCQVdmISZ listbox (신형 UI)
    r = _extract_naver_options_listbox(soup)
    if r:
        candidates.append(("listbox", r))

    if not candidates:
        return []

    # 각 방법의 결과를 dedup 후 그룹 수 기준으로 정렬
    scored: list[tuple[int, bool, str, list]] = []
    for name, opts in candidates:
        deduped = _dedup_naver_options(opts)
        has_soldout = any(o.soldout_values for o in deduped)
        scored.append((len(deduped), has_soldout, name, deduped))

    # soldout 있는 것 우선, 같으면 그룹 수 많은 것
    scored.sort(key=lambda x: (x[1], x[0]), reverse=True)
    best_count, best_soldout, best_name, best_opts = scored[0]
    logger.info("[HTML 파서/네이버] %s 옵션 %d그룹%s (후보 %d개: %s)",
                best_name, best_count,
                " (soldout 포함)" if best_soldout else "",
                len(scored),
                [(s[2], s[0]) for s in scored])
    return best_opts


def _parse_naver(html: str, page_title: Optional[str], url: Optional[str]) -> ProductInfo:
    soup = _soup(html)
    meta = _extract_meta(soup)
    product = _extract_jsonld_product(soup)

    offers = product.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}

    price = _to_num(_first(
        offers.get("price"),
        offers.get("lowPrice"),
        meta.get("product:price:amount"),
        meta.get("og:price:amount"),
    ))
    original = _to_num(_first(offers.get("highPrice")))  # None이면 아래에서 결정

    image = product.get("image") or meta.get("og:image")
    if isinstance(image, list):
        image = image[0] if image else None
    if isinstance(image, dict):
        image = image.get("url")

    title = _first(product.get("name"), meta.get("og:title"), page_title)

    logger.info("[HTML 파서/네이버] JSON-LD: price=%s original=%s title=%s", price, original, title)

    # PRELOADED_STATE fallback
    if not price or not title:
        preloaded = _extract_preloaded(html)
        for key, val in preloaded.items():
            if not isinstance(val, dict):
                continue
            if any(k in key.lower() for k in ("product", "item")):
                title = title or val.get("name") or val.get("productName")
                price = price or _to_num(val.get("salePrice") or val.get("price"))
                original = original or _to_num(
                    val.get("consumerPrice") or val.get("originalPrice")
                )
                image = image or val.get("representativeImageUrl") or val.get("mainImage")

    # 네이버 스마트스토어 전용 CSS 셀렉터로 가격 추출 (JSON-LD보다 신뢰)
    # del.v4swfx73Z2 → 할인전 / span.weP_mymkqG → 할인후 / span.ZsPUWVTk13 → 할인율
    rate_el = soup.select_one("span.ZsPUWVTk13")
    orig_el = soup.select_one("del.v4swfx73Z2")
    disc_el = soup.select_one("span.weP_mymkqG")
    logger.info("[HTML 파서/네이버] 셀렉터: rate_el=%s orig_el=%s disc_el=%s",
                rate_el.get_text(strip=True) if rate_el else None,
                orig_el.get_text(strip=True) if orig_el else None,
                disc_el.get_text(strip=True) if disc_el else None)

    if orig_el:
        m = re.search(r"([\d,]+)\s*원", orig_el.get_text())
        if m:
            original = float(m.group(1).replace(",", ""))
            logger.info("[HTML 파서/네이버] 할인전 CSS 추출: %s", original)
    if disc_el:
        v = _to_num(re.sub(r"[^\d]", "", disc_el.get_text()))
        if v:
            price = v
            logger.info("[HTML 파서/네이버] 할인후 CSS 추출: %s", price)

    # HTML 구조 fallback (del=원가, strong=판매가)
    if not original:
        del_el = soup.find("del")
        if del_el:
            m = re.search(r"([\d,]+)\s*원", del_el.get_text())
            if m:
                original = float(m.group(1).replace(",", ""))
                logger.info("[HTML 파서/네이버] 할인전 del fallback: %s", original)
    if not price:
        strong_el = soup.find("strong")
        if strong_el:
            v = _to_num(re.sub(r"[^\d]", "", strong_el.get_text()))
            if v:
                price = v

    if not original:
        original = price

    # 할인율: span.ZsPUWVTk13 → span.blind 순으로 추출
    discount_rate_html = None
    if rate_el:
        m_dr = re.search(r"(\d+)\s*%", rate_el.get_text())
        if m_dr:
            discount_rate_html = float(m_dr.group(1))
            logger.info("[HTML 파서/네이버] 할인율 CSS 추출: %s", discount_rate_html)
    if discount_rate_html is None:
        for blind in soup.find_all(class_="blind"):
            m_dr = re.search(r"(\d+)\s*%", blind.get_text())
            if m_dr:
                discount_rate_html = float(m_dr.group(1))
                break

    # 텍스트 fallback
    if not price:
        price = _price_from_text(html)
        original = original or price

    if not title:
        h = soup.find("h1") or soup.find("h2")
        title = h.get_text(strip=True) if h else page_title

    discount_rate = discount_rate_html
    if discount_rate is None and original and price and original > price:
        discount_rate = round((original - price) / original * 100, 1)

    currency = offers.get("priceCurrency", "KRW") or meta.get("product:price:currency", "KRW")

    naver_options = _extract_naver_options(soup, html)
    if not naver_options:
        logger.info("[HTML 파서/네이버] 옵션 없음 (또는 추출 실패)")

    # 배송비: span.Njct5hT6_B / span.X771s58c2z (SVG 제거 후 추출)
    shipping_fee: Optional[float] = None
    import copy as _copy
    ship_spans = soup.select("span.Njct5hT6_B, span.X771s58c2z")
    logger.info("[HTML 파서/네이버] 배송비 span 수: %d", len(ship_spans))
    for sp in ship_spans:
        tmp = _copy.copy(sp)
        for svg in tmp.find_all("svg"):
            svg.decompose()
        text = tmp.get_text(strip=True)
        logger.info("[HTML 파서/네이버] 배송비 span text=%r", text)
        if not text:
            continue
        if "무료" in text and "배송" in text and "이상" not in text:
            shipping_fee = 0.0
            break
        m_fee = re.search(r"([\d,]+)\s*원", text)
        if m_fee:
            shipping_fee = float(m_fee.group(1).replace(",", ""))
            break
    if shipping_fee is None:
        m_fee = re.search(r"([\d,]+)\s*원\s*\([^)]*이상\s*무료배송", html)
        if m_fee:
            shipping_fee = float(m_fee.group(1).replace(",", ""))
    logger.info("[HTML 파서/네이버] title=%s price=%s original=%s discount_rate=%s shipping_fee=%s",
                title, price, original, discount_rate, shipping_fee)

    return ProductInfo(
        title=title,
        original_price=original,
        discounted_price=price,
        discount_rate=discount_rate,
        main_image_url=image,
        shipping_period=None,
        shipping_fee=shipping_fee,
        product_options=naver_options,
        product_weight=None,
        currency=currency,
        hs_code=None,
        raw_data={},
    )


# ---------------------------------------------------------------------------
# 쿠팡 옵션 추출 — 패턴별 함수 + 통합 진입점
# 새 UI 패턴이 생기면 _extract_options_<패턴명> 함수를 추가하고
# _extract_coupang_options 리스트에 등록하면 됩니다.
# ---------------------------------------------------------------------------

_SKIP_OPTION_TEXTS = re.compile(r"모든 옵션|절약 금액|더 보기", re.I)


def _extract_options_table_list(scope) -> list:
    """option-table-list__options 컨테이너 방식 (수량·단순 텍스트 옵션)."""
    options = []
    for group in scope.find_all(class_=re.compile(r"option.?table.?list__options$", re.I)):
        values, prices, soldout_values, selected_value = [], {}, [], None
        for item in group.find_all(class_=re.compile(r"option.?table.?list__option$", re.I)):
            name_el = item.find(class_=re.compile(r"option.?table.?list__option.?name", re.I))
            price_el = item.find(class_=re.compile(r"option.?table.?list__option.?price", re.I))
            name = name_el.get_text(strip=True) if name_el else item.get_text(strip=True)[:60]
            if not name or _SKIP_OPTION_TEXTS.search(name):
                continue
            values.append(name)
            if "일시품절" in item.get_text():
                soldout_values.append(name)
            if price_el:
                m = re.search(r"[\d,]+원", price_el.get_text())
                if m:
                    p = _to_num(re.sub(r"[^\d]", "", m.group()))
                    if p:
                        prices[name] = p
            if item.get("class") and any("selected" in c or "active" in c for c in item["class"]):
                selected_value = name
        if values:
            options.append(ProductOption(
                option_type="옵션",
                available_values=values,
                selected_value=selected_value,
                option_prices=prices or None,
                soldout_values=soldout_values or None,
            ))
    return options


def _extract_options_picker(scope) -> list:
    """option-picker-container / select-item 드롭다운 방식 (색상·모델 등)."""
    container = scope.find(class_=re.compile(r"option-picker-container", re.I))
    if not container:
        return []

    options = []
    for picker in container.find_all(class_=re.compile(r"option-picker-select\b", re.I)):
        ul = picker.find("ul")
        if not ul:
            continue

        # 옵션 타입 이름: 헤더 최상단 첫 div → 내부 flex-1 div → 첫 번째 child div 텍스트
        option_type = "옵션"
        header = picker.find("div", recursive=False)
        if header:
            flex1 = header.find("div", recursive=False)
            if flex1:
                first_label = flex1.find("div", recursive=False)
                t = first_label.get_text(strip=True) if first_label else ""
                if t:
                    option_type = t

        values, prices, soldout_values, selected_value = [], {}, [], None
        for li in ul.find_all("li"):
            item = li.find(class_=re.compile(r"\bselect-item\b", re.I))
            if not item:
                continue
            # 이름: bold + leading 클래스가 있는 첫 번째 div
            name_el = item.find("div", attrs={"class": re.compile(r"\btwc-font-bold\b")})
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            if not name or _SKIP_OPTION_TEXTS.search(name):
                continue
            values.append(name)
            # 일시품절 감지: item 전체 텍스트에 "일시품절" 포함 여부
            if "일시품절" in item.get_text():
                soldout_values.append(name)
            # 가격: <strong class="price-text ...">28,800<strong>원</strong></strong>
            price_el = item.find("strong", class_=re.compile(r"\bprice-text\b", re.I))
            if price_el:
                p = _to_num(re.sub(r"[^\d]", "", price_el.get_text()))
                if p:
                    prices[name] = p
            # 선택 여부
            item_classes = " ".join(item.get("class", []))
            if "selected" in item_classes or "active" in item_classes:
                selected_value = name

        if values:
            options.append(ProductOption(
                option_type=option_type,
                available_values=values,
                selected_value=selected_value,
                option_prices=prices or None,
                soldout_values=soldout_values or None,
            ))
    return options


# 새 패턴 추가 시 이 리스트에 함수를 등록하세요
_COUPANG_OPTION_EXTRACTORS = [
    _extract_options_table_list,
    _extract_options_picker,
]


def _extract_coupang_options(scope) -> list:
    """모든 등록된 패턴을 순서대로 시도해 옵션을 통합 추출."""
    results = []
    for extractor in _COUPANG_OPTION_EXTRACTORS:
        results.extend(extractor(scope))
    return results


# ---------------------------------------------------------------------------
# 쿠팡 / 범용
# ---------------------------------------------------------------------------

def _parse_coupang(html: str, page_title: Optional[str], url: Optional[str]) -> ProductInfo:
    """
    쿠팡 상품 상세 파서.
    div[data-overlay-container] 스코프 안에서 추출하고 노이즈 영역은 제거.
    """
    soup = _soup(html)

    # 1. 파싱 스코프: data-overlay-container 우선, 없으면 전체
    _overlay = soup.find(attrs={"data-overlay-container": True})
    scope = _overlay or soup
    logger.info("[HTML 파서/쿠팡] scope=%s overlay_found=%s", getattr(scope, 'name', 'soup'), _overlay is not None)

    # 배송비 — 노이즈 제거 전에 추출
    shipping_fee: Optional[float] = None
    fee_container = scope.find(class_=re.compile(r"price-shipping-fee-info-container", re.I))
    if fee_container:
        fee_text = fee_container.get_text(" ", strip=True)
        if re.search(r"무료", fee_text):
            shipping_fee = 0.0
        else:
            _fm = re.search(r"([\d,]+)\s*원", fee_text)
            if _fm:
                shipping_fee = _to_num(_fm.group(1))

    # 배송 도착 예정일 (.pdd-contents) — 노이즈 제거 전에 추출. 선택된 배송 옵션 우선.
    shipping_period: Optional[str] = None
    _pdd = None
    for _item in scope.find_all(class_="radio-item"):
        _radio = _item.find("span", class_="radio")
        if _radio and "selected" in (_radio.get("class") or []):
            _pdd = _item.find(class_="pdd-contents")
            if _pdd:
                break
    if _pdd is None:
        _pdd = scope.find(class_="pdd-contents")
    if _pdd:
        _txt = " ".join(_pdd.get_text(" ", strip=True).split())
        shipping_period = _txt.replace("( ", "(").replace(" )", ")") or None

    # 노이즈 영역 제거 (추천/광고/리뷰/배송/적립금 등)
    _noise_attrs = [
        {"class": re.compile(r"recommend|related|advertisement|review|delivery|breadcrumb|banner|coupon|reward|saved|badge", re.I)},
        {"data-ad": True},
    ]
    for attr in _noise_attrs:
        for tag in scope.find_all(True, attr):
            tag.decompose()

    # 2. 제목 + 중고/반품 배지
    title = None
    used_condition = None

    # 2-a. 반품/중고 전용 페이지 배지 (used-only-badge-area) — 제목 탐색 전에 먼저 추출
    badge_area = scope.find(class_=re.compile(r"used.?only.?badge|used.?only.?product.?header", re.I))
    if not badge_area:
        badge_area = scope.find(class_="used-only-badge-area")
    if badge_area:
        offer_el = badge_area.find(class_=re.compile(r"\boffer\b", re.I))
        if offer_el:
            cond_text = offer_el.get_text(strip=True)
            if cond_text:
                used_condition = cond_text

    h1 = scope.find("h1", class_=re.compile(r"product.?title", re.I))
    if h1:
        # 반품/중고 배지(used-only-badge-area, offer 등)가 h1 안에 있으면
        # 텍스트를 먼저 읽어 used_condition에 저장한 뒤 제거
        for badge_el in h1.find_all(class_=re.compile(r"badge|offer|used.?only", re.I)):
            badge_text = badge_el.get_text(strip=True)
            if badge_text and not used_condition:
                used_condition = badge_text
            badge_el.decompose()
        span = h1.find("span")
        title = (span or h1).get_text(strip=True)

    # 2-b. 반품/중고 전용 레이아웃: h2.used-only-product-header__title
    if not title:
        h2_used = scope.find("h2", class_=re.compile(r"used.?only.?product.?header", re.I))
        if h2_used:
            title = h2_used.get_text(strip=True)

    if not title:
        # OG meta fallback
        og_title = soup.find("meta", property="og:title")
        title = og_title["content"].strip() if og_title and og_title.get("content") else page_title

    # 3 & 4. 가격 추출 — Tailwind 레이아웃 우선, 구형 클래스 셀렉터 폴백
    original = None
    price = None

    # [1순위] Tailwind 레이아웃 (신규 쿠팡 구조: price-layout-container)
    plc = scope.find(class_=re.compile(r"\bprice-layout-container\b"))
    # scope에서 못 찾으면 전체 soup에서 재시도
    if not plc and scope is not soup:
        plc = soup.find(class_=re.compile(r"\bprice-layout-container\b"))
    logger.info("[HTML 파서/쿠팡] price-layout-container 탐색: found=%s", plc is not None)
    if plc:
        # 원가: twc-line-through 클래스 요소
        lt_el = plc.find(class_=re.compile(r"\btwc-line-through\b"))
        if lt_el:
            original = _price_from_text(lt_el.get_text(separator=" "))
        # 판매가: 첫 번째 행에서 line-through·단위가격(당)·% 제외 후 추출
        rows = plc.find_all("div", recursive=False)
        if rows:
            for div in rows[0].find_all("div"):
                if "twc-line-through" in " ".join(div.get("class", [])):
                    continue
                txt = div.get_text(separator=" ", strip=True)
                if "당" in txt or "%" in txt:
                    continue
                p = _price_from_text(txt)
                if p and p >= 100:
                    price = p
                    break
        logger.info("[HTML 파서/쿠팡] Tailwind 레이아웃 추출: price=%s original=%s", price, original)

    # [2순위] 구형 클래스 셀렉터 (old layout)
    if not original:
        op_el = scope.find(class_=re.compile(r"original.?price.?amount", re.I))
        if not op_el:
            op_el = scope.find(class_=re.compile(r"original.?price", re.I))
        if op_el:
            original = _price_from_text(op_el.get_text(separator=" "))

    if not price:
        _MEMBERSHIP_KW = ("와우", "쿠폰")
        _final_title_el = scope.find(class_=re.compile(r"final.?price.?title", re.I))
        _final_price_title = _final_title_el.get_text(strip=True) if _final_title_el else ""
        _is_membership_price = any(kw in _final_price_title for kw in _MEMBERSHIP_KW)
        if _is_membership_price:
            sp_el = scope.find(class_=re.compile(r"sales.?price.?amount", re.I))
            if sp_el:
                price = _price_from_text(sp_el.get_text(separator=" "))
            if price:
                logger.info("[HTML 파서/쿠팡] %s 감지 → 쿠팡판매가 %s원 사용", _final_price_title, price)
    if not price:
        fp_el = scope.find(class_=re.compile(r"final.?price.?amount", re.I))
        if not fp_el:
            fp_el = scope.find(class_=re.compile(r"final.?price", re.I))
        if fp_el:
            price = _price_from_text(fp_el.get_text(separator=" "))

    # [3순위] OG meta
    if not price:
        og_price = soup.find("meta", attrs={"property": "product:price:amount"})
        if og_price:
            price = _to_num(og_price.get("content"))
    # [4순위] 전체 텍스트 스캔
    if not price:
        price = _price_from_text(scope.get_text())

    if not original:
        original = price

    # 5. 품절 감지 — out-of-stock-label div 또는 "일시품절" 텍스트
    sold_out = False
    oos_el = scope.find(class_=re.compile(r"out-of-stock-label|oos-stylized", re.I))
    if oos_el and re.search(r"(일시)?품절", oos_el.get_text(strip=True)):
        sold_out = True
    if not sold_out:
        # 구매 버튼 영역에 "품절" 단독 텍스트가 있으면 전체 품절
        buy_area = scope.find(class_=re.compile(r"prod-buy-button|purchase-button|buy-btn", re.I))
        if buy_area and re.search(r"^(일시)?품절$", buy_area.get_text(strip=True)):
            sold_out = True
    if sold_out:
        logger.info("[HTML 파서/쿠팡] 일시품절 감지")

    # 6. 옵션 — 패턴 자동 감지 (table-list / picker / 향후 추가 패턴)
    product_options = _extract_coupang_options(scope)

    discount_rate = round((original - price) / original * 100, 1) if original and price and original > price else None

    # 이미지 추출 (og:image 우선 → alt="Product image" → scope 첫 번째 coupangcdn.com)
    image = None
    og_img = soup.find("meta", property="og:image")
    if og_img:
        image = og_img.get("content")
    if not image:
        for img_tag in scope.find_all("img", alt=re.compile(r"^product.?image$", re.I)):
            src = img_tag.get("src") or img_tag.get("data-src") or ""
            if "coupangcdn.com" in src:
                image = src
                break
    if not image:
        img_tag = scope.find("img", src=re.compile(r"coupangcdn\.com", re.I))
        if img_tag:
            image = img_tag.get("src") or img_tag.get("data-src")
    # 프로토콜 생략 URL 보정: //thumbnail.coupangcdn.com/... → https://thumbnail.coupangcdn.com/...
    if image and image.startswith("//"):
        image = "https:" + image

    # 6. product-description 섹션에서 실측 치수 추출
    est_w = est_l = est_h = None
    dim_confidence = None
    dim_note = None
    coupang_desc_items: dict = {}

    desc_div = soup.find("div", class_="product-description")
    if desc_div:
        _items: dict = {}
        for li in desc_div.find_all("li"):
            text = li.get_text(strip=True)
            if ":" in text:
                k, _, v = text.partition(":")
                _items[k.strip()] = v.strip()
        coupang_desc_items = _items

        # 복합 사이즈 필드 (사이즈, 크기, 규격 등)
        _SIZE_KEYS = ("사이즈", "크기", "제품크기", "제품 크기", "본체크기", "본체 크기", "규격", "외형크기", "외형 크기")
        for _sk in _SIZE_KEYS:
            if _sk in _items:
                _m = re.search(
                    r"(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)",
                    _items[_sk],
                )
                if _m:
                    est_w, est_l, est_h = float(_m.group(1)), float(_m.group(2)), float(_m.group(3))
                    dim_confidence = "HIGH"
                    dim_note = f"쿠팡 상품설명 실측값 사용 ({_sk}: {_items[_sk]})"
                    break

        # 개별 치수 항목 보정
        def _sdim(s: str) -> Optional[float]:
            _mm = re.search(r"(\d+(?:\.\d+)?)", s)
            return float(_mm.group(1)) if _mm else None

        for _k in ("가로", "가로길이", "가로 길이", "폭", "너비"):
            if _k in _items and est_w is None:
                est_w = _sdim(_items[_k])
        for _k in ("세로", "세로길이", "세로 길이", "깊이"):
            if _k in _items and est_l is None:
                est_l = _sdim(_items[_k])
        for _k in ("높이", "높이(cm)", "높이 (cm)"):
            if _k in _items and est_h is None:
                est_h = _sdim(_items[_k])

        if est_w is not None and dim_confidence is None:
            _filled = sum(1 for v in (est_w, est_l, est_h) if v is not None)
            dim_confidence = "HIGH" if _filled == 3 else "MEDIUM"
            dim_note = "쿠팡 상품설명 개별 항목 조합"

    logger.info(
        "[HTML 파서/쿠팡] title=%s price=%s original=%s options=%d dims=(%s,%s,%s) sold_out=%s",
        title, price, original, len(product_options), est_w, est_l, est_h, sold_out,
    )
    return ProductInfo(
        title=title,
        original_price=original,
        discounted_price=price,
        discount_rate=discount_rate,
        main_image_url=image,
        shipping_period=shipping_period,
        shipping_fee=shipping_fee,
        product_options=product_options,
        product_weight=None,
        currency="KRW",
        hs_code=None,
        est_width_cm=est_w,
        est_length_cm=est_l,
        est_height_cm=est_h,
        dimension_confidence=dim_confidence,
        dimension_note=dim_note,
        used_condition=used_condition,
        sold_out=sold_out or None,
        raw_data={"coupang_description_items": coupang_desc_items} if coupang_desc_items else {},
    )


def _parse_generic(html: str, page_title: Optional[str], url: Optional[str]) -> ProductInfo:
    """OG meta + JSON-LD + 가격 정규식 기반 범용 파서."""
    soup = _soup(html)
    meta = _extract_meta(soup)
    product = _extract_jsonld_product(soup)

    offers = product.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}

    title = _first(
        product.get("name"),
        meta.get("og:title"),
        meta.get("twitter:title"),
        page_title,
    )

    price = _to_num(_first(
        offers.get("price"),
        offers.get("lowPrice"),
        meta.get("product:price:amount"),
        meta.get("og:price:amount"),
    ))
    original = _to_num(_first(offers.get("highPrice"))) or price

    image = _first(
        product.get("image"),
        meta.get("og:image"),
        meta.get("twitter:image:src"),
    )
    if isinstance(image, list):
        image = image[0] if image else None
    if isinstance(image, dict):
        image = image.get("url")

    # 가격 없으면 텍스트에서 추출
    if not price:
        price = _price_from_text(html)
        original = original or price

    # 제목 없으면 h1/h2
    if not title:
        h = soup.find("h1") or soup.find("h2")
        title = h.get_text(strip=True) if h else page_title

    discount_rate = None
    if original and price and original > price:
        discount_rate = round((original - price) / original * 100, 1)

    currency = (
        offers.get("priceCurrency")
        or meta.get("product:price:currency")
        or "KRW"
    )
    logger.info("[HTML 파서/범용] title=%s price=%s original=%s", title, price, original)

    return ProductInfo(
        title=title,
        original_price=original,
        discounted_price=price,
        discount_rate=discount_rate,
        main_image_url=image,
        shipping_period=None,
        product_options=[],
        product_weight=None,
        currency=currency,
        hs_code=None,
        raw_data={},
    )


# ---------------------------------------------------------------------------
# Next.js __NEXT_DATA__ 추출 (29cm, wconcept, ohou 등 SPA)
# ---------------------------------------------------------------------------

def _extract_next_data(soup) -> dict:
    """<script id="__NEXT_DATA__"> JSON 추출."""
    tag = soup.find("script", id="__NEXT_DATA__")
    if tag and tag.string:
        try:
            return json.loads(tag.string)
        except Exception:
            pass
    return {}


def _dig(obj, *keys):
    """중첩 dict/list에서 키 경로로 값 탐색."""
    for k in keys:
        if isinstance(obj, dict):
            obj = obj.get(k)
        elif isinstance(obj, list) and isinstance(k, int):
            obj = obj[k] if k < len(obj) else None
        else:
            return None
        if obj is None:
            return None
    return obj


# ---------------------------------------------------------------------------
# 사이트별 파서
# ---------------------------------------------------------------------------

def _parse_11st(html: str, page_title, url) -> ProductInfo:
    """
    11번가 상품 상세 파서.
    스코프: div#layBodyWrap — 광고/리뷰/스토어/카테고리 영역 제거 후 추출.
    """
    soup = _soup(html)

    # 1. 파싱 스코프
    scope = soup.find("div", id="layBodyWrap") or soup

    # 노이즈 영역 제거
    _noise = [
        {"id": re.compile(r"maxDiscountResult|coupon|review|banner|store|breadcrumb", re.I)},
        {"class": re.compile(r"c_product_store|review|breadcrumb|banner|coupon|share|wish|badge", re.I)},
    ]
    for attr in _noise:
        for tag in scope.find_all(True, attr):
            tag.decompose()
    for tag in scope.find_all("script"):
        tag.decompose()

    # 2. 제목
    title = None
    t_el = scope.select_one("div.c_product_info_title h1.title")
    if not t_el:
        t_el = scope.find("h1")
    if t_el:
        title = t_el.get_text(strip=True)
    if not title:
        og = soup.find("meta", property="og:title")
        title = og["content"].strip() if og and og.get("content") else page_title

    # 3. 원가 (취소선)
    original = None
    op_el = scope.select_one("div.b_product_info_price .price_regular del")
    if not op_el:
        op_el = scope.find("del")
    if op_el:
        original = _to_num(re.sub(r"[^\d]", "", op_el.get_text()))

    # 4. 최종 판매가
    price = None
    fp_el = scope.select_one("div.b_product_info_price #finalDscPrcArea dd.price strong")
    if not fp_el:
        # value + unit 조합
        val_el = scope.select_one("div.b_product_info_price #finalDscPrcArea dd.price .value")
        unit_el = scope.select_one("div.b_product_info_price #finalDscPrcArea dd.price .unit")
        if val_el:
            combined = val_el.get_text(strip=True) + (unit_el.get_text(strip=True) if unit_el else "")
            price = _to_num(re.sub(r"[^\d]", "", combined))
    if not fp_el and not price:
        fp_el = scope.select_one("div.b_product_info_price #finalDscPrcArea")
    if fp_el:
        price = _to_num(re.sub(r"[^\d]", "", fp_el.get_text()))
    if not price:
        og_price = soup.find("meta", attrs={"property": "product:price:amount"})
        if og_price:
            price = _to_num(og_price.get("content"))
    if not price:
        price = _price_from_text(scope.get_text())

    if not original:
        original = price

    # 5. 무게 (제목/옵션/속성에서)
    weight_text = None
    _weight_pat = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|g|ml|l|리터|킬로|그램)\b", re.I)
    _size_pat = re.compile(r"^\d{3}$")  # 230, 250 등 신발 사이즈 제외
    for text in [title or "", scope.get_text()]:
        m = _weight_pat.search(text)
        if m and not _size_pat.match(m.group(1)):
            weight_text = m.group(0).strip()
            break

    # 6. 옵션
    product_options = []

    def _11st_item_price(li_el) -> Optional[float]:
        """li 요소에서 가격 추출: data-price 속성 우선, 없으면 span.num.value"""
        raw = li_el.get("data-price") or li_el.get("data-addcompprc")
        if raw:
            return _to_num(re.sub(r"[^\d]", "", str(raw)))
        val_el = li_el.select_one("span.num.value, span.value")
        if val_el:
            return _to_num(re.sub(r"[^\d]", "", val_el.get_text()))
        return None

    # 6-a. 기본 옵션 (bot_option_section > ul.bot_typ_01)
    # l_product_buy_list 같은 floating 패널은 layBodyWrap 바깥에 있으므로 soup 전체도 탐색
    opt_sections = scope.select("div.accordion_section.bot_option_section")
    if not opt_sections:
        opt_sections = soup.select("div.accordion_section.bot_option_section")
    for opt_section in opt_sections:
        # 옵션 타입명: em.accordion_item.selected 또는 input[name=botOptTitle]
        type_el = opt_section.select_one("div.accordion_head em.accordion_item")
        inp_el  = opt_section.select_one("input[name='botOptTitle']")
        option_type = (
            (type_el.get_text(strip=True) if type_el else None)
            or (inp_el.get("value", "").strip() if inp_el else None)
            or "옵션"
        )

        ul = opt_section.select_one("ul.option_item_list")
        if not ul:
            continue

        values, prices, selected_val = [], {}, None
        for li in ul.select("li.option_item, li.c_product_option_item"):
            # 이름: data-dtloptnm > strong 텍스트
            name = (li.get("data-dtloptnm") or "").strip()
            if not name:
                strong = li.find("strong")
                name = strong.get_text(strip=True) if strong else ""
            if not name:
                continue
            values.append(name)
            p = _11st_item_price(li)
            if p:
                prices[name] = p
            # 선택 여부: 클래스에 'selected' 또는 'on' 포함
            cls = " ".join(li.get("class", []))
            if "selected" in cls or " on" in cls:
                selected_val = name

        if values:
            product_options.append(ProductOption(
                option_type=option_type,
                available_values=values,
                selected_value=selected_val,
                option_prices=prices or None,
            ))

    # 6-b. 추가구성품 (option_choice_wrap > bot_addPrd_section 그룹별)
    # 마찬가지로 scope 우선, 없으면 soup 전체
    add_wrap = scope.find(class_=re.compile(r"option_choice_wrap", re.I))
    if not add_wrap:
        add_wrap = soup.find(class_=re.compile(r"option_choice_wrap", re.I))
    if add_wrap:
        for section in add_wrap.select("div.accordion_section.bot_addPrd_section"):
            # 그룹명: em.accordion_item.selected
            grp_el = section.select_one("div.accordion_head em.accordion_item")
            grp_name = grp_el.get_text(strip=True) if grp_el else "추가구성"

            ul = section.select_one("ul.option_item_list")
            if not ul:
                continue

            values, prices = [], {}
            for li in ul.select("li"):
                # 이름: data-prdnm > strong 텍스트
                name = (li.get("data-prdnm") or "").strip()
                if not name:
                    strong = li.find("strong")
                    name = strong.get_text(strip=True) if strong else ""
                if not name:
                    continue
                values.append(name)
                p = _11st_item_price(li)
                if p:
                    prices[name] = p

            if values:
                product_options.append(ProductOption(
                    option_type=grp_name,
                    available_values=values,
                    selected_value=None,
                    option_prices=prices or None,
                ))

    discount_rate = round((original - price) / original * 100, 1) if original and price and original > price else None
    image = None
    og_img = soup.find("meta", property="og:image")
    if og_img:
        image = og_img.get("content")

    logger.info("[HTML 파서/11st] title=%s price=%s original=%s weight=%s options=%d",
                title, price, original, weight_text, len(product_options))
    return ProductInfo(
        title=title, original_price=original, discounted_price=price,
        discount_rate=discount_rate, main_image_url=image,
        shipping_period=None, product_options=product_options,
        product_weight=weight_text, currency="KRW", hs_code=None, raw_data={},
    )


def _extract_gmarket_minishop_options(scope) -> list:
    """지마켓 미니샵 스타일 옵션 박스 파싱.

    대상 구조:
        <div class="item_options uxeselectbox">
          <ul class="select-itemoption-list type_minishop uxeselect_dropdown">
            <li class="selected">  ← 현재 선택
              <a data-goodscode="..." data-groupindex="01">
                <img src="//gdimg.gmarket.co.kr/...">
                <span class="item_tit">상품 이름</span>
                <span class="item_price">5,500<em class="unit">원</em></span>
              </a>
            </li>
            <li class="">...</li>
          </ul>
        </div>
    """
    from models import ProductOption as _PO
    results = []
    seen_dropdowns: set = set()

    # div[class*='item_options'] 만 쓰면 div.item_options 도 포함됨
    # 콤마 셀렉터를 쓰면 같은 요소가 두 번 반환될 수 있으므로 하나로 통일
    containers = scope.select("div[class*='item_options']")
    logger.info("[gmarket/minishop] div.item_options 컨테이너 %d개 발견", len(containers))

    for ci, container in enumerate(containers):
        dropdown = container.select_one(
            "ul[class*='uxeselect_dropdown'], ul.select-itemoption-list"
        )
        if not dropdown:
            logger.info("[gmarket/minishop] 컨테이너[%d] ul.uxeselect_dropdown 없음 → 건너뜀", ci)
            continue

        dropdown_id = id(dropdown)
        if dropdown_id in seen_dropdowns:
            logger.info("[gmarket/minishop] 컨테이너[%d] 동일 dropdown 중복 → 건너뜀", ci)
            continue
        seen_dropdowns.add(dropdown_id)

        li_list = dropdown.select("li")
        logger.info("[gmarket/minishop] 컨테이너[%d] li %d개 발견", ci, len(li_list))

        available = []
        seen: set = set()
        prices: dict = {}
        images: dict = {}
        selected_val = None

        for li_idx, li in enumerate(li_list):
            a = li.find("a")
            if not a:
                logger.debug("[gmarket/minishop] li[%d] <a> 없음 → 건너뜀", li_idx)
                continue

            # lxml이 <a> 안의 <div>를 만나면 <a>를 미리 닫아버리므로
            # .item_tit / .item_price / img 가 <a>의 형제 노드가 될 수 있음.
            # → <li> 전체에서 검색해야 안정적으로 동작함.
            name_el = li.select_one(".item_tit")
            if not name_el:
                logger.debug("[gmarket/minishop] li[%d] .item_tit 없음 → 건너뜀", li_idx)
                continue
            name = name_el.get_text(strip=True)
            if not name:
                logger.debug("[gmarket/minishop] li[%d] .item_tit 텍스트 비어있음 → 건너뜀", li_idx)
                continue

            if name in seen:
                logger.debug("[gmarket/minishop] li[%d] '%s' 중복 → 건너뜀", li_idx, name)
                continue
            seen.add(name)

            # 가격: <span class="item_price">5,500<em class="unit">원</em></span>
            price_el = li.select_one(".item_price")
            if price_el:
                price_text = re.sub(r"[^\d]", "", price_el.get_text())
                if price_text:
                    prices[name] = float(price_text)

            # 썸네일 이미지
            img_el = li.find("img")
            if img_el:
                src = img_el.get("src") or img_el.get("data-src") or ""
                if src:
                    if src.startswith("//"):
                        src = "https:" + src
                    images[name] = src

            if "selected" in (li.get("class") or []):
                selected_val = name

            available.append(name)

        logger.info("[gmarket/minishop] 컨테이너[%d] 추출 결과: %d개 옵션, 이미지 %d개, 가격 %d개",
                    ci, len(available), len(images), len(prices))

        if available:
            available_key = tuple(available)
            if any(tuple(r.available_values) == available_key for r in results):
                logger.info("[gmarket/minishop] 컨테이너[%d] 동일 옵션 목록 중복 → 건너뜀", ci)
                continue
            results.append(_PO(
                option_type="상품",
                available_values=available,
                selected_value=selected_val,
                option_prices=prices or None,
                option_images=images or None,
                option_titles={n: n for n in available},
            ))

    logger.info("[gmarket/minishop] 최종 옵션 그룹 %d개 반환", len(results))
    return results


def _extract_gmarket_button_options(scope) -> list:
    """지마켓 버튼형 미니샵 옵션 파싱.

    대상 구조 A — 트리거 버튼 + 숨겨진 드롭다운:
        <div class="uxeselectbox item_options">
          <button class="select-item_option uxeselect_btn">
            <span class="txt minishop-selected">
              <div class="thumb"><img src="..."/></div>
              <div class="info">
                <span class="item_num">상품 <em>01</em></span>
                <span class="item_tit">롯데 마가렛트 352g</span>
                <span class="item_price">5,500<em class="unit">원</em></span>
              </div>
            </span>
            <span class="arr blind">열기</span>
          </button>
          <ul class="select-itemoption-list type_minishop ...">
            <li>...</li>
          </ul>
        </div>

    대상 구조 B — 버튼 그리드 (트리거 없이 각 상품이 개별 버튼으로 나열):
        여러 개의 <button class="select-item_option ..."> 직접 나열
    """
    from models import ProductOption as _PO

    def _parse_item_from_el(el):
        """el (li 또는 button) 에서 (name, price, image_url) 추출."""
        name_el = el.select_one(".item_tit")
        if not name_el:
            return None, None, None
        name = name_el.get_text(strip=True)
        if not name:
            return None, None, None
        price = None
        price_el = el.select_one(".item_price")
        if price_el:
            raw = re.sub(r"[^\d]", "", price_el.get_text())
            if raw:
                price = float(raw)
        img_url = None
        img_el = el.find("img")
        if img_el:
            src = img_el.get("src") or img_el.get("data-src") or ""
            if src.startswith("//"):
                src = "https:" + src
            if src:
                img_url = src
        return name, price, img_url

    results = []
    seen_containers: set = set()

    # --- 전략 A: uxeselectbox / item_options 컨테이너 내 button.uxeselect_btn ---
    for container in scope.select(
        "div[class*='uxeselectbox'], div[class*='item_options']"
    ):
        cid = id(container)
        if cid in seen_containers:
            continue
        trigger = container.select_one(
            "button[class*='uxeselect_btn'], button[class*='select-item_option']"
        )
        if not trigger:
            continue
        seen_containers.add(cid)

        available = []
        prices: dict = {}
        images: dict = {}
        selected_val = None
        seen_names: set = set()

        # 드롭다운 <ul> 우선
        ul = container.select_one(
            "ul[class*='select-itemoption-list'], ul[class*='uxeselect_dropdown']"
        )
        if ul:
            for li in ul.select("li"):
                name, price, img_url = _parse_item_from_el(li)
                if not name or name in seen_names:
                    continue
                seen_names.add(name)
                available.append(name)
                if price is not None:
                    prices[name] = price
                if img_url:
                    images[name] = img_url
                if "selected" in (li.get("class") or []):
                    selected_val = name
        else:
            # 드롭다운 없으면 트리거 버튼에서 현재 선택 항목만 추출
            name, price, img_url = _parse_item_from_el(trigger)
            if name:
                available.append(name)
                selected_val = name
                if price is not None:
                    prices[name] = price
                if img_url:
                    images[name] = img_url

        logger.info("[gmarket/button] 컨테이너 전략A: %d개 옵션, 이미지 %d개", len(available), len(images))
        if available:
            results.append(_PO(
                option_type="상품",
                available_values=available,
                selected_value=selected_val,
                option_prices=prices or None,
                option_images=images or None,
                option_titles={n: n for n in available},
            ))

    # --- 전략 B: 그리드형 — .select-item_option 버튼이 여러 개 직접 나열 ---
    if not results:
        btns = scope.select("button[class*='select-item_option']")
        if btns:
            available = []
            prices = {}
            images = {}
            selected_val = None
            seen_names = set()

            for btn in btns:
                name, price, img_url = _parse_item_from_el(btn)
                if not name or name in seen_names:
                    continue
                seen_names.add(name)
                available.append(name)
                if price is not None:
                    prices[name] = price
                if img_url:
                    images[name] = img_url
                # minishop-selected 클래스가 .txt span 에 있으면 현재 선택
                txt_el = btn.select_one(".txt")
                if txt_el and "minishop-selected" in (txt_el.get("class") or []):
                    selected_val = name

            logger.info("[gmarket/button] 전략B 그리드: %d개 옵션, 이미지 %d개", len(available), len(images))
            if available:
                results.append(_PO(
                    option_type="상품",
                    available_values=available,
                    selected_value=selected_val,
                    option_prices=prices or None,
                    option_images=images or None,
                    option_titles={n: n for n in available},
                ))

    logger.info("[gmarket/button] 최종 옵션 그룹 %d개 반환", len(results))
    return results


def _extract_gmarket_shipping(scope) -> tuple[Optional[float], Optional[str], dict]:
    """
    G마켓 VIP PDP 배송 영역 (list-item__delivery-*, box__delivery-schedule 등).
    노이즈 제거 전에 호출해야 함 — decompose가 delivery 클래스를 통째로 지움.
    """
    shipping_fee: Optional[float] = None
    shipping_period: Optional[str] = None
    raw: dict = {}

    root = scope.find("li", class_=re.compile(r"list-item__delivery", re.I)) or scope

    title_el = root.select_one(".box__delivery-schedule .box__title .text__title")
    if not title_el:
        title_el = root.select_one(".box__delivery-schedule .text__title")
    if title_el:
        shipping_period = title_el.get_text(" ", strip=True) or None

    fee_pat = re.compile(r"배송비\s*[:\s]*([\d,]+)\s*원")
    free_unconditional = re.compile(r"배송비[^0-9\n]{0,12}무료")
    free_over_pat = re.compile(r"([\d,]+)\s*원\s*이상\s*구매\s*시\s*무료")

    for branch in root.select("span.text__branch"):
        text = branch.get_text(" ", strip=True)
        if not text:
            continue
        if "배송비" in text:
            m = fee_pat.search(text)
            if m:
                shipping_fee = _to_num(m.group(1))
            elif free_unconditional.search(text):
                shipping_fee = 0.0
            guide = branch.select_one(".text__guide")
            if guide:
                gm = free_over_pat.search(guide.get_text(" ", strip=True))
                if gm:
                    raw["gmarket_free_shipping_threshold_krw"] = _to_num(gm.group(1))
            continue
        if len(text) <= 40 and ("택배" in text or "CJ" in text or "로젠" in text or "한진" in text or "우체국" in text):
            raw["gmarket_shipping_carrier"] = text.strip()

    if shipping_fee is None:
        chunk = root.get_text(" ", strip=True)[:8000]
        m = fee_pat.search(chunk)
        if m:
            shipping_fee = _to_num(m.group(1))
        elif free_unconditional.search(chunk):
            shipping_fee = 0.0
        fm = free_over_pat.search(chunk)
        if fm and "gmarket_free_shipping_threshold_krw" not in raw:
            raw["gmarket_free_shipping_threshold_krw"] = _to_num(fm.group(1))

    return shipping_fee, shipping_period, raw


def _parse_gmarket(html: str, page_title, url) -> ProductInfo:
    """
    G마켓 상품 상세 파서.
    스코프: div#container[role="main"].vip-content
    OrderSet JS 객체를 보조 소스로 활용.
    """
    soup = _soup(html)

    # 1. 파싱 스코프
    scope = (
        soup.find("div", id="container", attrs={"role": "main"})
        or soup.find("div", id="container")
        or soup
    )

    # 배송비/도착예측은 delivery 클래스 노이즈 제거로 사라지므로 먼저 추출
    shipping_fee, shipping_period, ship_raw = _extract_gmarket_shipping(scope)

    # 노이즈 제거
    _noise = [
        {"class": re.compile(r"seller|review|banner|coupon|share|wish|delivery|card.?benefit|smile.?card|point|행사|breadcrumb", re.I)},
        {"id": re.compile(r"review|coupon|banner|delivery", re.I)},
    ]
    for attr in _noise:
        for tag in scope.find_all(True, attr):
            tag.decompose()

    # 2. OrderSet JS 객체 파싱 (보조 소스)
    order_set = {}
    for script in soup.find_all("script"):
        t = script.string or ""
        if "OrderSet" not in t:
            continue
        for key, val_pat in [
            ("SellPrice",    r"OrderSet\.SellPrice\s*=\s*(\d+)"),
            ("OriginPrice",  r"OrderSet\.OriginPrice\s*=\s*(\d+)"),
            ("HasNoOption",  r"OrderSet\.HasNoOption\s*=\s*(true|false)"),
        ]:
            m = re.search(val_pat, t)
            if m:
                order_set[key] = m.group(1)

    has_no_option = order_set.get("HasNoOption", "").lower() == "true"

    # 3. 제목
    title = None
    t_el = scope.select_one("#itemcase_basic .box__item-title h1.itemtit")
    if not t_el:
        t_el = scope.find("h1")
    if t_el:
        title = t_el.get_text(strip=True)
    if not title:
        og = soup.find("meta", property="og:title")
        title = og["content"].strip() if og and og.get("content") else page_title

    # 4. 원가
    original = None
    op_el = scope.select_one(".box__price .price_original .text__price-original .text__price")
    if not op_el:
        op_el = scope.select_one(".price_original .text__price")
    if not op_el:
        op_el = scope.find("del") or scope.find(class_=re.compile(r"price.?origin|origin.?price", re.I))
    if op_el:
        original = _to_num(re.sub(r"[^\d]", "", op_el.get_text()))
    if not original and order_set.get("OriginPrice"):
        original = float(order_set["OriginPrice"])

    # 5. SOLD OUT 감지
    soldout_el = scope.select_one("strong.price_real.text__soldout, .price_real.text__soldout")
    if soldout_el and "sold out" in soldout_el.get_text(strip=True).lower():
        logger.info("[HTML 파서/gmarket] SOLD OUT 감지: %s", title)
        image = None
        og_img = soup.find("meta", property="og:image")
        if og_img:
            image = og_img.get("content")
        return ProductInfo(
            title=title, original_price=None, discounted_price=None,
            discount_rate=None, main_image_url=image,
            shipping_period=shipping_period, shipping_fee=shipping_fee,
            product_options=[],
            product_weight=None, currency="KRW", hs_code=None,
            sold_out=True, raw_data=ship_raw or {},
        )

    # 6. 최종 판매가 (쿠폰가/총금액 제외)
    price = None
    # 쿠폰 영역 임시 제거
    for coupon in scope.select(".price_innerwrap-coupon, [class*='coupon']"):
        coupon.decompose()
    fp_el = scope.select_one(".box__price > .price_innerwrap:first-of-type strong.price_real")
    if not fp_el:
        fp_el = scope.select_one(".price_real")
    if fp_el:
        price = _to_num(re.sub(r"[^\d]", "", fp_el.get_text()))
    if not price and order_set.get("SellPrice"):
        price = float(order_set["SellPrice"])
    if not price:
        og_price = soup.find("meta", attrs={"property": "product:price:amount"})
        if og_price:
            price = _to_num(og_price.get("content"))

    if not original:
        original = price

    # 6. 무게
    weight_text = None
    _weight_pat = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|g|ml|l|리터|킬로|그램)\b", re.I)
    _qty_pat = re.compile(r"\d+\s*(구|개|세트|팩|봉|캔|병|박스)", re.I)
    for text in [title or "", scope.get_text()[:3000]]:
        for m in _weight_pat.finditer(text):
            candidate = m.group(0).strip()
            context = text[max(0, m.start()-5):m.end()+5]
            if _qty_pat.search(context):
                continue
            weight_text = candidate
            break
        if weight_text:
            break

    # 7. 옵션
    product_options = []
    _skip_texts = re.compile(r"옵션 선택|선택하세요|수량|총 금액|구매가능|최대구매", re.I)

    logger.info("[HTML 파서/gmarket] has_no_option=%s", has_no_option)

    # 7-1. 미니샵 스타일 옵션 — has_no_option 무관하게 항상 먼저 시도
    # (미니샵 상품은 OrderSet.HasNoOption=true이면서도 상품 선택 드롭다운이 존재함)
    minishop_opts = _extract_gmarket_minishop_options(scope)
    if minishop_opts:
        product_options.extend(minishop_opts)
        logger.info("[HTML 파서/gmarket] 미니샵 옵션 %d그룹 (%d개 항목) 추출",
                    len(minishop_opts), sum(len(o.available_values) for o in minishop_opts))

    # 7-1b. 버튼형 미니샵 옵션 (신형 VIP PDP — <button class="select-item_option uxeselect_btn">)
    if not minishop_opts:
        button_opts = _extract_gmarket_button_options(scope)
        if button_opts:
            product_options.extend(button_opts)
            logger.info("[HTML 파서/gmarket] 버튼형 옵션 %d그룹 (%d개 항목) 추출",
                        len(button_opts), sum(len(o.available_values) for o in button_opts))

    if not has_no_option and not minishop_opts:
        # 7-2. 일반 옵션 박스 (미니샵이 없을 때)
        for group in scope.select("div[class*='box__option'], div[class*='option_wrap'], select[class*='option']"):
            label_el = group.find(class_=re.compile(r"option.?title|option.?label|opt.?tit", re.I))
            group_name = label_el.get_text(strip=True) if label_el else "옵션"

            items = group.select("option, li[class*='option'], [class*='option_item']")
            available = []
            seen_items: set = set()
            selected_val = None
            for item in items:
                name_text = item.get_text(strip=True)
                if not name_text or _skip_texts.search(name_text):
                    continue
                if name_text in seen_items:
                    continue
                seen_items.add(name_text)
                price_el = item.find(class_=re.compile(r"price|add.?price", re.I))
                opt_price_text = price_el.get_text(strip=True) if price_el else None
                is_selected = bool(item.get("selected") or
                                   any(c in ("on", "selected", "active") for c in item.get("class", [])))
                available.append(name_text)
                if is_selected:
                    selected_val = name_text

            if available:
                product_options.append(ProductOption(
                    option_type=group_name,
                    available_values=available,
                    selected_value=selected_val,
                ))

    # 할인율: original > price (쿠폰 미적용 가격 기준)일 때만 의미 있음.
    # .text__discount-rate 는 쿠폰 할인율을 표시하는 경우가 있으므로 바로 읽지 않고,
    # original과 price가 실제로 다를 때만 계산값을 사용.
    discount_rate = None
    if original and price and original > price:
        discount_rate = round((original - price) / original * 100, 1)

    image = None
    og_img = soup.find("meta", property="og:image")
    if og_img:
        image = og_img.get("content")

    logger.info("[HTML 파서/gmarket] title=%s price=%s original=%s discount_rate=%s weight=%s options=%d ship=%s",
                title, price, original, discount_rate, weight_text, len(product_options), shipping_fee)
    return ProductInfo(
        title=title, original_price=original, discounted_price=price,
        discount_rate=discount_rate, main_image_url=image,
        shipping_period=shipping_period, shipping_fee=shipping_fee,
        product_options=product_options,
        product_weight=weight_text, currency="KRW", hs_code=None,
        raw_data=ship_raw or {},
    )


def _parse_auction(html: str, page_title, url) -> ProductInfo:
    """
    옥션 상품 상세 파서.
    스코프: div.item-topinfowrap
    쿠폰가/총금액 제외, 취소선 원가 있을 때만 original_price 사용.
    """
    soup = _soup(html)

    # 1. 파싱 스코프
    scope = soup.find("div", class_=re.compile(r"item.?topinfowrap", re.I)) or soup

    # 배송비 — 노이즈 제거 전에 먼저 추출 (delivery 클래스가 제거되므로)
    shipping_fee: Optional[float] = None
    shipping_period: Optional[str] = None
    delivery_ul = scope.find("ul", class_=re.compile(r"item.?topinfo.?sub", re.I))
    if delivery_ul:
        # 무료배송: span.text__branch-blue 텍스트에 "무료" 포함
        free_el = delivery_ul.find(class_=re.compile(r"text__branch.?blue|branch.?blue", re.I))
        if free_el and "무료" in free_el.get_text():
            shipping_fee = 0.0
        # 유료배송: "배송비 X원" 패턴
        if shipping_fee is None:
            for span in delivery_ul.select("span.text__branch"):
                t = span.get_text(strip=True)
                m = re.search(r"배송비\s*([\d,]+)\s*원", t)
                if m:
                    shipping_fee = _to_num(re.sub(r"[^\d]", "", m.group(1)))
                    break
        # 배송 기간: span.text__title (예: "오늘출발", "내일출발")
        period_el = delivery_ul.select_one("span.text__branch span.text__title")
        if period_el:
            shipping_period = period_el.get_text(strip=True) or None

    # 노이즈 제거
    _noise = [
        {"class": re.compile(r"seller|review|delivery|card.?benefit|coupon|share|wish|point|banner|breadcrumb|sns", re.I)},
        {"id": re.compile(r"review|coupon|delivery|banner", re.I)},
    ]
    for attr in _noise:
        for tag in scope.find_all(True, attr):
            tag.decompose()
    for tag in scope.find_all("script"):
        tag.decompose()

    # 2. 제목
    title = None
    t_el = scope.select_one(".box__item-summary h1.itemtit")
    if not t_el:
        t_el = scope.find("h1")
    if t_el:
        title = t_el.get_text(strip=True)
    if not title:
        og = soup.find("meta", property="og:title")
        title = og["content"].strip() if og and og.get("content") else page_title

    # 3. 원가 (취소선이 있을 때만)
    original = None
    op_el = scope.find("del") or scope.find(class_=re.compile(r"price.?origin|origin.?price|price.?regular", re.I))
    if op_el:
        v = _to_num(re.sub(r"[^\d]", "", op_el.get_text()))
        if v:
            original = v

    # 4. 최종 판매가 (쿠폰가/총금액 제외)
    price = None
    for coupon in scope.select(".price_coupon, [class*='coupon'], [class*='total_price']"):
        coupon.decompose()
    fp_el = scope.select_one(".price_wrap .price strong.price_real")
    if not fp_el:
        fp_el = scope.select_one(".price_real")
    if not fp_el:
        fp_el = scope.select_one(".price_wrap strong")
    if fp_el:
        price = _to_num(re.sub(r"[^\d]", "", fp_el.get_text()))
    if not price:
        og_price = soup.find("meta", attrs={"property": "product:price:amount"})
        if og_price:
            price = _to_num(og_price.get("content"))
    if not price:
        price = _price_from_text(scope.get_text())

    if not original:
        original = price

    # 5. 무게
    # 특수 규칙: "총 Xkg", "Xkg+덤 Ykg" → 합산
    weight_text = None
    weight_value = None
    weight_unit = None

    full_text = (title or "") + " " + scope.get_text()[:3000]

    # "X+덤 Y" 합산 패턴 (예: 2kg+덤 1kg → 3kg)
    combined = re.search(
        r"(\d+(?:\.\d+)?)\s*(kg|g)\s*\+.*?(\d+(?:\.\d+)?)\s*(kg|g)", full_text, re.I
    )
    if combined:
        try:
            v1 = float(combined.group(1)) * (1000 if combined.group(2).lower() == "kg" else 1)
            v2 = float(combined.group(3)) * (1000 if combined.group(4).lower() == "kg" else 1)
            total_g = v1 + v2
            if total_g >= 1000:
                weight_value = total_g / 1000
                weight_unit = "kg"
            else:
                weight_value = total_g
                weight_unit = "g"
            weight_text = f"{weight_value}{weight_unit}"
        except Exception:
            pass

    # "총 Xkg" 패턴
    if not weight_text:
        m = re.search(r"총\s*(\d+(?:\.\d+)?)\s*(kg|g|ml|l)\b", full_text, re.I)
        if m:
            weight_value = float(m.group(1))
            weight_unit = m.group(2).lower()
            weight_text = f"{m.group(1)}{weight_unit}"

    # 일반 무게 패턴
    if not weight_text:
        _weight_pat = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|g|ml|l|리터|킬로|그램)\b", re.I)
        _qty_pat = re.compile(r"\d+\s*(구|개|세트|팩|봉|캔|병|박스)", re.I)
        for m in _weight_pat.finditer(full_text):
            ctx = full_text[max(0, m.start()-5):m.end()+5]
            if _qty_pat.search(ctx):
                continue
            weight_value = float(m.group(1))
            weight_unit = m.group(2).lower()
            weight_text = m.group(0).strip()
            break

    # 6. 옵션
    product_options = []
    _skip_texts = re.compile(r"옵션 선택|선택하세요|수량|총 금액|구매수량|남은수량", re.I)

    # 6-a. 그룹아이템 드롭다운 (div.item_options.opt_group.uxeselectbox)
    #   구조: div.item_options > ul.select-itemoption-list.uxeselect_dropdown > li
    #   이름: span.option_prod / 가격: span.text_price(쿠폰 제외) strong.num
    #   item_options가 item-topinfowrap 바깥에 있을 수 있으므로 soup 전체도 탐색
    _opt_containers = scope.select("div[class*='item_options']") or soup.select("div[class*='item_options']")
    for container in _opt_containers:
        ul = container.select_one(
            "ul.select-itemoption-list, ul[class*='uxeselect_dropdown']"
        )
        if not ul:
            continue

        values, prices, selected_val = [], {}, None
        for li in ul.find_all("li", recursive=False):
            name_el = li.select_one("span.option_prod")
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            if not name or _skip_texts.search(name):
                continue
            values.append(name)

            # 쿠폰가(text_price-coupon) 제외하고 첫 번째 text_price 사용
            for tp in li.select("span.text_price"):
                tp_cls = " ".join(tp.get("class", []))
                if "coupon" in tp_cls:
                    continue
                num_el = tp.select_one("strong.num")
                if num_el:
                    p = _to_num(re.sub(r"[^\d]", "", num_el.get_text()))
                    if p:
                        prices[name] = p
                break

            cls = " ".join(li.get("class", []))
            if "selected" in cls:
                selected_val = name

        if values:
            product_options.append(ProductOption(
                option_type="상품",
                available_values=values,
                selected_value=selected_val,
                option_prices=prices or None,
            ))

    # 6-b. 일반 옵션 (그룹아이템이 없을 때 fallback)
    if not product_options:
        for group in scope.select("div[class*='opt_wrap'], div[class*='option_wrap'], select[class*='option']"):
            label_el = group.find(class_=re.compile(r"opt.?tit|option.?title", re.I))
            group_name = label_el.get_text(strip=True) if label_el else "옵션"
            items = group.select("option, li[class*='option'], [class*='opt_item']")
            available, selected_val = [], None
            for item in items:
                name_text = item.get_text(strip=True)
                if not name_text or _skip_texts.search(name_text):
                    continue
                is_selected = bool(item.get("selected") or
                                   any(c in ("on", "selected", "active") for c in item.get("class", [])))
                available.append(name_text)
                if is_selected:
                    selected_val = name_text
            if available:
                product_options.append(ProductOption(
                    option_type=group_name,
                    available_values=available,
                    selected_value=selected_val,
                ))

    discount_rate = round((original - price) / original * 100, 1) if original and price and original > price else None
    image = None
    og_img = soup.find("meta", property="og:image")
    if og_img:
        image = og_img.get("content")

    logger.info("[HTML 파서/auction] title=%s price=%s original=%s discount=%s weight=%s options=%d ship=%s",
                title, price, original, discount_rate, weight_text, len(product_options), shipping_fee)
    return ProductInfo(
        title=title, original_price=original, discounted_price=price,
        discount_rate=discount_rate, main_image_url=image,
        shipping_period=shipping_period, shipping_fee=shipping_fee,
        product_options=product_options,
        product_weight=weight_text, currency="KRW", hs_code=None, raw_data={},
    )


def _parse_ssg(html: str, page_title, url) -> ProductInfo:
    """
    SSG.COM 상품 상세 파서.
    스코프: div[data-global="item_view"]
    카드혜택가(.mndtl_price) 제외, 취소선 원가 있을 때만 original_price 사용.
    """
    soup = _soup(html)

    # 1. 파싱 스코프
    scope = soup.find("div", attrs={"data-global": "item_view"}) or soup

    # 노이즈 제거
    _noise = [
        {"class": re.compile(r"relate|recommend|review|delivery|card.?benefit|mndtl_price|membership|banner|breadcrumb|sns|share|wish|coupon|point|store", re.I)},
        {"id": re.compile(r"review|recommend|delivery|banner|coupon", re.I)},
        {"data-global": re.compile(r"recommend|review|delivery|card|coupon", re.I)},
    ]
    for attr in _noise:
        for tag in scope.find_all(True, attr):
            tag.decompose()
    for tag in scope.find_all("script"):
        tag.decompose()

    # 2. 제목
    title = None
    t_el = scope.select_one(".cdtl_prd_info .cdtl_info_tit_txt")
    if not t_el:
        t_el = scope.select_one(".cdtl_info_tit_txt")
    if not t_el:
        t_el = scope.find("h1")
    if t_el:
        title = t_el.get_text(strip=True)
    if not title:
        og = soup.find("meta", property="og:title")
        title = og["content"].strip() if og and og.get("content") else page_title

    # 3. 원가 (취소선/판매가 영역)
    original = None
    op_el = scope.select_one(".cdtl_old_price .ssg_price")
    if not op_el:
        op_el = scope.find("del") or scope.find(class_=re.compile(r"old.?price|price.?old|origin.?price|price.?regular", re.I))
    if op_el:
        v = _to_num(re.sub(r"[^\d]", "", op_el.get_text()))
        if v:
            original = v

    # 4. 최종 판매가 (카드혜택가 mndtl_price 제외)
    price = None
    fp_el = scope.select_one(".cdtl_new_price .ssg_price")
    if not fp_el:
        fp_el = scope.select_one(".cdtl_prc_area .ssg_price")
    if not fp_el:
        # 최적가 텍스트 근처
        for el in scope.select(".ssg_price"):
            parent_text = (el.parent.get_text(strip=True) if el.parent else "")
            if any(kw in parent_text for kw in ("최적가", "판매가", "최저가")):
                fp_el = el
                break
    if not fp_el:
        # ssg_price 중 mndtl_price 아닌 첫 번째
        for el in scope.select(".ssg_price"):
            if not el.find_parent(class_=re.compile(r"mndtl|card|membership", re.I)):
                fp_el = el
                break
    if fp_el:
        price = _to_num(re.sub(r"[^\d]", "", fp_el.get_text()))
    if not price:
        og_price = soup.find("meta", attrs={"property": "product:price:amount"})
        if og_price:
            price = _to_num(og_price.get("content"))
    if not price:
        # JS 데이터 fallback
        m = re.search(r'"finalPrice"\s*:\s*(\d+)', html)
        if m:
            price = float(m.group(1))
        m2 = re.search(r'"normalPrice"\s*:\s*(\d+)', html)
        if m2 and not original:
            original = float(m2.group(1))
    if not price:
        price = _price_from_text(scope.get_text())

    if not original:
        original = price

    # 5. 무게
    # 우선순위: 제목 → "총 용량" 텍스트 → 일반 패턴
    weight_text = None
    _weight_pat = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l|리터|킬로|그램)\b", re.I)
    _qty_pat = re.compile(r"\d+\s*(개|구|세트|팩|봉|캔|병|박스)", re.I)
    full_text = (title or "") + " " + scope.get_text()[:4000]

    # "총 용량 X" 패턴 우선
    m_total = re.search(r"총\s*용량\s*[:\s]*(\d+(?:[.,]\d+)?)\s*(g|kg|ml|l)\b", full_text, re.I)
    if m_total:
        val_str = m_total.group(1).replace(",", "")
        weight_text = f"{val_str}{m_total.group(2).lower()}"

    if not weight_text:
        for text in [title or "", scope.get_text()[:3000]]:
            for m in _weight_pat.finditer(text):
                ctx = text[max(0, m.start() - 5):m.end() + 5]
                if _qty_pat.search(ctx):
                    continue
                weight_text = m.group(0).replace(",", "").strip()
                break
            if weight_text:
                break

    # 6. 옵션 (수량/총금액/배송/혜택 제외)
    product_options = []
    _skip_texts = re.compile(r"옵션 선택|선택하세요|수량|총 금액|남은수량|배송|혜택|멤버십|적립", re.I)

    for group in scope.select("div[class*='opt_wrap'], div[class*='option_wrap'], div[class*='cdtl_opt']"):
        label_el = group.find(class_=re.compile(r"opt.?tit|option.?title|opt.?label", re.I))
        group_name = label_el.get_text(strip=True) if label_el else "옵션"
        if _skip_texts.search(group_name):
            continue

        items = group.select("option, li[class*='option'], li[class*='opt_item'], [class*='opt_unit']")
        available = []
        selected_val = None
        for item in items:
            name_text = item.get_text(strip=True)
            if not name_text or _skip_texts.search(name_text):
                continue
            sold_out = bool(item.find(class_=re.compile(r"sold.?out|품절", re.I)) or "품절" in name_text)
            is_selected = bool(
                item.get("selected") or
                any(c in ("on", "selected", "active") for c in item.get("class", []))
            )
            available.append(name_text)
            if is_selected:
                selected_val = name_text

        if available:
            product_options.append(ProductOption(
                option_type=group_name,
                available_values=available,
                selected_value=selected_val,
            ))

    discount_rate = round((original - price) / original * 100, 1) if original and price and original > price else None
    image = None
    og_img = soup.find("meta", property="og:image")
    if og_img:
        image = og_img.get("content")

    logger.info("[HTML 파서/ssg] title=%s price=%s original=%s weight=%s options=%d",
                title, price, original, weight_text, len(product_options))
    return ProductInfo(
        title=title, original_price=original, discounted_price=price,
        discount_rate=discount_rate, main_image_url=image,
        shipping_period=None, product_options=product_options,
        product_weight=weight_text, currency="KRW", hs_code=None, raw_data={},
    )


def _parse_lotteon(html: str, page_title, url) -> ProductInfo:
    """
    롯데ON 상품 상세 파서.
    스코프: main#content .productWrap
    혜택가(.advantageBox__top--price) 제외, 판매가(.pd-price__info--number)만 final_price.
    """
    soup = _soup(html)

    # 1. 파싱 스코프: main#content > .productWrap
    main = soup.find("main", id="content") or soup
    scope = main.find(class_=re.compile(r"productWrap", re.I)) or main

    # 노이즈 제거
    _noise_classes = re.compile(
        r"advantageBox|purchaseInfoWrap|pd-DeliveryInfo|sellerInfo|"
        r"productReviewWrap|eventBanner|detailImgContents|essential-info|"
        r"buttonGroup|buttonWrapper|locationWrap|totalPriceWrap|shareWrap|wishWrap",
        re.I,
    )
    for tag in scope.find_all(True, {"class": _noise_classes}):
        tag.decompose()
    for tag in scope.find_all("script"):
        tag.decompose()
    for tag in scope.find_all("iframe"):
        tag.decompose()

    # 2. 제목
    title = None
    t_el = scope.select_one(".pd-widget1__product-name")
    if not t_el:
        t_el = scope.find("h2") or scope.find("h1")
    if t_el:
        # 브랜드명 제거
        for brand in t_el.select(".pd-widget1__product-seller-item"):
            brand.decompose()
        title = t_el.get_text(strip=True)
    if not title:
        og = soup.find("meta", property="og:title")
        title = og["content"].strip() if og and og.get("content") else page_title

    # 3. 할인율: span.pd-price__info--number.discount 안의 숫자+%
    discount_rate = None
    rate_el = scope.select_one(".pd-price__info--number.discount")
    if rate_el:
        m = re.search(r"(\d+)\s*%", rate_el.get_text())
        if m:
            discount_rate = float(m.group(1))

    # 4. 판매가(할인 후): strong.pd-price__info--number
    price = None
    fp_el = scope.select_one("strong.pd-price__info--number")
    if fp_el:
        price = _to_num(re.sub(r"[^\d]", "", fp_el.get_text()))
    if not price:
        og_price = soup.find("meta", attrs={"property": "product:price:amount"})
        if og_price:
            price = _to_num(og_price.get("content"))
    if not price:
        m = re.search(r'"salePrice"\s*:\s*(\d+)', html)
        if m:
            price = float(m.group(1))
    if not price:
        price = _price_from_text(scope.get_text())

    # 5. 원가(할인 전): span.pd-price__info--number.originPrice
    original = None
    op_el = scope.select_one(".pd-price__info--number.originPrice")
    if op_el:
        v = _to_num(re.sub(r"[^\d]", "", op_el.get_text()))
        if v:
            original = v
    if not original:
        original = price

    # 5. 무게
    weight_text = None
    _weight_pat = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l|리터|킬로|그램)\b", re.I)
    _size_pat = re.compile(r"\b(XS|S|M|L|XL|XXL|FREE|\d{2,3})\b")
    _qty_pat = re.compile(r"\d+\s*(개|구|세트|팩|봉|캔|병|박스)", re.I)
    full_text = (title or "") + " " + scope.get_text()[:3000]

    for m in _weight_pat.finditer(full_text):
        ctx = full_text[max(0, m.start() - 10):m.end() + 10]
        if _qty_pat.search(ctx):
            continue
        weight_text = m.group(0).replace(",", "").strip()
        break

    # 6. 옵션: .optionWrap .labelTextWrap 구조
    product_options = []
    _skip_texts = re.compile(r"선택하세요|수량|총\s*\d+|총 금액|배송|판매자|공유|찜", re.I)

    opt_wrap = scope.find(class_=re.compile(r"optionWrap", re.I))
    if opt_wrap:
        for group in opt_wrap.select("[class*='labelTextWrap'], [class*='optionGroup']"):
            group_el = group.select_one(".resultTitle, [class*='optionTitle'], [class*='option_title']")
            group_name = group_el.get_text(strip=True) if group_el else "옵션"
            if _skip_texts.search(group_name):
                continue

            items = group.select("[class*='caption'], option, li[class*='opt']")
            available = []
            selected_val = None
            for item in items:
                name_text = item.get_text(strip=True)
                if not name_text or _skip_texts.search(name_text):
                    continue
                price_el = item.find(class_=re.compile(r"\bprice\b", re.I))
                opt_price_text = price_el.get_text(strip=True) if price_el else None
                stock_el = item.find(class_=re.compile(r"stock|재고", re.I))
                stock_text = stock_el.get_text(strip=True) if stock_el else ""
                is_sold_out = bool(re.search(r"품절|일시품절|재고없음", name_text + stock_text))
                is_selected = bool(
                    item.get("selected") or
                    any(c in ("on", "selected", "active", "checked") for c in item.get("class", []))
                )
                display = name_text
                if opt_price_text:
                    display = f"{name_text} ({opt_price_text})"
                available.append(display)
                if is_selected:
                    selected_val = display

            if available:
                product_options.append(ProductOption(
                    option_type=group_name,
                    available_values=available,
                    selected_value=selected_val,
                ))

    # HTML에서 추출한 discount_rate 우선, 없으면 계산
    if discount_rate is None and original and price and original > price:
        discount_rate = round((original - price) / original * 100, 1)
    image = None
    og_img = soup.find("meta", property="og:image")
    if og_img:
        image = og_img.get("content")

    logger.info("[HTML 파서/lotteon] title=%s price=%s original=%s discount=%s weight=%s options=%d",
                title, price, original, discount_rate, weight_text, len(product_options))
    return ProductInfo(
        title=title, original_price=original, discounted_price=price,
        discount_rate=discount_rate, main_image_url=image,
        shipping_period=None, product_options=product_options,
        product_weight=weight_text, currency="KRW", hs_code=None, raw_data={},
    )


def _parse_oliveyoung(html: str, page_title, url) -> ProductInfo:
    """
    올리브영 상품 상세 파서.
    스코프: div.page_product-details-container
    원가: .GoodsDetailInfo_price-before span
    판매가: .GoodsDetailInfo_price span
    """
    soup = _soup(html)

    # 1. 파싱 스코프
    scope = soup.find("div", class_=re.compile(r"page_product-details-container", re.I)) or soup

    # 배송비/배송기간 — DeliveryInfo 노이즈 제거 전에 먼저 추출
    shipping_fee: Optional[float] = None
    shipping_period: Optional[str] = None
    for delivery_li in scope.select(
        "li[data-qa-name*='delivery'], li[class*='DeliveryInfo_delivery-item']"
    ):
        # 일반배송 항목만 처리 (퀵/당일 등 제외)
        title_el = delivery_li.select_one("[class*='DeliveryInfo_info-title']")
        section_title = title_el.get_text(strip=True) if title_el else ""
        if section_title and "일반" not in section_title and shipping_fee is not None:
            continue

        for p in delivery_li.select("[class*='DeliveryInfo_text']"):
            text = p.get_text(strip=True)
            # 배송비: "2,500원 ..." 또는 "무료배송"
            if shipping_fee is None:
                if "무료" in text and "배송" in text and "이상" not in text:
                    shipping_fee = 0.0
                else:
                    m = re.match(r"([\d,]+)\s*원", text)
                    if m:
                        shipping_fee = _to_num(re.sub(r"[^\d]", "", m.group(1)))
            # 배송기간: "평균 N일 이내 도착" 등
            if shipping_period is None and ("일" in text or "도착" in text) and "배송비" not in text:
                shipping_period = text
        if shipping_fee is not None:
            break

    # 6. 옵션 — OptionSelector_option-list (드랍다운 클릭 후 생성된 DOM)
    # ※ PurchaseBottom 노이즈 제거 전에 먼저 추출해야 함
    product_options = []
    for opt_ul in soup.find_all("ul", class_=re.compile(r"OptionSelector_option-list", re.I)):
        values, prices, soldout_values = [], {}, []
        for li in opt_ul.find_all("li", attrs={"data-qa-name": re.compile(r"text-product-option")}):
            tit_el = li.find(class_=re.compile(r"OptionSelector_option-item-tit", re.I))
            if not tit_el:
                continue
            name = tit_el.get_text(strip=True)
            if not name:
                continue
            values.append(name)

            # 옵션별 가격: span.OptionSelector_option-item-price 내 숫자만 추출
            price_el = li.find(class_=re.compile(r"OptionSelector_option-item-price", re.I))
            if price_el:
                p = _to_num(re.sub(r"[^\d]", "", price_el.get_text()))
                if p:
                    prices[name] = p

            # 품절: li/button 클래스에 soldout 또는 "품절" 텍스트
            li_cls = " ".join(li.get("class", []))
            btn = li.find("button")
            btn_cls = " ".join(btn.get("class", [])) if btn else ""
            if "soldout" in li_cls.lower() or "soldout" in btn_cls.lower() or "품절" in li.get_text():
                soldout_values.append(name)

        if values:
            # 옵션 타입: 드랍다운 트리거 버튼 플레이스홀더 텍스트 (없으면 "옵션")
            opt_btn = opt_ul.find_previous("button", class_=re.compile(r"OptionSelector_btn-option", re.I))
            type_label = "옵션"
            if opt_btn:
                ph_el = opt_btn.find("span")
                if ph_el:
                    t = ph_el.get_text(strip=True)
                    if t and "선택" not in t:
                        type_label = t
            product_options.append(ProductOption(
                option_type=type_label,
                available_values=values,
                option_prices=prices or None,
                soldout_values=soldout_values or None,
            ))

    # 노이즈 제거 (PurchaseBottom 포함 — 옵션은 이미 위에서 추출 완료)
    _noise = re.compile(
        r"ReviewArea|DeliveryInfo|PurchaseBottom|banner|recommend|"
        r"tab.?content|detail.?img|GoodsDetailTab",
        re.I,
    )
    for tag in scope.find_all(True, {"class": _noise}):
        tag.decompose()
    for tag in scope.find_all("script"):
        tag.decompose()

    # 2. 제목
    title = None
    t_el = scope.select_one("h3.GoodsDetailInfo_title")
    if not t_el:
        t_el = scope.select_one("[class*='GoodsDetailInfo_title']")
    if not t_el:
        t_el = scope.find("h3") or scope.find("h1")
    if t_el:
        for br in t_el.find_all("br"):
            br.replace_with(" ")
        title = re.sub(r"\s+", " ", t_el.get_text(strip=True))
    if not title:
        og = soup.find("meta", property="og:title")
        title = og["content"].strip() if og and og.get("content") else page_title

    # 3. 원가 (할인 전 가격)
    original = None
    op_el = scope.find(attrs={"data-qa-name": "text-product-original-price"})
    if not op_el:
        op_el = scope.select_one("[class*='GoodsDetailInfo_price-before']")
    if op_el:
        v = _to_num(re.sub(r"[^\d]", "", op_el.get_text()))
        if v:
            original = v

    # 4. 실 판매가 — PopupBenefits 최적가 우선 (쿠폰 포함 최종가)
    # PopupBenefits 구조: 판매가(원가) / 세일 / 쿠폰 / 최적가(최종가)
    price = None
    popup = scope.find(class_=re.compile(r"PopupBenefits_popup.benefits", re.I))
    if popup:
        base_price = None
        optimized_price = None
        for li in popup.select("li[class*='PopupBenefits_info-item']"):
            t_el = li.select_one("[class*='PopupBenefits_info-item-title']")
            v_el = li.select_one("[class*='PopupBenefits_info-item-price']")
            if not t_el or not v_el:
                continue
            t_text = t_el.get_text(strip=True)
            v_text = v_el.get_text(strip=True)
            val = _to_num(re.sub(r"[^\d]", "", v_text))
            if not val:
                continue
            if "판매가" in t_text and base_price is None:
                base_price = val
                if not original:
                    original = val
            elif "최적가" in t_text:
                optimized_price = val
        if optimized_price:
            price = optimized_price
        elif base_price:
            price = base_price

    if not price:
        # data-qa-name 기반으로 최적가 추출 (쿠폰 포함 가능, popup 없을 때 폴백)
        disc_el = scope.find(attrs={"data-qa-name": "text-product-discount-price"})
        if disc_el:
            first_span = disc_el.find("span")
            price = _to_num(re.sub(r"[^\d]", "", first_span.get_text())) if first_span \
                else _to_num(re.sub(r"[^\d]", "", disc_el.get_text()))
    if not price:
        og_price = soup.find("meta", attrs={"property": "product:price:amount"})
        if og_price:
            price = _to_num(og_price.get("content"))
    if not price:
        m = re.search(r'"finalPrice"\s*:\s*(\d+)', html)
        if m:
            price = float(m.group(1))
        if not original:
            m2 = re.search(r'"orgPrice"\s*:\s*(\d+)', html)
            if m2:
                original = float(m2.group(1))
    if not price:
        price = _price_from_text(scope.get_text())

    if not original:
        original = price

    # 5. 무게/용량 (제목에서 첫 번째 용량 패턴 우선)
    weight_text = None
    _weight_pat = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l|리터|킬로|그램)\b", re.I)
    _qty_pat = re.compile(r"\d+\s*(개|구|세트|팩|봉|캔|병|박스)", re.I)

    for text in [title or "", scope.get_text()[:2000]]:
        for m in _weight_pat.finditer(text):
            ctx = text[max(0, m.start() - 5):m.end() + 5]
            if _qty_pat.search(ctx):
                continue
            weight_text = m.group(0).replace(",", "").strip()
            break
        if weight_text:
            break

    discount_rate = round((original - price) / original * 100, 1) if original and price and original > price else None
    image = None
    og_img = soup.find("meta", property="og:image")
    if og_img:
        image = og_img.get("content")

    logger.info("[HTML 파서/oliveyoung] title=%s price=%s original=%s weight=%s ship=%s options=%d",
                title, price, original, weight_text, shipping_fee, len(product_options))
    return ProductInfo(
        title=title, original_price=original, discounted_price=price,
        discount_rate=discount_rate, main_image_url=image,
        shipping_fee=shipping_fee, shipping_period=shipping_period,
        product_options=product_options,
        product_weight=weight_text, currency="KRW", hs_code=None, raw_data={},
    )


def _parse_hmall(html: str, page_title, url) -> ProductInfo:
    """
    현대홈쇼핑(Hmall) 상품 상세 파서.
    스코프: main.cmain .cnt-product
    원가: .sale-before em / 판매가: .sale-price em
    """
    soup = _soup(html)

    # 1. 파싱 스코프
    main = soup.find("main", class_=re.compile(r"cmain", re.I)) or soup
    scope = main.find(class_=re.compile(r"cnt-product", re.I)) or main

    # 노이즈 제거
    _noise = re.compile(
        r"pdbenefitWrap|cnt-benefit|cnt-explain|discount-details|onair|"
        r"review|qna|delivery|card.?benefit|banner|btn.?wrap|button.?wrap",
        re.I,
    )
    for tag in scope.find_all(True, {"class": _noise}):
        tag.decompose()
    for tag in scope.find_all("script"):
        tag.decompose()
    for tag in scope.find_all("iframe"):
        tag.decompose()

    # 2. 제목
    title = None
    t_el = scope.select_one(".pdname")
    if t_el:
        # <br> → 공백
        for br in t_el.find_all("br"):
            br.replace_with(" ")
        title = re.sub(r"\s+", " ", t_el.get_text(strip=True))
    if not title:
        og = soup.find("meta", property="og:title")
        title = og["content"].strip() if og and og.get("content") else page_title

    # 3. 원가 (.sale-before em)
    original = None
    op_el = scope.select_one(".sale-before em")
    if not op_el:
        op_el = scope.select_one(".sale-before")
    if op_el:
        v = _to_num(re.sub(r"[^\d]", "", op_el.get_text()))
        if v:
            original = v

    # 4. 최종 판매가 (.sale-price em)
    price = None
    fp_el = scope.select_one(".sale-price em")
    if not fp_el:
        fp_el = scope.select_one(".sale-price")
    if fp_el:
        price = _to_num(re.sub(r"[^\d]", "", fp_el.get_text()))
    if not price:
        og_price = soup.find("meta", attrs={"property": "product:price:amount"})
        if og_price:
            price = _to_num(og_price.get("content"))
    if not price:
        price = _price_from_text(scope.get_text())

    if not original:
        original = price

    # 5. 무게 (제목/상품정보에서; 제품 중량 935g 등 크기 정보 제외)
    weight_text = None
    _weight_pat = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l|리터|킬로|그램)\b", re.I)
    _qty_pat = re.compile(r"\d+\s*(개|구|세트|팩|봉|캔|병|박스)", re.I)
    # 제품 크기/무게 표기 제외 (ex: 제품중량, 크기, 무게)
    _size_ctx_pat = re.compile(r"제품\s*(중량|크기|무게|사이즈)", re.I)
    full_text = (title or "") + " " + scope.get_text()[:3000]

    for m in _weight_pat.finditer(full_text):
        ctx = full_text[max(0, m.start() - 15):m.end() + 15]
        if _qty_pat.search(ctx) or _size_ctx_pat.search(ctx):
            continue
        weight_text = m.group(0).replace(",", "").strip()
        break

    # 6. 옵션 — __NEXT_DATA__ stockList
    product_options = []
    nd_tag = soup.find("script", id="__NEXT_DATA__")
    if nd_tag and nd_tag.string:
        try:
            import json as _json
            nd = _json.loads(nd_tag.string)
            stock_list = (
                _dig(nd, "props", "pageProps", "respData", "itemPtc", "stockList") or []
            )
            if stock_list:
                values, soldouts, opt_prices = [], [], {}
                for item in stock_list:
                    name = (item.get("uitmAttrNm") or item.get("uitmTotNm") or "").strip()
                    if not name:
                        continue
                    values.append(name)
                    if (item.get("stockCount") or 0) == 0:
                        soldouts.append(name)
                    sp = item.get("sellPrc") or 0
                    if sp:
                        opt_prices[name] = float(sp)
                if values:
                    product_options.append(ProductOption(
                        option_type="옵션",
                        available_values=values,
                        soldout_values=soldouts or None,
                        option_prices=opt_prices or None,
                    ))
        except Exception as _e:
            logger.debug("[hmall] __NEXT_DATA__ 옵션 파싱 실패: %s", _e)

    discount_rate = round((original - price) / original * 100, 1) if original and price and original > price else None
    image = None
    og_img = soup.find("meta", property="og:image")
    if og_img:
        image = og_img.get("content")

    logger.info("[HTML 파서/hmall] title=%s price=%s original=%s weight=%s options=%d",
                title, price, original, weight_text, len(product_options))
    return ProductInfo(
        title=title, original_price=original, discounted_price=price,
        discount_rate=discount_rate, main_image_url=image,
        shipping_period=None, product_options=product_options,
        product_weight=weight_text, currency="KRW", hs_code=None, raw_data={},
    )


def _29cm_options_from_rsc(html: str) -> list:
    """29cm Next.js App Router RSC flight(__next_f) 데이터에서 옵션 추출.

    스크립트 내 형식 (JS 문자열 이스케이프):
        self.__next_f.push([1,"...\\n72:{\\\"optionId\\\":44729760,...,\\\"optionItemName\\\":\\\"SIZE\\\",\\\"optionItemValue\\\":\\\"XS\\\",...}\\n..."])
    이스케이프 해제 후 각 줄: "72:{...json...}"
    """
    soup = _soup(html)
    by_type: dict = {}  # optionItemName → {"values": [...], "soldouts": [...]}

    for script in soup.find_all("script"):
        text = script.string or ""
        if "__next_f" not in text or "optionId" not in text:
            continue
        # JS 문자열 이스케이프 해제: \" → "  \n → newline
        decoded = text.replace('\\"', '"').replace('\\n', '\n')
        for line in decoded.splitlines():
            line = line.strip()
            # 형태: "7a:{...json...}"  (키는 16진수 또는 숫자)
            m = re.match(r'^[0-9a-f]+:(\{.+\})\s*$', line)
            if not m:
                continue
            try:
                obj = json.loads(m.group(1))
            except Exception:
                continue
            if "optionId" not in obj:
                continue
            item_name = obj.get("optionItemName")
            item_value = obj.get("optionItemValue")
            is_soldout = obj.get("isSoldOut", False)
            is_visible = obj.get("isVisible", True)
            if not item_name or not item_value or not is_visible:
                continue
            if item_name not in by_type:
                by_type[item_name] = {"values": [], "soldouts": []}
            by_type[item_name]["values"].append(item_value)
            if is_soldout:
                by_type[item_name]["soldouts"].append(item_value)

    return [
        ProductOption(
            option_type=opt_type,
            available_values=data["values"],
            soldout_values=data["soldouts"] or None,
        )
        for opt_type, data in by_type.items()
    ]


def _parse_29cm(html: str, page_title, url) -> ProductInfo:
    """
    29CM 상품 상세 파서.
    스코프: main[class*='select-none'] (webview:select-none)
    원가: span.text-tertiary.line-through
    판매가: #pdp_product_price
    """
    soup = _soup(html)

    # 1. 파싱 스코프 (main.webview:select-none — 콜론 포함 클래스)
    scope = (
        soup.find("main", class_=re.compile(r"select-none", re.I))
        or soup.find("main")
        or soup
    )

    # 노이즈 제거
    _noise = re.compile(
        r"coupon|review|recommend|banner|event|brand.?intro|detail.?image|reward|point",
        re.I,
    )
    for tag in scope.find_all(True, {"class": _noise}):
        tag.decompose()
    for tag in scope.find_all("script"):
        tag.decompose()

    # 2. 제목
    title = None
    t_el = scope.find(id="pdp_product_name")
    if not t_el:
        t_el = scope.find("h1") or scope.find("h2")
    if t_el:
        for br in t_el.find_all("br"):
            br.replace_with(" ")
        title = re.sub(r"\s+", " ", t_el.get_text(strip=True))
    if not title:
        og = soup.find("meta", property="og:title")
        title = og["content"].strip() if og and og.get("content") else page_title

    # 3. 원가 (span.text-tertiary.line-through 또는 취소선)
    original = None
    op_el = scope.select_one("span.text-tertiary.line-through")
    if not op_el:
        op_el = scope.find("del") or scope.find(class_=re.compile(r"line.?through|strike|origin.?price|before.?price", re.I))
    if op_el:
        v = _to_num(re.sub(r"[^\d]", "", op_el.get_text()))
        if v:
            original = v

    # 4. 최종 판매가 (#pdp_product_price; 쿠폰가/첫구매가 제외)
    price = None
    fp_el = scope.find(id="pdp_product_price")
    if fp_el:
        # 쿠폰/첫구매 하위 텍스트 제외: id 자체 텍스트만
        for child in fp_el.find_all(class_=re.compile(r"coupon|first.?buy|benefit|event", re.I)):
            child.decompose()
        price = _to_num(re.sub(r"[^\d]", "", fp_el.get_text()))
    if not price:
        og_price = soup.find("meta", attrs={"property": "product:price:amount"})
        if og_price:
            price = _to_num(og_price.get("content"))
    if not price:
        # __NEXT_DATA__ fallback
        next_data = _extract_next_data(soup)
        if next_data:
            page_props = _dig(next_data, "props", "pageProps") or {}
            for key in ("product", "item", "goodsDetail", "catalogDetail"):
                obj = page_props.get(key) or {}
                if isinstance(obj, dict):
                    price = price or _to_num(obj.get("salePrice") or obj.get("price") or obj.get("sellPrice"))
                    original = original or _to_num(obj.get("originalPrice") or obj.get("consumerPrice"))
                    if price:
                        break
    if not price:
        price = _price_from_text(scope.get_text())

    if not original:
        original = price

    # 5. 무게/사이즈 (제목 우선 → 용량/무게 패턴)
    weight_text = None
    _weight_pat = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l|cm|mm|리터|킬로)\b", re.I)
    _qty_pat = re.compile(r"\d+\s*(개|구|세트|팩|봉|캔|병|박스)", re.I)

    for text in [title or "", scope.get_text()[:2000]]:
        for m in _weight_pat.finditer(text):
            ctx = text[max(0, m.start() - 5):m.end() + 5]
            if _qty_pat.search(ctx):
                continue
            weight_text = m.group(0).replace(",", "").strip()
            break
        if weight_text:
            break

    discount_rate = round((original - price) / original * 100, 1) if original and price and original > price else None
    image = None
    og_img = soup.find("meta", property="og:image")
    if og_img:
        image = og_img.get("content")

    # 6. 옵션 — RSC flight(__next_f) 데이터에서 추출
    options = _29cm_options_from_rsc(html)

    logger.info("[HTML 파서/29cm] title=%s price=%s original=%s weight=%s options=%d",
                title, price, original, weight_text, len(options))
    return ProductInfo(
        title=title, original_price=original, discounted_price=price,
        discount_rate=discount_rate, main_image_url=image,
        shipping_period=None, product_options=options,
        product_weight=weight_text, currency="KRW", hs_code=None, raw_data={},
    )


def _parse_wconcept(html: str, page_title, url) -> ProductInfo:
    """
    W Concept 상품 상세 파서.
    스코프: div.content
    원가: .price-box .original .eswPrc
    판매가: .price-box .price .eswPrc
    통화: USD 가능 (eswPrc 기준)
    """
    soup = _soup(html)

    # 1. 파싱 스코프
    scope = soup.find("div", class_=re.compile(r"^content$", re.I)) or soup.find("div", class_="content") or soup

    # 노이즈 제거
    _noise_ids = re.compile(r"reviews|coupon.?box|review.?box|wmuse.?box", re.I)
    _noise_cls = re.compile(r"coupon-box|review-box|detail-info2|wmuse-box|prd-img-box|addsauce", re.I)
    for tag in scope.find_all(True, {"id": _noise_ids}):
        tag.decompose()
    for tag in scope.find_all(True, {"class": _noise_cls}):
        tag.decompose()
    for tag in scope.find_all("script"):
        tag.decompose()

    # 2. 제목
    title = None
    t_el = scope.select_one(".product-name")
    if t_el:
        for brand in t_el.select(".brand-name"):
            brand.decompose()
        for br in t_el.find_all("br"):
            br.replace_with(" ")
        title = re.sub(r"\s+", " ", t_el.get_text(strip=True))
    if not title:
        og = soup.find("meta", property="og:title")
        title = og["content"].strip() if og and og.get("content") else page_title

    # 3. 통화 감지 (eswPrc 텍스트에서 $ / ₩ 또는 KRW/USD 판단)
    def _detect_currency_and_value(text: str):
        text = text.strip()
        if text.startswith("$"):
            return "USD", _to_num(text[1:].replace(",", ""))
        if text.startswith("₩") or text.startswith("￦"):
            return "KRW", _to_num(text[1:].replace(",", ""))
        v = _to_num(re.sub(r"[^\d.]", "", text))
        return "KRW", v

    # 4. 원가
    original = None
    currency = "KRW"
    # dl.price 구조 (wconcept 현행 레이아웃: dd.normal > em)
    _dl_price = scope.select_one("dl.price")
    if _dl_price:
        _em = _dl_price.select_one("dd.normal em")
        if _em:
            v = _to_num(re.sub(r"[^\d]", "", _em.get_text()))
            if v:
                original = v
                currency = "KRW"
    if not original:
        op_el = scope.select_one(".price-box .original .eswPrc")
        if not op_el:
            op_el = scope.select_one(".price-box .original")
        if not op_el:
            op_el = scope.find("del") or scope.find(class_=re.compile(r"original.?price|before.?price|old.?price", re.I))
        if op_el:
            cur, v = _detect_currency_and_value(op_el.get_text(strip=True))
            if v:
                original = v
                currency = cur

    # 5. 최종 판매가
    price = None
    # dl.price 구조 (wconcept 현행 레이아웃: dd.cupon > em)
    if _dl_price:
        _cupon_em = _dl_price.select_one("dd.cupon em")
        if _cupon_em:
            v = _to_num(re.sub(r"[^\d]", "", _cupon_em.get_text()))
            if v:
                price = v
                currency = "KRW"
    if not price:
        fp_el = scope.select_one(".price-box .price .eswPrc")
        if not fp_el:
            fp_el = scope.select_one(".price-box .price")
        if not fp_el:
            for el in scope.select(".eswPrc"):
                if not el.find_parent(class_=re.compile(r"original|coupon|loyalty|point", re.I)):
                    fp_el = el
                    break
        if fp_el:
            cur, v = _detect_currency_and_value(fp_el.get_text(strip=True))
            if v:
                price = v
                currency = cur
    if not price:
        og_price = soup.find("meta", attrs={"property": "product:price:amount"})
        if og_price:
            price = _to_num(og_price.get("content"))
    if not price:
        next_data = _extract_next_data(soup)
        if next_data:
            page_props = _dig(next_data, "props", "pageProps") or {}
            for key in ("product", "item", "goodsDetail"):
                obj = page_props.get(key) or {}
                if isinstance(obj, dict):
                    price = price or _to_num(obj.get("salePrice") or obj.get("price"))
                    original = original or _to_num(obj.get("originalPrice") or obj.get("consumerPrice"))
                    if price:
                        break
    if not price:
        price = _price_from_text(scope.get_text())

    if not original:
        original = price

    # 6. 무게/용량 (제목 우선)
    weight_text = None
    _weight_pat = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l|oz|fl\.?oz|리터|킬로)\b", re.I)
    _qty_pat = re.compile(r"\d+\s*(개|구|세트|팩|봉|캔|병|박스|color)", re.I)

    for text in [title or "", scope.get_text()[:2000]]:
        for m in _weight_pat.finditer(text):
            ctx = text[max(0, m.start() - 5):m.end() + 5]
            if _qty_pat.search(ctx):
                continue
            weight_text = m.group(0).replace(",", "").strip()
            break
        if weight_text:
            break

    # 7. 옵션: .option-item → group_name .title, items .option-cont li / ul.select-list
    product_options = []
    _skip_texts = re.compile(r"선택하세요|선택해|수량|총 금액|배송|쿠폰|적립", re.I)

    for group in scope.select(".option-item"):
        label_el = group.select_one(".title")
        group_name = label_el.get_text(strip=True) if label_el else "옵션"
        if _skip_texts.search(group_name):
            continue

        items = group.select(".option-cont li, .option-cont option, .option-list li")
        available = []
        soldout_values = []
        selected_val = None
        for item in items:
            # select-list-selected 는 플레이스홀더 ("선택해 주세요.") → 스킵
            inner_a = item.find("a")
            if inner_a and "select-list-selected" in " ".join(inner_a.get("class", [])):
                continue
            name_text = (inner_a.get("title") or inner_a.get_text(strip=True)).strip() if inner_a \
                else item.get_text(strip=True)
            if not name_text or _skip_texts.search(name_text):
                continue
            if re.search(r"품절|sold.?out", name_text, re.I):
                soldout_values.append(name_text)
            is_selected = bool(
                item.get("selected") or
                any(c in ("on", "selected", "active", "checked") for c in item.get("class", []))
            )
            available.append(name_text)
            if is_selected:
                selected_val = name_text

        if available:
            product_options.append(ProductOption(
                option_type=group_name,
                available_values=available,
                selected_value=selected_val,
                soldout_values=soldout_values or None,
            ))

    # ul.select-list 직접 탐색 폴백 (.option-item 래퍼 없는 경우 대비)
    if not product_options:
        for ul in scope.select("ul.select-list"):
            available = []
            soldout_values = []
            for li in ul.find_all("li"):
                a = li.find("a", class_=re.compile(r"select-list-link", re.I))
                if not a:
                    continue
                if "select-list-selected" in " ".join(a.get("class", [])):
                    continue  # 플레이스홀더 스킵
                name = (a.get("title") or a.get_text(strip=True)).strip()
                if not name or _skip_texts.search(name):
                    continue
                if re.search(r"품절|sold.?out", name, re.I):
                    soldout_values.append(name)
                available.append(name)
            if available:
                group_name = "옵션"
                parent = ul.find_parent(class_=re.compile(r"\boption-item\b", re.I))
                if parent:
                    title_el = parent.select_one(".title")
                    if title_el:
                        group_name = title_el.get_text(strip=True)
                product_options.append(ProductOption(
                    option_type=group_name,
                    available_values=available,
                    soldout_values=soldout_values or None,
                ))

    discount_rate = round((original - price) / original * 100, 1) if original and price and original > price else None
    # dl.price .discount_percent → 할인율 직접 추출
    if not discount_rate:
        _dp_el = (scope.select_one("dl.price .discount_percent")
                  or scope.select_one("span.discount_percent"))
        if _dp_el:
            _m = re.search(r"(\d+)", _dp_el.get_text())
            if _m:
                discount_rate = int(_m.group(1))

    image = None
    og_img = soup.find("meta", property="og:image")
    if og_img:
        image = og_img.get("content")

    # 배송비: dl.card_info_wrap dd
    shipping_fee: Optional[float] = None
    for _dd in soup.select("dl.card_info_wrap dd"):
        _text = _dd.get_text(strip=True)
        if "배송" in _text:
            if "무료" in _text:
                shipping_fee = 0.0
            else:
                _m2 = re.search(r"([\d,]+)\s*원", _text)
                if _m2:
                    shipping_fee = float(_m2.group(1).replace(",", ""))
            break

    logger.info("[HTML 파서/wconcept] title=%s price=%s original=%s currency=%s weight=%s options=%d shipping=%s",
                title, price, original, currency, weight_text, len(product_options), shipping_fee)
    return ProductInfo(
        title=title, original_price=original, discounted_price=price,
        discount_rate=discount_rate, main_image_url=image,
        shipping_fee=shipping_fee, shipping_period=None, product_options=product_options,
        product_weight=weight_text, currency=currency, hs_code=None, raw_data={},
    )


def _parse_next_spa(shop_type: str, html: str, page_title, url) -> ProductInfo:
    """Next.js 기반 SPA 공통 파서 (29cm, wconcept, ohou, zigzag)."""
    soup = _soup(html)
    meta = _extract_meta(soup)
    product = _extract_jsonld_product(soup)
    next_data = _extract_next_data(soup)

    offers = product.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}

    title = _first(product.get("name"), meta.get("og:title"), page_title)
    price = _to_num(_first(offers.get("price"), meta.get("product:price:amount")))
    original = _to_num(offers.get("highPrice")) or price
    image = _first(product.get("image"), meta.get("og:image"))

    # __NEXT_DATA__ fallback: props.pageProps 안에서 price 탐색
    if not price and next_data:
        page_props = _dig(next_data, "props", "pageProps") or {}
        # 공통 키 패턴으로 탐색
        for key in ("product", "item", "goodsDetail", "catalogDetail"):
            obj = page_props.get(key) or {}
            if not isinstance(obj, dict):
                continue
            price = price or _to_num(obj.get("salePrice") or obj.get("price") or obj.get("sellPrice"))
            original = original or _to_num(obj.get("originalPrice") or obj.get("consumerPrice") or obj.get("retailPrice"))
            title = title or obj.get("name") or obj.get("productName") or obj.get("goodsName")
            img = obj.get("mainImageUrl") or obj.get("imageUrl") or obj.get("thumbnailUrl")
            image = image or (img[0] if isinstance(img, list) and img else img)
            if price:
                break

    # 정규식 fallback
    if not price:
        price = _price_from_text(html)
    if not original:
        original = price

    if not title:
        h = soup.find("h1") or soup.find("h2")
        title = h.get_text(strip=True) if h else page_title

    discount_rate = round((original - price) / original * 100, 1) if original and price and original > price else None
    logger.info("[HTML 파서/%s] title=%s price=%s", shop_type, title, price)
    return ProductInfo(title=title, original_price=original, discounted_price=price,
                       discount_rate=discount_rate, main_image_url=image,
                       shipping_period=None, product_options=[], product_weight=None,
                       currency="KRW", hs_code=None, raw_data={})


def _parse_ohou(html: str, page_title, url) -> ProductInfo:
    """
    오늘의집(Ohouse) 상품 상세 파서.
    스코프: div[data-element="Section"][data-object-section*="PDP 상품정보"]
    원가: del[data-testid="original-price"]
    판매가: [data-testid="selling-price"]
    CSS 해시 클래스는 보조 fallback으로만 사용.
    """
    soup = _soup(html)

    # 1. 파싱 스코프 (data-testid 기반이 우선; Section 전체도 허용)
    scope = (
        soup.find(attrs={"data-object-section": re.compile(r"PDP\s*상품정보", re.I)})
        or soup.find(attrs={"data-element": "Section"})
        or soup
    )

    # 노이즈 제거
    _noise = re.compile(
        r"review|rating|carousel|thumbnail|breadcrumb|share|delivery|"
        r"banner|recommend|detail.?image|script",
        re.I,
    )
    for tag in scope.find_all(True, {"class": _noise}):
        tag.decompose()
    for tag in scope.find_all("script"):
        tag.decompose()

    # 2. 제목 (data-testid 우선 → CSS 해시 클래스 → h1/h2)
    title = None
    t_el = scope.find(attrs={"data-testid": re.compile(r"product.?name|item.?name|title", re.I)})
    if not t_el:
        # 알려진 해시 클래스 (fallback, 변경 가능)
        t_el = scope.select_one(".eszk2530")
    if not t_el:
        # h1/h2 중 브랜드명이 아닌 것
        for h in scope.find_all(["h1", "h2"]):
            brand_el = h.find(class_=re.compile(r"brand|css-uliyhk", re.I))
            if brand_el:
                brand_el.decompose()
            candidate = h.get_text(strip=True)
            if candidate and len(candidate) > 3:
                t_el = h
                break
    if t_el:
        # 브랜드 요소 제거
        for brand in t_el.find_all(class_=re.compile(r"css-uliyhk|brand", re.I)):
            brand.decompose()
        for br in t_el.find_all("br"):
            br.replace_with(" ")
        title = re.sub(r"\s+", " ", t_el.get_text(strip=True))
    if not title:
        og = soup.find("meta", property="og:title")
        title = og["content"].strip() if og and og.get("content") else page_title

    # 3. 원가 (data-testid="original-price" del 태그)
    original = None
    op_el = scope.find("del", attrs={"data-testid": "original-price"})
    if not op_el:
        op_el = scope.find(attrs={"data-testid": "original-price"})
    if not op_el:
        op_el = scope.find("del")
    if op_el:
        v = _to_num(re.sub(r"[^\d]", "", op_el.get_text()))
        if v:
            original = v

    # 4. 최종 판매가 (data-testid="selling-price")
    price = None
    fp_container = scope.find(attrs={"data-testid": "selling-price"})
    if fp_container:
        # 내부에서 가장 대표 숫자 추출 (특가 라벨 텍스트 제거)
        for label in fp_container.find_all(class_=re.compile(r"label|badge|tag|특가", re.I)):
            label.decompose()
        # .css-1jia7tc 또는 첫 번째 숫자 포함 요소
        inner = fp_container.select_one(".css-1jia7tc") or fp_container
        price = _to_num(re.sub(r"[^\d]", "", inner.get_text()))
    if not price:
        og_price = soup.find("meta", attrs={"property": "product:price:amount"})
        if og_price:
            price = _to_num(og_price.get("content"))
    if not price:
        # __NEXT_DATA__ fallback
        next_data = _extract_next_data(soup)
        if next_data:
            page_props = _dig(next_data, "props", "pageProps") or {}
            for key in ("product", "item", "goodsDetail"):
                obj = page_props.get(key) or {}
                if isinstance(obj, dict):
                    price = price or _to_num(obj.get("salePrice") or obj.get("price") or obj.get("sellPrice"))
                    original = original or _to_num(obj.get("originalPrice") or obj.get("consumerPrice"))
                    if price:
                        break
    if not price:
        price = _price_from_text(scope.get_text()[:3000])

    if not original:
        original = price

    # 5. 무게/사이즈 (제목에서 cm/mm/kg 패턴)
    weight_text = None
    _weight_pat = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l|cm|mm|리터|킬로)\b", re.I)
    _qty_pat = re.compile(r"\d+\s*(개|구|세트|팩|봉|캔|병|박스)", re.I)

    for m in _weight_pat.finditer(title or ""):
        ctx = (title or "")[max(0, m.start() - 5):m.end() + 5]
        if _qty_pat.search(ctx):
            continue
        weight_text = m.group(0).replace(",", "").strip()
        break

    # 6. 배송비 — "무료배송" span 또는 배송 섹션 가격 추출
    shipping_fee: Optional[float] = None
    for span in soup.find_all("span", string="무료배송"):
        shipping_fee = 0.0
        break
    if shipping_fee is None:
        m_ship = re.search(r'배송비\s*[^0-9]*([\d,]+)\s*원', html)
        if m_ship:
            shipping_fee = _to_num(re.sub(r'[^\d]', '', m_ship.group(1)))

    # 7. 옵션 — data-testid select 기반
    # first-depth-select: 메인 옵션 (사이즈 등), additional-select: 추가상품
    # option 텍스트 형식: "이름 (N,NNN원)" 또는 "이름 (N,NNN원) / 품절"
    product_options = []
    option_div = soup.find(attrs={"data-testid": "option"})
    if option_div:
        for sel in option_div.find_all(
            "select",
            attrs={"data-testid": re.compile(r"first-depth|second-depth|additional", re.I)},
        ):
            # 선택 가능한 option이 하나도 없으면(빈 select) 스킵
            real_opts = [o for o in sel.find_all("option") if not o.has_attr("hidden")]
            if not real_opts:
                continue

            # 옵션 타입: placeholder(hidden disabled) 텍스트
            placeholder = sel.find("option", hidden=True)
            opt_type = placeholder.get_text(strip=True) if placeholder else "옵션"
            opt_type = re.sub(r'\s*\(선택\)\s*$', '', opt_type).strip()

            values = []
            soldout_values = []
            option_prices: dict = {}

            for opt in real_opts:
                raw = opt.get_text(strip=True)
                is_soldout = opt.has_attr("disabled") or "품절" in raw

                # 가격 추출: "이름 (N,NNN원)"
                pm = re.search(r'\(([\d,]+)\s*원\)', raw)
                item_price = _to_num(re.sub(r'[^\d]', '', pm.group(1))) if pm else None

                # 이름 정제
                clean = re.sub(r'\s*\([\d,]+\s*원\)', '', raw)
                clean = re.sub(r'\s*/\s*품절\s*$', '', clean).strip()
                if not clean:
                    continue

                values.append(clean)
                if is_soldout:
                    soldout_values.append(clean)
                if item_price:
                    option_prices[clean] = item_price

            if values:
                product_options.append(ProductOption(
                    option_type=opt_type,
                    available_values=values,
                    soldout_values=soldout_values or None,
                    option_prices=option_prices or None,
                ))

    discount_rate = round((original - price) / original * 100, 1) if original and price and original > price else None
    image = None
    og_img = soup.find("meta", property="og:image")
    if og_img:
        image = og_img.get("content")

    logger.info("[HTML 파서/ohou] title=%s price=%s original=%s weight=%s ship=%s options=%d",
                title, price, original, weight_text, shipping_fee, len(product_options))
    return ProductInfo(
        title=title, original_price=original, discounted_price=price,
        discount_rate=discount_rate, main_image_url=image,
        shipping_fee=shipping_fee, shipping_period=None,
        product_options=product_options,
        product_weight=weight_text, currency="KRW", hs_code=None, raw_data={},
    )


def _parse_zigzag(html: str, page_title, url) -> ProductInfo:
    """
    지그재그(Zigzag) 상품 상세 파서.
    1순위: __NEXT_DATA__ props.pageProps.product
      - 원가:   product_price.max_price_info.price
      - 할인가: product_price.product_promotion_discount_info.discount_price (쿠폰 제외)
      - 할인율: product_price.product_promotion_discount_info.discount_rate
      - 배송비: shipping_fee.fee_type / base_fee
      - 옵션:   product_item_attribute_list[].name + value_list[].value
    2순위: HTML 파싱 폴백
    """
    soup = _soup(html)

    # ── 1. __NEXT_DATA__ 우선 파싱 ───────────────────────────────────────────
    next_data = _extract_next_data(soup)
    nd_product = _dig(next_data, "props", "pageProps", "product") or {}

    title = nd_product.get("name") or None
    original: Optional[float] = None
    price: Optional[float] = None
    discount_rate: Optional[float] = None
    shipping_fee: Optional[float] = None
    product_options = []
    image = None

    if nd_product:
        pp = nd_product.get("product_price") or {}

        # 원가 (정상가)
        original = _to_num(_dig(pp, "max_price_info", "price"))

        # 할인가: product_promotion_discount_info (쿠폰 제외 실할인)
        promo = pp.get("product_promotion_discount_info") or {}
        if promo and promo.get("discount_price"):
            price = _to_num(promo["discount_price"])
            discount_rate = _to_num(promo.get("discount_rate"))
        else:
            price = original  # 실할인 없음

        # 배송비
        sf = nd_product.get("shipping_fee") or {}
        if sf.get("fee_type") == "FREE" or sf.get("base_fee") == 0:
            shipping_fee = 0.0
        elif sf.get("base_fee"):
            shipping_fee = float(sf["base_fee"])

        # 옵션: product_item_attribute_list
        # 옵션값 코드 제거: "(19)BLACK" → "BLACK", "FREE(999)" → "FREE"
        for attr in (nd_product.get("product_item_attribute_list") or []):
            opt_name = attr.get("name")
            if not opt_name:
                continue
            values = []
            for v in (attr.get("value_list") or []):
                raw = (v.get("value") or "").strip()
                raw = re.sub(r'^\(\d+\)\s*', '', raw)   # 앞 코드: (19)
                raw = re.sub(r'\s*\(\d+\)$', '', raw)   # 뒤 코드: (999)
                raw = raw.strip()
                if raw:
                    values.append(raw)
            if values:
                product_options.append(ProductOption(
                    option_type=opt_name,
                    available_values=values,
                ))

        # 이미지: MAIN 타입 우선
        for img in (nd_product.get("product_image_list") or []):
            if img.get("image_type") == "MAIN":
                image = img.get("url")
                break

    # ── 1-b. collect_zigzag synthetic HTML 옵션 (있으면 __NEXT_DATA__ 덮어씀) ──
    # 구조: div#zigzag-all-options > div > p.zds4_s96ru81v(그룹명) + div.list-container > p.zds4_s96ru81t(아이템)
    synth = soup.find("div", id="zigzag-all-options")
    if synth:
        html_options = []
        from bs4 import Tag as _Tag
        for group_div in synth.children:
            if not isinstance(group_div, _Tag):
                continue
            name_p = group_div.find("p", class_=re.compile(r"zds4_s96ru81v", re.I))
            group_name = name_p.get_text(strip=True) if name_p else "옵션"
            lc = group_div.find("div", class_="list-container")
            if not lc:
                continue
            values, soldouts = [], []
            for item_p in lc.find_all("p", attrs={"data-zds-component": "Text"}):
                if "zds4_s96ru81t" not in " ".join(item_p.get("class", [])):
                    continue
                raw = item_p.get_text(strip=True)
                name = re.sub(r'^\(\d+\)\s*', '', raw).strip()
                if not name:
                    continue
                values.append(name)
                if "zds-soldout" in " ".join(item_p.get("class", [])):
                    soldouts.append(name)
            if values:
                html_options.append(ProductOption(
                    option_type=group_name,
                    available_values=values,
                    soldout_values=soldouts or None,
                ))
        if html_options:
            product_options = html_options
            logger.info("[HTML 파서/zigzag] synthetic 옵션 %d그룹", len(product_options))

    # ── 2. HTML 폴백 (제목·가격·이미지) ─────────────────────────────────────
    if not title:
        scope = soup.find("div", class_=re.compile(r"zds-themes", re.I)) or soup
        t_el = scope.select_one(".pdp__title h1") or scope.find("h1")
        if t_el:
            title = re.sub(r"\s+", " ", t_el.get_text(strip=True))
    if not title:
        og = soup.find("meta", property="og:title")
        title = (og["content"].strip() if og and og.get("content") else None) or page_title

    if not price:
        og_price = soup.find("meta", attrs={"property": "product:price:amount"})
        if og_price:
            price = _to_num(og_price.get("content"))
    if not price:
        price = _price_from_text(html[:3000])
    if not original:
        original = price

    if not image:
        og_img = soup.find("meta", property="og:image")
        if og_img:
            image = og_img.get("content")

    # 할인율 재계산 (폴백 경로)
    if discount_rate is None and original and price and original > price:
        discount_rate = round((original - price) / original * 100, 1)

    # 무게/용량 (제목에서만)
    weight_text = None
    _weight_pat = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l|oz|리터|킬로)\b", re.I)
    _qty_pat = re.compile(r"\d+\s*(개|구|세트|팩|봉|캔|병|박스)", re.I)
    for m in _weight_pat.finditer(title or ""):
        ctx = (title or "")[max(0, m.start() - 5):m.end() + 5]
        if _qty_pat.search(ctx):
            continue
        weight_text = m.group(0).replace(",", "").strip()
        break

    logger.info("[HTML 파서/zigzag] title=%s price=%s original=%s discount_rate=%s options=%d ship=%s",
                title, price, original, discount_rate, len(product_options), shipping_fee)
    return ProductInfo(
        title=title, original_price=original, discounted_price=price,
        discount_rate=discount_rate, main_image_url=image,
        shipping_fee=shipping_fee, shipping_period=None,
        product_options=product_options,
        product_weight=weight_text, currency="KRW", hs_code=None, raw_data={},
    )


def _parse_ably(html: str, page_title, url) -> ProductInfo:
    """
    에이블리(m.a-bly) 상품 상세 파서.
    제목/가격: OG meta + JSON-LD (풀 페이지)
    옵션: div.AblyDrawer_drawer__body 내 그룹 헤더 + .typography__subtitle2
    """
    soup = _soup(html)

    # 1. 제목/가격은 풀 페이지에서 OG meta / JSON-LD로 추출
    meta = _extract_meta(soup)
    product = _extract_jsonld_product(soup)
    offers = product.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}

    title = _first(product.get("name"), meta.get("og:title"), page_title)

    price = _to_num(_first(
        offers.get("price"),
        offers.get("lowPrice"),
        meta.get("product:price:amount"),
        meta.get("og:price:amount"),
    ))
    original = _to_num(offers.get("highPrice")) or price

    image = _first(product.get("image"), meta.get("og:image"))
    if isinstance(image, list):
        image = image[0] if image else None
    if isinstance(image, dict):
        image = image.get("url")

    # 에이블리 color__ 시맨틱 클래스 (sc-* 해시와 달리 안정적)
    # color__content_disabled = 원가(취소선)
    # color__pink* = 할인율 (pink30/pink40 등 버전마다 다름)
    # typography__h4.color__gray70 = 할인가 (body2 gray70은 일반 텍스트이므로 h4로 한정)
    discount_rate = None
    op_color = soup.select_one("p.color__content_disabled")
    if op_color:
        v = _to_num(re.sub(r"[^\d]", "", op_color.get_text()))
        if v:
            original = v  # JSON-LD보다 우선
    dr_color = soup.select_one("p[class*='color__pink']")
    if dr_color:
        m_dr = re.search(r"(\d+)\s*%", dr_color.get_text())
        if m_dr:
            discount_rate = float(m_dr.group(1))
    fp_color = soup.select_one("p.typography__h4.color__gray70")
    if fp_color:
        v = _to_num(re.sub(r"[^\d]", "", fp_color.get_text()))
        if v:
            price = v  # JSON-LD보다 우선

    # JS 데이터 fallback
    if not price:
        m = re.search(r'"(salePrice|finalPrice|sellPrice)"\s*:\s*(\d+)', html)
        if m:
            price = float(m.group(2))
        m2 = re.search(r'"(originPrice|originalPrice|normalPrice)"\s*:\s*(\d+)', html)
        if m2 and not original:
            original = float(m2.group(2))
    if not price:
        price = _price_from_text(html[:5000])
    if not original:
        original = price
    if discount_rate is None and original and price and original > price:
        discount_rate = round((original - price) / original * 100, 1)

    # 2. 옵션: AblyDrawer_drawer__body 스코프
    product_options = []
    _skip_texts = re.compile(r"일반배송|오늘출발|선택하기$|배송|선택", re.I)
    # group_name 정제: "색상 선택하기" → "색상"
    _group_clean = re.compile(r"\s*선택하기\s*$", re.I)

    # id="ably-all-options" 는 collect_ably가 주입한 synthetic HTML (모든 그룹 포함)
    drawer = (
        soup.find("div", id="ably-all-options") or
        soup.find("div", class_=re.compile(r"AblyDrawer_drawer__body", re.I)) or
        soup
    )

    # 그룹 헤더: 텍스트가 "XX 선택하기" 패턴인 요소 탐색
    # 구조: [그룹헤더] [옵션li...] [그룹헤더] ...
    _group_pat = re.compile(r"(색상|사이즈|기장|컬러|색깔|치수)\s*(선택하기)?", re.I)

    # 방법 0: AblyDrawer 클릭 후 DOM 구조 직접 탐색
    # 구조: p.typography__body2 "XX 선택하기" → 부모(header div) → 다음 형제(content div)
    #        → 내부 p.typography__subtitle2 = 옵션명
    groups_found = False
    if drawer is not soup:
        for header_p in drawer.find_all("p", class_=re.compile(r"typography__body2", re.I)):
            group_name_raw = header_p.get_text(strip=True)
            if "선택하기" not in group_name_raw:
                continue
            group_name = _group_clean.sub("", group_name_raw).strip() or "옵션"

            header_container = header_p.parent
            if not header_container:
                continue
            content_div = header_container.find_next_sibling()
            if not content_div:
                continue
            # height="0" → 접힌 그룹 스킵
            if content_div.get("height") == "0":
                continue

            available = []
            for item_p in content_div.find_all("p", class_=re.compile(r"typography__subtitle2", re.I)):
                name = item_p.get_text(strip=True)
                if not name:
                    continue
                available.append(name)

            if available:
                groups_found = True
                product_options.append(ProductOption(
                    option_type=group_name,
                    available_values=available,
                ))

    # 방법 1: AblyDrawer 내부 섹션/그룹 구조 직접 탐색
    if not groups_found:
        for section in drawer.select("[class*='OptionGroup'], [class*='option-group'], [class*='optionGroup']"):
            header = section.find(class_=re.compile(r"subtitle|title|label|header", re.I))
            group_name_raw = header.get_text(strip=True) if header else "옵션"
            group_name = _group_clean.sub("", group_name_raw).strip()
            if not group_name:
                group_name = "옵션"

            items_els = section.select("[class*='subtitle2'], [class*='option-item'], li")
            available = []
            selected_val = None
            for item in items_els:
                name_text = item.get_text(strip=True)
                if not name_text or _skip_texts.search(name_text) or len(name_text) > 50:
                    continue
                is_sold_out = bool(re.search(r"품절|sold.?out", name_text, re.I))
                is_selected = bool(any(c in ("on", "selected", "active") for c in item.get("class", [])))
                available.append(name_text)
                if is_selected:
                    selected_val = name_text

            if available:
                groups_found = True
                product_options.append(ProductOption(
                    option_type=group_name,
                    available_values=available,
                    selected_value=selected_val,
                ))

    # 방법 2: 그룹 헤더 텍스트 기반 순서 탐색
    if not groups_found:
        all_texts = drawer.find_all(string=_group_pat)
        seen_groups = {}
        for txt_node in all_texts:
            group_name_raw = txt_node.strip()
            group_name = _group_clean.sub("", group_name_raw).strip()
            if group_name in seen_groups:
                continue

            # 그룹 헤더 부모 다음 형제에서 옵션 수집
            parent = txt_node.parent
            container = parent.parent if parent else None
            if not container:
                continue

            subtitles = container.select("[class*='subtitle2']")
            if not subtitles:
                # 이전 그룹 옵션과 혼합될 수 있으므로 인접 형제 탐색
                subtitles = []
                sibling = parent.find_next_sibling()
                while sibling:
                    sub_items = sibling.select("[class*='subtitle2']") or ([sibling] if "subtitle2" in " ".join(sibling.get("class", [])) else [])
                    if not sub_items:
                        # 다음 그룹 헤더면 중단
                        if _group_pat.search(sibling.get_text(strip=True)):
                            break
                    subtitles.extend(sub_items)
                    sibling = sibling.find_next_sibling()

            available = []
            selected_val = None
            for el in subtitles:
                name_text = el.get_text(strip=True)
                if not name_text or _skip_texts.search(name_text) or len(name_text) > 50:
                    continue
                if _group_pat.match(name_text):
                    continue
                is_sold_out = bool(re.search(r"품절|sold.?out", name_text, re.I))
                is_selected = bool(any(c in ("on", "selected", "active") for c in el.get("class", [])))
                available.append(name_text)
                if is_selected:
                    selected_val = name_text

            if available:
                seen_groups[group_name] = True
                product_options.append(ProductOption(
                    option_type=group_name,
                    available_values=available,
                    selected_value=selected_val,
                ))

    # 방법 3: typography__subtitle2/body2 쌍 기반 추출 (Drawer 미노출 시 폴백)
    if not product_options:
        _non_option = re.compile(
            r"소재|성분|원산지|제조|주의|모델\s*피팅|모델\s*착용|피팅\s*정보|상세|배송|반품|교환|브랜드",
            re.I,
        )
        seen_labels: set = set()
        for label_el in soup.select("p[class*='typography__subtitle2']"):
            label = label_el.get_text(strip=True)
            if not label or _non_option.search(label) or label in seen_labels:
                continue
            # 바로 다음 형제 p 또는 부모 div 내 body2
            val_el = label_el.find_next_sibling("p")
            if not val_el:
                parent = label_el.parent
                val_el = parent.find("p", class_=re.compile(r"body2", re.I)) if parent else None
            if not val_el:
                continue
            raw_val = val_el.get_text(strip=True)
            if not raw_val:
                continue

            # 콤마 분리 후 항목별 가격 추출: "3부, 핀턱 (+2,000원)" → 핀턱만 2000
            values = []
            option_prices: dict = {}
            for raw_item in raw_val.split(','):
                item = raw_item.strip()
                if not item:
                    continue
                item_price_m = re.search(r'\(\+?([\d,]+)\s*원\)', item)
                if item_price_m:
                    p = _to_num(re.sub(r'[^\d]', '', item_price_m.group(1)))
                    clean_item = re.sub(r'\s*\(\+?[\d,]+\s*원\)\s*', '', item).strip()
                    values.append(clean_item)
                    if p:
                        option_prices[clean_item] = p
                else:
                    values.append(item)
            if not values:
                continue

            option_prices = option_prices if option_prices else None
            seen_labels.add(label)
            product_options.append(ProductOption(
                option_type=label,
                available_values=values,
                option_prices=option_prices,
            ))

    if discount_rate is None and original and price and original > price:
        discount_rate = round((original - price) / original * 100, 1)

    logger.info("[HTML 파서/ably] title=%s price=%s original=%s discount_rate=%s options=%d",
                title, price, original, discount_rate, len(product_options))
    return ProductInfo(
        title=title, original_price=original, discounted_price=price,
        discount_rate=discount_rate, main_image_url=image,
        shipping_period=None, product_options=product_options,
        product_weight=None, currency="KRW", hs_code=None, raw_data={},
    )


# ---------------------------------------------------------------------------
# 공개 인터페이스
# ---------------------------------------------------------------------------

def _parse_musinsa(html: str, page_title, url) -> ProductInfo:
    """
    무신사 상품 상세 파서.
    할인율·할인가: [class*='price__discountwrap'] (price__currentprice 내부)
    원가: [class*='price__original'] 또는 취소선
    """
    soup = _soup(html)

    # 1. 제목
    title = None
    t_el = (
        soup.select_one("[class*='product_article_head'] h2")
        or soup.select_one("[class*='product-info__title']")
        or soup.select_one("h2[class*='product']")
        or soup.find("h1")
    )
    if t_el:
        title = re.sub(r"\s+", " ", t_el.get_text(strip=True))
    if not title:
        og = soup.find("meta", property="og:title")
        title = og["content"].strip() if og and og.get("content") else page_title

    # 2. 품절 감지 — 상품 전체 품절 버튼만 확인 (옵션별 재입고 알림은 제외)
    sold_out = False
    for btn in soup.find_all("button"):
        btn_text = btn.get_text(strip=True)
        # 전체 품절: disabled 속성 있는 "품절" 단독 버튼 (옵션 선택 전 구매 버튼 위치)
        if btn_text == "품절" and btn.get("disabled") is not None:
            sold_out = True
            break

    if sold_out:
        image = None
        og_img = soup.find("meta", property="og:image")
        if og_img:
            image = og_img.get("content")
        logger.info("[HTML 파서/musinsa] 품절 감지: %s", title)
        return ProductInfo(
            title=title, original_price=None, discounted_price=None,
            discount_rate=None, main_image_url=image,
            shipping_period=None, product_options=[],
            product_weight=None, currency="KRW", hs_code=None,
            sold_out=True, raw_data={},
        )

    # 3. 가격 영역
    # DiscountWrap: 쿠폰적용가 라벨 + line-through 가격(쿠폰 전 실판매가)
    # CurrentPrice: 할인율(%) + 쿠폰 적용 후 가격
    discount_wrap = soup.find(class_=re.compile(r"price__discountwrap", re.I))
    current_price_wrap = soup.find(class_=re.compile(r"price__currentprice", re.I))

    # 쿠폰 할인 전용 여부: DiscountWrap에 "쿠폰" 텍스트가 있으면 쿠폰 전용
    _is_coupon_only = bool(
        discount_wrap and "쿠폰" in discount_wrap.get_text()
    )

    original = None
    price = None
    discount_rate = None

    if _is_coupon_only:
        # line-through 가격 = 쿠폰 미적용 실판매가 → original = price
        op_el = discount_wrap.find(class_=re.compile(r"line-through", re.I))
        if op_el:
            v = _to_num(re.sub(r"[^\d]", "", op_el.get_text()))
            if v:
                original = v
                price = v
        # discount_rate = None (쿠폰 할인은 반영 안 함)
    else:
        # 일반 할인: line-through = 원가, CurrentPrice = 할인가
        if discount_wrap:
            op_el = discount_wrap.find(class_=re.compile(r"line-through", re.I))
            if op_el:
                v = _to_num(re.sub(r"[^\d]", "", op_el.get_text()))
                if v:
                    original = v
        if not original:
            op_el = soup.find("del") or soup.find(
                class_=re.compile(r"price__original|before.?price", re.I)
            )
            if op_el:
                v = _to_num(re.sub(r"[^\d]", "", op_el.get_text()))
                if v:
                    original = v

        if current_price_wrap:
            m = re.search(r"(\d+)\s*%", current_price_wrap.get_text())
            if m:
                discount_rate = float(m.group(1))
            text = re.sub(r"\d+\s*%", "", current_price_wrap.get_text())
            price = _to_num(re.sub(r"[^\d]", "", text))

    if not price:
        og_price = soup.find("meta", attrs={"property": "product:price:amount"})
        if og_price:
            price = _to_num(og_price.get("content"))
    if not price:
        price = _price_from_text(soup.get_text()[:3000])

    if not original:
        original = price

    # 4. 무게
    weight_text = None
    _weight_pat = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l|리터|킬로)\b", re.I)
    _qty_pat = re.compile(r"\d+\s*(개|구|세트|팩|봉|캔|병|박스)", re.I)
    for text in [title or "", soup.get_text()[:2000]]:
        for m in _weight_pat.finditer(text):
            ctx = text[max(0, m.start() - 5):m.end() + 5]
            if _qty_pat.search(ctx):
                continue
            weight_text = m.group(0).replace(",", "").strip()
            break
        if weight_text:
            break

    # 5. 옵션
    product_options = []

    # 5-a. StaticDropdownMenu 방식 (무신사 신 UI / Radix UI)
    #   Radix UI portal 구조: StaticDropdownMenuContent 가 StaticDropdownMenu 바깥
    #   (body 레벨)에 렌더링되므로 triggers / contents를 각각 수집 후 인덱스로 매핑.
    #
    #   각 item 내부 구조:
    #     div[data-mds="StaticDropdownMenuItem"]
    #       > div[class*="ContentColumn"]        ← 옵션 이름 (+ DeliverySection 자식)
    #         "230" 또는 "240 (품절)"
    triggers = soup.find_all(attrs={"data-mds": "StaticDropdownMenu"})
    contents = soup.find_all(attrs={"data-mds": "StaticDropdownMenuContent"})

    for i, dropdown in enumerate(triggers):
        trigger_input = dropdown.find(attrs={"data-mds": "DropdownTriggerInput"})
        option_type = "옵션"
        if trigger_input:
            ph = trigger_input.get("placeholder", "").strip()
            if ph:
                option_type = ph

        # portal이면 같은 순서의 content, 아니면 dropdown 자체에서 탐색
        content = contents[i] if i < len(contents) else dropdown

        values, soldout_values, selected_val = [], [], None
        for item in content.find_all(attrs={"data-mds": "StaticDropdownMenuItem"}):
            col = item.find(class_=re.compile(r"ContentColumn", re.I))
            if not col:
                continue
            # 배송 섹션 (DeliverySection/DeliveryRow) 제거 후 텍스트만 추출
            for delivery in col.find_all(class_=re.compile(r"DeliverySection|DeliveryRow", re.I)):
                delivery.decompose()
            name = col.get_text(strip=True)
            if not name:
                continue

            is_soldout = "품절" in name
            clean_name = re.sub(r"\s*\(품절\)", "", name).strip()
            if not clean_name:
                continue

            values.append(clean_name)
            if is_soldout:
                soldout_values.append(clean_name)

        if values:
            product_options.append(ProductOption(
                option_type=option_type,
                available_values=values,
                selected_value=selected_val,
                soldout_values=soldout_values or None,
            ))

    # 5-b. 구형 옵션 방식 fallback
    if not product_options:
        _skip_texts = re.compile(r"선택하세요|옵션 선택|수량|총 금액|배송", re.I)
        for group in soup.select("[class*='option_list'], [class*='select_box'], [class*='product_option']"):
            label_el = group.find(class_=re.compile(r"option.?title|option.?label|tit", re.I))
            group_name = label_el.get_text(strip=True) if label_el else "옵션"
            if _skip_texts.search(group_name):
                continue
            items = group.select("li, option")
            available, selected_val = [], None
            for item in items:
                name_text = item.get_text(strip=True)
                if not name_text or _skip_texts.search(name_text):
                    continue
                is_selected = bool(item.get("selected") or
                                   any(c in ("on", "selected", "active") for c in item.get("class", [])))
                available.append(name_text)
                if is_selected:
                    selected_val = name_text
            if available:
                product_options.append(ProductOption(
                    option_type=group_name,
                    available_values=available,
                    selected_value=selected_val,
                ))

    discount_rate = discount_rate or (
        round((original - price) / original * 100, 1) if original and price and original > price else None
    )
    image = None
    og_img = soup.find("meta", property="og:image")
    if og_img:
        image = og_img.get("content")

    logger.info("[HTML 파서/musinsa] title=%s price=%s original=%s discount=%s",
                title, price, original, discount_rate)
    return ProductInfo(
        title=title, original_price=original, discounted_price=price,
        discount_rate=discount_rate, main_image_url=image,
        shipping_period=None, product_options=product_options,
        product_weight=weight_text, currency="KRW", hs_code=None, raw_data={},
    )


_SITE_PARSERS = {
    '11st':       _parse_11st,
    'ssg':        _parse_ssg,
    'lotteon':    _parse_lotteon,
    'oliveyoung': _parse_oliveyoung,
    '29cm':       _parse_29cm,
    'wconcept':   _parse_wconcept,
    'zigzag':     _parse_zigzag,
    'ohou':       _parse_ohou,
    'musinsa':    _parse_musinsa,
    # Windows 수집 후 파싱
    'coupang':    _parse_coupang,
    'gmarket':    _parse_gmarket,
    'auction':    _parse_auction,
    'hmall':      _parse_hmall,
    'ably':       _parse_ably,
}


def parse_html_only(
    html: str,
    shop_type: str,
    page_title: Optional[str] = None,
    url: Optional[str] = None,
) -> ProductInfo:
    """
    Claude 없이 HTML만으로 상품 정보 파싱.

    Args:
        html: 수집된 페이지 HTML
        shop_type: detect_shop_type() 반환값
        page_title: 페이지 제목
        url: 페이지 URL
    """
    st = shop_type.lower()
    if "naver" in st:
        base = _parse_naver(html, page_title, url)
    else:
        parser = _SITE_PARSERS.get(st, _parse_generic)
        base = parser(html, page_title, url)
    # 모든 사이트 공통: JSON-LD/OG/microdata로 빈 필드(평점·리뷰·브랜드·이미지 등) 보강
    try:
        base = _merge_universal(base, _soup(html))
    except Exception:
        pass
    # HTML 내장 JSON 리뷰 키로 평점/리뷰 최후 보강 (네이버 등 — JSON-LD에 평점 없는 사이트)
    if base.rating is None or base.review_count is None:
        try:
            r, c = _extract_embedded_review(html)
            if base.rating is None and r is not None:
                base.rating = r
            if base.review_count is None and c is not None:
                base.review_count = c
        except Exception:
            pass
    # 배송비 범용 보강 (텍스트 기반 — site 파서가 못 채웠을 때)
    if base.shipping_fee is None and not base.shipping_fee_text:
        try:
            fee, fee_text = _extract_shipping_universal(_soup(html))
            if fee is not None:
                base.shipping_fee = fee
            if fee_text:
                base.shipping_fee_text = fee_text
        except Exception:
            pass
    return base

