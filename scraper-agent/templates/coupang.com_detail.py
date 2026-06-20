# Template: coupang.com (detail)
# Generated: 2026-06-08T01:51:27.275Z
# Notes: 쿠팡 상품 상세 페이지 스크레이퍼. 상품명/브랜드/가격/할인율/옵션/별점/리뷰수/배송정보/원산지/판매자/필수표기정보/이미지 추출. Tailwind CSS 클래스 기반 SDP(상품 상세 페이지). 옵션 가격은 .option-table-list__option 에서 추출.

import requests
from bs4 import BeautifulSoup
import json
import re


def scrape(url: str) -> dict:
    # 로컬 수집 서버를 통해 페이지 수집
    resp = requests.post(
        "http://localhost:18080/collect/general",
        json={"url": url},
        timeout=30
    )
    data = resp.json()
    html = data.get("html", "")
    soup = BeautifulSoup(html, "html.parser")

    # ── 제목 ──────────────────────────────────────────────
    title = ""
    title_tag = soup.select_one("h1.product-title span")
    if title_tag:
        title = title_tag.get_text(strip=True)
    if not title:
        og_title = soup.select_one('meta[property="og:title"]')
        if og_title:
            title = og_title.get("content", "").replace(" | 쿠팡", "").strip()

    # ── 설명 (meta) ───────────────────────────────────────
    description = ""
    meta_desc = soup.select_one('meta[name="description"]')
    if meta_desc:
        description = meta_desc.get("content", "")

    # ── 브랜드 ────────────────────────────────────────────
    brand = ""
    brand_tag = soup.select_one(".brand-info .twc-font-bold")
    if brand_tag:
        brand = brand_tag.get_text(strip=True)

    # ── 카테고리 (빵크럼) ──────────────────────────────────
    categories = []
    breadcrumb_items = soup.select("ul.breadcrumb li a")
    for item in breadcrumb_items:
        txt = item.get_text(strip=True)
        if txt and txt != "쿠팡 홈":
            categories.append(txt)

    # ── 상품 ID ───────────────────────────────────────────
    product_id = ""
    m = re.search(r'/products/(\d+)', url)
    if m:
        product_id = m.group(1)

    # ── 가격 정보 ─────────────────────────────────────────
    sale_price = None
    original_price = None
    discount_rate = None
    currency = "KRW"

    # 할인율
    discount_tag = soup.select_one(".price-container .twc-text-\\[14px\\]")
    if not discount_tag:
        for tag in soup.select("[class*='twc-text']"):
            txt = tag.get_text(strip=True)
            if txt.endswith('%') and len(txt) <= 4:
                try:
                    discount_rate = int(txt.replace('%', ''))
                    break
                except:
                    pass

    # 판매가
    price_tag = soup.select_one(".price-container .twc-text-\\[22px\\]")
    if price_tag:
        price_txt = price_tag.get_text(strip=True).replace(',', '').replace('원', '')
        try:
            sale_price = int(price_txt)
        except:
            pass

    # 원가
    orig_tag = soup.select_one(".price-container .twc-line-through")
    if orig_tag:
        orig_txt = orig_tag.get_text(strip=True).replace(',', '').replace('원', '')
        try:
            original_price = int(orig_txt)
        except:
            pass

    # HTML 선추출 데이터에서 가격 보완
    for script in soup.find_all("script"):
        script_text = script.string or ""
        if '"discounted_price"' in script_text or '"salePrice"' in script_text:
            try:
                json_match = re.search(r'\{.*?"discounted_price".*?\}', script_text, re.DOTALL)
                if json_match:
                    jd = json.loads(json_match.group())
                    if not sale_price and jd.get("discounted_price"):
                        sale_price = jd["discounted_price"]
                    if not original_price and jd.get("original_price"):
                        original_price = jd["original_price"]
                    if not discount_rate and jd.get("discount_rate"):
                        discount_rate = jd["discount_rate"]
            except:
                pass

    # CSS 클래스 fallback
    if not sale_price:
        for tag in soup.select(".prod-atf-contents .twc-text-\\[22px\\]"):
            txt = tag.get_text(strip=True).replace(',', '').replace('원', '')
            try:
                sale_price = int(txt)
                break
            except:
                pass

    # ── 옵션 ──────────────────────────────────────────────
    options = []
    option_items = soup.select(".option-table-list__option")
    for item in option_items:
        name_tag = item.select_one(".option-table-list__option-name")
        price_tag_opt = item.select_one(".option-table-list__option-price span")
        if name_tag:
            opt = {"name": name_tag.get_text(strip=True)}
            if price_tag_opt:
                price_txt = price_tag_opt.get_text(strip=True).replace(',', '').replace('원', '')
                try:
                    opt["price"] = int(price_txt)
                except:
                    opt["price_text"] = price_tag_opt.get_text(strip=True)
            options.append(opt)

    # ── 별점 & 리뷰 수 ───────────────────────────────────
    rating = None
    review_count = None

    # og:description에서 추출
    if description:
        rating_m = re.search(r'별점\s*([\d.]+)점', description)
        review_m = re.search(r'리뷰\s*([\d,]+)개', description)
        if rating_m:
            try:
                rating = float(rating_m.group(1))
            except:
                pass
        if review_m:
            try:
                review_count = int(review_m.group(1).replace(',', ''))
            except:
                pass

    # HTML에서 별점
    if not rating:
        for tag in soup.find_all(attrs={"aria-label": True}):
            label = tag.get("aria-label", "")
            try:
                v = float(label)
                if 0 < v <= 5:
                    rating = v
                    break
            except:
                pass

    # HTML에서 리뷰 수
    if not review_count:
        review_tag = soup.select_one("#prod-buy-header__productreview .twc-font-\\[400\\]")
        if review_tag:
            txt = review_tag.get_text(strip=True).strip('()')
            try:
                review_count = int(txt.replace(',', ''))
            except:
                pass

    # ── 배송 정보 ─────────────────────────────────────────
    delivery_info = ""
    pdd_tags = soup.select(".pdd-contents em")
    parts = [t.get_text(strip=True) for t in pdd_tags if t.get_text(strip=True)]
    if parts:
        delivery_info = " ".join(parts)

    # ── 원산지 ────────────────────────────────────────────
    origin = ""
    origin_tag = soup.select_one(".twc-text-bluegray-700.twc-truncate")
    if origin_tag:
        origin = origin_tag.get_text(strip=True)

    # ── 이미지 ────────────────────────────────────────────
    images = []
    # 메인 이미지
    main_img = soup.select_one(".product-image img[src*='492x492']")
    if main_img:
        src = main_img.get("src", "")
        if src and not src.startswith("http"):
            src = "https:" + src
        images.append(src)

    # 썸네일 이미지들
    thumb_imgs = soup.select(".product-image ul li img")
    for img in thumb_imgs:
        src = img.get("src", "")
        if src:
            if not src.startswith("http"):
                src = "https:" + src
            src = src.replace("48x48ex", "492x492ex")
            if src not in images:
                images.append(src)

    # 상품 상세 이미지
    detail_imgs = soup.select(".product-detail-content img[src*='thumbnail']")
    for img in detail_imgs:
        src = img.get("src", "")
        if src:
            if not src.startswith("http"):
                src = "https:" + src
            if src not in images:
                images.append(src)

    # ── 링크 ──────────────────────────────────────────────
    links = [url]
    brand_link = soup.select_one(".brand-info a")
    if brand_link and brand_link.get("href"):
        href = brand_link["href"]
        if href.startswith("/"):
            href = "https://www.coupang.com" + href
        links.append(href)

    for cat_link in soup.select("ul.breadcrumb li a"):
        href = cat_link.get("href", "")
        if href and href != "https://www.coupang.com":
            links.append(href)

    # ── 필수 표기 정보 ────────────────────────────────────
    product_info_table = {}
    table = soup.select_one("#itemBrief table")
    if table:
        rows = table.select("tr")
        for row in rows:
            ths = row.select("td.twc-bg-\\[\\#fafafa\\]")
            tds = row.select("td:not(.twc-bg-\\[\\#fafafa\\])")
            for th, td in zip(ths, tds):
                key = th.get_text(strip=True)
                val = td.get_text(strip=True)
                if key and val:
                    product_info_table[key] = val

    # ── 판매자 ────────────────────────────────────────────
    seller = ""
    seller_table = soup.select_one(".product-seller table")
    if seller_table:
        seller_td = seller_table.select_one("td")
        if seller_td:
            seller = seller_td.get_text(strip=True).replace("1577-7011", "").strip()

    return {
        "title": title,
        "page_type": "product",
        "description": description,
        "data": {
            "product_id": product_id,
            "brand": brand,
            "categories": categories,
            "sale_price": sale_price,
            "original_price": original_price,
            "discount_rate": discount_rate,
            "currency": currency,
            "options": options,
            "rating": rating,
            "review_count": review_count,
            "delivery_info": delivery_info,
            "origin": origin,
            "seller": seller,
            "product_info": product_info_table,
        },
        "images": images[:10],
        "links": links[:10],
    }
