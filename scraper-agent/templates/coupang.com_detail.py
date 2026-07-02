# Template: coupang.com (detail)
# Generated: 2026-06-26T08:05:11.167Z
# Notes: 쿠팡 상품 상세 페이지 스크레이퍼. /collect/general이 반환하는 product_info(제목·가격·옵션·이미지·치수)를 우선 사용하고, HTML에서 브랜드·판매자·필수표기정보·이미지 갤러리를 보강한다. 평점·리뷰수는 network_log의 /next-api/review API에서 파싱(ratingAverage/ratingCount). 배송비는 로켓배송=무료, HTML 배송비 영역 파싱. 이미지는 coupangcdn.com/thumbnails/ 및 coupangcdn.com/image/retail 패턴만 허용해 로고/아이콘 제외. size는 /extract/size 호출.

# Template: coupang.com (detail)
# Generated: 2026-06-08T01:51:27.275Z
# Updated:   2026-06-27 — 평점·리뷰수를 network_log(/next-api/review) API에서 파싱,
#            이미지 필터링 강화(thumbnails/retail 경로만 허용, 아이콘·로고 제외),
#            shipping_fee_text 필드 추가, size(/extract/size) 호출 추가.
# Notes: 쿠팡 상품 상세 페이지 스크레이퍼. /collect/general이 반환하는 product_info(제목·가격·
#        옵션·이미지·치수)를 우선 사용하고, HTML에서 브랜드·판매자·필수표기정보·이미지 갤러리를
#        보강한다.

import requests
from bs4 import BeautifulSoup
import re
import json


def _num(v):
    """문자열/숫자 → int. 실패 시 None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    m = re.search(r"\d[\d,]*", str(v))
    return int(m.group(0).replace(",", "")) if m else None


def _pick_api(net_log, *keywords):
    """network_log(=[{url, body, ct}])에서 url에 keyword가 포함된 첫 JSON 응답을 dict로 반환."""
    for e in net_log or []:
        u = (e.get("url") or "")
        if any(k in u for k in keywords):
            body = e.get("body") or ""
            try:
                return json.loads(body)
            except Exception:
                continue
    return None


def _extract_shipping(soup, info, net_log):
    """shipping_fee(int/None), shipping_fee_text(str/None) 추출."""
    # product_info 우선
    fee = info.get("shipping_fee")
    if fee is not None:
        fee = int(fee)
        return fee, ("무료배송" if fee == 0 else f"{fee:,}원")

    # quantity-info API에서 배송비 확인
    qi = _pick_api(net_log, "quantity-info")
    if qi and isinstance(qi, list) and len(qi) > 0:
        first = qi[0]
        for mod in (first.get("moduleData") or []):
            dpb = mod.get("detailPriceBundle") or {}
            fp = dpb.get("finalPrice") or {}
            bp = fp.get("bestPriceInfo") or {}
            pw = bp.get("priceWithDeliveryFee")
            p = bp.get("price")
            if pw is not None and p is not None:
                diff = int(pw) - int(p)
                if diff == 0:
                    return 0, "무료배송"
                elif diff > 0:
                    return diff, f"{diff:,}원"

    # HTML에서 파싱
    rocket = soup.select_one("[class*='rocket']") or soup.select_one(".badge-rocket")
    if rocket and "로켓" in rocket.get_text():
        return 0, "무료배송"

    text = soup.get_text(" ", strip=True)
    area_m = re.search(r"배송비.{0,500}", text, re.DOTALL)
    area = area_m.group(0) if area_m else text[:3000]

    if re.search(r"무료\s*배송|배송\s*무료|로켓\s*배송", area):
        return 0, "무료배송"

    combined = re.search(
        r"([\d,]+)\s*원[^(]{0,30}\([^)]*[\d,]+\s*만?\s*원\s*이상[^)]*무료[^)]*\)", area
    )
    if combined:
        fee_val = int(combined.group(1).replace(",", ""))
        return fee_val, combined.group(0).strip()

    m = re.search(r"([\d,]+)\s*원", area)
    if m:
        fee_val = int(m.group(1).replace(",", ""))
        if 0 < fee_val < 100000:
            return fee_val, f"{m.group(1)}원"

    return None, None


def scrape(url: str) -> dict:
    # 로컬 수집 서버(브라우저 기반, 봇 우회)로 페이지 수집.
    resp = requests.post(
        "http://localhost:18080/collect/general",
        json={"url": url},
        timeout=120,
    )
    data = resp.json()
    html = data.get("html", "") or ""
    info = data.get("product_info") or {}
    net_log = data.get("network_log", [])
    soup = BeautifulSoup(html, "html.parser")

    # ── 핵심 필드: 수집 서버 product_info 우선 ───────────────────────────────
    title = info.get("title") or ""
    price_original = _num(info.get("original_price"))
    price_discounted = _num(info.get("discounted_price"))

    # 옵션: product_info의 [{option_type, available_values, soldout_values}]
    #       → 공통 스키마 [{name, values}]로 변환
    options = []
    for opt in (info.get("product_options") or []):
        values = opt.get("available_values") or []
        if values:
            options.append({"name": opt.get("option_type") or "옵션", "values": values})

    # 재고
    availability = "out_of_stock" if info.get("sold_out") else "in_stock"

    # 배송 도착 예정일: product_info.shipping_period 우선, 없으면 .pdd-contents 직접 파싱
    delivery_date = info.get("shipping_period")
    if not delivery_date:
        pdd = None
        for item in soup.select(".radio-item"):
            radio = item.select_one("span.radio")
            if radio and "selected" in (radio.get("class") or []):
                pdd = item.select_one(".pdd-contents")
                if pdd:
                    break
        if pdd is None:
            pdd = soup.select_one(".pdd-contents")
        if pdd:
            _t = " ".join(pdd.get_text(" ", strip=True).split())
            delivery_date = _t.replace("( ", "(").replace(" )", ")") or None

    # 배송비
    shipping_fee, shipping_fee_text = _extract_shipping(soup, info, net_log)

    # 스펙(필수표기정보·치수): product_info.raw_data.coupang_description_items 우선
    specifications = {}
    raw_items = (info.get("raw_data") or {}).get("coupang_description_items") or {}
    if isinstance(raw_items, dict):
        specifications.update({str(k): str(v) for k, v in raw_items.items()})
    dims = [info.get("est_width_cm"), info.get("est_length_cm"), info.get("est_height_cm")]
    if any(d is not None for d in dims):
        specifications.setdefault(
            "크기(cm)",
            " x ".join(str(d) for d in dims if d is not None),
        )
    if info.get("used_condition"):
        specifications.setdefault("상품상태", str(info["used_condition"]))

    # 필수표기정보 테이블(#itemBrief) — specifications 보강
    table = soup.select_one("#itemBrief table")
    if table:
        for row in table.select("tr"):
            cells = row.select("td")
            for i in range(0, len(cells) - 1, 2):
                key = cells[i].get_text(strip=True)
                val = cells[i + 1].get_text(strip=True)
                if key and val and key not in specifications:
                    specifications[key] = val

    # ── 이미지: 상품 이미지만 (thumbnails/retail 경로만 허용, 아이콘·로고 제외) ──
    _PRODUCT_IMG_PAT = re.compile(
        r"coupangcdn\.com/thumbnails/|"
        r"coupangcdn\.com/image/(?:retail|vendor_inventory)",
        re.IGNORECASE,
    )
    images = []
    main_img = info.get("main_image_url")
    if main_img:
        images.append(main_img)

    for img in soup.select("img"):
        src = img.get("src") or img.get("data-src") or ""
        if not _PRODUCT_IMG_PAT.search(src):
            continue
        if src.startswith("//"):
            src = "https:" + src
        # 썸네일 크기 → 492x492
        src = re.sub(r"/\d+x\d+ex/", "/492x492ex/", src)
        base = src.split("?")[0]
        if base and base not in images:
            images.append(base)
        if len(images) >= 10:
            break

    # ── HTML 보강 ──────────────────────────────────────────────────────────────
    if not title:
        og_title = soup.select_one('meta[property="og:title"]')
        if og_title:
            title = (og_title.get("content", "") or "").replace(" | 쿠팡", "").strip()

    description = ""
    meta_desc = soup.select_one('meta[name="description"]')
    if meta_desc:
        description = meta_desc.get("content", "") or ""

    # 브랜드
    brand = None
    brand_tag = soup.select_one(".brand-info .twc-font-bold") or soup.select_one(".brand-info a")
    if brand_tag:
        brand = brand_tag.get_text(strip=True) or None

    # ── 평점 & 리뷰수: network_log의 /next-api/review API 우선 ────────────────
    rating = None
    review_count = None
    review_data = _pick_api(net_log, "/next-api/review")
    if review_data:
        r_data = review_data.get("rData") or {}
        rs = r_data.get("ratingSummaryTotal") or {}
        if rs.get("ratingAverage") is not None:
            try:
                rating = float(rs["ratingAverage"])
            except (ValueError, TypeError):
                pass
        if rs.get("ratingCount") is not None:
            try:
                review_count = int(rs["ratingCount"])
            except (ValueError, TypeError):
                pass

    # 폴백: meta description에서 평점/리뷰수
    if (rating is None or review_count is None) and description:
        rm = re.search(r"별점\s*([\d.]+)\s*점", description)
        vm = re.search(r"리뷰\s*([\d,]+)\s*개", description)
        if rm and rating is None:
            try:
                rating = float(rm.group(1))
            except ValueError:
                pass
        if vm and review_count is None:
            review_count = _num(vm.group(1))

    # 판매자
    seller = None
    seller_table = soup.select_one(".product-seller table")
    if seller_table:
        td = seller_table.select_one("td")
        if td:
            seller = td.get_text(strip=True).replace("1577-7011", "").strip() or None

    # 가격 폴백
    if price_discounted is None:
        og_price = soup.select_one('meta[property="product:price:amount"]')
        if og_price:
            price_discounted = _num(og_price.get("content"))
    if price_original is None:
        price_original = price_discounted

    # ── size: /extract/size 호출 ───────────────────────────────────────────────
    try:
        size = requests.post(
            "http://localhost:18080/extract/size",
            json={
                "title": title,
                "category": "",
                "specs": specifications,
                "text": soup.get_text(" ", strip=True)[:5000],
                "images": images,
                "allow_ocr": False,
            },
            timeout=30,
        ).json()
        # 치수 없고 신뢰도 낮으면 OCR 보강 (유료)
        if (
            size.get("girth_sum_cm") is None
            and size.get("confidence") in ("LOW", "MEDIUM")
            and images
        ):
            size = requests.post(
                "http://localhost:18080/extract/size",
                json={
                    "title": title,
                    "category": "",
                    "specs": specifications,
                    "text": "",
                    "images": images,
                    "allow_ocr": True,
                },
                timeout=40,
            ).json()
    except Exception:
        size = None

    return {
        "title": title,
        "description": description or None,
        "price_original": price_original,
        "price_discounted": price_discounted,
        "options": options,
        "images": images[:10],
        "brand": brand,
        "availability": availability,
        "shipping_fee": shipping_fee,
        "shipping_fee_text": shipping_fee_text,
        "delivery_date": delivery_date,
        "rating": rating,
        "review_count": review_count,
        "seller": seller,
        "specifications": specifications,
        "size": size,
    }


if __name__ == "__main__":
    import sys as _sys, json as _json
    _url = _sys.argv[1] if len(_sys.argv) > 1 else ""
    _result = scrape(_url)
    print(_json.dumps(_result, ensure_ascii=False))
