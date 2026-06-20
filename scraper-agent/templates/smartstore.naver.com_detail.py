# Template: smartstore.naver.com (detail)
# Generated: 2026-06-01T01:32:38.960Z
# Notes: 스마트스토어 상품 상세 페이지 스크레이퍼.
- 가격: del.v4swfx73Z2 (원가), span.weP_mymkqG (할인가)
- 옵션: ul.vuCQVdmISZ li a[role=option] → data-shp-contents-type (옵션명), data-shp-contents-id (옵션값)
- 이미지: og:image + li.wQbS3Q5MEC img → ?type=o1000 변환
- 판매자: span.n_SxvDlJ7T 또는 span.Gse77WNa5Q
- 재고: JSON "soldOut":true 패턴 검사

import requests
from bs4 import BeautifulSoup
import re


def scrape(url: str) -> dict:
    # 1. 페이지 수집
    resp = requests.post(
        "http://localhost:18080/collect/general",
        json={"url": url},
        timeout=30
    )
    data = resp.json()
    html = data.get("html", "")
    soup = BeautifulSoup(html, "html.parser")

    # ── 2. 제목 ───────────────────────────────────────────────────────────
    title = ""
    h3 = soup.select_one("h3.y67cdgB6Ve")
    if h3:
        title = h3.get_text(strip=True)
    if not title:
        og = soup.find("meta", property="og:title")
        if og:
            title = og.get("content", "").split(" : ")[0].strip()

    # ── 3. 가격 ───────────────────────────────────────────────────────────
    price_original = None
    price_discounted = None

    # 원가: <del class="v4swfx73Z2">37,600원</del>
    del_el = soup.select_one("del.v4swfx73Z2")
    if del_el:
        num = re.sub(r"[^\d]", "", del_el.get_text())
        if num:
            price_original = int(num)

    # 할인가: <span class="weP_mymkqG">25,500</span>
    sale_el = soup.select_one("span.weP_mymkqG")
    if sale_el:
        num = re.sub(r"[^\d]", "", sale_el.get_text())
        if num:
            price_discounted = int(num)

    # 할인 없는 경우 (일반가만 있을 때)
    if not price_original and not price_discounted:
        price_el = soup.select_one("span.weP_mymkqG")
        if price_el:
            num = re.sub(r"[^\d]", "", price_el.get_text())
            if num:
                price_original = int(num)

    # ── 4. 옵션 ───────────────────────────────────────────────────────────
    options = []
    option_groups = {}  # {옵션명: [값, ...]}

    # ul.vuCQVdmISZ > li > a[role=option]
    # data-shp-contents-type: 옵션명, data-shp-contents-id: 옵션값
    for opt_li in soup.select("ul.vuCQVdmISZ li a[role='option']"):
        opt_type = opt_li.get("data-shp-contents-type", "옵션")
        opt_val_raw = opt_li.get("data-shp-contents-id", "").strip()
        if not opt_val_raw:
            opt_val_raw = opt_li.get_text(strip=True)

        # 부가 설명 제거: (품절), (+N원)
        opt_val = re.sub(r'\s*\(품절\)\s*', '', opt_val_raw).strip()
        opt_val = re.sub(r'\s*\(\+[\d,]+원\)\s*', '', opt_val).strip()
        opt_val = opt_val.strip()

        if opt_type not in option_groups:
            option_groups[opt_type] = []
        if opt_val and opt_val not in option_groups[opt_type]:
            option_groups[opt_type].append(opt_val)

    for opt_name, vals in option_groups.items():
        if vals:
            options.append({"name": opt_name, "values": vals})

    # ── 5. 이미지 ─────────────────────────────────────────────────────────
    images = []
    seen = set()

    # og:image (대표 이미지)
    og_img = soup.find("meta", property="og:image")
    if og_img:
        og_src = og_img.get("content", "")
        if og_src and og_src not in seen:
            seen.add(og_src)
            images.append(og_src)

    # 썸네일 목록: li.wQbS3Q5MEC img → 원본 해상도로 변환
    for img in soup.select("li.wQbS3Q5MEC img"):
        src = img.get("data-src") or img.get("src") or ""
        src_orig = re.sub(r'\?type=.*$', '?type=o1000', src) if src else src
        if "pstatic.net" in src_orig and src_orig not in seen:
            seen.add(src_orig)
            images.append(src_orig)

    # 메인 슬라이더 이미지 보완
    for img in soup.select("div.HzHE4Cmc8J img.JWwKITZmiu"):
        src = img.get("data-src") or img.get("src") or ""
        src_orig = re.sub(r'\?type=.*$', '?type=o1000', src) if src else src
        if "pstatic.net" in src_orig and src_orig not in seen:
            seen.add(src_orig)
            images.append(src_orig)

    # ── 6. 판매자 ─────────────────────────────────────────────────────────
    seller = ""
    seller_el = soup.select_one("span.n_SxvDlJ7T")
    if seller_el:
        seller = seller_el.get_text(strip=True)
    if not seller:
        seller_el2 = soup.select_one("span.Gse77WNa5Q")
        if seller_el2:
            seller = seller_el2.get_text(strip=True)
    if not seller:
        m = re.search(r'"storeName"\s*:\s*"([^"]+)"', html)
        if m:
            seller = m.group(1)

    # ── 7. 재고 ───────────────────────────────────────────────────────────
    availability = "unknown"
    if re.search(r'"soldOut"\s*:\s*true', html):
        availability = "out_of_stock"
    elif title or price_discounted or price_original:
        availability = "in_stock"

    return {
        "title": title,
        "price_original": price_original,
        "price_discounted": price_discounted,
        "options": options,
        "images": images[:10],
        "availability": availability,
        "seller": seller,
    }
