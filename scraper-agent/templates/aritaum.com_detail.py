# Template: aritaum.com (detail)
# Generated: 2026-06-10T04:57:46.154Z
# Notes: aritaum.com 상품 상세 페이지. simple 방식으로 수집 가능. 가격은 #i_sSalePrice / #i_sListPrice hidden input 또는 eg:salePrice / eg:originalPrice meta 태그에서 추출. 옵션은 #barOptSel select에서 추출. 배송비는 텍스트 "배송비 2,500원 (2만원 이상 무료배송)" 패턴으로 추출.

import requests
from bs4 import BeautifulSoup
import re

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'ko-KR,ko;q=0.9',
}

def scrape(url: str) -> dict:
    resp = requests.get(url, headers=HEADERS, timeout=15)
    html = resp.text
    soup = BeautifulSoup(html, 'html.parser')

    # ── 제목 ──────────────────────────────────────────────
    title = None
    title_el = soup.select_one('.goods-detail-summary__title') or soup.select_one('h1')
    if title_el:
        title = title_el.get_text(strip=True)
    if not title:
        og_title = soup.find('meta', property='og:title')
        if og_title:
            title = og_title.get('content', '').strip()
    if title and ' | ARITAUM' in title:
        title = title.replace(' | ARITAUM', '').strip()

    # ── 가격 ──────────────────────────────────────────────
    price_discounted = None
    price_original = None

    # hidden input i_sSalePrice / i_sListPrice
    sale_input = soup.select_one('#i_sSalePrice')
    if sale_input:
        v = sale_input.get('value', '').replace(',', '')
        if v.isdigit():
            price_discounted = int(v)

    list_input = soup.select_one('#i_sListPrice')
    if list_input:
        v = list_input.get('value', '').replace(',', '')
        if v.isdigit():
            price_original = int(v)

    # eg:salePrice / eg:originalPrice meta 태그 fallback
    if not price_discounted:
        eg_sale = soup.find('meta', property='eg:salePrice')
        if eg_sale:
            price_discounted = int(float(eg_sale.get('content', '0')))
    if not price_original:
        eg_orig = soup.find('meta', property='eg:originalPrice')
        if eg_orig:
            price_original = int(float(eg_orig.get('content', '0')))

    if not price_discounted:
        price_discounted = price_original
    if not price_original:
        price_original = price_discounted

    # ── 옵션 ──────────────────────────────────────────────
    options = []

    # #barOptSel select (하단 바 옵션)
    bar_sel = soup.select_one('#barOptSel')
    if bar_sel:
        opt_values = []
        for opt in bar_sel.find_all('option'):
            val = opt.get('value', '').strip()
            text = opt.get_text(strip=True)
            if val and text and '선택' not in text:
                opt_values.append(text)
        if opt_values:
            options.append({'name': '색상/호수', 'values': opt_values})

    # .optionList 버튼 fallback
    if not options:
        opt_list = soup.select('.optionList button')
        if opt_list:
            vals = [b.get_text(strip=True) for b in opt_list if b.get_text(strip=True)]
            if vals:
                options.append({'name': '옵션', 'values': vals})

    # ── 이미지 ────────────────────────────────────────────
    images = []
    og_img = soup.find('meta', property='og:image')
    if og_img and og_img.get('content'):
        images.append(og_img['content'])

    for img in soup.select('.goods-detail-thumbnail img, .swiper-slide img, .thumb-area img'):
        src = img.get('src') or img.get('data-src') or ''
        if src and src.startswith('http') and src not in images:
            images.append(src)

    # ── 재고 ──────────────────────────────────────────────
    availability = 'in_stock'
    if soup.select_one('.btn-soldout, .sold-out-btn'):
        availability = 'out_of_stock'

    # ── 판매자 ────────────────────────────────────────────
    seller = 'ARITAUM'

    # ── 배송비 ────────────────────────────────────────────
    shipping_fee = None
    shipping_fee_text = None

    text_all = soup.get_text(' ', strip=True)
    area_m = re.search(r'배송비.{0,300}', text_all, re.DOTALL)
    area = area_m.group(0) if area_m else text_all

    # 패턴: "2,500원 (2만원 이상 무료배송)"
    combined = re.search(r'([\d,]+)원[^(]{0,15}\(([^)]*이상[^)]*무료[^)]*)\)', area)
    if combined:
        shipping_fee = int(combined.group(1).replace(',', ''))
        shipping_fee_text = f"{combined.group(1)}원 ({combined.group(2)})"
    elif re.search(r'무료\s*배송|배송\s*무료', area):
        shipping_fee = 0
        shipping_fee_text = '무료배송'
    else:
        m = re.search(r'([\d,]+)\s*원', area)
        if m:
            fee = int(m.group(1).replace(',', ''))
            if 0 < fee < 100000:
                shipping_fee = fee
                shipping_fee_text = f"{m.group(1)}원"

    return {
        'title': title,
        'price_original': price_original,
        'price_discounted': price_discounted,
        'options': options,
        'images': images,
        'availability': availability,
        'seller': seller,
        'shipping_fee': shipping_fee,
        'shipping_fee_text': shipping_fee_text,
    }


if __name__ == "__main__":
    import sys as _sys, json as _json
    _url = _sys.argv[1] if len(_sys.argv) > 1 else ""
    _result = scrape(_url)
    print(_json.dumps(_result, ensure_ascii=False))
