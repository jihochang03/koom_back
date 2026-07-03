# Template: ordinairement.com (detail)
# Generated: 2026-07-03T03:47:04.392Z
# Notes: cafe24 기반 쇼핑몰. simple 수집 가능. 옵션은 select[product_type="product_option"]으로 현재 상품 옵션만 추출(추가상품 제외). option_stock_data JS 변수에서 옵션별 품절(is_selling=F 또는 stock_number=0) 정보 파싱 → values에 sold_out/stock_number/option_price 포함. 이미지는 BigImage + product_image_tiny(tiny→big) + JSON-LD + 상세영역 ec-data-src에서 최대 10장.

# Template: ordinairement.com (detail)
# Notes: cafe24 기반 쇼핑몰. simple 수집 가능.
# 옵션: select[product_type="product_option"]으로 현재 상품 옵션만 추출(추가상품 addproduct_option 제외).
# option_stock_data JS 변수에서 옵션별 품절(is_selling=F 또는 stock_number=0) 파싱 → values에 sold_out/stock_number/option_price 포함.
# 이미지: BigImage + product_image_tiny(tiny→big 치환) + JSON-LD image + 상세영역 ec-data-src 속성에서 최대 10장.

import requests
from bs4 import BeautifulSoup
import re
import json

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'ko-KR,ko;q=0.9',
}

def scrape(url: str) -> dict:
    resp = requests.get(url, headers=HEADERS, timeout=15)
    html = resp.text
    soup = BeautifulSoup(html, 'html.parser')

    # ── 타이틀 ──
    title = None
    og_title = soup.select_one('meta[property="og:title"]')
    if og_title:
        title = og_title.get('content', '').strip()
    if not title:
        h1 = soup.select_one('h2.name, h1')
        title = h1.get_text(strip=True) if h1 else None

    # ── JSON-LD 파싱 ──
    ld = {}
    ld_tag = soup.find('script', type='application/ld+json')
    if ld_tag:
        try:
            ld = json.loads(ld_tag.string)
        except:
            pass

    # ── 가격 ──
    price_original = None
    price_discounted = None

    meta_price = soup.select_one('meta[property="product:price:amount"]')
    if meta_price:
        try:
            price_original = int(float(meta_price.get('content', 0)))
        except:
            pass

    meta_sale = soup.select_one('meta[property="product:sale_price:amount"]')
    if meta_sale:
        try:
            sale_val = int(float(meta_sale.get('content', 0)))
            if sale_val and sale_val != price_original:
                price_discounted = sale_val
        except:
            pass

    # JSON-LD offers fallback
    if not price_original and ld.get('offers'):
        try:
            price_original = int(ld['offers'][0].get('price', 0))
        except:
            pass

    # HTML fallback
    if not price_original:
        price_el = soup.select_one('p.price strong, span#span_product_price_text')
        if price_el:
            m = re.search(r'[\d,]+', price_el.get_text())
            if m:
                price_original = int(m.group().replace(',', ''))

    # ── option_stock_data JS 변수 파싱 (옵션별 품절·재고 정보) ──
    # is_selling=F 또는 stock_number=0 이면 품절
    option_stock_map = {}  # option_value → {sold_out, stock_number, option_price}
    osd_m = re.search(r"var option_stock_data\s*=\s*'((?:[^'\\]|\\.)*)'", html)
    if osd_m:
        try:
            raw = osd_m.group(1).encode('utf-8').decode('unicode_escape')
            osd = json.loads(raw)
        except Exception:
            try:
                osd = json.loads(osd_m.group(1).replace('\\"', '"').replace('\\\\', '\\'))
            except Exception:
                osd = {}
        for code, info in osd.items():
            val = info.get('option_value', '')
            if val:
                is_selling = info.get('is_selling', 'T')
                stock = info.get('stock_number', 1)
                sold_out = (is_selling == 'F') or (stock == 0)
                option_stock_map[val] = {
                    'sold_out': sold_out,
                    'stock_number': stock,
                    'option_price': info.get('option_price'),
                }

    # ── 이미지 ──
    images = []
    # 메인 BigImage
    big_img = soup.select_one('div.thumbnail img.BigImage')
    if big_img:
        src = big_img.get('src', '')
        if src.startswith('//'):
            src = 'https:' + src
        if src:
            images.append(src)

    og_img = soup.select_one('meta[property="og:image"]')
    if og_img:
        src = og_img.get('content', '')
        if src and src not in images:
            images.append(src)

    # product_image_tiny JS 변수 → big 경로로 치환
    tiny_m = re.search(r"product_image_tiny\s*=\s*'([^']+)'", html)
    if tiny_m:
        tiny_path = tiny_m.group(1)
        big_src = f"https://ordinairement.com/web/product/big/{tiny_path}"
        if big_src not in images:
            images.append(big_src)

    # JSON-LD image 배열
    if ld.get('image'):
        for img_src in (ld['image'] if isinstance(ld['image'], list) else [ld['image']]):
            if img_src and img_src not in images:
                images.append(img_src)

    # 상세 이미지: ec-data-src 속성 (cafe24 lazy-load)
    base_url = 'https://ordinairement.com'
    detail_area = soup.select_one('div#prdDetail, div#prdDetailContentLazy, div.cont')
    if detail_area:
        for img in detail_area.find_all('img'):
            src = (img.get('ec-data-src') or img.get('data-src') or
                   img.get('data-original') or img.get('src') or '')
            if src:
                if src.startswith('//'):
                    src = 'https:' + src
                elif src.startswith('/'):
                    src = base_url + src
                if src not in images and 'tiny' not in src and 'menu_' not in src:
                    images.append(src)

    images = images[:10]

    # ── 옵션 (품절 정보 포함) ──
    options = []
    # 현재 상품 옵션만 (product_type="product_option"), 추가상품(addproduct_option) 제외
    option_table = soup.select('table.xans-product-option tbody.xans-record-')
    for tbody in option_table:
        sel_el = tbody.select_one('select[product_type="product_option"]')
        if not sel_el:
            continue
        opt_title = sel_el.get('option_title', '') or sel_el.get('name', '')
        values = []
        for opt in sel_el.find_all('option'):
            val = opt.get('value', '').strip()
            if not val or val.startswith('*') or val.startswith('-'):
                continue
            label = opt.get_text(strip=True) or val
            entry = {'value': label}
            # option_stock_map에서 품절·재고·가격 보강
            stock_info = option_stock_map.get(val, {})
            if stock_info:
                entry['sold_out'] = stock_info['sold_out']
                entry['stock_number'] = stock_info['stock_number']
                if stock_info.get('option_price'):
                    entry['option_price'] = stock_info['option_price']
            values.append(entry)
        if values:
            options.append({'name': opt_title, 'values': values})

    # fallback: name^="option" 중 product_option만
    if not options:
        for sel_el in soup.select('select[name^="option"][product_type="product_option"]'):
            opt_title = sel_el.get('option_title', '') or sel_el.get('name', '')
            values = []
            for opt in sel_el.find_all('option'):
                val = opt.get('value', '').strip()
                if not val or val.startswith('*') or val.startswith('-'):
                    continue
                label = opt.get_text(strip=True) or val
                entry = {'value': label}
                stock_info = option_stock_map.get(val, {})
                if stock_info:
                    entry['sold_out'] = stock_info['sold_out']
                    entry['stock_number'] = stock_info['stock_number']
                    if stock_info.get('option_price'):
                        entry['option_price'] = stock_info['option_price']
                values.append(entry)
            if values:
                options.append({'name': opt_title, 'values': values})

    # ── 배송비 ──
    shipping_fee = None
    shipping_fee_text = None
    text_all = soup.get_text(' ', strip=True)
    ship_area_m = re.search(r'배송비.{0,300}', text_all, re.DOTALL)
    ship_area = ship_area_m.group(0) if ship_area_m else text_all

    if re.search(r'무료\s*배송|배송\s*무료', ship_area):
        shipping_fee = 0
        shipping_fee_text = '무료배송'
    else:
        combined = re.search(r'([\d,]+)\s*원[^(]{0,30}\(([^)]*[\d,]+\s*만?\s*원\s*이상[^)]*무료[^)]*)\)', ship_area)
        if combined:
            shipping_fee = int(combined.group(1).replace(',', ''))
            shipping_fee_text = combined.group(0).strip()
        else:
            m = re.search(r'([\d,]+)\s*원', ship_area)
            if m:
                shipping_fee = int(m.group(1).replace(',', ''))
                shipping_fee_text = m.group(0).strip()

    # ── 브랜드 ──
    brand = None
    if ld.get('brand'):
        brand_info = ld['brand']
        brand = brand_info.get('name') if isinstance(brand_info, dict) else None
    if not brand:
        meta_brand = soup.select_one('meta[property="product:brand"]')
        if meta_brand:
            brand = meta_brand.get('content', '').strip() or None

    # ── 평점·리뷰수 ──
    rating = None
    review_count = None
    agg = ld.get('aggregateRating', {})
    if agg:
        rating = float(agg.get('ratingValue', 0)) or None
        review_count = int(agg.get('reviewCount', 0)) or None

    if rating is None:
        star_el = soup.select_one('[class*="rating"], [class*="star"], .review_score')
        if star_el:
            rm = re.search(r'([\d.]+)', star_el.get_text())
            if rm:
                rating = float(rm.group(1))

    if review_count is None:
        rc_el = soup.select_one('[class*="review_count"], [id*="review_count"]')
        if rc_el:
            rcm = re.search(r'[\d,]+', rc_el.get_text())
            if rcm:
                review_count = int(rcm.group().replace(',', ''))

    # ── 재고 ──
    availability = 'unknown'
    offers = ld.get('offers', [])
    if offers:
        avail_str = offers[0].get('availability', '')
        if 'InStock' in avail_str:
            availability = 'in_stock'
        elif 'OutOfStock' in avail_str:
            availability = 'out_of_stock'

    # ── 판매자 ──
    seller = None
    site_name = soup.select_one('meta[property="og:site_name"]')
    if site_name:
        seller = site_name.get('content', '').strip() or None

    # ── 배송 예정일 ──
    delivery_date = None
    for pattern in [r'오늘\s*출발', r'내일\s*도착', r'[0-9]+일\s*이내\s*도착', r'배송\s*예정']:
        dm = re.search(pattern, text_all)
        if dm:
            delivery_date = dm.group(0).strip()
            break

    # ── 스펙 ──
    specifications = {}
    spec_rows = soup.select('table.xans-product-detail tr, .spec_tb tr')
    for row in spec_rows:
        th = row.select_one('th')
        td = row.select_one('td')
        if th and td:
            k = th.get_text(strip=True)
            v = td.get_text(strip=True)
            if k and v:
                specifications[k] = v

    # ── size ──
    size = requests.post("http://localhost:18080/extract/size", json={
        "title": title,
        "category": "여성의류",
        "specs": specifications,
        "text": soup.get_text(" ", strip=True)[:5000],
        "images": images,
        "allow_ocr": False,
    }, timeout=30).json()

    if size.get("girth_sum_cm") is None and size.get("confidence") in ("LOW", "MEDIUM") and images:
        size = requests.post("http://localhost:18080/extract/size", json={
            "title": title, "category": "여성의류", "specs": specifications,
            "text": "", "images": images, "allow_ocr": True,
        }, timeout=40).json()

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
