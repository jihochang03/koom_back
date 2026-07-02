# Template: ssg.com (detail)
# Generated: 2026-06-26T05:06:09.422Z
# Notes: SSG.COM 상품 상세 페이지 스크레이퍼. simple 모드(requests)로 수집 가능. 가격/옵션/브랜드는 HTML 내 JS 변수(uitemObj, orgPrc, salePrc, uitemOptnTypeNm, uitemOptnNm 등)에서 추출. 배송비는 dl.cdtl_delivery_fee에서 추출.

import requests
from bs4 import BeautifulSoup
import re

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'ko-KR,ko;q=0.9',
}


def _extract_shipping(soup):
    """배송비: .cdtl_delivery_fee 블록에서 추출"""
    dl = soup.select_one('dl.cdtl_delivery_fee')
    if dl:
        em = dl.select_one('em.ssg_price')
        if em:
            fee_txt = em.get_text(strip=True).replace(',', '')
            fee = int(fee_txt) if fee_txt.isdigit() else None
            full = dl.get_text(' ', strip=True)
            cond = re.search(r'\((.+?)\)', full)
            cond_txt = f" ({cond.group(1)})" if cond else ''
            return fee, f"{em.get_text(strip=True)}원{cond_txt}"
        full = dl.get_text(' ', strip=True)
        if '무료' in full:
            return 0, '무료배송'
    return None, None


def _extract_images(soup, html):
    """이미지 추출: itemImgUrl JS 변수 + uitemObj imgUrl + og:image"""
    seen = set()
    images = []

    def add_img(url):
        if not url:
            return
        url = url.strip()
        if url.startswith('//'):
            url = 'https:' + url
        # 저해상도 → 고해상도 변환
        url = re.sub(r'(_i\d+_)\d+(\.jpg)', r'\g<1>750\2', url)
        # 배너/아이콘 제외 (ssgcdn.com 도메인만 허용)
        if url not in seen and 'ssgcdn.com' in url and '/item/' in url:
            seen.add(url)
            images.append(url)

    # JS itemImgUrl (메인 이미지)
    m = re.search(r"itemImgUrl\s*:\s*'([^']+)'", html)
    if m:
        add_img(m.group(1))

    # og:image
    og = soup.select_one('meta[property="og:image"]')
    if og:
        add_img(og.get('content', ''))

    # uitemObj 내 imgUrl (썸네일 리스트)
    for im in re.findall(r"imgUrl\s*:\s*'([^']+)'", html):
        add_img(im)

    # HTML img 태그 (상품 썸네일)
    for img in soup.select('.cdtl_img_area img, .thumb_list img, [class*="thumb"] img'):
        for attr in ['src', 'data-src', 'data-original']:
            src = img.get(attr, '')
            if src and 'ssgcdn.com' in src and '/item/' in src:
                add_img(src)

    return images[:10]


def _extract_options(html):
    """uitemObj 블록에서 옵션 그룹·값 추출"""
    # 옵션 타입명 수집
    type_nms = {}
    for i in range(1, 6):
        found = re.search(rf"uitemOptnTypeNm{i}\s*:\s*'([^']*)'", html)
        if found and found.group(1):
            type_nms[i] = found.group(1)

    opt_values = {i: [] for i in type_nms}
    seen_vals = {i: set() for i in type_nms}

    # uitemObj 블록에서 옵션값 수집
    for block in re.finditer(r'uitemObj\s*=\s*\{.*?\};', html, re.DOTALL):
        blk = block.group(0)
        for i in type_nms:
            nm_m = re.search(rf"uitemOptnNm{i}\s*:\s*'([^']*)'", blk)
            if nm_m and nm_m.group(1):
                val = nm_m.group(1).strip()
                if val and val not in seen_vals[i]:
                    seen_vals[i].add(val)
                    opt_values[i].append(val)

    options = []
    for i, type_nm in sorted(type_nms.items()):
        if opt_values[i]:
            options.append({'name': type_nm, 'values': opt_values[i]})
    return options


def _extract_delivery_date(soup):
    """배송 도착 예정일"""
    for el in soup.select('.arrival_date, [class*="arrival"], [class*="expect_delivery"]'):
        txt = el.get_text(' ', strip=True)
        if txt:
            return txt
    full = soup.get_text(' ', strip=True)
    m = re.search(r'(내일|오늘|모레)[^\n]{0,50}도착', full)
    if m:
        return m.group(0).strip()
    return None


def scrape(url: str) -> dict:
    resp = requests.get(url, headers=HEADERS, timeout=15)
    html = resp.text
    soup = BeautifulSoup(html, 'html.parser')

    # ── 제목 ──
    title = None
    nm_m = re.search(r"itemNm\s*:\s*'([^']+)'", html)
    if nm_m:
        title = nm_m.group(1).strip()
    if not title:
        el = soup.select_one('.cdtl_item_tit')
        if el:
            title = el.get_text(' ', strip=True)
    if not title:
        og = soup.select_one('meta[property="og:title"]')
        if og:
            title = og.get('content', '').replace(' - SSG.COM', '').strip()

    # ── 가격 ──
    price_original = None
    price_discounted = None

    # JS 원가/할인가 변수 (단따옴표 형식)
    orig_m = re.search(r"orgPrc\s*:\s*'([\d,]+)'", html)
    disc_m = re.search(r"salePrc\s*:\s*'([\d,]+)'", html)
    if orig_m:
        price_original = int(orig_m.group(1).replace(',', ''))
    if disc_m:
        price_discounted = int(disc_m.group(1).replace(',', ''))

    # bestAmt fallback
    if not price_discounted:
        best_m = re.search(r'bestAmt\s*[=:]\s*["\']?([\d,]+)', html)
        if best_m:
            price_discounted = int(best_m.group(1).replace(',', ''))

    # sellprc URL 파라미터 fallback
    if not price_discounted:
        sellprc_m = re.search(r'sellprc=(\d+)', html)
        if sellprc_m:
            price_discounted = int(sellprc_m.group(1))

    # HTML 가격 태그 fallback
    if not price_original:
        del_el = soup.select_one('.cdtl_price del, em.origin_price')
        if del_el:
            m = re.search(r'([\d,]+)', del_el.get_text())
            if m:
                price_original = int(m.group(1).replace(',', ''))
    if not price_discounted:
        sale_el = soup.select_one('.cdtl_price strong, em.sale_price')
        if sale_el:
            m = re.search(r'([\d,]+)', sale_el.get_text())
            if m:
                price_discounted = int(m.group(1).replace(',', ''))

    # ── 배송비 ──
    shipping_fee, shipping_fee_text = _extract_shipping(soup)

    # ── 이미지 ──
    images = _extract_images(soup, html)

    # ── 옵션 ──
    options = _extract_options(html)

    # ── 판매자 ──
    seller = None
    str_m = re.search(r"strNm\s*:\s*'([^']+)'", html)
    if str_m:
        seller = str_m.group(1)
    if not seller:
        el = soup.select_one('.cdtl_store_name, [class*="seller_name"]')
        if el:
            seller = el.get_text(strip=True)

    # ── 재고 ──
    availability = 'in_stock'
    # 명확한 품절 신호만 감지 (soldOutYn: 'Y' 형태)
    if re.search(r"soldOutYn\s*:\s*'Y'", html) or re.search(r'class="cdtl_soldout"', html):
        availability = 'out_of_stock'

    # ── 배송 도착일 ──
    delivery_date = _extract_delivery_date(soup)

    # ── 평점·리뷰 ──
    rating = None
    review_count = None
    rv_m = re.search(r'avgScore\s*[=:]\s*["\']?([\d.]+)', html)
    cnt_m = re.search(r'rvwCnt\s*[=:]\s*["\']?([\d,]+)', html)
    if rv_m:
        rating = float(rv_m.group(1))
    if cnt_m:
        review_count = int(cnt_m.group(1).replace(',', ''))

    # ── 브랜드 ──
    brand = None
    brand_m = re.search(r"brandNm\s*:\s*'([^']+)'", html)
    if brand_m:
        brand = brand_m.group(1)

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
        'delivery_date': delivery_date,
        'rating': rating,
        'review_count': review_count,
        'brand': brand,
    }


if __name__ == "__main__":
    import sys as _sys, json as _json
    _url = _sys.argv[1] if len(_sys.argv) > 1 else ""
    _result = scrape(_url)
    print(_json.dumps(_result, ensure_ascii=False))
