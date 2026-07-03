# Template: lotteimall.com (detail)
# Generated: 2026-07-03T00:44:09.215Z
# Notes: 롯데아이몰 상품 상세 페이지. JSON-LD(@graph)에서 가격/브랜드/판매자/평점 추출. simple requests 가능. trailing comma 제거 필요.

import requests
from bs4 import BeautifulSoup
import json, re

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'ko-KR,ko;q=0.9',
}

def _parse_ld_json(html):
    """JSON-LD에서 Product 타입 추출 (@graph 포함). trailing comma 허용."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.select("script[type='application/ld+json']"):
        raw = tag.string or ""
        raw_clean = re.sub(r",\s*([}\]])", r"\1", raw)
        try:
            data = json.loads(raw_clean)
        except:
            continue
        if "@graph" in data:
            for item in data["@graph"]:
                if item.get("@type") == "Product":
                    return item
        elif data.get("@type") == "Product":
            return data
    return {}

def _extract_shipping(soup):
    text = soup.get_text(" ", strip=True)
    area_m = re.search(r"배송비.{0,300}", text, re.DOTALL)
    area = area_m.group(0) if area_m else text

    # 유료 + 조건부 무료
    combined = re.search(r"([\d,]+)\s*원[^(]{0,30}\(([^)]*[\d,]+\s*만?\s*원\s*이상[^)]*무료[^)]*)\)", area)
    if combined:
        fee = int(combined.group(1).replace(",", ""))
        return fee, combined.group(0).strip()

    # 무료배송
    if re.search(r"무료\s*배송|배송\s*무료", area):
        return 0, "무료배송"

    # 조건부 무료
    cond = re.search(r"([\d,]+만?\s*원)\s*이상.*?무료", area)
    if cond:
        return None, cond.group(0).strip()

    # 일반 유료
    m = re.search(r"([\d,]+)\s*원", area)
    if m:
        fee = int(m.group(1).replace(",", ""))
        return fee, f"{m.group(1)}원"

    return None, None

def _extract_delivery_date(soup):
    text = soup.get_text(" ", strip=True)
    m = re.search(r"(오늘|내일|모레|[\d]+일\s*이내)[^.。\n]{0,60}(도착|출발|발송)", text)
    if m:
        return m.group(0).strip()
    return None

def _extract_options(soup):
    options = []
    seen_labels = set()
    SKIP_KW = ["사업자", "email", "이메일", "계좌"]
    for sel in soup.select("select"):
        label = sel.get("title") or sel.get("aria-label") or sel.get("id") or ""
        name_attr = sel.get("name") or ""
        if any(kw in label or kw in name_attr for kw in SKIP_KW):
            continue
        values = []
        for o in sel.select("option"):
            txt = o.get_text(strip=True)
            if txt and not o.get("disabled") and "선택하세요" not in txt and txt != "선택":
                values.append(txt)
        if values and label not in seen_labels:
            seen_labels.add(label)
            options.append({"name": label or "옵션", "values": values})
    return options

def scrape(url: str) -> dict:
    resp = requests.get(url, headers=HEADERS, timeout=15)
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    ld = _parse_ld_json(html)

    # ── 제목 ──
    title = ld.get("name") or ""
    if not title:
        og = soup.find("meta", property="og:title")
        title = og["content"].strip() if og else ""

    # ── 가격 ──
    offers = ld.get("offers", {})
    price_original_str = offers.get("price")
    sale_price_str = offers.get("salePrice")
    try:
        price_original = int(float(str(price_original_str).replace(",", ""))) if price_original_str else None
    except:
        price_original = None
    try:
        price_discounted = int(float(str(sale_price_str).replace(",", ""))) if sale_price_str else None
    except:
        price_discounted = None
    if price_discounted is None:
        price_discounted = price_original

    # ── 브랜드 ──
    brand_info = ld.get("brand", {})
    brand = brand_info.get("name") if isinstance(brand_info, dict) else None

    # ── 판매자 ──
    seller_info = offers.get("seller", {})
    seller = seller_info.get("name") if isinstance(seller_info, dict) else None

    # ── 평점·리뷰 ──
    agg = ld.get("aggregateRating", {})
    rating = float(agg["ratingValue"]) if agg.get("ratingValue") else None
    review_count = int(agg["reviewCount"]) if agg.get("reviewCount") else None

    # ── 이미지 ──
    images = []
    ld_img = ld.get("image")
    if ld_img:
        if isinstance(ld_img, list):
            images.extend(ld_img)
        else:
            images.append(ld_img)
    og_img = soup.find("meta", property="og:image")
    if og_img and og_img.get("content"):
        img_url = og_img["content"]
        if img_url.startswith("//"):
            img_url = "https:" + img_url
        if img_url not in images:
            images.append(img_url)
    # HTML에서 lotteimall 이미지 URL 패턴 수집
    for m in re.finditer(r'(https://image\d*\.lotteimall\.com/goods/[^\s"\'<>]+\.jpg)', html):
        src = m.group(1)
        if src not in images:
            images.append(src)
    images = list(dict.fromkeys(images))[:10]

    # ── 배송비 ──
    shipping_detail = offers.get("shippingDetails", {})
    shipping_rate = shipping_detail.get("shippingRate", {}) if isinstance(shipping_detail, dict) else {}
    ship_value = shipping_rate.get("value") if isinstance(shipping_rate, dict) else None
    if ship_value is not None:
        shipping_fee = int(float(str(ship_value)))
        shipping_fee_text = "무료배송" if shipping_fee == 0 else f"{shipping_fee:,}원"
    else:
        shipping_fee, shipping_fee_text = _extract_shipping(soup)

    # ── 배송 예정일 ──
    delivery_date = _extract_delivery_date(soup)

    # ── 재고 ──
    avail = offers.get("availability", "")
    if "InStock" in avail:
        availability = "in_stock"
    elif "OutOfStock" in avail:
        availability = "out_of_stock"
    else:
        availability = "unknown"

    # ── 옵션 ──
    options = _extract_options(soup)

    # ── 스펙 ──
    specifications = {}
    for row in soup.select("table tr"):
        th = row.select_one("th")
        td = row.select_one("td")
        if th and td:
            key = th.get_text(strip=True)
            val = td.get_text(strip=True)
            if key and val and len(key) < 40:
                specifications[key] = val

    # ── 사이즈 추출 ──
    size = requests.post("http://localhost:18080/extract/size", json={
        "title": title,
        "category": ld.get("category", ""),
        "specs": specifications,
        "text": soup.get_text(" ", strip=True)[:5000],
        "images": images,
        "allow_ocr": False,
    }, timeout=30).json()

    if size.get("girth_sum_cm") is None and size.get("confidence") in ("LOW",) and images:
        size = requests.post("http://localhost:18080/extract/size", json={
            "title": title, "category": "", "specs": specifications,
            "text": "", "images": images, "allow_ocr": True,
        }, timeout=40).json()

    return {
        "title": title,
        "price_original": price_original,
        "price_discounted": price_discounted,
        "brand": brand,
        "seller": seller,
        "rating": rating,
        "review_count": review_count,
        "options": options,
        "images": images,
        "availability": availability,
        "shipping_fee": shipping_fee,
        "shipping_fee_text": shipping_fee_text,
        "delivery_date": delivery_date,
        "specifications": specifications,
        "size": size,
    }


if __name__ == "__main__":
    import sys as _sys, json as _json
    _url = _sys.argv[1] if len(_sys.argv) > 1 else ""
    _result = scrape(_url)
    print(_json.dumps(_result, ensure_ascii=False))
