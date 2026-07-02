# Template: item.gmarket.co.kr (detail)
# Generated: 2026-06-26T07:12:53.508Z
# Notes: 지마켓 상품 상세 페이지. chrome 모드 필요. 선추출 product_info 활용. 옵션은 클릭형(button.select-item_option). 배송비는 isFreeShipping 기반으로 무료/유료 판별.

import requests
import re
import json
from bs4 import BeautifulSoup


def _pick_api(net_log, *keywords):
    """network_log에서 키워드가 URL에 포함된 첫 번째 JSON 응답 반환"""
    for e in net_log or []:
        u = (e.get("url") or "")
        if any(k in u for k in keywords):
            body = e.get("body") or ""
            try:
                return json.loads(body)
            except Exception:
                continue
    return None


def _extract_options(soup):
    """옵션 영역에서 옵션 그룹/값 추출 (클릭형 드롭다운)"""
    options = []
    option_divs = soup.select('.section_option_area .item_options')
    for opt_div in option_divs:
        btn = opt_div.select_one('.select-item_option .txt')
        group_name = btn.get_text(strip=True) if btn else None
        # 열려있는 옵션 리스트 추출 시도
        li_items = opt_div.select('ul.list-options li')
        values = [li.get_text(strip=True) for li in li_items if li.get_text(strip=True)]
        if group_name:
            options.append({"name": group_name, "values": values})
    return options


def _extract_images(soup, goodscode, product_info):
    """메인 이미지 + 갤러리 이미지 수집 (최대 10장)"""
    images = []

    # product_info의 main_image_url 우선
    main_img = product_info.get('main_image_url', '')
    if main_img:
        if main_img.startswith('//'):
            main_img = 'https:' + main_img
        # 고해상도로 치환 (280 → 600)
        main_img = re.sub(r'/(\d+)\?', '/600?', main_img)
        images.append(main_img)

    # og:image
    og_img = soup.select_one('meta[property="og:image"]')
    if og_img and og_img.get('content'):
        img_url = og_img['content']
        if img_url.startswith('//'):
            img_url = 'https:' + img_url
        if img_url not in images:
            images.append(img_url)

    # 슬라이더/갤러리 이미지
    for img in soup.select('.item-photo img, .photo_slide img, .swiper-slide img, [class*="photo"] img'):
        src = img.get('src') or img.get('data-src') or img.get('data-original') or ''
        if src and 'gdimg.gmarket' in src:
            if src.startswith('//'):
                src = 'https:' + src
            src = re.sub(r'/(\d+)\?', '/600?', src)
            if src not in images:
                images.append(src)

    # goodscode 기반 이미지 (기본)
    if goodscode:
        base_img = f"https://gdimg.gmarket.co.kr/{goodscode}/still/600?ver=1782436689"
        if base_img not in images:
            images.insert(0, base_img)

    return images[:10]


def _extract_delivery_date(soup, product_info):
    """배송 도착 예정일 추출"""
    # product_info의 shipping_period 우선
    sp = product_info.get('shipping_period')
    if sp:
        return sp

    # HTML에서 도착 예정 안내 탐색
    for sel in ['.arrival-date', '.delivery_info', '[class*="arrival"]', '[class*="delivery"]']:
        el = soup.select_one(sel)
        if el:
            text = el.get_text(strip=True)
            if text and ('도착' in text or '발송' in text):
                return text
    return None


def _extract_seller(soup):
    """판매자 정보 추출"""
    for sel in ['.seller_store .title', '.info-seller .name', '[class*="seller"] .name',
                '.store_info .name', '.seller-info .name']:
        el = soup.select_one(sel)
        if el:
            return el.get_text(strip=True)
    return None


def _extract_rating_review(soup, net_log):
    """평점/리뷰 수 추출 (HTML 또는 network_log API)"""
    rating = None
    review_count = None

    # HTML 탐색
    for sel in ['[class*="starRate"] em', '[class*="star_rate"] em', '.rating em', '.star em']:
        el = soup.select_one(sel)
        if el:
            try:
                rating = float(el.get_text(strip=True))
                break
            except:
                pass

    for sel in ['[class*="reviewCount"]', '[class*="review_count"]', '.count_review', '.review_count']:
        el = soup.select_one(sel)
        if el:
            txt = el.get_text(strip=True)
            m = re.search(r'[\d,]+', txt)
            if m:
                try:
                    review_count = int(m.group().replace(',', ''))
                    break
                except:
                    pass

    # network_log에서 리뷰 API 탐색
    review_api = _pick_api(net_log, 'review', 'rvw', 'comment', 'score')
    if review_api and rating is None:
        rating = review_api.get('averageScore') or review_api.get('avgScore') or review_api.get('averageRating')
        if rating:
            try:
                rating = float(rating)
            except:
                rating = None

    if review_api and review_count is None:
        review_count = review_api.get('totalCount') or review_api.get('reviewCount') or review_api.get('count')
        if review_count:
            try:
                review_count = int(review_count)
            except:
                review_count = None

    return rating, review_count


def _extract_specifications(soup):
    """필수표기정보/상품 스펙 추출"""
    specs = {}
    # iframe 병합 영역
    full_html = str(soup)
    iframe_match = re.search(r'<!-- IFRAME.*?-->(.*)', full_html, re.DOTALL)
    if iframe_match:
        iframe_soup = BeautifulSoup(iframe_match.group(1), 'html.parser')
        for dl in iframe_soup.select('dl'):
            dts = dl.select('dt')
            dds = dl.select('dd')
            for dt, dd in zip(dts, dds):
                k = dt.get_text(strip=True)
                v = dd.get_text(strip=True)
                if k and v:
                    specs[k] = v
        for table in iframe_soup.select('table'):
            for row in table.select('tr'):
                cells = row.select('th, td')
                if len(cells) >= 2:
                    k = cells[0].get_text(strip=True)
                    v = cells[1].get_text(strip=True)
                    if k and v:
                        specs[k] = v
    return specs


def _extract_shipping(product_info, soup):
    """배송비 추출"""
    # product_info에서 우선 확인
    fee = product_info.get('shipping_fee')
    is_free = product_info.get('isFreeShipping')

    if fee == 0 or is_free is True or is_free == 'true':
        return 0, "무료배송"

    if isinstance(fee, (int, float)) and fee > 0:
        return int(fee), f"{int(fee):,}원"

    # HTML에서 배송비 탐색
    text = soup.get_text(" ", strip=True)
    area_m = re.search(r"배송비.{0,300}", text, re.DOTALL)
    area = area_m.group(0) if area_m else ""

    if re.search(r"무료\s*배송|배송\s*무료", area):
        return 0, "무료배송"

    combined = re.search(r"([\d,]+)\s*원[^(]{0,30}\(([^)]*[\d,]+\s*만?\s*원\s*이상[^)]*무료[^)]*)\)", area)
    if combined:
        f = int(combined.group(1).replace(',', ''))
        return f, combined.group(0).strip()

    fee_m = re.search(r"([\d,]+)\s*원", area)
    if fee_m:
        f = int(fee_m.group(1).replace(',', ''))
        return f, f"{fee_m.group(1)}원"

    return None, None


def scrape(url: str) -> dict:
    """지마켓 상품 상세 페이지 스크레이퍼"""
    data = requests.post(
        "http://localhost:18080/collect/general",
        json={"url": url},
        timeout=90
    ).json()

    html = data.get("html", "")
    net_log = data.get("network_log", [])
    product_info = data.get("product_info", {})

    soup = BeautifulSoup(html, 'html.parser')

    # goodscode 추출
    goodscode_m = re.search(r'goodscode=(\d+)', url, re.IGNORECASE)
    goodscode = goodscode_m.group(1) if goodscode_m else None

    # === [A] 필수 필드 ===
    # 제목
    title = product_info.get('title')
    if not title:
        og_title = soup.select_one('meta[property="og:title"]')
        title = og_title['content'] if og_title else None
    if not title:
        h1 = soup.select_one('h1.itemtit, h1.item-tit, .item-topinfo_headline h1')
        title = h1.get_text(strip=True) if h1 else None

    # 가격
    price_original = product_info.get('original_price')
    price_discounted = product_info.get('discounted_price')
    discount_rate = product_info.get('discount_rate')

    # 배송비
    shipping_fee, shipping_fee_text = _extract_shipping(product_info, soup)

    # === [B] 추가 필드 ===
    # 옵션 (클릭형: 기본 그룹명만 포함, 값은 빈 리스트)
    options = _extract_options(soup)

    # 이미지
    images = _extract_images(soup, goodscode, product_info)

    # 재고/구매 가능 여부
    sold_out = soup.select_one('.soldout, [class*="soldout"], .btn-soldout')
    availability = "out_of_stock" if sold_out else "in_stock"

    # 판매자
    seller = _extract_seller(soup)

    # 브랜드
    brand = product_info.get('brand')
    if not brand:
        brand_el = soup.select_one('[class*="brand"] .name, .brand_name, .item-brand')
        brand = brand_el.get_text(strip=True) if brand_el else None

    # 평점/리뷰
    rating, review_count = _extract_rating_review(soup, net_log)

    # 배송 도착 예정일
    delivery_date = _extract_delivery_date(soup, product_info)

    # 스펙
    specifications = _extract_specifications(soup)

    return {
        "title": title,
        "price_original": price_original,
        "price_discounted": price_discounted,
        "discount_rate": discount_rate,
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
    }


if __name__ == "__main__":
    import sys as _sys, json as _json
    _url = _sys.argv[1] if len(_sys.argv) > 1 else ""
    _result = scrape(_url)
    print(_json.dumps(_result, ensure_ascii=False))
