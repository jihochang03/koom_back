# Template: mariomall.co.kr (detail)
# Generated: 2026-07-03T05:35:24.055Z
# Notes: 마리오몰 상품 상세 페이지. simple requests로 수집. eg:originalPrice/salePrice 메타태그로 가격, JS var SoldOut으로 품절, #sel02 select로 옵션, /Product/ 경로 img로 이미지 추출. 배송비: 무료배송 span 확인 → 기본 정책(60000원 이상 무료, 미만 3200원).

import requests
from bs4 import BeautifulSoup
import re
import json

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'ko-KR,ko;q=0.9',
}

BASE_URL = "http://mariomall.co.kr"


def _fix_image(url):
    if not url:
        return None
    # http → https 통일
    if url.startswith("http://cdn"):
        url = "https" + url[4:]
    if url.startswith("//"):
        url = "https:" + url
    elif url.startswith("/") and not url.startswith("//"):
        url = BASE_URL + url
    # 쿼리스트링 제거 → 원본 이미지
    url = re.sub(r'\?.*$', '', url)
    return url


def _is_valid_product_image(url):
    """아이콘/UI 이미지 필터"""
    if not url:
        return False
    if re.search(r'icon-|/ui/common/|noimg|\.gif$', url, re.IGNORECASE):
        return False
    return True


def _extract_images(soup):
    images = []
    seen = set()

    def add(url):
        fixed = _fix_image(url)
        if fixed and fixed not in seen and _is_valid_product_image(fixed):
            images.append(fixed)
            seen.add(fixed)

    # og:image 메타 (메인 이미지)
    og = soup.select_one('meta[property="og:image"]')
    if og:
        add(og.get('content', ''))

    # /Product/ 경로를 가진 img 태그 (갤러리 이미지)
    for img in soup.find_all('img'):
        src = img.get('src') or img.get('data-src', '') or img.get('data-original', '')
        if src and '/Product/' in src:
            add(src)

    # eg:image 메타
    for meta in soup.select('meta[property="eg:image"]'):
        add(meta.get('content', ''))

    return images[:10]


def _extract_options(soup):
    options = []
    sel = soup.select_one('#sel02')
    if sel:
        values = []
        soldout_values = []
        for opt in sel.find_all('option'):
            val_attr = opt.get('value', '').strip()
            if val_attr and val_attr != '0':
                text = opt.get_text(strip=True)
                is_soldout = '품절' in text or bool(opt.get('disabled'))
                clean = re.sub(r'\s*\(품절\)\s*', '', text).strip()
                if clean:
                    values.append(clean)
                    if is_soldout:
                        soldout_values.append(clean)
        if values:
            entry = {"name": "선택", "values": values}
            if soldout_values:
                entry["soldout_values"] = soldout_values
            options.append(entry)
    return options


def _extract_shipping(soup, price_discounted, price_original):
    """배송비 추출:
    - 개별 상품에 (무료배송) span 있으면 무료
    - 없으면 기본 정책: 60,000원 이상 무료, 미만 3,200원
    """
    # 개별 상품 무료배송 표시
    for em in soup.find_all('em'):
        span = em.find('span')
        if span and '무료배송' in span.get_text():
            return 0, "무료배송"

    # 배송비 구역에서 금액 추출
    for s in soup.find_all(string=re.compile(r'배송비')):
        parent = s.parent
        if parent:
            text = parent.get_text(" ", strip=True)
            m = re.search(r'(\d[\d,]+)\s*원', text)
            if m:
                fee = int(m.group(1).replace(',', ''))
                if fee < 10000:  # 배송비는 보통 10,000원 미만
                    return fee, f"{m.group(1)}원"

    # 기본 정책 적용
    price_check = price_discounted or price_original
    if price_check is not None:
        if price_check >= 60000:
            return 0, "무료배송 (60,000원 이상)"
        else:
            return 3200, "3,200원 (60,000원 이상 무료배송)"

    return None, "3,200원 (60,000원 이상 무료배송)"


def scrape(url: str) -> dict:
    resp = requests.get(url, headers=HEADERS, timeout=15)
    html = resp.text
    soup = BeautifulSoup(html, 'html.parser')

    # 제목: <title> 태그에서 사이트명 제거
    title = None
    title_tag = soup.find('title')
    if title_tag:
        title = title_tag.get_text(strip=True)
        title = re.sub(r'\s*[-|–]\s*마리오몰.*$', '', title).strip()

    # 가격: eg:originalPrice / eg:salePrice 메타태그
    price_original = None
    price_discounted = None

    orig_meta = soup.select_one('meta[property="eg:originalPrice"]')
    if orig_meta:
        v = orig_meta.get('content', '').replace(',', '')
        if v.isdigit():
            price_original = int(v)

    sale_meta = soup.select_one('meta[property="eg:salePrice"]')
    if sale_meta:
        v = sale_meta.get('content', '').replace(',', '')
        if v.isdigit():
            price_discounted = int(v)

    # fallback: HTML에서 가격 직접 파싱
    if not price_discounted:
        for sel_str in ['.sale-price', '.prd-price', '[class*="sale-price"]', '.price strong', '.item-price']:
            el = soup.select_one(sel_str)
            if el:
                m = re.search(r'(\d[\d,]+)', el.get_text())
                if m:
                    price_discounted = int(m.group(1).replace(',', ''))
                    break

    # 브랜드: eg:brandName 메타태그
    brand = None
    brand_meta = soup.select_one('meta[property="eg:brandName"]')
    if brand_meta:
        brand = brand_meta.get('content', '').strip() or None

    # 이미지
    images = _extract_images(soup)

    # 옵션
    options = _extract_options(soup)

    # 품절 여부: JS 변수 var SoldOut = 'True'/'False'
    availability = "in_stock"
    soldout_match = re.search(r"var\s+SoldOut\s*=\s*'([^']+)'", html)
    if soldout_match:
        if soldout_match.group(1).lower() == 'true':
            availability = "out_of_stock"

    # 배송비
    shipping_fee, shipping_fee_text = _extract_shipping(soup, price_discounted, price_original)

    # 평점/리뷰 (og:description에 들어있는 경우)
    rating = None
    review_count = None
    og_desc = soup.select_one('meta[property="og:description"], meta[name="description"]')
    if og_desc:
        desc = og_desc.get('content', '')
        m = re.search(r'별점\s*(\d+\.?\d*)', desc)
        if m:
            rating = float(m.group(1))
        m2 = re.search(r'리뷰\s*(\d+)', desc)
        if m2:
            review_count = int(m2.group(1))

    # specifications: 필수표기정보 테이블
    specifications = {}
    for table in soup.select('table'):
        for row in table.find_all('tr'):
            cells = row.find_all(['th', 'td'])
            if len(cells) >= 2:
                key = cells[0].get_text(strip=True)
                val = cells[1].get_text(strip=True)
                if key and val and len(key) < 50:
                    specifications[key] = val

    # size 추출 (/extract/size 서비스 호출)
    size = requests.post("http://localhost:18080/extract/size", json={
        "title": title,
        "category": "",
        "specs": specifications,
        "text": soup.get_text(" ", strip=True)[:5000],
        "images": images,
        "allow_ocr": False,
    }, timeout=30).json()

    if size.get("girth_sum_cm") is None and size.get("confidence") in ("LOW", "MEDIUM") and images:
        size = requests.post("http://localhost:18080/extract/size", json={
            "title": title, "category": "", "specs": specifications,
            "text": "", "images": images, "allow_ocr": True,
        }, timeout=40).json()

    return {
        "title": title,
        "price_original": price_original,
        "price_discounted": price_discounted,
        "options": options,
        "images": images,
        "availability": availability,
        "seller": "마리오몰",
        "brand": brand,
        "rating": rating,
        "review_count": review_count,
        "shipping_fee": shipping_fee,
        "shipping_fee_text": shipping_fee_text,
        "delivery_date": None,
        "specifications": specifications,
        "size": size,
    }


if __name__ == "__main__":
    import sys as _sys, json as _json
    _url = _sys.argv[1] if len(_sys.argv) > 1 else ""
    _result = scrape(_url)
    print(_json.dumps(_result, ensure_ascii=False))
