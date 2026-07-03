# Template: attrangs.co.kr (detail)
# Generated: 2026-07-03T00:24:37.239Z
# Notes: 아뜨랑스 상세 페이지. simple requests로 수집 가능.
# 가격: .p3=원가(정가), .p2=할인판매가, meta product:price:amount / script 변수 보조, 역전 방지 로직 포함.
# 옵션: 색상=select[name="op1"] + .colorbox a[data-opname] 보완, 사이즈=ul.size li a[data-opname] 우선 (select[name="op2"]는 JS cascade라 빈 상태).
# 이미지: og:image + atimg.sonyunara.com/files/attrangs/goods/{id}/ 패턴으로 전체 수집.
# rating/review_count: onclick="tabmove('2')" div 내 span 파싱 (4.9 / 리뷰 212 형태).
# shipping_fee: "배송비 3500원이 별도로 부과됩니다" 패턴.
# specifications: table th/td + dl/dt/dd.
# availability: 옵션 전체 품절 여부 기반 판단.

import requests
from bs4 import BeautifulSoup
import re

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'ko-KR,ko;q=0.9',
}

COLLECTOR_URL = 'http://localhost:18080'


def scrape(url: str) -> dict:
    resp = requests.get(url, headers=HEADERS, timeout=15)
    html = resp.text
    soup = BeautifulSoup(html, 'html.parser')

    # ── title ──
    title = None
    og_title = soup.find('meta', property='og:title')
    if og_title:
        title = og_title.get('content', '').strip()
    if not title:
        h1 = soup.find('h1')
        if h1:
            title = h1.get_text(strip=True)

    # ── price ──
    # 구조: .p3 = 정가(원가), .p2 = 할인판매가, meta product:price:amount = 현재 판매가
    price_original = None
    price_discounted = None

    # 1순위: .p3(정가) / .p2(할인판매가) 구조
    p3_tag = soup.select_one('.p3')
    if p3_tag:
        m = re.search(r'([\d,]+)', p3_tag.get_text(strip=True))
        if m:
            price_original = int(m.group(1).replace(',', ''))

    p2_tag = soup.select_one('.p2')
    if p2_tag:
        m = re.search(r'([\d,]+)', p2_tag.get_text(strip=True))
        if m:
            val = int(m.group(1).replace(',', ''))
            if 1000 <= val <= 9999999:
                price_discounted = val

    # 2순위: meta product:price:amount (현재 판매가)
    meta_price = soup.find('meta', property='product:price:amount')
    if meta_price:
        try:
            meta_val = int(meta_price.get('content', '').strip())
            if price_original is None:
                price_original = meta_val
            elif price_discounted is None and meta_val != price_original:
                price_discounted = meta_val
        except Exception:
            pass

    # 3순위: script 변수 추출
    if price_original is None or price_discounted is None:
        for sc in soup.find_all('script'):
            text = sc.get_text()
            if price_original is None:
                m = re.search(r"sell_price\s*[=:]\s*['\"]?(\d+)", text)
                if m:
                    price_original = int(m.group(1))
            if price_discounted is None:
                m2 = re.search(r"dc_price\s*[=:]\s*['\"]?(\d+)", text)
                if m2 and int(m2.group(1)) > 0:
                    price_discounted = int(m2.group(1))

    # price_discounted가 price_original보다 크면 역전 수정
    if price_original and price_discounted and price_discounted > price_original:
        price_original, price_discounted = price_discounted, price_original

    # ── shipping_fee ──
    shipping_fee = None
    shipping_fee_text = None
    text_all = soup.get_text(' ', strip=True)
    area_m = re.search(r'배송비.{0,300}', text_all, re.DOTALL)
    area = area_m.group(0) if area_m else text_all

    if re.search(r'무료\s*배송|배송\s*무료', area):
        shipping_fee = 0
        shipping_fee_text = '무료배송'
    else:
        # 유료+조건부 무료 패턴
        combined = re.search(r'([\d,]+)\s*원[^(]{0,30}\(([^)]*[\d,]+\s*만?\s*원\s*이상[^)]*무료[^)]*)\)', area)
        if combined:
            shipping_fee = int(combined.group(1).replace(',', ''))
            shipping_fee_text = combined.group(0).strip()
        else:
            # "배송비 3500원이 별도로 부과됩니다" 일반 유료 패턴
            m_fee = re.search(r'([\d,]+)\s*원', area)
            if m_fee:
                fee_val = int(m_fee.group(1).replace(',', ''))
                if 1000 <= fee_val <= 99999:
                    shipping_fee = fee_val
                    shipping_fee_text = f'{m_fee.group(1)}원'

    # ── options ──
    # 구조: 색상은 select[name="op1"](hidden) + .colorbox a[data-opname]
    #       사이즈는 select[name="op2"]가 JS cascade라 정적 HTML에서 비어있음
    #       → ul.size li a[data-opname] 에서 직접 추출
    options = []

    # 색상 — hidden select[name="op1"] (이너상품 surcharge 텍스트 포함)
    color_values = []
    color_seen = set()
    color_sel = soup.find('select', attrs={'name': 'op1'})
    if color_sel:
        for opt in color_sel.find_all('option'):
            val = opt.get('value', '')
            text = opt.get_text(strip=True)
            if val and text and '선택' not in text:
                if text not in color_seen:
                    color_values.append(text)
                    color_seen.add(text)
    # select에 없으면 colorbox data-opname 보완
    for a in soup.select('.colorbox a[data-opname]'):
        opname = a.get('data-opname', '').strip()
        if opname and opname not in color_seen:
            color_values.append(opname)
            color_seen.add(opname)
    if color_values:
        options.append({'name': '색상', 'values': color_values})

    # 사이즈 — ul.size li a[data-opname] 우선 (select[name="op2"]는 cascade라 빈 상태)
    size_values = []
    size_seen = set()
    for a in soup.select('ul.size li a[data-opname], ul.size.optSelect li a[data-opname]'):
        opname = a.get('data-opname', '').strip()
        if opname and opname not in size_seen:
            size_values.append(opname)
            size_seen.add(opname)
    # li 방식으로 못 뽑으면 select[name="op2"] 폴백 (동적 로드 후 HTML 재캡처된 경우)
    if not size_values:
        size_sel = soup.find('select', attrs={'name': 'op2'})
        if size_sel:
            for opt in size_sel.find_all('option'):
                val = opt.get('value', '')
                text = opt.get_text(strip=True)
                if val and text and '선택' not in text and '먼저' not in text:
                    if text not in size_seen:
                        size_values.append(text)
                        size_seen.add(text)
    if size_values:
        options.append({'name': '사이즈', 'values': size_values})

    # op3 이상 추가 옵션
    for sel in soup.find_all('select', attrs={'name': re.compile(r'^op[3-9]')}):
        values = []
        for opt in sel.find_all('option'):
            val = opt.get('value', '')
            text = opt.get_text(strip=True)
            if val and text and '선택' not in text:
                values.append(text)
        if values:
            th_label = sel.get('name', '')
            tr = sel.find_parent('tr')
            if tr:
                th_el = tr.find('th')
                if th_el:
                    th_label = th_el.get_text(strip=True) or th_label
            options.append({'name': th_label, 'values': values})

    # ── images ──
    images = []
    og_img = soup.find('meta', property='og:image')
    if og_img:
        img_url = og_img.get('content', '')
        if img_url.startswith('//'):
            img_url = 'https:' + img_url
        if img_url:
            images.append(img_url)

    # 상품 ID 추출 후 해당 상품 이미지 모두 수집
    m_id = re.search(r'index_no=(\d+)', url)
    if m_id:
        goods_id = m_id.group(1)
        all_imgs = re.findall(
            r'((?:https?:)?//atimg\.sonyunara\.com/files/attrangs/goods/' + goods_id + r'/[^\s"\'<>]+)',
            html
        )
        seen = set(images)
        for img in all_imgs:
            full = 'https:' + img if img.startswith('//') else img
            # 쿼리스트링 제거
            clean = re.sub(r'\?.*$', '', full)
            if clean not in seen:
                images.append(clean)
                seen.add(clean)

    # ── availability ──
    # 상품 주요 영역에서만 품절 확인 (추천 상품 .soldout 제외)
    availability = 'in_stock'
    main_area = soup.select_one('#detail, .wrap_prd, .view_prd') or soup
    if re.search(r'품절|sold.?out', main_area.get_text(' ', strip=True), re.IGNORECASE):
        # 옵션이 있으면 전체 품절 여부로 판단
        all_opts = soup.select('select[name^="op"] option[value!=""]')
        if all_opts:
            all_soldout = all(
                '품절' in opt.get_text() or opt.get('disabled') for opt in all_opts
            )
            if all_soldout:
                availability = 'out_of_stock'
        else:
            availability = 'out_of_stock'

    # ── seller / brand ──
    seller = '아뜨랑스'
    brand = '아뜨랑스'

    # ── rating / review_count ──
    # onclick="tabmove('2')" div 내부: <span> 4.9 </span><span>리뷰 212</span> 패턴
    rating = None
    review_count = None
    tabmove_div = soup.find('div', onclick=re.compile(r"tabmove\('2'\)"))
    if tabmove_div:
        for sp in tabmove_div.find_all('span'):
            t = sp.get_text(strip=True)
            # 숫자만 있으면 별점
            if re.match(r'^[\d.]+$', t):
                try:
                    v = float(t)
                    if 0 <= v <= 5:
                        rating = v
                except Exception:
                    pass
            # "리뷰 212" 패턴
            m_rv = re.search(r'리뷰\s*(\d+)', t)
            if m_rv:
                review_count = int(m_rv.group(1))

    # 폴백: 텍스트 전체 별점/평점 패턴
    if rating is None:
        m_rt = re.search(r'별점\s*([\d.]+)|평점\s*([\d.]+)', text_all)
        if m_rt:
            try:
                rating = float(m_rt.group(1) or m_rt.group(2))
            except Exception:
                pass

    # ── delivery_date ──
    delivery_date = None
    d_m = re.search(r'(오늘|내일|모레)[^도착]{0,20}도착', text_all)
    if d_m:
        delivery_date = d_m.group(0).strip()

    # ── specifications ──
    specifications = {}
    # 필수정보고시 테이블 탐색
    for table in soup.find_all('table'):
        rows = table.find_all('tr')
        for row in rows:
            th = row.find('th')
            td = row.find('td')
            if th and td:
                key = th.get_text(strip=True)
                val = td.get_text(' ', strip=True)
                if key and val and len(key) < 50:
                    specifications[key] = val

    # dl/dt/dd 구조도 탐색
    if not specifications:
        for dl in soup.find_all('dl'):
            dts = dl.find_all('dt')
            dds = dl.find_all('dd')
            for dt, dd in zip(dts, dds):
                key = dt.get_text(strip=True)
                val = dd.get_text(' ', strip=True)
                if key and val:
                    specifications[key] = val

    # ── size ──
    size = _extract_size(title, images, specifications, soup.get_text(" ", strip=True)[:5000])

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


def _extract_size(title: str, images: list, specs: dict = None, text: str = '') -> dict:
    try:
        size = requests.post(f'{COLLECTOR_URL}/extract/size', json={
            'title': title or '',
            'category': '의류',
            'specs': specs or {},
            'text': text,
            'images': images or [],
            'allow_ocr': False,
        }, timeout=30).json()
        if size.get('girth_sum_cm') is None and size.get('confidence') in ('LOW', 'MEDIUM') and images:
            size = requests.post(f'{COLLECTOR_URL}/extract/size', json={
                'title': title or '', 'category': '의류', 'specs': specs or {},
                'text': '', 'images': images, 'allow_ocr': True,
            }, timeout=40).json()
        return size
    except Exception:
        return {}


if __name__ == "__main__":
    import sys as _sys, json as _json
    _url = _sys.argv[1] if len(_sys.argv) > 1 else ""
    _result = scrape(_url)
    print(_json.dumps(_result, ensure_ascii=False))
