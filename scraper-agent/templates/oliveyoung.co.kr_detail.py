# Template: oliveyoung.co.kr (detail)
# Generated: 2026-06-26T06:03:24.963Z
# Notes: 올리브영 상품 상세 페이지. simple 403 차단 → chrome 모드 필수. Next.js SSR 앱 (CSS Module 클래스명 빌드마다 변동 → 부분 일치 [class*='...'] 사용). 가격/옵션은 __next_f script JSON에서 추출. 이미지는 swiper-slide img alt 속성에 원본 URL 포함(쿼리스트링 제거). 평점/리뷰는 HTML에 직접 노출. 배송비·배송기간은 data-qa-name='text-product-normal-delivery-info' 내 DeliveryInfo_text 클래스 파싱.

import requests
import re
import json
from bs4 import BeautifulSoup


def scrape(url: str) -> dict:
    # chrome 모드로 수집 (oliveyoung은 simple 403 차단)
    data = requests.post("http://localhost:18080/collect/general", json={"url": url}, timeout=90).json()
    html = data.get("html", "")
    net_log = data.get("network_log", [])
    soup = BeautifulSoup(html, "html.parser")
    product_info = data.get("product_info", {})

    # ── 제목 ──
    title_tag = soup.select_one("h3.GoodsDetailInfo_title__Vl_IP")
    if not title_tag:
        # CSS Module 클래스명은 빌드마다 변동 → 부분 일치로 탐색
        title_tag = soup.find(
            "h3",
            class_=lambda c: c and "GoodsDetailInfo_title" in (c if isinstance(c, str) else " ".join(c))
        )
    title = title_tag.get_text(strip=True) if title_tag else None
    # og:title fallback (| 올리브영 제거)
    if not title:
        og = soup.find("meta", property="og:title")
        if og:
            title = re.sub(r"\s*\|\s*올리브영\s*$", "", og.get("content", "")).strip()

    # ── 가격 (Next.js __next_f script JSON에서 추출) ──
    price_original = None
    price_discounted = None
    for script in soup.find_all("script"):
        text = script.string or ""
        if "salePrice" not in text:
            continue
        m = re.search(r'"salePrice":(\d+)', text)
        if m:
            price_original = int(m.group(1))
        m2 = re.search(r'"finalPrice":(\d+)', text)
        if m2:
            price_discounted = int(m2.group(1))
        if price_original and price_discounted:
            break
    # HTML fallback
    if not price_original:
        price_el = soup.select_one("[data-qa-name='text-product-discount-price'] span")
        if price_el:
            m = re.search(r"[\d,]+", price_el.get_text(strip=True))
            if m:
                price_original = int(m.group(0).replace(",", ""))
                price_discounted = price_original

    # ── 이미지 (swiper-slide img alt에 원본 URL, 쿼리스트링 제거) ──
    images = []
    seen = set()
    for img in soup.select(".GoodsDetailCarousel_visual-container__1kSZN .swiper-slide img"):
        alt_url = img.get("alt", "")
        if alt_url and alt_url.startswith("https://image.oliveyoung"):
            clean_url = alt_url.split("?")[0]
            if clean_url not in seen:
                seen.add(clean_url)
                images.append(clean_url)
    # Next.js data thumbnailImage fallback
    if not images:
        for script in soup.find_all("script"):
            text = script.string or ""
            if "thumbnailImage" not in text:
                continue
            m = re.search(r'"thumbnailImage":\[(.*?)\]', text, re.DOTALL)
            if m:
                try:
                    items = json.loads("[" + m.group(1) + "]")
                    for item in items:
                        base_url = item.get("url", "")
                        path = item.get("path", "")
                        if base_url and path:
                            full = re.sub(r"(?<!:)//+", "/", f"{base_url}/{path}").split("?")[0]
                            if full not in seen:
                                seen.add(full)
                                images.append(full)
                except Exception:
                    pass
            break
    # og:image fallback
    if not images:
        og_img = soup.find("meta", property="og:image")
        if og_img:
            images.append(og_img.get("content", "").split("?")[0])

    # ── 브랜드 ──
    brand = None
    brand_btn = soup.select_one("[class*='TopUtils_btn-brand']")
    if brand_btn:
        brand = brand_btn.get_text(strip=True)
    if not brand:
        eg_brand = soup.find("meta", {"property": "eg:brandName"})
        if eg_brand:
            brand = eg_brand.get("content", "")

    # ── 평점 & 리뷰수 ──
    rating = None
    review_count = None
    rating_el = soup.select_one("[class*='ReviewArea_rating-star'] .rating")
    if rating_el:
        m = re.search(r"([\d.]+)", rating_el.get_text(strip=True))
        if m:
            rating = float(m.group(1))
    review_el = soup.select_one("[class*='ReviewArea_review-count'] span")
    if review_el:
        m = re.search(r"[\d,]+", review_el.get_text(strip=True))
        if m:
            review_count = int(m.group(0).replace(",", ""))

    # ── 배송비 & 배송 기간 ──
    shipping_fee = None
    shipping_fee_text = None
    delivery_date = None

    delivery_item = soup.select_one("[data-qa-name='text-product-normal-delivery-info']")
    if delivery_item:
        texts = [
            el.get_text(strip=True)
            for el in delivery_item.select("[class*='DeliveryInfo_text']")
        ]
        for t in texts:
            # 배송비 패턴: "2,500원 ..." 또는 "무료배송"
            if "원" in t and shipping_fee is None:
                m = re.search(r"^([\d,]+)원", t)
                if m:
                    shipping_fee = int(m.group(1).replace(",", ""))
                    shipping_fee_text = t
                elif "무료" in t:
                    shipping_fee = 0
                    shipping_fee_text = t
            # 배송 기간: "평균 3일 이내 도착", "오늘출발" 등
            if ("도착" in t or "이내" in t or "출발" in t) and delivery_date is None:
                delivery_date = t

    # 선추출 product_info fallback
    if not delivery_date:
        delivery_date = product_info.get("shipping_period")
    if shipping_fee is None:
        sf = product_info.get("shipping_fee")
        if sf is not None:
            shipping_fee = sf
            shipping_fee_text = "무료배송" if sf == 0 else f"{sf:,}원"

    # ── 재고 여부 ──
    availability = "in_stock"
    for script in soup.find_all("script"):
        text = script.string or ""
        if '"soldOutFlag":true' in text:
            availability = "out_of_stock"
            break

    # ── 옵션 (단일 상품은 [], 다중 옵션은 combinationTypeInfo에서 파싱) ──
    options = []
    for script in soup.find_all("script"):
        text = script.string or ""
        if '"combinationOptionFlag":true' not in text:
            continue
        m = re.search(r'"combinationTypeInfo":\[(.*?)\]', text, re.DOTALL)
        if m:
            try:
                combo = json.loads("[" + m.group(1) + "]")
                for c in combo:
                    opt_name = c.get("combinationTypeName", "옵션")
                    opt_values = [v.get("combinationName", "") for v in c.get("combinationList", [])]
                    if opt_values:
                        options.append({"name": opt_name, "values": opt_values})
            except Exception:
                pass
        break

    # ── 판매자 (자체 몰이면 null) ──
    seller = None
    for script in soup.find_all("script"):
        text = script.string or ""
        m = re.search(r'"supplierName":"([^"]+)"', text)
        if m:
            seller = m.group(1)
            break

    # ── specifications (용량·카테고리) ──
    specifications = {}
    weight = product_info.get("product_weight")
    if weight:
        specifications["용량"] = weight
    breadcrumbs = soup.select("[class*='Breadcrumb_breadcrumb-inner'] a")
    if breadcrumbs:
        specifications["카테고리"] = " > ".join(b.get_text(strip=True) for b in breadcrumbs)

    return {
        "title": title,
        "price_original": price_original,
        "price_discounted": price_discounted if price_discounted and price_discounted != price_original else None,
        "options": options,
        "images": images[:10],
        "availability": availability,
        "seller": seller,
        "shipping_fee": shipping_fee,
        "shipping_fee_text": shipping_fee_text,
        "delivery_date": delivery_date,
        "brand": brand,
        "rating": rating,
        "review_count": review_count,
        "specifications": specifications,
    }


if __name__ == "__main__":
    import sys as _sys, json as _json
    _url = _sys.argv[1] if len(_sys.argv) > 1 else ""
    _result = scrape(_url)
    print(_json.dumps(_result, ensure_ascii=False))
