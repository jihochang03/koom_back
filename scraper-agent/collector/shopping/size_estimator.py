"""
사이즈·무게 추정 — 관세(종량세 yen/kg)·국제배송(세 변의 합) 계산용.

비용 절감 단계 (싼 것 → 비싼 것 순서, 앞 단계로 충분하면 다음 단계 생략):
  1) parse_written_size : 스펙/본문 텍스트에서 작성된 무게·치수 정규식 파싱 (LLM 없음)
  2) guess_weight_from_title : 제목/카테고리 키워드로 포장 무게 대략 추정 (LLM 없음)
  3) ocr_size_from_images : 상세/스펙 이미지에서 Claude Haiku(vision)로 추출 (유료 — 최후·옵트인)

estimate_size()가 1→2→(필요·허용 시)3 순으로 호출하고,
세 변의 합(girth_sum_cm)·최장변(longest_side_cm)을 계산해 돌려준다.
"""
from __future__ import annotations

import os
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _to_g(value: float, unit: str) -> int:
    return int(round(value * 1000)) if unit.lower() == "kg" else int(round(value))


def parse_written_size(text: str) -> dict:
    """텍스트에서 작성된 무게·치수 파싱. 반환 키: weight_g, width_cm, length_cm, height_cm (없으면 None)."""
    out = {"weight_g": None, "width_cm": None, "length_cm": None, "height_cm": None}
    if not text:
        return out
    t = re.sub(r"\s+", " ", str(text))

    # ── 무게: "1.2kg", "500 g", "중량 800g" (수량 표기 'x4'가 있으면 곱)
    wm = re.search(r"(?:무게|중량|weight|총?\s*중량)?\s*([\d.]+)\s*(kg|g)\b", t, re.I)
    if wm:
        try:
            w = _to_g(float(wm.group(1)), wm.group(2))
            # 수량(N개/Nea/Nset) 곱 — 예: "285g, 4개"
            qm = re.search(r"([\d]+)\s*(?:개|개입|ea|set|세트|팩|pack)\b", t, re.I)
            if qm and w < 5000:
                try:
                    q = int(qm.group(1))
                    if 1 < q <= 50:
                        w *= q
                except ValueError:
                    pass
            out["weight_g"] = w
        except ValueError:
            pass

    # ── 치수: "30x20x10", "30 x 20 x 10 cm" (cm 가정)
    dm = re.search(r"([\d.]+)\s*[xX×*]\s*([\d.]+)\s*[xX×*]\s*([\d.]+)\s*(cm|mm)?", t)
    if dm:
        unit = (dm.group(4) or "cm").lower()
        div = 10.0 if unit == "mm" else 1.0
        try:
            out["width_cm"] = round(float(dm.group(1)) / div, 1)
            out["length_cm"] = round(float(dm.group(2)) / div, 1)
            out["height_cm"] = round(float(dm.group(3)) / div, 1)
        except ValueError:
            pass

    # ── 개별 치수: 가로/세로/높이/폭/너비/깊이 N cm
    def _dim(label_pat: str) -> Optional[float]:
        m = re.search(label_pat + r"\s*[:：]?\s*([\d.]+)\s*(cm|mm)?", t)
        if not m:
            return None
        try:
            v = float(m.group(1))
            return round(v / 10.0, 1) if (m.group(2) or "").lower() == "mm" else round(v, 1)
        except ValueError:
            return None

    if out["width_cm"] is None:
        out["width_cm"] = _dim(r"(?:가로|폭|너비|width)")
    if out["length_cm"] is None:
        out["length_cm"] = _dim(r"(?:세로|깊이|length|depth)")
    if out["height_cm"] is None:
        out["height_cm"] = _dim(r"(?:높이|height)")

    return out


# 카테고리/키워드 → 포장 포함 대략 무게(g). 앞쪽(구체) 우선 매칭.
_WEIGHT_KEYWORDS = [
    (r"노트북|laptop|데스크탑|모니터|monitor", 2500),
    (r"태블릿|tablet|아이패드|ipad", 700),
    (r"스마트폰|휴대폰|핸드폰|smartphone|갤럭시|아이폰|iphone", 350),
    (r"운동화|스니커즈|신발|구두|부츠|sneaker|shoe", 900),
    (r"가방|백팩|backpack|핸드백|토트|크로스백", 700),
    (r"패딩|코트|아우터|자켓|점퍼|outer|coat|jacket", 900),
    (r"청바지|데님|바지|팬츠|슬랙스|pants|jeans", 500),
    (r"원피스|드레스|dress", 400),
    (r"니트|스웨터|맨투맨|후드|hood|knit|sweater", 450),
    (r"티셔츠|셔츠|블라우스|상의|tee|shirt", 300),
    (r"양말|속옷|언더웨어|socks", 120),
    (r"앰플|세럼|에센스|크림|로션|스킨|토너|ampoule|serum|cream", 300),
    (r"향수|perfume", 350),
    (r"마스카라|틴트|립스틱|쿠션|파운데이션|메이크업|makeup", 150),
    (r"라면|즉석|컵밥|과자|스낵|식품|간식|커피|믹스", 600),
    (r"영양제|비타민|supplement|vitamin", 300),
    (r"책|도서|book", 450),
    (r"장난감|완구|toy|피규어|figure", 500),
    (r"이어폰|에어팟|airpods|earphone|헤드폰|headphone", 300),
    (r"충전기|케이블|charger|cable|어댑터", 250),
    (r"텀블러|머그|컵|tumbler|mug", 500),
]
_DEFAULT_WEIGHT_G = 500


def guess_weight_from_title(title: str, category: str = "") -> tuple[int, str]:
    """제목/카테고리 키워드로 포장 무게(g) 대략 추정. 반환: (weight_g, 근거문구)."""
    hay = f"{title or ''} {category or ''}".lower()
    for pat, w in _WEIGHT_KEYWORDS:
        if re.search(pat, hay):
            return w, f"제목 키워드 추정({pat.split('|')[0]}≈{w}g)"
    return _DEFAULT_WEIGHT_G, f"기본값 {_DEFAULT_WEIGHT_G}g (키워드 미매칭)"


_SIZE_OCR_SYSTEM = (
    "당신은 상품 스펙/상세 이미지에서 무게·크기 정보를 읽어내는 전문가입니다. "
    "이미지 속 한국어/영문 표(제품 사양, 크기, 중량, 규격)에서 무게와 가로·세로·높이를 찾으세요. "
    "포장 크기가 있으면 우선합니다. 없으면 null. JSON만 출력."
)


def ocr_size_from_images(image_urls: list, api_key: Optional[str] = None, max_images: int = 3) -> dict:
    """상세/스펙 이미지에서 Claude Haiku(vision)로 무게·치수 추출. 유료 — 최후 수단."""
    empty = {"weight_g": None, "width_cm": None, "length_cm": None, "height_cm": None}
    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key or not image_urls:
        return empty
    try:
        import anthropic
        import urllib.request
        import base64

        blocks = []
        for u in image_urls[:max_images]:
            try:
                if u.startswith("//"):
                    u = "https:" + u
                req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=10) as r:
                    raw = r.read()
                if len(raw) > 4_500_000:
                    continue
                ct = "image/jpeg"
                if u.lower().endswith(".png"):
                    ct = "image/png"
                elif u.lower().endswith(".webp"):
                    ct = "image/webp"
                blocks.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": ct,
                               "data": base64.b64encode(raw).decode()},
                })
            except Exception:
                continue
        if not blocks:
            return empty

        client = anthropic.Anthropic(api_key=key)
        model = os.environ.get("SIZE_OCR_MODEL", "claude-haiku-4-5-20251001")
        resp = client.messages.create(
            model=model,
            max_tokens=300,
            temperature=0,
            system=_SIZE_OCR_SYSTEM,
            messages=[{"role": "user", "content": blocks + [{
                "type": "text",
                "text": ('이미지에서 무게·크기를 찾아 JSON으로만: '
                         '{"weight_g": 숫자또는null, "width_cm": 숫자또는null, '
                         '"length_cm": 숫자또는null, "height_cm": 숫자또는null}. '
                         'kg은 g으로, mm는 cm로 환산.'),
            }]}],
        )
        import json as _j
        text = resp.content[0].text.strip()
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return empty
        p = _j.loads(m.group())
        return {
            "weight_g": p.get("weight_g"),
            "width_cm": p.get("width_cm"),
            "length_cm": p.get("length_cm"),
            "height_cm": p.get("height_cm"),
        }
    except Exception as e:
        logger.warning("[size-ocr] 실패 (무시): %s", e)
        return empty


def estimate_size(
    title: str = "",
    category: str = "",
    specs: Optional[dict] = None,
    text: str = "",
    images: Optional[list] = None,
    allow_ocr: bool = False,
    api_key: Optional[str] = None,
) -> dict:
    """
    무게·치수 추정 (비용 절감 단계). 반환 키:
      weight_g, width_cm, length_cm, height_cm,
      girth_sum_cm(세 변의 합), longest_side_cm(최장변),
      source('written'|'title_guess'|'image_ocr'|'mixed'|'none'),
      confidence('HIGH'|'MEDIUM'|'LOW'), note
    """
    # 스펙 dict + 본문 텍스트 합쳐서 파싱
    spec_text = ""
    if specs and isinstance(specs, dict):
        spec_text = " ".join(f"{k} {v}" for k, v in specs.items())
    combined = f"{spec_text} {text or ''}".strip()

    written = parse_written_size(combined)
    weight_g = written["weight_g"]
    w, l, h = written["width_cm"], written["length_cm"], written["height_cm"]
    sources = set()
    notes = []
    if weight_g is not None:
        sources.add("written")
    if any(v is not None for v in (w, l, h)):
        sources.add("written")

    # 무게 없으면 제목/카테고리로 추정 (싼 단계)
    if weight_g is None:
        weight_g, why = guess_weight_from_title(title, category)
        sources.add("title_guess")
        notes.append(why)

    # 치수가 비고, OCR 허용 시에만 이미지 OCR (유료, 최후)
    if allow_ocr and (w is None or l is None or h is None) and images:
        ocr = ocr_size_from_images(images, api_key=api_key)
        if any(ocr.get(k) is not None for k in ("width_cm", "length_cm", "height_cm", "weight_g")):
            sources.add("image_ocr")
            notes.append("이미지 OCR 보강")
            w = w if w is not None else ocr.get("width_cm")
            l = l if l is not None else ocr.get("length_cm")
            h = h if h is not None else ocr.get("height_cm")
            if written["weight_g"] is None and ocr.get("weight_g"):
                weight_g = ocr["weight_g"]
                sources.discard("title_guess")

    girth_sum = round(w + l + h, 1) if None not in (w, l, h) else None
    longest = max(v for v in (w, l, h) if v is not None) if any(v is not None for v in (w, l, h)) else None

    # 신뢰도
    if "written" in sources and girth_sum is not None:
        confidence = "HIGH"
    elif girth_sum is not None or "written" in sources:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    if len(sources) > 1:
        source = "mixed"
    elif sources:
        source = next(iter(sources))
    else:
        source = "none"

    return {
        "weight_g": weight_g,
        "width_cm": w,
        "length_cm": l,
        "height_cm": h,
        "girth_sum_cm": girth_sum,
        "longest_side_cm": longest,
        "source": source,
        "confidence": confidence,
        "note": " · ".join(notes) if notes else "작성된 값 사용",
    }
