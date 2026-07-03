# Template: hago.kr (detail)
# Generated: 2026-07-03T05:45:06.207Z
# Notes: 하고(hago.kr) 상세 페이지 스크레이퍼.
- access_method: chrome (옵션 API 네트워크 로그 필요)
- 제목: og:title에서 "- HAGO" 이하 제거
- 가격: p.text_price > del(원가) / strong(판매가). 옵션 API _price로 보완
- 이미지: HTML 전체에서 view_N.jpg 정규식 패턴으로 10장 추출 (쿼리스트링 제거, 중복 제거)
  ※ thumbnail buttons의 data-preload는 JSON 파싱 불안정 → 정규식으로 교체
- 옵션: /goods/detail/{id}/options API (network_log 우선, fallback 직접 호출)
  - 1단계: options[i]._name=색상, sub[j]._name=사이즈, _qty=재고
  - 2단계: options[i].sub[j].sub 있으면 색상+사이즈 분리
  - FREE 단독 옵션은 제외
- 배송비: .m_prodetail-head-info 텍스트 파싱 ("배송비 N원 무료배송 조건 N원")
- 브랜드: [class*="brand"] 첫 번째 텍스트
- 판매자: 브랜드명과 동일 (별도 표기 없음)
- 평점: [class*="rating"] aria-label 또는 텍스트
- 리뷰수: 페이지 텍스트에서 "리뷰 N" 또는 "후기 N" 패턴
- 품절: .btn_soldout / .m_prodetail-soldout

import requests
import re
import json
from bs4 import BeautifulSoup

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'ko-KR,ko;q=0.9',
}


def _pick_api(net_log, *keywords):
    """network_log에서 url에 keyword가 포함된 첫 JSON 응답을 dict로 반환."""
    for e in net_log or []:
        u = (e.get("url") or "")
        if any(k in u for k in keywords):
            body = e.get("body") or ""
            try:
                return json.loads(body)
            except Exception:
                continue
    return None


def _extract_images(soup, html):
    """이미지 추출: view_N.jpg 정규식 패턴 (전체 갤러리 최대 10장)."""
    # HTML 전체에서 view_N.jpg 패턴으로 순서 유지 중복 제거
    urls = re.findall(r'https://image\.hago\.kr/mall/goods/[\d/]+/view_\d+\.[a-z]+', html)
    images = list(dict.fromkeys(urls))  # 순서 유지 중복 제거
    if images:
        return images
    # fallback: og:image
    og = soup.select_one('meta[property="og:image"]')
    if og:
        src = og.get('content', '')
        if src:
            return [src.split('?')[0]]
    return []


def _extract_review_info(soup):
    """평점·리뷰수 추출."""
    rating = None
    review_count = None

    # 리뷰수: "리뷰 N" 또는 "후기 N" 패턴
    text = soup.get_text(' ', strip=True)
    m_rv = re.search(r'리뷰\s*\(?\s*([\d,]+)\s*\)?', text)
    if m_rv:
        review_count = int(m_rv.group(1).replace(',', ''))
    if review_count is None:
        m_rv2 = re.search(r'후기\s*\(?\s*([\d,]+)\s*\)?', text)
        if m_rv2:
            review_count = int(m_rv2.group(1).replace(',', ''))

    # 평점: [class*="rating"] aria-label 또는 텍스트
    rating_el = soup.select_one('[class*="rating"], [class*="star"]')
    if rating_el:
        m = re.search(r'(\d+\.?\d*)', rating_el.get('aria-label', '') or rating_el.get_text())
        if m:
            rating = float(m.group(1))

    return rating, review_count


def _extract_options(net_log, url):
    """네트워크 로그 또는 API 직접 호출로 옵션 추출."""
    opt_data = _pick_api(net_log, '/options')
    if not opt_data:
        gid = re.search(r'/goods/detail/(\d+)', url)
        if gid:
            h = {**HEADERS, 'Referer': url, 'X-Requested-With': 'XMLHttpRequest'}
            try:
                r = requests.get(
                    f"https://www.hago.kr/goods/detail/{gid.group(1)}/options",
                    headers=h, timeout=15
                )
                opt_data = r.json()
            except Exception:
                pass
    if not opt_data or 'options' not in opt_data:
        return []

    raw_opts = opt_data.get('options', [])
    options = []

    # 2단계 옵션: options[i].sub[j].sub 존재 → 색상 + 사이즈
    if (raw_opts
            and raw_opts[0].get('sub')
            and raw_opts[0]['sub']
            and raw_opts[0]['sub'][0].get('sub')):
        color_vals, color_soldout = [], []
        size_vals, size_soldout   = [], []
        for color_item in raw_opts:
            cname = color_item.get('_name', '')
            if cname:
                color_vals.append(cname)
                if all(s.get('_qty', 0) <= 0 for s in color_item.get('sub', [])):
                    color_soldout.append(cname)
            for size_item in color_item.get('sub', []):
                sname = size_item.get('_name', '')
                if sname and sname not in size_vals:
                    size_vals.append(sname)
                if size_item.get('_qty', 0) <= 0 and sname not in size_soldout:
                    size_soldout.append(sname)
        if color_vals:
            o = {"name": "색상", "values": color_vals}
            if color_soldout:
                o["soldout_values"] = color_soldout
            options.append(o)
        if size_vals:
            o = {"name": "사이즈", "values": size_vals}
            if size_soldout:
                o["soldout_values"] = size_soldout
            options.append(o)
    else:
        # 1단계: options[i]._name = 색상(그룹), sub[j]._name = 사이즈
        color_vals, color_soldout = [], []
        size_vals, size_soldout   = [], []
        for group in raw_opts:
            gname = group.get('_name', '')
            if gname and gname not in color_vals:
                color_vals.append(gname)
            for sub in group.get('sub', []):
                sname = sub.get('_name', '')
                qty   = sub.get('_qty', 0)
                if sname and sname not in size_vals:
                    size_vals.append(sname)
                if qty <= 0 and sname not in size_soldout:
                    size_soldout.append(sname)
        # 의미 있는 옵션만 추가 (FREE·빈값 단독은 제외)
        has_real_color = len(color_vals) > 1 or (
            len(color_vals) == 1 and color_vals[0] not in ('FREE', ''))
        has_real_size  = len(size_vals) > 1 or (
            len(size_vals)  == 1 and size_vals[0]  not in ('FREE', ''))
        if has_real_color:
            o = {"name": "색상", "values": color_vals}
            if color_soldout:
                o["soldout_values"] = color_soldout
            options.append(o)
        if has_real_size:
            o = {"name": "사이즈", "values": size_vals}
            if size_soldout:
                o["soldout_values"] = size_soldout
            options.append(o)
    return options


def _extract_shipping(soup):
    """배송비 추출 (.m_prodetail-head-info)."""
    head_info = soup.select_one('.m_prodetail-head-info')
    if not head_info:
        return None, None
    text = head_info.get_text(' ', strip=True)
    m_fee  = re.search(r'배송비\s*([\d,]+)\s*원', text)
    m_free = re.search(r'무료배송\s*조건\s*([\d,]+)\s*원', text)
    if m_fee:
        fee = int(m_fee.group(1).replace(',', ''))
        if m_free:
            free_int = int(m_free.group(1).replace(',', ''))
            fee_text = f"{m_fee.group(1)}원 ({free_int // 10000}만원 이상 무료배송)"
        else:
            fee_text = f"{m_fee.group(1)}원"
        return fee, fee_text
    if '무료배송' in text:
        return 0, "무료배송"
    return None, None


def scrape(url: str) -> dict:
    # chrome 모드로 수집 (옵션 API 네트워크 로그 필요)
    data    = requests.post("http://localhost:18080/collect/general", json={"url": url}, timeout=90).json()
    html    = data.get("html", "")
    net_log = data.get("network_log", [])
    soup    = BeautifulSoup(html, 'html.parser')

    # ── 제목 (사이트명 제거) ──────────────────────────────────────
    title = None
    og_title = soup.select_one('meta[property="og:title"]')
    if og_title:
        raw   = og_title.get('content', '').strip()
        title = re.sub(r'\s*[-|]\s*HAGO.*$', '', raw, flags=re.IGNORECASE).strip()
    if not title:
        el = soup.select_one('p.text_product')
        if el:
            title = el.get_text(strip=True)

    # ── 가격 ─────────────────────────────────────────────────────
    price_original   = None
    price_discounted = None
    price_el = soup.select_one('p.text_price')
    if price_el:
        # 원가: <del> 태그
        del_el = price_el.select_one('del')
        if del_el:
            m = re.search(r'[\d,]+', del_el.get_text())
            if m:
                price_original = int(m.group().replace(',', ''))
        # 판매가: class 없는 <strong>
        for s in price_el.select('strong'):
            if not s.get('class'):
                m = re.search(r'[\d,]+', s.get_text())
                if m:
                    price_discounted = int(m.group().replace(',', ''))
                    break
    # 옵션 API에서 원가 보완
    opt_data_raw = _pick_api(net_log, '/options')
    if opt_data_raw and not price_original:
        api_price = opt_data_raw.get('_price')
        if api_price:
            price_original = int(api_price)
    # 할인가 == 원가면 할인 없음으로 처리
    if price_discounted and price_original and price_discounted == price_original:
        price_discounted = None

    # ── 이미지 (view_N.jpg 정규식 → og:image fallback) ──────────
    images = _extract_images(soup, html)

    # ── 옵션 ─────────────────────────────────────────────────────
    options = _extract_options(net_log, url)

    # ── 배송비 ───────────────────────────────────────────────────
    shipping_fee, shipping_fee_text = _extract_shipping(soup)

    # ── 브랜드 ───────────────────────────────────────────────────
    brand = None
    for el in soup.select('[class*="brand"]'):
        t = el.get_text(strip=True)
        if t and len(t) < 50:
            brand = t
            break

    # ── 판매자 ───────────────────────────────────────────────────
    seller = brand  # 하고는 판매자 = 브랜드명
    seller_el = soup.select_one('.m_prodetail-seller a')
    if seller_el:
        seller = seller_el.get_text(strip=True)

    # ── 평점·리뷰수 ──────────────────────────────────────────────
    rating, review_count = _extract_review_info(soup)

    # ── 가용성 ───────────────────────────────────────────────────
    availability = "in_stock"
    if soup.select_one('.btn_soldout, .m_prodetail-soldout'):
        availability = "out_of_stock"

    # ── 사이즈 추출 (/extract/size) ──────────────────────────────
    size = requests.post("http://localhost:18080/extract/size", json={
        "title":    title or "",
        "category": "의류",
        "specs":    {},
        "text":     soup.get_text(" ", strip=True)[:5000],
        "images":   images,
        "allow_ocr": False,
    }, timeout=30).json()

    # 치수 없고 신뢰도 낮으면 OCR 보강 (선택, 부피 과금 상품에만)
    if (size.get("girth_sum_cm") is None
            and size.get("confidence") in ("LOW", "MEDIUM")
            and images):
        size = requests.post("http://localhost:18080/extract/size", json={
            "title":    title or "",
            "category": "의류",
            "specs":    {},
            "text":     "",
            "images":   images,
            "allow_ocr": True,
        }, timeout=40).json()

    return {
        "title":             title,
        "price_original":    price_original,
        "price_discounted":  price_discounted,
        "brand":             brand,
        "seller":            seller,
        "rating":            rating,
        "review_count":      review_count,
        "images":            images,
        "options":           options,
        "shipping_fee":      shipping_fee,
        "shipping_fee_text": shipping_fee_text,
        "delivery_date":     None,
        "availability":      availability,
        "size":              size,
    }


if __name__ == "__main__":
    import sys as _sys, json as _json
    _url = _sys.argv[1] if len(_sys.argv) > 1 else ""
    _result = scrape(_url)
    print(_json.dumps(_result, ensure_ascii=False))
