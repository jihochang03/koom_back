# Template: mall.epost.go.kr (detail)
# Generated: 2026-07-03T03:10:11.108Z
# Notes: 우체국쇼핑 상품 상세 페이지. chrome 모드 필수. 가격은 .txtG1 em(판매가) / .txtG2 em(할인가) 직접 파싱. 평점(#satisfactionPt1)/리뷰수(#evlTotCnt1) HTML 렌더링. 옵션은 goodsOptnDetail API(network_log). 배송비: 무료배송 패턴.

import requests
from bs4 import BeautifulSoup
import re
import json

html_global = ""

def _pick_api(net_log, *keywords):
    for e in net_log or []:
        u = (e.get("url") or "")
        if any(k in u for k in keywords):
            body = e.get("body") or ""
            try:
                return json.loads(body)
            except Exception:
                continue
    return None

def _extract_images(soup):
    images = []
    og_img = soup.find("meta", property="og:image")
    if og_img:
        src = og_img.get("content", "").strip()
        if src:
            if src.startswith("//"):
                src = "https:" + src
            images.append(src)
    for a in soup.select("#thumbsnail a"):
        img = a.find("img")
        if not img:
            continue
        src = (img.get("src") or img.get("data-src") or "").strip()
        if not src:
            continue
        if src.startswith("//"):
            src = "https:" + src
        elif src.startswith("/"):
            src = "https://mall.epost.go.kr" + src
        if src not in images:
            images.append(src)
    for li in soup.select(".goodsImg ul li"):
        img = li.find("img")
        if not img:
            continue
        src = (img.get("src") or img.get("data-src") or "").strip()
        if not src:
            continue
        if src.startswith("//"):
            src = "https:" + src
        elif src.startswith("/"):
            src = "https://mall.epost.go.kr" + src
        if src not in images and "epost.go.kr" in src:
            images.append(src)
    for sel in [".img_big img", ".big_img img", ".main_img img", "#imgMain img",
                ".thumb_list img", ".img_thumbnail img"]:
        for img in soup.select(sel):
            src = (img.get("src") or img.get("data-src") or img.get("data-original") or "").strip()
            if not src:
                continue
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                src = "https://mall.epost.go.kr" + src
            if src not in images and "epost.go.kr" in src:
                images.append(src)
    return images[:10]

def _extract_options(soup, net_log):
    options = []
    optn_api = _pick_api(net_log, "goodsOptnDetail")
    if optn_api:
        for grp in (optn_api.get("goodsOptnGrpList") or []):
            grp_nm = grp.get("optnGrpNm", "옵션")
            vals = []
            for d in grp.get("optnDtailList", []):
                nm = d.get("optnDtailNm", "")
                prc = d.get("optnAddPrc", 0)
                if nm:
                    vals.append(f"{nm} (+{int(prc):,}원)" if prc and int(prc) > 0 else nm)
            if vals:
                options.append({"name": grp_nm, "values": vals})
        if options:
            return options
    for sel_el in soup.select("select[id*='optn'], select[name*='optn'], select.opt_select"):
        name_el = sel_el.get("title") or sel_el.get("aria-label") or "옵션"
        values = []
        for opt in sel_el.find_all("option"):
            val = opt.get_text(strip=True)
            ov = opt.get("value", "")
            if val and ov and not re.search(r"선택|={3,}|-{3,}|^0$", val):
                values.append(val)
        if values:
            options.append({"name": name_el, "values": values})
    return options

def _extract_shipping(soup, text):
    for sel in [".txtG4", "[class*='dlvr']"]:
        el = soup.select_one(sel)
        if el:
            t = el.get_text(" ", strip=True)
            if re.search(r"무료", t):
                return 0, "무료배송"
            combined = re.search(r"([\d,]+)\s*원[^(]{0,30}\(([^)]*이상[^)]*무료[^)]*)\)", t)
            if combined:
                f = int(combined.group(1).replace(",", ""))
                return f, combined.group(0).strip()
            m = re.search(r"([\d,]+)\s*원", t)
            if m:
                f = int(m.group(1).replace(",", ""))
                if f <= 10000:
                    return f, f"{m.group(1)}원"
    area_m = re.search(r"배송비.{0,300}", text, re.DOTALL)
    if area_m:
        area = area_m.group(0)
        if re.search(r"무료", area):
            return 0, "무료배송"
        combined = re.search(r"([\d,]+)\s*원[^(]{0,30}\(([^)]*이상[^)]*무료[^)]*)\)", area)
        if combined:
            f = int(combined.group(1).replace(",", ""))
            return f, combined.group(0).strip()
        m = re.search(r"([\d,]+)\s*원", area)
        if m:
            f = int(m.group(1).replace(",", ""))
            if f <= 10000:
                return f, f"{m.group(1)}원"
    if re.search(r"무료\s*배송|배송\s*무료", text):
        return 0, "무료배송"
    return None, None

def _extract_specs(soup):
    specifications = {}
    for table in soup.select("table"):
        for row in table.find_all("tr"):
            ths = row.find_all("th")
            tds = row.find_all("td")
            if ths and tds:
                key = ths[0].get_text(strip=True)
                val = tds[0].get_text(" ", strip=True)
                if key and val and len(key) < 40 and not re.match(r"^\d+$", key):
                    specifications[key] = val
    return specifications

def scrape(url: str) -> dict:
    global html_global
    data = requests.post("http://localhost:18080/collect/general", json={"url": url}, timeout=90).json()
    html = data.get("html", "")
    html_global = html
    net_log = data.get("network_log", [])
    product_info = data.get("product_info", {})

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    # title
    title = product_info.get("title", "")
    if not title:
        og_title = soup.find("meta", property="og:title")
        title = og_title.get("content", "").strip() if og_title else ""
    title = re.sub(r"^\[우체국쇼핑\]\s*", "", title).strip()

    # 가격: .txtG1 em(판매가), .txtG2 em(할인가)
    price_original = None
    price_discounted = None
    g1 = soup.select_one(".txtG1 em")
    g2 = soup.select_one(".txtG2 em")
    if g1:
        try:
            price_original = int(g1.get_text(strip=True).replace(",", ""))
        except ValueError:
            pass
    if g2:
        try:
            price_discounted = int(g2.get_text(strip=True).replace(",", ""))
        except ValueError:
            pass
    # fallback: product_info
    if not price_original:
        price_original = product_info.get("original_price") or product_info.get("price_original")
    if not price_discounted:
        price_discounted = product_info.get("discounted_price") or product_info.get("price_discounted")
    # fallback: 텍스트 파싱
    if not price_original and not price_discounted:
        for pat in [r"정가\s*([\d,]+)\s*원", r"소비자가\s*([\d,]+)\s*원", r"판매가\s*([\d,]+)\s*원"]:
            m = re.search(pat, text)
            if m:
                price_original = int(m.group(1).replace(",", ""))
                break
        for pat in [r"할인가\s*([\d,]+)\s*원"]:
            m = re.search(pat, text)
            if m:
                price_discounted = int(m.group(1).replace(",", ""))
                break
    if price_original and price_discounted and price_original == price_discounted:
        price_discounted = None

    # 이미지
    images = _extract_images(soup)

    # 배송비: product_info 우선, 없으면 HTML 파싱
    shipping_fee = product_info.get("shipping_fee")
    shipping_fee_text = product_info.get("shipping_fee_text")
    if shipping_fee is None:
        shipping_fee, shipping_fee_text = _extract_shipping(soup, text)

    # 옵션
    options = _extract_options(soup, net_log)

    # 재고
    availability = "in_stock"
    if soup.select_one(".btn_soldout, .soldout_wrap, [class*='soldout']"):
        availability = "out_of_stock"
    elif re.search(r"판매\s*종료|판매\s*불가|구매\s*불가", text[:2000]):
        availability = "out_of_stock"

    # 평점/리뷰 (HTML에 렌더링됨)
    rating = None
    review_count = None
    sat_el = soup.select_one("#satisfactionPt1, #satisfactionPt2")
    if sat_el:
        try:
            rating = float(sat_el.get_text(strip=True))
        except ValueError:
            pass
    evl_el = soup.select_one("#evlTotCnt1, #evlTotCnt2")
    if evl_el:
        rc_m = re.search(r"([\d,]+)", evl_el.get_text(strip=True))
        if rc_m:
            review_count = int(rc_m.group(1).replace(",", ""))

    # delivery_date
    delivery_date = product_info.get("shipping_period")
    if not delivery_date:
        del_m = re.search(r"(배송\s*예정일|예상\s*도착일|도착\s*예정|오늘\s*출발|내일\s*출발)[^\n<]{0,60}", text)
        if del_m:
            delivery_date = del_m.group(0).strip()

    # 스펙
    specifications = _extract_specs(soup)

    # size
    size = requests.post("http://localhost:18080/extract/size", json={
        "title": title,
        "category": "",
        "specs": specifications,
        "text": text[:5000],
        "images": images,
        "allow_ocr": False,
    }, timeout=30).json()
    if size.get("girth_sum_cm") is None and size.get("confidence") in ("LOW", "MEDIUM") and images:
        size = requests.post("http://localhost:18080/extract/size", json={
            "title": title, "category": "", "specs": specifications,
            "text": "", "images": images, "allow_ocr": True,
        }, timeout=40).json()

    return {
        "title": title,
        "price_original": price_original,
        "price_discounted": price_discounted,
        "options": options,
        "images": images,
        "availability": availability,
        "seller": None,
        "brand": None,
        "rating": rating,
        "review_count": review_count,
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
