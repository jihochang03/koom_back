# Template: m.a-bly.com (detail)
# Generated: 2026-06-28T04:50:20.410Z
# Notes: 에이블리 모바일 상품 상세 페이지. chrome 모드 필수(SPA). network_log의 /api/v3/goods/{id}/basic, /discounts, /options/?depth=1, /options/brief, /review_summary, /information API를 파싱. 이미지: cover_images(API) + product_info 선추출 + swiper HTML fallback. 배지/딜리버리 이미지는 base64 경로 디코딩으로 필터링, 썸네일 프리셋은 GOODS_DETAIL로 교체. 옵션 depth=1(컬러)은 network_log, depth=2(사이즈)는 HTML 버튼 fallback. 배송비 무료배송. 평점은 positive_percent/20 환산. 카테고리 자동 추출로 size API 정확도 개선.

# Template: m.a-bly.com (detail)
# Generated: 2026-06-28T04:30:00.000Z
# Notes: 에이블리 모바일 상품 상세 페이지. chrome 모드 필수(SPA).
# network_log: /api/v3/goods/{id}/basic, /discounts, /options/?depth=1, /options/brief,
#              /review_summary, /information API 파싱.
# 이미지: cover_images(API) + product_info 선추출 + swiper HTML fallback.
# 배지·딜리버리 이미지 base64 경로 디코딩 필터, 썸네일→GOODS_DETAIL 고해상도 교체.
# 옵션 depth=1(컬러)=network_log, depth=2(사이즈)=HTML버튼 fallback.
# 배송비 무료배송. 평점=positive_percent/20 환산. 카테고리 자동 추출.

import requests
import json
import re
import base64
from bs4 import BeautifulSoup

def _pick_api(net_log, keywords):
    if isinstance(keywords, str):
        keywords = [keywords]
    for e in net_log or []:
        u = (e.get("url") or "")
        if all(k in u for k in keywords):
            body = e.get("body") or ""
            try:
                return json.loads(body)
            except Exception:
                continue
    return None

def _is_product_image(url):
    """배지·딜리버리아이콘·리뷰 이미지 제외, 상품 이미지만 통과"""
    if not url:
        return False
    # base64 path segment 디코딩하여 내부 s3 경로 확인
    path_seg = url.split("/")[-1]
    try:
        padding = 4 - len(path_seg) % 4
        padded = path_seg + "=" * (padding % 4)
        decoded = base64.b64decode(padded).decode("utf-8", errors="replace")
        if re.search(r'/badge/|/delivery-type/|/data/goods/badge|/data/goods/delivery', decoded):
            return False
    except Exception:
        pass
    # 리뷰 이미지 제외
    if "REVIEW_THUMB" in url or "/review/" in url:
        return False
    return True

def _normalize_image(url):
    """썸네일 프리셋을 고해상도 GOODS_DETAIL로 교체, 배지 이미지 제외"""
    if not url:
        return None
    if url.startswith("//"):
        url = "https:" + url
    if not _is_product_image(url):
        return None
    url = re.sub(r'/pr:NEW_GOODS_THUMB_WEBP/', '/pr:GOODS_DETAIL/', url)
    url = re.sub(r'/pr:NEW_GOODS_THUMB/', '/pr:GOODS_DETAIL/', url)
    url = re.sub(r'/pr:CONVERT_TO_WEBP/', '/pr:GOODS_DETAIL/', url)
    return url

def scrape(url):
    m = re.search(r'/goods/(\d+)', url)
    goods_id = m.group(1) if m else None

    data = requests.post("http://localhost:18080/collect/general", json={"url": url}, timeout=90).json()
    html = data.get("html", "")
    net_log = data.get("network_log", [])
    soup = BeautifulSoup(html, "html.parser")

    # === 기본 상품 정보 (v3 API) ===
    basic = _pick_api(net_log, [f"goods/{goods_id}/basic"])
    goods = basic.get("goods", {}) if basic else {}

    title = goods.get("name", "")
    if not title:
        og = soup.find("meta", property="og:title")
        title = og["content"].strip() if og and og.get("content") else ""

    market = goods.get("market") or {}
    brand = market.get("name", "") if isinstance(market, dict) else ""
    seller = brand

    # === 가격 ===
    discount_data = _pick_api(net_log, [f"goods/{goods_id}/discounts"])
    price_original = None
    price_discounted = None
    if discount_data:
        price_original = discount_data.get("display_consumer")
        price_discounted = discount_data.get("sale_price")
        if price_original == price_discounted:
            price_discounted = None
    if not price_original:
        price_info = goods.get("price_info") or {}
        price_original = price_info.get("consumer") or goods.get("consumer_price") or goods.get("price")
        thumbnail_price = price_info.get("thumbnail_price")
        if thumbnail_price and thumbnail_price != price_original:
            price_discounted = thumbnail_price

    # === 이미지 — 여러 장 수집 (배지·리뷰 제외, 프리셋 고해상도 보정) ===
    images = []
    seen = set()

    def _add_img(u):
        u2 = _normalize_image(u)
        if u2 and u2 not in seen:
            seen.add(u2)
            images.append(u2)

    # 1) cover_images (API)
    for img in goods.get("cover_images", []):
        _add_img(img)

    # 2) product_info 선추출 이미지 (수집 서버 HTML파서가 찾은 swiper 등)
    pi = data.get("product_info") or {}
    for img_url in (pi.get("images") or []):
        _add_img(img_url)

    # 3) HTML swiper-slide img (fallback)
    if len(images) < 3:
        for img_tag in soup.select(".swiper-slide img[src], .swiper-slide img[data-src]"):
            src = img_tag.get("src") or img_tag.get("data-src", "")
            if src and "cloudfront" in src:
                _add_img(src)

    # 4) og:image fallback
    if not images:
        og_img = soup.find("meta", property="og:image")
        if og_img and og_img.get("content"):
            _add_img(og_img["content"])

    images = images[:10]

    # === 옵션 (network_log depth=1, depth=2는 HTML 버튼) ===
    options = []
    opt1_data = _pick_api(net_log, [f"goods/{goods_id}/options/", "depth=1"])
    if opt1_data:
        name1 = opt1_data.get("name") or "컬러"
        components1 = opt1_data.get("option_components", [])
        values1 = [c["name"] for c in components1 if c.get("name")]
        if values1:
            options.append({"name": name1, "values": values1})
        # depth=2(사이즈): is_final_depth=False이면 HTML 버튼에서 추출
        if components1 and not components1[0].get("is_final_depth", True):
            size_vals = []
            for btn in soup.select("[class*='SizeChip'], [class*='sizeChip'], [class*='size_chip']"):
                t = btn.get_text(strip=True)
                if t and t not in size_vals:
                    size_vals.append(t)
            if size_vals:
                options.append({"name": "사이즈", "values": size_vals})

    # option_names fallback (brief API)
    if not options:
        brief_data_tmp = _pick_api(net_log, [f"goods/{goods_id}/options/brief"])
        if brief_data_tmp:
            for oname in (brief_data_tmp.get("option_names") or []):
                options.append({"name": oname, "values": []})

    # === 배송 ===
    shipping_fee = 0
    shipping_fee_text = "무료배송"

    # === 리뷰/평점 ===
    review_data = _pick_api(net_log, [f"goods/{goods_id}/review_summary"])
    rating = None
    review_count = 0
    if review_data:
        rv = review_data.get("review") or {}
        review_count = int(rv.get("count") or 0)
        pos_pct = float(rv.get("positive_percent") or 0)
        if pos_pct and review_count > 0:
            rating = round(pos_pct / 20, 1)
    # fallback: positive_review_rate in goods (basic API)
    if rating is None and goods.get("positive_review_rate"):
        pos_pct = float(goods["positive_review_rate"])
        rating = round(pos_pct / 20, 1)
    # fallback: webview reviews summary
    if review_count == 0:
        webview_rv = _pick_api(net_log, ["reviews/summary"])
        if webview_rv:
            review_count = int(webview_rv.get("count") or 0)

    # === 배송 도착일 ===
    delivery_date = None
    brief_data = _pick_api(net_log, [f"goods/{goods_id}/options/brief"])
    if brief_data:
        deadline = brief_data.get("today_delivery_order_deadline_time")
        if deadline:
            hm = str(deadline)[:5]
            delivery_date = f"오늘 {hm}까지 주문 시 오늘 출발"
    # fallback: market 정보
    if not delivery_date and isinstance(market, dict):
        mkt_deadline = market.get("today_delivery_order_deadline_time")
        if mkt_deadline:
            delivery_date = f"오늘 {str(mkt_deadline)[:5]}까지 주문 시 오늘 출발"

    # === 스펙(필수표기정보) ===
    specifications = {}
    info_data = _pick_api(net_log, [f"goods/{goods_id}/information"])
    if info_data:
        pipn = info_data.get("pipn") or {}
        pipn_data = pipn.get("pipn_data") or {}
        for key, val in pipn_data.items():
            if isinstance(val, dict):
                t = val.get("title", key)
                v = val.get("value", "")
                if v and "참조" not in v:
                    specifications[t] = v

    # === 카테고리 추출 (size 추출 정확도 개선) ===
    category = ""
    std_cat = goods.get("standard_category") or {}
    if isinstance(std_cat, dict):
        category = std_cat.get("name", "")
    if not category:
        disp_cats = goods.get("display_categories") or []
        if disp_cats:
            category = disp_cats[0].get("name", "")

    # === 가용성 ===
    sale_type = goods.get("sale_type", "")
    availability = "in_stock" if sale_type == "ON_SALE" else \
                   ("out_of_stock" if sale_type in ("SOLD_OUT", "SUSPENDED") else "unknown")

    # === 사이즈 추출 ===
    size = requests.post("http://localhost:18080/extract/size", json={
        "title": title,
        "category": category or "의류",
        "specs": specifications,
        "text": soup.get_text(" ", strip=True)[:5000],
        "images": images,
        "allow_ocr": False,
    }, timeout=30).json()

    return {
        "title": title,
        "brand": brand,
        "seller": seller,
        "price_original": price_original,
        "price_discounted": price_discounted,
        "shipping_fee": shipping_fee,
        "shipping_fee_text": shipping_fee_text,
        "delivery_date": delivery_date,
        "options": options,
        "images": images,
        "availability": availability,
        "rating": rating,
        "review_count": review_count,
        "specifications": specifications,
        "size": size,
    }


if __name__ == "__main__":
    import sys as _sys, json as _json
    _url = _sys.argv[1] if len(_sys.argv) > 1 else ""
    _result = scrape(_url)
    print(_json.dumps(_result, ensure_ascii=False))
