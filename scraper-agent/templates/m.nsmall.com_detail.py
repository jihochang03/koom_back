# Template: m.nsmall.com (detail)
# Generated: 2026-07-03T16:19:13.637Z
# Notes: NS홈쇼핑 모바일 상품 상세 페이지. Chrome 모드 필요. mapi.nsmall.com API에서 상품정보(product/info)와 옵션(buy-layer)을 네트워크 로그로 추출. 옵션은 unitList로 제공되며 각각 가격과 재고를 포함.

import requests
import json
from bs4 import BeautifulSoup
import re

def scrape(url: str) -> dict:
    # Chrome 모드로 수집 (simple은 차단됨) — 먼저 수집해야 final_url 확인 가능
    resp = requests.post(
        "http://localhost:18080/collect/general",
        json={"url": url},
        timeout=90
    ).json()
    html = resp.get("html", "")
    net_log = resp.get("network_log", [])

    # goods_cd 추출: goods URL 직접 → network_log API → store 패턴 순으로 시도
    final_url = resp.get("final_url", url)
    m = re.search(r'/goods/(\d+)', url) or re.search(r'/goods/(\d+)', final_url)
    if not m:
        # network_log에서 product/info/<id> 패턴 추출 (store 패트너 URL 대응)
        for entry in net_log:
            nm = re.search(r'/product/info/(\d+)', entry.get("url", ""))
            if nm:
                m = nm
                break
    if not m:
        # 마지막 수단: /store/브랜드/숫자 패턴
        m = re.search(r'/store/[^/?]+/(\d+)', url)
    if not m:
        raise ValueError(f"상품 코드를 URL에서 찾을 수 없습니다: {url}")
    goods_cd = m.group(1)

    # API 1: 상품 상세 정보
    product_api_body = None
    for entry in net_log:
        if f"product/info/{goods_cd}" in entry.get("url", ""):
            try:
                product_api_body = json.loads(entry.get("body", "{}"))
            except:
                pass
            break

    # API 2: 옵션/구매 레이어 정보
    buy_layer_body = None
    for entry in net_log:
        if f"buy-layer/{goods_cd}" in entry.get("url", ""):
            try:
                buy_layer_body = json.loads(entry.get("body", "{}"))
            except:
                pass
            break

    data = {}
    title = None
    price_original = None
    price_discounted = None
    images = []

    if product_api_body:
        detail = product_api_body.get("data", {}).get("resultData", {})
        detail_info = detail.get("detailInfo", {})
        dlvr_info = detail.get("dlvrInfo", {})
        marketing = detail.get("marketingScriptInfo", {})
        label_info = detail.get("labelInfo", {})

        title = detail_info.get("productNm")
        sale_price = detail_info.get("salePrice")
        dc_price = detail_info.get("dcPrice")

        # 정가 vs 할인가
        if sale_price and dc_price:
            if dc_price < sale_price:
                price_original = sale_price
                price_discounted = dc_price
            else:
                price_discounted = dc_price
                price_original = sale_price
        else:
            price_discounted = dc_price or sale_price

        dc_rate = detail_info.get("dcRate", 0)

        # 이미지
        for photo in detail_info.get("photoList", []):
            path = photo.get("photoPath", "")
            if path:
                if path.startswith("//"):
                    path = "https:" + path
                images.append(path)

        # 배송정보
        dlvr_prc = dlvr_info.get("dlvrPrc", 0)
        dlvr_msg = dlvr_info.get("dlvrPrcMsg", "")
        intuitive_ship_date = dlvr_info.get("intuitiveShippingDate", "")

        # 라벨 (무료배송 등)
        labels = [l.get("text", "") for l in label_info.get("labelList", [])]

        # 상세이미지 (goodsSpcsHtml에서 이미지 추출)
        goods_html = detail_info.get("goodsSpcsHtml", "")
        if goods_html:
            soup_detail = BeautifulSoup(goods_html, "html.parser")
            for img in soup_detail.find_all("img"):
                src = img.get("src", "")
                if src and src not in images:
                    if src.startswith("//"):
                        src = "https:" + src
                    images.append(src)

        data.update({
            "brand": detail_info.get("brandNm"),
            "manufacturer": detail_info.get("mnfNm"),
            "model": detail_info.get("modelNm"),
            "made_in": detail_info.get("makeNatnText"),
            "rating": detail_info.get("score"),
            "review_count": detail_info.get("ptcptCnt"),
            "category": marketing.get("productFullCategory"),
            "seller_team": marketing.get("mdTeamNm"),
            "md_name": marketing.get("mdNm"),
            "shipping_fee": dlvr_prc,
            "shipping_fee_text": "무료배송" if dlvr_prc == 0 else f"{dlvr_prc:,}원",
            "delivery_date": intuitive_ship_date,
            "labels": labels,
            "discount_rate": dc_rate,
            "price_original": price_original,
            "price_discounted": price_discounted,
        })

    # 옵션 정보
    options = []
    if buy_layer_body:
        goods_opt = buy_layer_body.get("data", {}).get("resultData", {}).get("goodsOptionInfo", {})
        unit_list = goods_opt.get("unitList", [])
        for unit in unit_list:
            options.append({
                "unit_cd": unit.get("unitCd"),
                "name": unit.get("unitNm"),
                "price": unit.get("unitDcPrice"),
                "original_price": unit.get("unitSalePrice"),
                "stock": unit.get("stockQty"),
            })
        data["options"] = options

    # HTML에서 og 정보 보조 추출
    soup = BeautifulSoup(html, "html.parser")
    if not title:
        og_title = soup.find("meta", property="og:title")
        if og_title:
            title = og_title.get("content", "").strip()

    og_image = soup.find("meta", property="og:image")
    if og_image:
        og_img_url = og_image.get("content", "")
        if og_img_url and og_img_url not in images:
            if og_img_url.startswith("//"):
                og_img_url = "https:" + og_img_url
            images.insert(0, og_img_url)

    og_desc = soup.find("meta", property="og:description")
    description = og_desc.get("content", "") if og_desc else ""

    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("http") and href not in links:
            links.append(href)

    return {
        "title": title,
        "page_type": "product",
        "description": description,
        "data": data,
        "images": images,
        "links": links[:20],
    }


if __name__ == "__main__":
    import sys as _sys, json as _json
    _url = _sys.argv[1] if len(_sys.argv) > 1 else ""
    _result = scrape(_url)
    print(_json.dumps(_result, ensure_ascii=False))
