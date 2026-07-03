# Template: canmart.co.kr (detail)
# Generated: 2026-07-03T00:57:48.721Z
# Notes: 캔마트(makeshop 기반). chrome 모드 필요. 가격: input#price/disprice. 옵션: select.basic_option[label]. 갤러리: .swiper-slide img. 배송비: 페이지 텍스트에서 "배송비" 주변 파싱. 사이즈옵션은 색상 선택 후 JS로 채워지므로 크롬 클릭 필요(extra_clicks 참고).

import requests
from bs4 import BeautifulSoup
import re

def scrape(url: str) -> dict:
    data = requests.post("http://localhost:18080/collect/general", json={"url": url}, timeout=90).json()
    html = data.get("html", "")
    net_log = data.get("network_log", [])
    soup = BeautifulSoup(html, "html.parser")
    full_text = soup.get_text(" ", strip=True)

    # === title ===
    og_title = soup.find("meta", property="og:title")
    title = og_title["content"].strip() if og_title else None
    for suffix in [" - 캔마트쇼핑몰", " - 캔마트"]:
        if title and suffix in title:
            title = title.split(suffix)[0].strip()

    # === 가격 ===
    def _parse_price(el):
        if not el:
            return None
        v = re.sub(r"[^\d]", "", el.get("value", ""))
        return int(v) if v else None

    price_original   = _parse_price(soup.find("input", {"id": "price"}))
    price_discounted = _parse_price(soup.find("input", {"id": "disprice"}))
    if price_original and price_discounted and price_discounted >= price_original:
        price_discounted = None  # 할인가가 정가 이상이면 무시

    # === 옵션 (select.basic_option) ===
    options = []
    for sel in soup.find_all("select", class_="basic_option"):
        label = sel.get("label") or "옵션"
        values = []
        for opt in sel.find_all("option"):
            v = opt.get("value", "").strip()
            t = opt.get_text(strip=True)
            if v and "선택" not in t and t:
                values.append(t)
        if values:
            options.append({"name": label, "values": values})

    # === 이미지 ===
    images = []
    # 슬라이더 갤러리 이미지 우선
    for img in soup.select(".swiper-slide img, .multiImgList img"):
        src = img.get("src") or img.get("data-src") or ""
        if src and src not in images:
            images.append(src)
    # og:image 보조
    og_img = soup.find("meta", property="og:image")
    if og_img and og_img.get("content"):
        src = og_img["content"]
        if src.startswith("//"):
            src = "https:" + src
        if src not in images:
            images.append(src)
    # shopimages (썸네일 등)
    for img in soup.find_all("img"):
        src = img.get("src") or ""
        if "shopimages" in src:
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                src = "https://www.canmart.co.kr" + src
            if src not in images:
                images.append(src)
    images = [s for s in images if s][:10]

    # === 배송비 ===
    shipping_fee = None
    shipping_fee_text = None
    ship_m = re.search(r"배송비.{0,150}", full_text, re.DOTALL)
    if ship_m:
        area = ship_m.group(0)
        if re.search(r"무료", area):
            shipping_fee = 0
            shipping_fee_text = "무료배송"
        else:
            fm = re.search(r"([\d,]+)\s*원", area)
            if fm:
                shipping_fee = int(fm.group(1).replace(",", ""))
                shipping_fee_text = fm.group(1) + "원"

    # === 가용성 ===
    # "품절" 버튼/뱃지로만 판단 (설명 텍스트 오매칭 방지)
    availability = "in_stock"
    sold_el = soup.find(class_=re.compile(r"sold.?out|품절", re.I))
    if sold_el:
        availability = "out_of_stock"
    else:
        btn = soup.find("button")
        if btn and re.search(r"품절|sold.?out", btn.get_text(), re.I):
            availability = "out_of_stock"

    # === 배송 도착 예정일 ===
    delivery_date = None
    del_m = re.search(r"(오늘출발|내일출발|평균\s*\d+\s*[~\-]\s*\d+일)[^\n。]{0,50}", full_text)
    if del_m:
        delivery_date = del_m.group(0).strip()

    # === 판매자 ===
    seller = "캔마트"

    # === specifications ===
    specifications = {}
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) >= 2:
                k = cells[0].get_text(strip=True)
                v = cells[1].get_text(strip=True)
                if k and v and k not in ("네이버페이 구매하기",):
                    specifications[k] = v

    # === size ===
    size = requests.post("http://localhost:18080/extract/size", json={
        "title": title,
        "category": "패션/의류",
        "specs": specifications,
        "text": full_text[:5000],
        "images": images,
        "allow_ocr": False,
    }, timeout=30).json()

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
        "delivery_date": delivery_date,
        "size": size,
        "specifications": specifications,
    }


if __name__ == "__main__":
    import sys as _sys, json as _json
    _url = _sys.argv[1] if len(_sys.argv) > 1 else ""
    _result = scrape(_url)
    print(_json.dumps(_result, ensure_ascii=False))
