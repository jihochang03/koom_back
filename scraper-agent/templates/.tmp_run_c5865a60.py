import sys; sys.stdout.reconfigure(encoding='utf-8'); sys.stderr.reconfigure(encoding='utf-8')

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
    price_original = None
    price_discounted = None

    # .price-box 영역에서 추출
    price_box = soup.find(class_='price-box')
    if price_box:
        # 정가: span.sell > strong
        sell_tag = price_box.find('span', class_='sell')
        if sell_tag:
            m = re.search(r'([\d,]+)', sell_tag.get_text())
            if m:
                price_original = int(m.group(1).replace(',', ''))

        # 할인가: span.p2 (첫 번째 = 가격, 두 번째 = 퍼센트)
        p2_tags = price_box.find_all('span', class_='p2')
        for tag in p2_tags:
            text = tag.get_text(strip=True)
            m = re.search(r'^([\d,]+)$', text)  # 숫자만 있는 것 = 가격
            if m:
                price_discounted = int(m.group(1).replace(',', ''))
                break

    # 폴백: script 내 sell_price / dc_price
    if price_original is None:
        for sc in soup.find_all('script'):
            t = sc.get_text()
            m = re.search(r"sell_price\s*[=:]\s*['\"]?(\d+)", t)
            if m:
                price_original = int(m.group(1))
            m2 = re.search(r"dc_price\s*[=:]\s*['\"]?(\d+)", t)
            if m2 and int(m2.group(1)) > 0:
                price_discounted = int(m2.group(1))

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
        combined = re.search(r'([\d,]+)\s*원[^(]{0,30}\(([^)]*[\d,]+\s*만?\s*원\s*이상[^)]*무료[^)]*)\)', area)
        if combined:
            shipping_fee = int(combined.group(1).replace(',', ''))
            shipping_fee_text = combined.group(0).strip()
        else:
            m = re.search(r'([\d,]+)\s*원', area)
            if m:
                shipping_fee = int(m.group(1).replace(',', ''))
                shipping_fee_text = m.group(0).strip()

    # ── options ──
    options = []
    for sel in soup.find_all('select', attrs={'name': re.compile(r'^op\d')}):
        opt_name = sel.get('name', '')
        values = []
        for opt in sel.find_all('option'):
            val = opt.get('value', '')
            text = opt.get_text(strip=True)
            if val and text and '선택' not in text:
                values.append(text)
        if values:
            options.append({'name': opt_name, 'values': values})

    # ── images ──
    images = []
    og_img = soup.find('meta', property='og:image')
    if og_img:
        img_url = og_img.get('content', '')
        if img_url.startswith('//'):
            img_url = 'https:' + img_url
        if img_url:
            images.append(img_url)

    m_id = re.search(r'index_no=(\d+)', url)
    if m_id:
        goods_id = m_id.group(1)
        all_imgs = re.findall(
            r'((?:https?:)?//atimg\.sonyunara\.com/files/attrangs/goods/' + goods_id + r'/[^\s"\']+)',
            html
        )
        seen = set(images)
        for img in all_imgs:
            full = 'https:' + img if img.startswith('//') else img
            if full not in seen:
                images.append(full)
                seen.add(full)

    # ── availability ──
    availability = 'in_stock'
    if re.search(r'품절|sold.?out', text_all, re.IGNORECASE):
        availability = 'out_of_stock'

    # ── seller / brand ──
    seller = '아뜨랑스'
    brand = '아뜨랑스'

    # ── delivery_date ──
    delivery_date = None
    d_m = re.search(r'(오늘|내일|모레)[^도착]{0,20}도착', text_all)
    if d_m:
        delivery_date = d_m.group(0).strip()

    # ── specifications ──
    specifications = {}
    info_table = soup.find('table', class_=re.compile(r'info|spec|필수'))
    if info_table:
        for row in info_table.find_all('tr'):
            th = row.find('th')
            td = row.find('td')
            if th and td:
                specifications[th.get_text(strip=True)] = td.get_text(strip=True)

    # ── size ──
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
        'specifications': specifications,
        'size': size,
    }


if __name__ == "__main__":
    _url = sys.argv[1] if len(sys.argv) > 1 else ""
    _r = scrape(_url)
    print(__import__("json").dumps(_r, ensure_ascii=False, indent=2))
