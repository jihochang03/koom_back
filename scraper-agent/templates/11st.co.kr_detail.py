# Template: 11st.co.kr (detail)
# Generated: 2026-06-26T06:09:55.810Z
# Notes: 11번가 상품 상세 페이지 스크레이퍼. simple 모드(requests)로 수집. brazeProperty JSON에서 가격/평점/배송비/배송예정일 추출, productPrdInfo JSON 보조. available_values에서 옵션 추출. /products/spec/provision/{id} API로 스펙 수집.

import requests
import re
import json
from bs4 import BeautifulSoup

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'ko-KR,ko;q=0.9',
}

def _extract_specs(product_no):
    """상품정보 제공고시 API에서 스펙 파싱."""
    try:
        resp = requests.get(
            f"https://www.11st.co.kr/products/spec/provision/{product_no}",
            headers=HEADERS, timeout=10
        )
        spec_soup = BeautifulSoup(resp.text, 'html.parser')
        specs = {}
        for row in spec_soup.select('table tr'):
            cells = row.find_all(['th', 'td'])
            if len(cells) >= 2:
                key = cells[0].get_text(strip=True)
                val = cells[1].get_text(strip=True)
                if key and val:
                    specs[key] = val
        return specs if specs else None
    except:
        return None

def scrape(url: str) -> dict:
    # simple 모드 수집 (brazeProperty JSON 포함)
    resp = requests.get(url, headers=HEADERS, timeout=15)
    html = resp.text
    soup = BeautifulSoup(html, 'html.parser')

    # ── 1. brazeProperty JSON 파싱 (핵심 상품 데이터)
    prd_info = {}
    braze_m = re.search(r'var brazeProperty\s*=\s*(\{.*?\});', html, re.DOTALL)
    if braze_m:
        try:
            prd_info = json.loads(braze_m.group(1))
        except:
            pass

    # 보조: productPrdInfo JSON
    prd_info2 = {}
    prd_info_m = re.search(r'var productPrdInfo\s*=\s*(\{.*?\});', html, re.DOTALL)
    if prd_info_m:
        try:
            prd_info2 = json.loads(prd_info_m.group(1))
        except:
            pass

    # ── 2. 상품명
    title = prd_info.get('product_name') or prd_info2.get('prdNm')
    if not title:
        og = soup.find('meta', property='og:title')
        title = og['content'] if og else None

    # ── 3. 가격
    price_original = prd_info.get('original_price') or prd_info2.get('selPrc')
    price_discounted = prd_info.get('discount_price') or prd_info2.get('finalDscPrc')
    if price_discounted and price_original and price_discounted == price_original:
        price_discounted = None

    # ── 4. 배송비
    delivery_fee = prd_info.get('delivery_fee')
    delivery_free_price = prd_info.get('delivery_free_price', 0)
    if delivery_fee == 0:
        shipping_fee = 0
        shipping_fee_text = "무료배송"
    elif delivery_fee:
        shipping_fee = delivery_fee
        if delivery_free_price and delivery_free_price > 0:
            shipping_fee_text = f"{delivery_fee:,}원 ({delivery_free_price:,}원 이상 무료배송)"
        else:
            shipping_fee_text = f"{delivery_fee:,}원"
    else:
        shipping_fee = None
        shipping_fee_text = None

    # ── 5. 배송 예정일
    delivery_date = prd_info.get('delivery_expect_date') or None

    # ── 6. 평점·리뷰
    rating = prd_info.get('review_score')
    review_count = prd_info.get('review_count')

    # ── 7. 판매자/브랜드
    seller = prd_info.get('store_name') or prd_info2.get('sellerId')
    brand_nm_m = re.search(r'"brand_name"\s*:\s*"([^"]+)"', html)
    brand = brand_nm_m.group(1) if brand_nm_m else None

    # ── 8. 옵션 (available_values / productPrdInfo 내 스마트옵션)
    options = []
    av_m = re.search(r'"available_values"\s*:\s*(\[.*?\])', html, re.DOTALL)
    if av_m:
        try:
            vals = json.loads(av_m.group(1))
            if vals:
                op_m = re.search(r'"option_prices"\s*:\s*(\{.*?\})', html, re.DOTALL)
                option_prices = {}
                if op_m:
                    try:
                        option_prices = json.loads(op_m.group(1))
                    except:
                        pass
                name_m = re.search(r'"option_name"\s*:\s*"([^"]+)"', html)
                option_name = name_m.group(1) if name_m else '옵션'
                options.append({
                    'name': option_name,
                    'values': vals,
                    'option_prices': option_prices
                })
        except:
            pass

    # ── 9. 이미지
    images = []
    og_img = soup.find('meta', property='og:image')
    if og_img and og_img.get('content'):
        img_url = og_img['content']
        if img_url.startswith('//'):
            img_url = 'https:' + img_url
        images.append(img_url)

    # script 내 cdn.011st.com 이미지 URL 수집 (600 이상 우선)
    img_matches = re.findall(r'https://cdn\.011st\.com/11dims/resize/\d+x\d+[^\s"\'\\>]+\.(?:jpg|jpeg|png|webp)[^\s"\'\\>]*', html)
    seen = set(images)
    for img_url in img_matches:
        # 이스케이프 문자 제거
        img_url = img_url.rstrip('\\')
        size_m = re.search(r'resize/(\d+)x(\d+)', img_url)
        if size_m:
            w = int(size_m.group(1))
            if w < 400:
                img_url = re.sub(r'resize/\d+x\d+', 'resize/600x600', img_url)
        if img_url not in seen:
            seen.add(img_url)
            images.append(img_url)
    images = images[:10]

    # ── 10. 스펙
    product_no_m = re.search(r'/products/(\d+)', url)
    specifications = None
    if product_no_m:
        specifications = _extract_specs(product_no_m.group(1))

    # ── 11. 재고
    if re.search(r'품절|sold.?out|일시품절', html, re.IGNORECASE):
        availability = 'out_of_stock'
    else:
        availability = 'in_stock'

    return {
        'title': title,
        'price_original': price_original,
        'price_discounted': price_discounted,
        'options': options,
        'images': images,
        'availability': availability,
        'seller': seller,
        'brand': brand,
        'shipping_fee': shipping_fee,
        'shipping_fee_text': shipping_fee_text,
        'delivery_date': delivery_date,
        'rating': rating,
        'review_count': review_count,
        'specifications': specifications,
    }


if __name__ == "__main__":
    import sys as _sys, json as _json
    _url = _sys.argv[1] if len(_sys.argv) > 1 else ""
    _result = scrape(_url)
    print(_json.dumps(_result, ensure_ascii=False))
