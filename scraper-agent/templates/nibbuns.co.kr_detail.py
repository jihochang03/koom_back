# Template: nibbuns.co.kr (detail)
# Generated: 2026-07-03T01:08:40.353Z
# Notes: 니뽄즈(makeshop 기반 쇼핑몰). simple requests로 수집 가능. JSON-LD에 상품명/가격/재고, select.basic_option에 옵션값, 배송비는 무료배송 텍스트 파싱.

import requests
from bs4 import BeautifulSoup
import re
import json

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'ko-KR,ko;q=0.9',
}

def _extract_options(soup):
    """basic_option select에서 옵션 그룹/값 추출"""
    options = []
    for sel in soup.select('select.basic_option'):
        label = sel.get('label', '') or sel.get('name', '')
        values = []
        for opt in sel.find_all('option'):
            v = opt.get_text(strip=True)
            if v and v != '옵션 선택':
                values.append(v)
        if values:
            options.append({'name': label, 'values': values})
    return options

def _extract_images(soup, html):
    """썸네일 및 상세 이미지 추출"""
    images = []
    seen = set()

    # 메인 이미지
    main = soup.select_one('.thumb-wrap .detail_image')
    if main:
        src = main.get('src', '')
        if src:
            src = ('https:' + src) if src.startswith('//') else src
            src = re.sub(r'\?.*$', '', src)
            if src not in seen:
                images.append(src)
                seen.add(src)

    # JSON-LD 이미지
    for tag in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(tag.string or '')
            if isinstance(data, dict) and data.get('@type') == 'Product':
                for img in (data.get('image') or []):
                    url = img if isinstance(img, str) else img.get('url', '')
                    if url:
                        url = ('https:' + url) if url.startswith('//') else url
                        url = re.sub(r'\?.*$', '', url)
                        if url not in seen:
                            images.append(url)
                            seen.add(url)
        except Exception:
            pass

    # HTML에서 현재 상품 SKU 이미지 패턴 찾기 (branduid 기반 xcode 추출)
    m_xcode = re.search(r'xcode=(\d+)', html)
    if m_xcode:
        xcode = m_xcode.group(1).zfill(3)
        for m in re.finditer(
            r'((?:https?:)?//[^"\']+/shopimages/piasom/' + xcode + r'[^"\'?]+\.(?:jpg|gif|png|webp))',
            html
        ):
            url = m.group(1)
            url = ('https:' + url) if url.startswith('//') else url
            url = re.sub(r'\?.*$', '', url)
            if url not in seen:
                images.append(url)
                seen.add(url)

    return images[:10]

def _extract_shipping(soup):
    """배송비 추출"""
    text = soup.get_text(' ', strip=True)
    area_m = re.search(r'배송비.{0,300}', text, re.DOTALL)
    area = area_m.group(0) if area_m else text

    # 무료배송
    if re.search(r'무료\s*배송|배송\s*무료', area):
        return 0, '무료배송'

    # 유료 + 조건
    m = re.search(r'([0-9,]+)\s*원', area)
    if m:
        fee = int(m.group(1).replace(',', ''))
        # 조건부 무료 패턴
        cond = re.search(r'[0-9,]+\s*원.*?이상.*?무료', area)
        if cond:
            return fee, cond.group(0).strip()
        return fee, f"{m.group(1)}원"

    return None, None

def _extract_price(soup):
    """가격 추출 (JSON-LD 또는 HTML)"""
    # JSON-LD
    for tag in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(tag.string or '')
            if isinstance(data, dict) and data.get('@type') == 'Product':
                offers = data.get('offers', {})
                price = offers.get('price')
                if price:
                    return int(float(price)), None
        except Exception:
            pass
    # HTML fallback
    for sel in ['.selling-price', '.price', '[class*="price"]']:
        el = soup.select_one(sel)
        if el:
            m = re.search(r'([0-9,]+)', el.get_text())
            if m:
                return int(m.group(1).replace(',', '')), None
    return None, None

def scrape(url: str) -> dict:
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.encoding = resp.apparent_encoding or 'utf-8'
    html = resp.text
    soup = BeautifulSoup(html, 'html.parser')

    # 타이틀
    title = None
    og_title = soup.find('meta', property='og:title')
    if og_title:
        title = og_title.get('content', '').strip()
    if not title:
        for tag in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(tag.string or '')
                if isinstance(data, dict) and data.get('@type') == 'Product':
                    title = data.get('name', '').strip()
                    break
            except Exception:
                pass

    # 가격
    price_original, price_discounted = _extract_price(soup)

    # 배송비
    shipping_fee, shipping_fee_text = _extract_shipping(soup)

    # 옵션
    options = _extract_options(soup)

    # 이미지
    images = _extract_images(soup, html)

    # 재고
    availability = 'unknown'
    for tag in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(tag.string or '')
            if isinstance(data, dict) and data.get('@type') == 'Product':
                avail = data.get('offers', {}).get('availability', '')
                if 'InStock' in avail:
                    availability = 'in_stock'
                elif 'OutOfStock' in avail:
                    availability = 'out_of_stock'
                break
        except Exception:
            pass

    # 브랜드
    brand = None
    for tag in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(tag.string or '')
            if isinstance(data, dict) and data.get('@type') == 'Product':
                b = data.get('brand', {})
                brand = b.get('name') if isinstance(b, dict) else b
                break
        except Exception:
            pass

    # 평점/리뷰 (HTML에 없으면 None)
    rating = None
    review_count = None

    # 배송 도착 안내
    delivery_date = None
    delivery_el = soup.find(string=re.compile(r'도착|배송\s*예정|오늘출발'))
    if delivery_el:
        delivery_date = delivery_el.strip()

    # 스펙/필수표기정보 (table/dl 파싱)
    specifications = {}
    for table in soup.select('table'):
        for row in table.select('tr'):
            cells = row.select('th, td')
            if len(cells) >= 2:
                k = cells[0].get_text(strip=True)
                v = cells[1].get_text(strip=True)
                if k and v:
                    specifications[k] = v

    # 판매자
    seller_el = soup.select_one('[class*="seller"], [class*="shop-name"]')
    seller = seller_el.get_text(strip=True) if seller_el else None

    # 사이즈 추출
    size = requests.post("http://localhost:18080/extract/size", json={
        "title": title,
        "category": "PANTS",
        "specs": specifications,
        "text": soup.get_text(" ", strip=True)[:5000],
        "images": images,
        "allow_ocr": False,
    }, timeout=30).json()

    # OCR 보강 (치수 없고 신뢰도 낮을 때)
    if size.get("girth_sum_cm") is None and size.get("confidence") in ("LOW", "MEDIUM") and images:
        size = requests.post("http://localhost:18080/extract/size", json={
            "title": title,
            "category": "PANTS",
            "specs": specifications,
            "text": "",
            "images": images,
            "allow_ocr": True,
        }, timeout=40).json()

    return {
        'title': title,
        'price_original': price_original,
        'price_discounted': price_discounted,
        'options': options,
        'images': images,
        'availability': availability,
        'seller': seller,
        'brand': brand,
        'rating': rating,
        'review_count': review_count,
        'shipping_fee': shipping_fee,
        'shipping_fee_text': shipping_fee_text,
        'delivery_date': delivery_date,
        'specifications': specifications,
        'size': size,
    }


if __name__ == "__main__":
    import sys as _sys, json as _json
    _url = _sys.argv[1] if len(_sys.argv) > 1 else ""
    _result = scrape(_url)
    print(_json.dumps(_result, ensure_ascii=False))
