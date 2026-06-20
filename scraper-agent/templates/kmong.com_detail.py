# Template: kmong.com (detail)
# Generated: 2026-06-10T08:33:33.280Z
# Notes: 크몽 서비스 상세 페이지. chrome 모드 필요. 기본 정보는 api.kmong.com REST API에서 조회, 이미지/패키지 옵션은 HTML 파싱. 패키지(STANDARD/DELUXE/PREMIUM) 가격은 #gig-package-table 섹션에서 추출. 배송비 없음(디지털 서비스 플랫폼).

import requests
import re
from bs4 import BeautifulSoup

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'ko-KR,ko;q=0.9',
    'Accept': 'application/json',
    'Referer': 'https://kmong.com/',
}

def _extract_gig_id(url: str) -> str:
    m = re.search(r'/gig/(\d+)', url)
    return m.group(1) if m else None

def scrape(url: str) -> dict:
    gig_id = _extract_gig_id(url)
    if not gig_id:
        raise ValueError(f"URL에서 gig ID를 추출할 수 없습니다: {url}")

    # 크몽 API로 기본 정보 조회
    api_url = f"https://api.kmong.com/gig-app/gig/v1/gigs/{gig_id}/detail-modules?is_money_plus_path=false&clientType=DESKTOP"
    resp = requests.get(api_url, headers=HEADERS, timeout=15)
    data = resp.json()
    common = data.get("COMMON", {})

    # 제목
    title = common.get("title", "")

    # 가격 (COMMON.price = 최저가/STANDARD 패키지)
    price_discounted = common.get("price")
    price_discounted = int(price_discounted) if price_discounted is not None else None

    # 판매자
    user = common.get("user", {})
    seller = user.get("username") or user.get("nickname") or user.get("name") or None

    # 재고
    on_vacation = common.get("on_vacation", False)
    availability = "out_of_stock" if on_vacation else "in_stock"

    # HTML 수집 (이미지, 패키지 정보 추출)
    collect_resp = requests.post(
        "http://localhost:18080/collect/general",
        json={"url": url},
        timeout=60
    ).json()
    html = collect_resp.get("html", "")
    soup = BeautifulSoup(html, "html.parser")

    # 대표 이미지: 슬라이더 내 메인 이미지
    images = []
    for img in soup.select('img[alt="메인 이미지"]'):
        src = img.get("src", "")
        if src:
            clean_src = re.sub(r'\?.*$', '', src)
            if clean_src not in images:
                images.append(clean_src)

    # 상세 이미지
    for img in soup.select('img[alt^="상세이미지"]'):
        src = img.get("src", "")
        if src:
            clean_src = re.sub(r'\?.*$', '', src)
            if clean_src not in images:
                images.append(clean_src)

    # 패키지 옵션 추출 (가격 정보 섹션)
    options = []
    pkg_values = []
    price_original = None

    pkg_section = soup.select_one('#gig-package-table')
    if pkg_section:
        pkg_headers = pkg_section.select('.flex.min-h-\\[37px\\].basis-\\[176px\\].flex-col.items-center.justify-center.rounded-lg')
        for ph in pkg_headers:
            name_el = ph.select_one('p.typo-14')
            price_el = ph.select_one('p.typo-18')
            if name_el and price_el:
                name = name_el.get_text(strip=True)
                price_text = price_el.get_text(strip=True)
                price_m = re.search(r'([\d,]+)', price_text)
                if price_m:
                    price_val = int(price_m.group(1).replace(",", ""))
                    pkg_values.append(f"{name} ({price_val:,}원)")
                    if price_original is None or price_val > price_original:
                        price_original = price_val

    # 대안: 사이드바 탭에서 패키지명 추출
    if not pkg_values:
        sidebar_tabs = soup.select('button[type="button"] span.typo-16')
        for tab in sidebar_tabs:
            text = tab.get_text(strip=True)
            if text in ('STANDARD', 'DELUXE', 'PREMIUM'):
                pkg_values.append(text)

    if pkg_values:
        options.append({"name": "패키지", "values": pkg_values})

    # 크몽은 디지털 서비스 플랫폼이므로 배송비 없음
    shipping_fee = None
    shipping_fee_text = None

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
