# Template: joamom.co.kr (detail)
# Generated: 2026-07-03T15:55:57.525Z
# Notes: joamom.co.kr 쇼핑몰 상세 페이지. EUC-KR 인코딩 필수. 가격은 .price01(할인가)/.price02(정가) CSS 셀렉터 우선, JS 변수 fallback. 옵션은 JS var optionJsonData 정규식 파싱(sto_state로 품절 판별). 이미지는 JSON-LD image 배열 우선+이벤트 배너 필터링. 이미지 URL joamom.co.kr//joamom.jpg2.kr// 이중 슬래시 보정. specifications는 JSON-LD description에서 마지막 ']' 이후 텍스트 파싱. 무료배송 사이트. simple mode로 수집 가능.

# Template: joamom.co.kr (detail)
# Notes: joamom.co.kr 쇼핑몰 상세 페이지.
#        - EUC-KR 인코딩 필수(resp.encoding='euc-kr')
#        - 가격: .price01(할인가) / .price02(정가) CSS 우선, JS 변수 fallback
#        - 옵션: JS var optionJsonData 정규식 파싱 (sto_state로 품절 판별)
#        - 이미지: JSON-LD image 배열 우선 + 이벤트 배너 필터링(_is_product_image)
#        - 이미지 URL joamom.co.kr//joamom.jpg2.kr// 이중 슬래시 보정
#        - specifications: JSON-LD description에서 마지막 ']' 이후 텍스트 파싱
#        - 무료배송 사이트. simple mode로 수집 가능.

import requests
import re
import json
from bs4 import BeautifulSoup

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'ko-KR,ko;q=0.9',
}


def _fix_image_url(url):
    """이미지 URL 보정: 이중슬래시(joamom.co.kr//joamom.jpg2.kr) → https://joamom.jpg2.kr/..."""
    if not url:
        return url
    url = re.sub(
        r'https?://[^/]+//([^/]+)(//|/)(.+)',
        lambda m: 'https://' + m.group(1) + '/' + m.group(3),
        url, flags=re.IGNORECASE
    )
    url = re.sub(r'([^:])//+', r'\1/', url)
    if url.startswith('//'):
        url = 'https:' + url
    url = url.replace(' ', '%20')
    return url


def _is_product_image(url: str) -> bool:
    """이벤트 배너, 아이콘, 버튼 등 비상품 이미지 제외"""
    exclude_patterns = [
        'event_bn', 'banner', '_btn', '_icon', 'favicon',
        'mobile_web_icon', 'all_og_', 'shopimages/yamiyami',
        '_scroll', '_top_ct', '_logo',
    ]
    url_lower = url.lower()
    return not any(p in url_lower for p in exclude_patterns)


def _parse_price(text: str):
    """텍스트에서 숫자만 추출 (콤마 제거)"""
    m = re.search(r'[\d,]+', text.replace(' ', ''))
    return int(m.group(0).replace(',', '')) if m else None


def _extract_prices(soup, html):
    """
    가격 추출 우선순위:
    1. .price01 (할인가) / .price02 (정가) — joamom 표준 패턴
       price01=낮은 값(할인가), price02=높은 값(정가)
    2. JS var product_price / discount_price 변수 (fallback)
    반환: (price_original, price_discounted)
    """
    price_original = None
    price_discounted = None

    p01 = soup.select_one('p.price01, .price01')
    p02 = soup.select_one('p.price02, .price02')

    val01 = _parse_price(p01.get_text()) if p01 else None
    val02 = _parse_price(p02.get_text()) if p02 else None

    if val01 and val02:
        price_discounted = min(val01, val02)
        price_original   = max(val01, val02)
    elif val01:
        price_original = val01
    elif val02:
        price_original = val02

    # fallback: JS 변수
    if price_original is None:
        m = re.search(r"var\s+product_price\s*=\s*'(\d+)'", html)
        if m:
            price_original = int(m.group(1))

    if price_discounted is None and price_original:
        disc_m = re.search(r'(?:discount_price|sale_price|discountprice)\s*[=:]\s*[\'"]?(\d+)', html)
        if disc_m:
            disc = int(disc_m.group(1))
            if disc < price_original:
                price_discounted = disc

    return price_original, price_discounted


def _extract_options(html: str):
    """optionJsonData JS 변수에서 옵션 목록 추출 (sto_state로 품절 판별)"""
    m = re.search(r'var\s+optionJsonData\s*=\s*(\{.+?\});\s*\n', html, re.DOTALL)
    if not m:
        return []
    raw = m.group(1)

    seen_names: dict = {}
    for entry in re.finditer(r"opt_name:'([^']+)',.*?opt_value:'([^']+)'", raw, re.DOTALL):
        name = entry.group(1)
        values_raw = entry.group(2).split(',')
        if name not in seen_names:
            seen_names[name] = []
        for v in values_raw:
            v = v.strip()
            if v and v not in seen_names[name]:
                seen_names[name].append(v)

    soldout_map: dict = {}
    for entry in re.finditer(
        r"opt_name:'([^']+)',.*?opt_values:'([^']+)',.*?sto_state:'([^']+)'", raw, re.DOTALL
    ):
        name = entry.group(1)
        opt_vals = [v.strip() for v in entry.group(2).split(',')]
        state = entry.group(3)
        if name not in soldout_map:
            soldout_map[name] = {}
        for v in opt_vals:
            if v and v not in soldout_map[name]:
                soldout_map[name][v] = state

    options = []
    for name, vals in seen_names.items():
        soldout_vals = []
        if name in soldout_map:
            for v in vals:
                st = soldout_map[name].get(v, 'SALE')
                if st != 'SALE':
                    soldout_vals.append(v)
        opt = {"name": name, "values": vals}
        if soldout_vals:
            opt["soldout_values"] = soldout_vals
        options.append(opt)

    return options


def _extract_shipping(soup, text):
    """배송비 추출"""
    area_m = re.search(r"배송비.{0,300}", text, re.DOTALL)
    area = area_m.group(0) if area_m else text

    if re.search(r'무료\s*배송|배송\s*무료', area):
        return 0, "무료배송"

    combined = re.search(
        r'([\d,]+)\s*원[^(]{0,30}([^)]*[\d,]+\s*만?\s*원\s*이상[^)]*무료[^)]*)', area
    )
    if combined:
        fee = int(combined.group(1).replace(',', ''))
        return fee, combined.group(0).strip()

    cond = re.search(r'([\d,]+만?\s*원)\s*이상.*?무료', area)
    if cond:
        return None, cond.group(0).strip()

    m_fee = re.search(r'([\d,]+)\s*원', area)
    if m_fee:
        fee = int(m_fee.group(1).replace(',', ''))
        return fee, f"{m_fee.group(1)}원"

    return None, None


def _parse_specifications(ld_desc: str) -> dict:
    """
    JSON-LD description에서 스펙 파싱.
    형태: "[[상품명] 소재..." → rfind(']')로 마지막 ']' 이후 내용만 추출.
    """
    if not ld_desc:
        return {}
    idx = ld_desc.rfind(']')
    raw_spec = ld_desc[idx + 1:].strip() if idx >= 0 else ld_desc.strip()
    if not raw_spec:
        return {}
    specs = {}
    if ':' in raw_spec and '/' in raw_spec:
        for part in re.split(r'\s*/\s*', raw_spec):
            kv = part.split(':', 1)
            if len(kv) == 2 and kv[0].strip():
                specs[kv[0].strip()] = kv[1].strip()
    elif '%' in raw_spec or '소재' in raw_spec or re.search(r'[\w가-힣]+\s+\d+', raw_spec):
        specs['소재'] = raw_spec
    elif raw_spec:
        specs['설명'] = raw_spec
    return specs


def scrape(url: str) -> dict:
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.encoding = 'euc-kr'   # 반드시 EUC-KR로 디코딩
    html = resp.text
    soup = BeautifulSoup(html, 'html.parser')

    # ── 제목
    title = None
    og_title = soup.find('meta', property='og:title')
    if og_title:
        t = og_title.get('content', '')
        title = t.split(' - ', 1)[1].strip() if ' - ' in t else t.strip()
    if not title:
        h1 = soup.find('h1')
        if h1:
            title = h1.get_text(strip=True)

    # ── 가격 (.price01/.price02 우선, JS 변수 fallback)
    price_original, price_discounted = _extract_prices(soup, html)

    # ── 이미지
    images = []
    ld_script = soup.find('script', type='application/ld+json')
    if ld_script:
        try:
            ld = json.loads(ld_script.string)
            for img in ld.get('image', []):
                fixed = _fix_image_url(img)
                if fixed and _is_product_image(fixed) and fixed not in images:
                    images.append(fixed)
        except Exception:
            pass
    if len(images) < 3:
        for img_tag in soup.select('img[src]'):
            src = img_tag.get('src', '')
            if 'joamom.jpg2.kr' in src:
                fixed = _fix_image_url(src)
                if fixed and _is_product_image(fixed) and fixed not in images and len(images) < 10:
                    images.append(fixed)

    # ── 배송비
    text = soup.get_text(" ", strip=True)
    shipping_fee, shipping_fee_text = _extract_shipping(soup, text)

    # ── 옵션
    options = _extract_options(html)

    # ── 가용성
    availability = "in_stock"
    if soup.select_one('.sold-out, .soldout') or re.search(r'전체.*?품절', text):
        availability = "out_of_stock"

    # ── 판매자·브랜드
    seller = "조아맘"
    brand = None

    # ── 배송 예정일
    delivery_date = None

    # ── 스펙(필수표기정보)
    specifications = {}
    if ld_script:
        try:
            ld_desc = json.loads(ld_script.string).get('description', '')
            specifications = _parse_specifications(ld_desc)
        except Exception:
            pass

    # ── 사이즈
    size = requests.post("http://localhost:18080/extract/size", json={
        "title": title or "",
        "category": "의류",
        "specs": specifications,
        "text": text[:5000],
        "images": images,
        "allow_ocr": False,
    }, timeout=30).json()

    if size.get("girth_sum_cm") is None and size.get("confidence") in ("LOW", "MEDIUM") and images:
        size = requests.post("http://localhost:18080/extract/size", json={
            "title": title or "",
            "category": "의류",
            "specs": specifications,
            "text": "",
            "images": images,
            "allow_ocr": True,
        }, timeout=40).json()

    return {
        "title": title,
        "price_original": price_original,
        "price_discounted": price_discounted,
        "options": options,
        "images": images[:10],
        "availability": availability,
        "seller": seller,
        "brand": brand,
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
