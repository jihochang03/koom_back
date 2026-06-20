# Template: amoremall.com (detail)
# Generated: 2026-06-10T08:20:15.190Z
# Notes: 아모레몰 상품 상세 페이지. simple requests로 수집 가능. 할인율 표시 상품의 정가/할인가, 배송비 2500원(2만원 이상 무료), 단일 옵션, Swiper 슬라이드 이미지 추출.

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

    # ── 제목 ──
    name_el = soup.select_one('.summary .name')
    if name_el:
        title = name_el.get_text(strip=True)
    else:
        title_tag = soup.find('title')
        title = title_tag.get_text(strip=True).split('|')[0].strip() if title_tag else ''

    # ── 가격 ──
    price_original = None
    price_discounted = None

    origin_el = soup.select_one('.priceInfo__inner-item.origin .priceInfo__inner-price strong')
    if origin_el:
        price_original = int(origin_el.get_text(strip=True).replace(',', ''))

    discount_el = soup.select_one('.priceInfo__inner-item.discount .priceInfo__inner-price strong')
    if discount_el:
        price_discounted = int(discount_el.get_text(strip=True).replace(',', ''))

    if price_discounted is None and price_original is not None:
        price_discounted = price_original

    # ── 옵션 ──
    options = []
    option_names = soup.select('.optionName.lg')
    if option_names:
        values = list({el.get_text(strip=True) for el in option_names})
        options = [{"name": "옵션", "values": values}]

    # ── 이미지 ──
    images = []
    seen = set()
    slides = soup.select('.swiper-slide.detailCard:not(.swiper-slide-duplicate)')
    for slide in slides:
        img = slide.select_one('img')
        if img:
            src = img.get('data-src') or img.get('src', '')
            base = src.split('?')[0]
            if base and base not in seen:
                seen.add(base)
                images.append(base)

    # ── 재고 ──
    availability = "in_stock"
    soldout_btn = soup.select_one('button.soldout, .status-soldout, .btnSoldout')
    if soldout_btn:
        availability = "out_of_stock"

    # ── 판매자 (브랜드명) ──
    brand_el = soup.select_one('.summary .brand')
    seller = brand_el.get_text(strip=True) if brand_el else "아모레퍼시픽"

    # ── 배송비 ──
    shipping_fee = None
    shipping_fee_text = None

    for strong in soup.select('.product-info strong'):
        txt = strong.get_text(strip=True)
        if '배송비' in txt:
            m = re.search(r'배송비\s*([\d,]+)원', txt)
            if m:
                shipping_fee = int(m.group(1).replace(',', ''))
            elif '무료' in txt:
                shipping_fee = 0
            shipping_fee_text = txt
            break

    # fallback
    if shipping_fee_text is None:
        full_text = soup.get_text(' ', strip=True)
        area_m = re.search(r'배송비.{0,200}', full_text)
        if area_m:
            area_text = area_m.group(0)
            m = re.search(r'배송비\s*([\d,]+)원', area_text)
            if m:
                shipping_fee = int(m.group(1).replace(',', ''))
                cond = re.search(r'([\d,]+원\s*이상[^\s]+\s*무료배송)', area_text)
                shipping_fee_text = f"배송비 {m.group(1)}원" + (f" ({cond.group(1)})" if cond else "")
            elif re.search(r'무료\s*배송|배송\s*무료', area_text):
                shipping_fee = 0
                shipping_fee_text = "무료배송"

    return {
        "title": title,
        "price_original": price_original,
        "price_discounted": price_discounted,
        "options": options,
        "images": images,
        "availability": availability,
        "seller": seller,
        "shipping_fee": shipping_fee,
        "shipping_fee_text": shipping_fee_text,
    }


if __name__ == "__main__":
    import sys as _sys, json as _json
    _url = _sys.argv[1] if len(_sys.argv) > 1 else ""
    _result = scrape(_url)
    print(_json.dumps(_result, ensure_ascii=False))
