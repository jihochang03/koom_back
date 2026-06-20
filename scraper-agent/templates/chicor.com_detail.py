# Template: chicor.com (detail)
# Generated: 2026-06-10T08:23:24.325Z
# Notes: chicor.com 상품 상세 페이지. simple requests로 수집 가능. 가격은 div.price.num > div.price-inner 내 del(원가)/strong(할인가) 구조. 이미지는 JS 스크립트에서 cdn.chicor.com/images/goods 경로로 추출하거나 없으면 에디터 이미지 사용. 배송비는 p.desc 텍스트에서 추출. goosSelect는 단품 상품 자기 자신 선택 셀렉트로 옵션 아님.

import requests
from bs4 import BeautifulSoup
import re

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'ko-KR,ko;q=0.9',
}

def _parse_price(text):
    text = re.sub(r'\s', '', text)
    m = re.search(r'[\d,]+', text)
    return int(m.group(0).replace(',', '')) if m else None

def _extract_shipping(soup):
    desc_els = soup.select('p.desc')
    for el in desc_els:
        txt = ' '.join(el.get_text(' ', strip=True).split())
        if '배송' not in txt and '무료' not in txt:
            continue
        # "2,500원 (30,000원 이상 구매시 무료배송...)" → fee=2500
        combined = re.search(r'([\d,]+)\s*원[^(]{0,30}\([^)]*[\d,]+\s*원\s*이상[^)]*무료[^)]*\)', txt)
        if combined:
            fee = int(combined.group(1).replace(',', ''))
            return fee, txt.strip()
        if re.search(r'무료\s*배송|배송\s*무료', txt):
            return 0, txt.strip()
        m = re.search(r'([\d,]+)\s*원', txt)
        if m:
            fee = int(m.group(1).replace(',', ''))
            if 0 < fee < 100_000:
                return fee, txt.strip()
        return None, txt.strip()
    return None, None

def scrape(url: str) -> dict:
    resp = requests.get(url, headers=HEADERS, timeout=15)
    html = resp.text
    soup = BeautifulSoup(html, 'html.parser')

    # ── 제목
    title_el = soup.select_one('h1.name')
    title = title_el.get_text(strip=True) if title_el else None

    # ── 브랜드
    brand_el = soup.select_one('div.brand')
    brand_text = None
    if brand_el:
        for a in brand_el.find_all('a'):
            a.decompose()
        brand_text = brand_el.get_text(strip=True)

    # ── 가격
    price_original = None
    price_discounted = None
    price_area = soup.select_one('div.price.num')
    if price_area:
        target = price_area.select_one('div.price-inner') or price_area
        del_el = target.select_one('del')
        strong_el = target.select_one('strong')
        if del_el:
            price_original = _parse_price(del_el.get_text())
        if strong_el:
            price_discounted = _parse_price(strong_el.get_text())
        if price_original is None and price_discounted is not None:
            price_original = price_discounted
            price_discounted = None

    # ── 이미지 (JS 스크립트 goods 경로 우선, 없으면 에디터 이미지)
    images = []
    for script in soup.find_all('script'):
        sc_text = script.string or ''
        found = re.findall(r'https://cdn\.chicor\.com/images/goods[^\s\'"<>]+', sc_text)
        images.extend(found)
    if not images:
        for img in soup.select('div.wrap-info-img img'):
            src = img.get('src', '')
            if src.startswith('http') and 'cdn.chicor.com' in src:
                images.append(src)
    seen = set()
    images = [x for x in images if not (x in seen or seen.add(x))]

    # ── 옵션 파싱
    options = []
    optn_containers = soup.select('div.optn-change')
    for container in optn_containers:
        for sel in container.select('select'):
            # goosSelect(단품 자기 자신 선택)은 옵션 아님
            if sel.get('id', '').lower() == 'goosselect' or sel.get('name', '').lower() == 'goosselect':
                continue
            opt_name = sel.get('data-optn-nm') or sel.get('title') or sel.get('name') or '옵션'
            values = []
            for o in sel.select('option'):
                v = o.get_text(strip=True)
                if not v or '선택' in v or '할인기간' in v or '기간은' in v or len(v) > 60:
                    continue
                values.append(v)
            if values:
                options.append({'name': opt_name, 'values': values})

    # ── 재고 여부
    availability = 'in_stock'
    if soup.select_one('.btn-soldout, .out-of-stock, .sold-out'):
        availability = 'out_of_stock'

    # ── 배송비
    shipping_fee, shipping_fee_text = _extract_shipping(soup)

    return {
        'title': title,
        'brand': brand_text,
        'price_original': price_original,
        'price_discounted': price_discounted,
        'options': options,
        'images': images[:5],
        'availability': availability,
        'seller': brand_text,
        'shipping_fee': shipping_fee,
        'shipping_fee_text': shipping_fee_text,
    }


if __name__ == "__main__":
    import sys as _sys, json as _json
    _url = _sys.argv[1] if len(_sys.argv) > 1 else ""
    _result = scrape(_url)
    print(_json.dumps(_result, ensure_ascii=False))
