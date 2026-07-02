# Template: thirtymall.com (detail)
# Generated: 2026-06-28T03:19:54.724Z
# Notes: thirtymall.com 상세 페이지. NHN Commerce 기반 쇼핑몰. chrome 모드 필요. shop-api.e-ncp.com API로 상품정보/옵션/리뷰 수집. 가격 구조: salePrice=정가(원가), immediateDiscountAmt=즉시할인액, 실제현재가=salePrice-immediateDiscountAmt. 단일/다단계 연계 옵션 처리. dutyInfo JSON→specifications 파싱. content 안 상세이미지 추출. reviewRate/counter.reviewCnt에서 평점/리뷰수 직접 추출.

# Template: thirtymall.com (detail)
# Generated: 2026-06-28T03:14:19.976Z (업그레이드)
# Notes: thirtymall.com 상세 페이지. NHN Commerce 기반 쇼핑몰. chrome 모드 필요. shop-api.e-ncp.com API로 상품정보/옵션/리뷰 수집. 가격 구조: salePrice=정가(원가), immediateDiscountAmt=즉시할인액, 실제현재가=salePrice-immediateDiscountAmt. 단일/다단계 연계 옵션 처리. dutyInfo JSON→specifications 파싱. content 안 상세이미지 추출. reviewRate/counter.reviewCnt에서 평점/리뷰수 직접 추출.

import requests
import json
import re
from bs4 import BeautifulSoup

def _pick_api(net_log, *keywords):
    """network_log에서 keyword가 포함된 첫 JSON 응답을 dict로 반환."""
    for e in net_log or []:
        u = e.get("url") or ""
        if any(k in u for k in keywords):
            body = e.get("body") or ""
            try:
                return json.loads(body)
            except Exception:
                continue
    return None

def _extract_shipping(soup):
    text = soup.get_text(" ", strip=True)
    area_m = re.search(r"배송비.{0,300}", text, re.DOTALL) or re.search(r"배송.{0,300}", text, re.DOTALL)
    area = area_m.group(0) if area_m else text
    if re.search(r"무료\s*배송|배송\s*무료", area):
        return 0, "무료배송"
    combined = re.search(r"([\d,]+)\s*원.{0,50}([\d,]+\s*만?\s*원\s*이상[^)]*무료[^)]*)", area)
    if combined:
        fee = int(combined.group(1).replace(",", ""))
        return fee, combined.group(0).strip()
    m = re.search(r"([\d,]+)\s*원", area)
    if m:
        fee = int(m.group(1).replace(",", ""))
        return fee, f"{m.group(1)}원"
    return None, None

def _parse_duty_info(duty_info_str):
    """dutyInfo JSON 문자열을 dict(specifications)로 변환."""
    if not duty_info_str:
        return {}
    try:
        duty = json.loads(duty_info_str)
    except Exception:
        return {}
    specs = {}
    category_name = duty.get("categoryName", "")
    if category_name:
        specs["품목분류"] = category_name
    for item in duty.get("contents", []):
        if isinstance(item, dict):
            for k, v in item.items():
                if k and v and v != "상품상세 참조":
                    specs[k] = v
    return specs

def scrape(url: str) -> dict:
    # chrome 모드로 수집 (Next.js SPA)
    data = requests.post("http://localhost:18080/collect/general", json={"url": url}, timeout=90).json()
    html = data.get("html", "")
    net_log = data.get("network_log", [])
    soup = BeautifulSoup(html, "html.parser")

    # 상품 ID 추출
    m = re.search(r"id=(\d+)", url)
    product_no = m.group(1) if m else None

    # 1. 상품 기본 정보 API (shop-api.e-ncp.com/products/{no}?preview)
    product_api = _pick_api(net_log, f"/products/{product_no}?preview")
    title = None
    price_original = None
    price_discounted = None
    brand = None
    seller = None
    ship_fee = None
    ship_text = None
    availability = "unknown"

    if product_api:
        base = product_api.get("baseInfo", {})
        title = base.get("productName")

        # 가격 구조:
        #   salePrice        = 정가(원가)
        #   immediateDiscountAmt = 즉시할인액(WON 단위)
        #   additionDiscountAmt  = 추가할인액
        #   실제 판매가 = salePrice - immediateDiscountAmt - additionDiscountAmt
        price_info = product_api.get("price", {}) or {}
        sale_price   = float(price_info.get("salePrice", 0) or 0)
        imm_discount = float(price_info.get("immediateDiscountAmt", 0) or 0)
        add_discount = float(price_info.get("additionDiscountAmt", 0) or 0)

        price_original  = int(sale_price)
        actual_price    = int(sale_price - imm_discount - add_discount)
        price_discounted = actual_price if actual_price != price_original else None

        # 브랜드
        brand_info = product_api.get("brand", {}) or {}
        brand = brand_info.get("brandName") or brand_info.get("name") or None

        # 판매자
        seller_info = product_api.get("partner", {}) or product_api.get("supplier", {}) or {}
        seller = seller_info.get("partnerName") or seller_info.get("name")

        # 재고/판매 가능 여부
        status = product_api.get("status", {}) or {}
        sold_out = status.get("soldout", False)
        sale_status = status.get("saleStatusType", "ONSALE")
        if sold_out or sale_status not in ("ONSALE", "AVAILABLE"):
            availability = "out_of_stock"
        else:
            avail_yn = base.get("frontDisplayYn", "Y")
            availability = "in_stock" if avail_yn != "N" else "out_of_stock"

        # 배송비 (deliveryFee 직접 구조)
        delivery_fee_info = product_api.get("deliveryFee", {}) or {}
        cond_type = delivery_fee_info.get("deliveryConditionType", "")
        ship_fee2 = delivery_fee_info.get("deliveryAmt")
        if ship_fee2 is not None:
            ship_fee = int(float(ship_fee2))
            default_label = delivery_fee_info.get("defaultDeliveryConditionLabel", "")
            if cond_type == "FREE" or ship_fee == 0:
                ship_fee = 0
                ship_text = default_label or "무료배송"
            else:
                above_amt = delivery_fee_info.get("aboveDeliveryAmt", 0)
                if above_amt:
                    ship_text = f"{ship_fee:,}원 ({int(above_amt):,}원 이상 무료배송)"
                else:
                    ship_text = default_label or f"{ship_fee:,}원"

        # defaultDelivery fallback
        if ship_fee is None:
            def_info = product_api.get("defaultDelivery", {}) or {}
            ship_fee2 = def_info.get("deliveryAmt") or def_info.get("deliveryFee")
            if ship_fee2 is not None:
                ship_fee = int(ship_fee2)
                ship_text = "무료배송" if ship_fee == 0 else f"{ship_fee:,}원"
    else:
        # fallback: HTML h1
        h1 = soup.select_one("h1")
        title = h1.get_text(strip=True) if h1 else None

    # 배송비 guest/recent-products API fallback
    if ship_fee is None:
        recent_api = _pick_api(net_log, "guest/recent-products")
        if recent_api:
            item = recent_api[0] if isinstance(recent_api, list) else recent_api
            delivery_cond = item.get("deliveryConditionInfo", {}) or {}
            summary = delivery_cond.get("summary", "")
            if "무료" in summary:
                ship_fee = 0
                ship_text = "무료배송"

    # 배송비 HTML fallback
    if ship_fee is None:
        ship_fee, ship_text = _extract_shipping(soup)

    # 2. 옵션 API (단일/다단계)
    options = []
    option_api = _pick_api(net_log, f"/products/{product_no}/options")
    if option_api:
        labels = option_api.get("labels", [])
        multi = option_api.get("multiLevelOptions", [])
        select_type = option_api.get("selectType", "MULTI")

        if multi and labels:
            if select_type == "MULTI" and len(labels) == 1:
                # 단일 선택 옵션 (1단계)
                vals = [o.get("value") for o in multi if o.get("value")]
                if vals:
                    options.append({"name": labels[0], "values": vals})
            else:
                # 다단계 연계 옵션
                brand_vals = [o.get("value") for o in multi if o.get("value")]
                color_vals = list(dict.fromkeys(
                    c.get("value") for o in multi for c in (o.get("children") or []) if c.get("value")
                ))
                size_vals = list(dict.fromkeys(
                    s.get("value") for o in multi
                    for c in (o.get("children") or [])
                    for s in (c.get("children") or []) if s.get("value")
                ))
                if brand_vals:
                    options.append({"name": labels[0] if len(labels) > 0 else "옵션1", "values": brand_vals})
                if color_vals:
                    options.append({"name": labels[1] if len(labels) > 1 else "옵션2", "values": color_vals})
                if size_vals:
                    options.append({"name": labels[2] if len(labels) > 2 else "옵션3", "values": size_vals})

    # 3. 이미지 수집 (API imageUrls + content 안 상세이미지 + HTML CDN 이미지)
    images = []

    if product_api:
        base = product_api.get("baseInfo", {})

        # 3-1. 메인 이미지 (imageUrls / imageUrlInfo)
        for img in (base.get("imageUrls", []) or []):
            src = img if isinstance(img, str) else (img.get("url") or "")
            if src:
                if src.startswith("//"):
                    src = "https:" + src
                src = re.sub(r"\?\d+x\d+$", "", src)
                if src not in images:
                    images.append(src)

        # imageUrlInfo 추가
        for img_info in (base.get("imageUrlInfo", []) or []):
            src = img_info.get("url", "") if isinstance(img_info, dict) else ""
            if src:
                if src.startswith("//"):
                    src = "https:" + src
                src = re.sub(r"\?\d+x\d+$", "", src)
                if src not in images:
                    images.append(src)

        # 3-2. content(상세설명) 안 이미지 추출
        content_html = base.get("content", "")
        if content_html:
            content_soup = BeautifulSoup(content_html, "html.parser")
            for img_tag in content_soup.find_all("img"):
                src = img_tag.get("src") or img_tag.get("data-src") or ""
                if src:
                    if src.startswith("//"):
                        src = "https:" + src
                    src = re.sub(r"\?\d+x\d+$", "", src)
                    if src not in images:
                        images.append(src)

    # 3-3. HTML 내 CDN 이미지 보완
    for img_tag in soup.select("img"):
        src = img_tag.get("src") or img_tag.get("data-src") or ""
        if src and "cdn-nhncommerce.com" in src:
            if src.startswith("//"):
                src = "https:" + src
            src = re.sub(r"\?\d+x\d+$", "", src)
            if src not in images:
                images.append(src)

    # 포토리뷰 이미지 제외 (REVIEW 경로)
    images = [img for img in images if "/REVIEW/" not in img]
    images = list(dict.fromkeys(images))[:10]

    # 4. 리뷰/평점 API
    rating = None
    review_count = None
    # API reviewRate / counter.reviewCnt 직접 사용 (빠른 접근)
    if product_api:
        rate_val = product_api.get("reviewRate")
        if rate_val is not None:
            rating = float(rate_val)
        cnt_val = (product_api.get("counter") or {}).get("reviewCnt")
        if cnt_val is not None:
            review_count = int(cnt_val)
    # 리뷰 전용 API fallback
    if rating is None or review_count is None:
        review_api = _pick_api(net_log, f"/products/{product_no}/product-reviews")
        if review_api:
            if rating is None:
                rate_val = review_api.get("rate")
                rating = float(rate_val) if rate_val is not None else None
            if review_count is None:
                cnt_val = review_api.get("totalCount")
                review_count = int(cnt_val) if cnt_val is not None else None

    # 5. 배송 예정일 (API deliveryDate 필드, 없으면 None)
    delivery_date = None
    if product_api:
        delivery_date = product_api.get("deliveryDate")  # 최상위 deliveryDate
        if not delivery_date:
            ship_info = product_api.get("shippingInfo", {}) or {}
            delivery_date = ship_info.get("deliveryPeriodText") or ship_info.get("deliveryPeriod")
        if not delivery_date:
            delivery_guide = product_api.get("deliveryGuide") or ""
            if delivery_guide:
                delivery_date = BeautifulSoup(delivery_guide, "html.parser").get_text(strip=True) or None

    # 6. 스펙/필수표기정보 (productAttribute + dutyInfo JSON 파싱)
    specifications = {}
    if product_api:
        base = product_api.get("baseInfo", {})

        # 6-1. productAttribute / attributes
        for spec in (product_api.get("productAttribute", []) or product_api.get("attributes", []) or []):
            k = spec.get("name") or spec.get("attributeName")
            v = spec.get("value") or spec.get("attributeValue")
            if k and v:
                specifications[k] = v

        # 6-2. dutyInfo JSON 문자열 파싱 (필수표기정보)
        duty_info_str = base.get("dutyInfo", "")
        if duty_info_str:
            duty_specs = _parse_duty_info(duty_info_str)
            for k, v in duty_specs.items():
                if k not in specifications:
                    specifications[k] = v

        # 6-3. 카테고리 정보 추가
        categories = product_api.get("categories", [])
        if categories:
            full_label = categories[0].get("fullCategoryLabel", "")
            if full_label:
                specifications["카테고리"] = full_label

    # 7. size 추출
    size = requests.post("http://localhost:18080/extract/size", json={
        "title": title or "",
        "category": specifications.get("카테고리", ""),
        "specs": specifications,
        "text": soup.get_text(" ", strip=True)[:5000],
        "images": images,
        "allow_ocr": False,
    }, timeout=30).json()

    return {
        "title": title,
        "price_original": price_original,
        "price_discounted": price_discounted,
        "options": options,
        "images": images,
        "availability": availability,
        "seller": seller,
        "brand": brand,
        "rating": rating,
        "review_count": review_count,
        "shipping_fee": ship_fee,
        "shipping_fee_text": ship_text,
        "delivery_date": delivery_date,
        "specifications": specifications,
        "size": size,
    }


if __name__ == "__main__":
    import sys as _sys, json as _json
    _url = _sys.argv[1] if len(_sys.argv) > 1 else ""
    _result = scrape(_url)
    print(_json.dumps(_result, ensure_ascii=False))
