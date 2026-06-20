"""
DK 구매대행 최종 견적 (엔 기준 수수료·세금 룰 → 원화 표시).

cfg 파라미터로 admin에서 설정한 DB 값을 override할 수 있다.
cfg가 없으면 환경변수 → 하드코딩 기본값 순으로 적용.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

import os

# 모듈 기본값 (env → fallback)
AGENCY_FEE_UNDER_EQ_10K_JPY = int(os.getenv("DK_AGENCY_FEE_LOW_JPY", "300"))
AGENCY_FEE_OVER_10K_JPY     = int(os.getenv("DK_AGENCY_FEE_HIGH_JPY", "500"))
AGENCY_PRICE_THRESHOLD_JPY  = float(os.getenv("DK_AGENCY_THRESHOLD_JPY", "10000"))
CUSTOMS_RATIO_FOR_EXEMPT    = float(os.getenv("DK_CUSTOMS_RATIO", "0.6"))
CUSTOMS_EXEMPT_LINE_JPY     = float(os.getenv("DK_CUSTOMS_EXEMPT_JPY", "10000"))
CONSUMPTION_TAX_RATE        = float(os.getenv("DK_CONSUMPTION_TAX_RATE", "0.10"))
DEFAULT_TARIFF_RATE         = float(os.getenv("DK_DEFAULT_TARIFF_RATE", "0.05"))
TAX_ADVANCE_FEE_RATE        = float(os.getenv("DK_TAX_ADVANCE_FEE_RATE", "0.05"))
EXCHANGE_MARGIN_RATE        = float(os.getenv("DK_EXCHANGE_MARGIN_RATE", "0.04"))
BUNDLE_FEE_JPY              = int(os.getenv("DK_BUNDLE_FEE_JPY", "200"))
PHOTO_INSPECTION_JPY        = int(os.getenv("DK_PHOTO_INSPECTION_JPY", "300"))
SPEED_SHIP_JPY              = int(os.getenv("DK_SPEED_SHIP_JPY", "500"))
POINTS_RATE                 = float(os.getenv("DK_POINTS_RATE", "0.01"))
INTL_SHIPPING_MARKUP_RATE   = float(os.getenv("DK_INTL_SHIPPING_MARKUP_RATE", "1.4"))


def _f(x: Optional[float]) -> float:
    if x is None:
        return 0.0
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _b(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    if val is None:
        return False
    return str(val).strip().lower() in ("1", "true", "yes", "on")


def _clamp_tariff_rate(r: float) -> float:
    return min(0.10, max(0.0, r))


def compute_dk_pricing(
    *,
    discounted_price: Optional[float],
    original_price: Optional[float],
    currency: str,
    krw_per_jpy_market: float,
    req_data: Optional[Dict[str, Any]] = None,
    cfg: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    cfg: SiteConfig.get_group('pricing') 반환값으로 DB 설정값을 전달.
         없으면 모듈 기본값(환경변수) 사용.
    """
    req_data = req_data or {}
    if _b(req_data.get("dk_skip_pricing")):
        return None

    base = discounted_price if discounted_price is not None else original_price
    if base is None:
        return None

    # DB 설정값 resolve (cfg → 모듈 기본값)
    c = cfg or {}
    _AGENCY_FEE_LOW    = int(c.get('DK_AGENCY_FEE_LOW_JPY',          AGENCY_FEE_UNDER_EQ_10K_JPY))
    _AGENCY_FEE_HIGH   = int(c.get('DK_AGENCY_FEE_HIGH_JPY',         AGENCY_FEE_OVER_10K_JPY))
    _AGENCY_THRESHOLD  = float(c.get('DK_AGENCY_THRESHOLD_JPY',      AGENCY_PRICE_THRESHOLD_JPY))
    _CUSTOMS_RATIO     = float(c.get('DK_CUSTOMS_RATIO',             CUSTOMS_RATIO_FOR_EXEMPT))
    _CUSTOMS_EXEMPT    = float(c.get('DK_CUSTOMS_EXEMPT_JPY',        CUSTOMS_EXEMPT_LINE_JPY))
    _CONSUMPTION_TAX   = float(c.get('DK_CONSUMPTION_TAX_RATE',      CONSUMPTION_TAX_RATE))
    _DEFAULT_TARIFF    = float(c.get('DK_DEFAULT_TARIFF_RATE',       DEFAULT_TARIFF_RATE))
    _TAX_ADVANCE       = float(c.get('DK_TAX_ADVANCE_FEE_RATE',      TAX_ADVANCE_FEE_RATE))
    _EXCHANGE_MARGIN   = float(c.get('DK_EXCHANGE_MARGIN_RATE',      EXCHANGE_MARGIN_RATE))
    _INTL_MARKUP       = float(c.get('DK_INTL_SHIPPING_MARKUP_RATE', INTL_SHIPPING_MARKUP_RATE))
    _BUNDLE_FEE        = int(c.get('DK_BUNDLE_FEE_JPY',              BUNDLE_FEE_JPY))
    _PHOTO_FEE         = int(c.get('DK_PHOTO_INSPECTION_JPY',        PHOTO_INSPECTION_JPY))
    _SPEED_FEE         = int(c.get('DK_SPEED_SHIP_JPY',              SPEED_SHIP_JPY))
    _POINTS            = float(c.get('DK_POINTS_RATE',               POINTS_RATE))

    cur = (currency or "KRW").upper().strip()
    if krw_per_jpy_market <= 0:
        krw_per_jpy_market = 10.0

    krw_per_jpy_customer = krw_per_jpy_market / (1.0 + _EXCHANGE_MARGIN)

    if cur == "JPY":
        product_jpy_nominal = _f(base)
        product_krw_line = round(product_jpy_nominal * krw_per_jpy_customer, 2)
    else:
        product_krw_line = round(_f(base), 2)
        product_jpy_nominal = product_krw_line / krw_per_jpy_market

    domestic_shipping_krw = _f(req_data.get("shipping_krw") or req_data.get("shipping_fee"))
    intl_shipping_jpy = _f(req_data.get("intl_shipping_jpy"))
    intl_shipping_jpy_display = intl_shipping_jpy * _INTL_MARKUP
    quantity = max(1.0, _f(req_data.get("quantity")) or 1.0)

    tr_raw = req_data.get("tariff_rate")
    tariff_from_request = tr_raw is not None and str(tr_raw).strip() != ""
    tariff_lookup = req_data.get("_tariff_lookup") or {}
    lookup_rate = tariff_lookup.get("rate")
    lookup_has_rate = lookup_rate is not None
    is_non_physical = bool(tariff_lookup.get("non_physical"))
    lookup_duty_type = tariff_lookup.get("duty_type")
    lookup_specific_yen = tariff_lookup.get("specific_yen_per_unit")
    lookup_specific_unit = tariff_lookup.get("specific_unit")

    if tariff_from_request:
        tariff_rate = _clamp_tariff_rate(_f(tr_raw))
        effective_duty_type = "ad_valorem"
        specific_duty_jpy: Optional[float] = None
        rate_policy_source = "request"
        rate_fallback_reason = None
    elif is_non_physical:
        tariff_rate = 0.0
        effective_duty_type = "ad_valorem"
        specific_duty_jpy = None
        rate_policy_source = "non_physical"
        rate_fallback_reason = None
    elif lookup_has_rate:
        tariff_rate = _clamp_tariff_rate(float(lookup_rate))
        rs = str(tariff_lookup.get("rate_source") or "lookup")
        rate_policy_source = f"lookup_{rs}"
        rate_fallback_reason = None
        if lookup_duty_type == "compound" and lookup_specific_yen:
            effective_duty_type = "compound"
            specific_duty_jpy = lookup_specific_yen * quantity
        else:
            effective_duty_type = "ad_valorem"
            specific_duty_jpy = None
    elif lookup_duty_type == "specific" and lookup_specific_yen:
        tariff_rate = 0.0
        effective_duty_type = "specific"
        specific_duty_jpy = lookup_specific_yen * quantity
        rs = str(tariff_lookup.get("rate_source") or "lookup")
        rate_policy_source = f"lookup_{rs}_specific"
        rate_fallback_reason = None
    elif tariff_lookup.get("matched_item"):
        tariff_rate = _clamp_tariff_rate(_DEFAULT_TARIFF)
        effective_duty_type = "ad_valorem"
        specific_duty_jpy = None
        rate_policy_source = "default"
        rate_fallback_reason = "lookup_matched_but_not_ad_valorem"
    else:
        tariff_rate = _clamp_tariff_rate(_DEFAULT_TARIFF)
        effective_duty_type = "ad_valorem"
        specific_duty_jpy = None
        rate_policy_source = "default"
        rate_fallback_reason = (
            "lookup_no_match_or_empty" if "_tariff_lookup" in req_data else None
        )

    bundle = _b(req_data.get("dk_bundle_consolidation")) or _b(req_data.get("bundle_consolidation"))
    photo  = _b(req_data.get("dk_photo_inspection"))     or _b(req_data.get("photo_inspection"))
    speed  = _b(req_data.get("dk_speed_shipping"))       or _b(req_data.get("speed_shipping"))

    lines: List[Dict[str, Any]] = []
    lines_hidden: List[Dict[str, Any]] = []

    domestic_jpy_market = round(domestic_shipping_krw / krw_per_jpy_market, 2) if krw_per_jpy_market else 0.0

    lines.append({"code": "product", "label": "상품 (할인가 기준)",
                  "jpy": round(product_jpy_nominal, 2), "krw": product_krw_line, "visible": True})
    lines.append({"code": "domestic_shipping", "label": "국내 배송비",
                  "jpy": domestic_jpy_market, "krw": round(domestic_shipping_krw, 2),
                  "visible": True, "note": "마진 없음 · 과세 CIF에 포함"})

    # 구매대행 수수료
    agency_jpy = _AGENCY_FEE_LOW if product_jpy_nominal <= _AGENCY_THRESHOLD else _AGENCY_FEE_HIGH
    agency_krw = agency_jpy * krw_per_jpy_customer
    agency_krw_market = agency_jpy * krw_per_jpy_market
    lines.append({"code": "agency_fee", "label": "구매대행 수수료",
                  "jpy": agency_jpy, "krw": round(agency_krw, 2), "visible": True,
                  "note": f"상품가 {_AGENCY_THRESHOLD:,.0f}엔 이하 {_AGENCY_FEE_LOW}엔 / 초과 {_AGENCY_FEE_HIGH}엔"})
    lines_hidden.append({"code": "exchange_margin_on_agency", "label": "환율 마진(구매대행 수수료)",
                          "krw": round(agency_krw - agency_krw_market, 2), "visible": False})

    if intl_shipping_jpy > 0:
        is_krw   = intl_shipping_jpy_display * krw_per_jpy_customer
        is_krw_m = intl_shipping_jpy_display * krw_per_jpy_market
        lines.append({"code": "intl_shipping", "label": "국제 배송비(추정/입력)",
                      "jpy": round(intl_shipping_jpy_display, 2), "krw": round(is_krw, 2), "visible": True,
                      "note": f"원가 ¥{round(intl_shipping_jpy, 0):.0f} × {_INTL_MARKUP} (마진 적용)"})
        lines_hidden.append({"code": "exchange_margin_on_intl", "label": "내부환율 마진(국제배송)",
                              "krw": round(is_krw - is_krw_m, 2), "visible": False})

    opt_total_jpy = 0
    for flag, fee, code, label in [
        (bundle, _BUNDLE_FEE, "bundle_consolidation", "합배송 처리비"),
        (photo,  _PHOTO_FEE,  "photo_inspection",     "사진 검수 서비스"),
        (speed,  _SPEED_FEE,  "speed_shipping",       "스피드 출하 서비스"),
    ]:
        if flag:
            opt_total_jpy += fee
            f_krw = fee * krw_per_jpy_customer
            f_m   = fee * krw_per_jpy_market
            lines.append({"code": code, "label": label, "jpy": fee, "krw": round(f_krw, 2), "visible": True})
            lines_hidden.append({"code": f"exchange_margin_on_{code}", "label": f"환율 마진({label})",
                                  "krw": round(f_krw - f_m, 2), "visible": False})

    # 통관 면세 판정
    non_physical = bool(tariff_lookup.get("non_physical"))
    cif_base_jpy = product_jpy_nominal + domestic_jpy_market + intl_shipping_jpy
    customs_value_line = cif_base_jpy * _CUSTOMS_RATIO
    duty_free = non_physical or customs_value_line <= _CUSTOMS_EXEMPT + 1e-9
    customs_detail: Dict[str, Any] = {
        "duty_free": duty_free,
        "rule": (
            "비실물 품목(서비스·티켓 등) — 수입 관세 대상 아님" if non_physical
            else "(상품가+국내배송비+국제배송비) × 60% ≤ 10,000엔 → 면세 추정"
        ),
        "cif_times_60pct_jpy": round(customs_value_line, 2),
        "approx_exempt_product_jpy_max": round(_CUSTOMS_EXEMPT / _CUSTOMS_RATIO, 2),
    }

    customs_tax_jpy = 0.0
    if not duty_free:
        ad_valorem_duty = cif_base_jpy * tariff_rate
        if effective_duty_type == "specific" and specific_duty_jpy is not None:
            duty_jpy = specific_duty_jpy
        elif effective_duty_type == "compound" and specific_duty_jpy is not None:
            duty_jpy = max(ad_valorem_duty, specific_duty_jpy)
        else:
            duty_jpy = ad_valorem_duty

        vat_jpy       = (cif_base_jpy + duty_jpy) * _CONSUMPTION_TAX
        tax_visible   = duty_jpy + vat_jpy
        tax_advance   = tax_visible * _TAX_ADVANCE

        est = {
            "duty_jpy": round(duty_jpy, 2), "duty_type": effective_duty_type,
            "ad_valorem_duty_jpy": round(ad_valorem_duty, 2),
            "vat_jpy": round(vat_jpy, 2),
            "tax_subtotal_jpy": round(tax_visible, 2),
            "tax_advance_fee_jpy": round(tax_advance, 2),
            "tariff_rate_applied": tariff_rate,
        }
        customs_detail.update(est)
        customs_tax_jpy = est["tax_subtotal_jpy"] + est["tax_advance_fee_jpy"]

        tax_krw  = est["tax_subtotal_jpy"] * krw_per_jpy_customer
        tax_krw_m = est["tax_subtotal_jpy"] * krw_per_jpy_market
        adv_krw  = est["tax_advance_fee_jpy"] * krw_per_jpy_customer
        adv_krw_m = est["tax_advance_fee_jpy"] * krw_per_jpy_market
        lines.append({"code": "customs_duty_vat", "label": "통관 추정(관세+부가세)",
                      "jpy": est["tax_subtotal_jpy"], "krw": round(tax_krw, 2), "visible": True})
        lines_hidden += [
            {"code": "exchange_margin_on_customs_visible", "label": "환율 마진(통관 세금)",
             "krw": round(tax_krw - tax_krw_m, 2), "visible": False},
            {"code": "tax_advance_fee", "label": "세금 대납 수수료(숨김)",
             "jpy": est["tax_advance_fee_jpy"], "krw": round(adv_krw, 2), "visible": False},
            {"code": "exchange_margin_on_tax_advance", "label": "환율 마진(세금대납)",
             "krw": round(adv_krw - adv_krw_m, 2), "visible": False},
        ]

    if cur == "JPY":
        diff = round(product_krw_line - product_jpy_nominal * krw_per_jpy_market, 2)
        if abs(diff) > 1e-6:
            lines_hidden.append({"code": "exchange_margin_on_product", "label": "환율 마진(엔화 상품가)",
                                  "krw": diff, "visible": False})

    def _jpy_to_krw(jpy: float) -> float:
        return round(jpy * krw_per_jpy_customer, 2)

    subtotal_krw = (
        product_krw_line
        + domestic_shipping_krw
        + _jpy_to_krw(float(agency_jpy))
        + _jpy_to_krw(intl_shipping_jpy_display)
        + _jpy_to_krw(float(opt_total_jpy))
        + (_jpy_to_krw(float(customs_tax_jpy)) if not duty_free else 0)
    )
    subtotal_jpy = round(
        product_jpy_nominal + domestic_jpy_market + float(agency_jpy)
        + intl_shipping_jpy_display + float(opt_total_jpy)
        + (float(customs_tax_jpy) if not duty_free else 0),
        2,
    )
    total_krw = subtotal_krw

    return {
        "schema_version": 1,
        "product_currency": cur,
        "product_jpy_nominal_market": round(product_jpy_nominal, 2),
        "tariff_policy": {
            "uses_tariff_table_lookup": bool(tariff_lookup),
            "non_physical": is_non_physical,
            "matched_item": tariff_lookup.get("matched_item"),
            "lookup_candidates_found": tariff_lookup.get("candidates_found"),
            "search_expansion": tariff_lookup.get("search_expansion"),
            "rate_source": rate_policy_source,
            "duty_type": effective_duty_type,
            "specific_yen_per_unit": lookup_specific_yen,
            "specific_unit": lookup_specific_unit,
            "quantity_used": quantity if effective_duty_type in ("specific", "compound") else None,
            "default_rate": _DEFAULT_TARIFF,
            "applied_rate": 0.0 if duty_free else tariff_rate,
            "fallback_reason": rate_fallback_reason,
            "note": (
                "관세율표 행은 매칭됐으나 퍼센트(%) 세율이 없어 기본율을 사용했습니다."
                if rate_fallback_reason == "lookup_matched_but_not_ad_valorem"
                else (
                    "관세율표에서 적합한 퍼센트 세율을 찾지 못했습니다. 기본 관세율을 사용했습니다."
                    if rate_fallback_reason == "lookup_no_match_or_empty"
                    else None
                )
            ),
        },
        "exchange": {
            "krw_per_jpy_market": round(krw_per_jpy_market, 6),
            "krw_per_jpy_customer": round(krw_per_jpy_customer, 6),
            "margin_rate_pct": round(_EXCHANGE_MARGIN * 100, 2),
        },
        "lines": lines,
        "lines_hidden": lines_hidden,
        "domestic_shipping_krw": round(domestic_shipping_krw, 2),
        "domestic_shipping_jpy": domestic_jpy_market if domestic_shipping_krw else None,
        "subtotal_jpy": subtotal_jpy,
        "subtotal_krw": round(subtotal_krw, 2),
        "subtotal_krw_ceil_won": int(math.ceil(subtotal_krw)),
        "total_jpy_estimated": subtotal_jpy,
        "total_jpy_estimated_ceil": int(math.ceil(subtotal_jpy)),
        "total_krw_estimated": round(total_krw, 2),
        "total_krw_estimated_ceil_won": int(math.ceil(total_krw)),
        "customs": customs_detail,
        "points_earn_krw": round(product_krw_line * _POINTS, 2),
        "points_note": "할인가(표시 통화) 기준 1% 적립 안내 — 고객 환율(일본 청구 기준, 마진 반영) 적용",
        "disclaimer": "추정 금액입니다. 실제 관세·환율은 결제(송금) 시점 및 품목·신고에 따라 달라질 수 있습니다.",
    }


def attach_dk_pricing_to_response(
    response_data: Dict[str, Any],
    product_info: Any,
    req_data: Dict[str, Any],
    krw_per_jpy_market: float,
    cfg: Optional[Dict[str, Any]] = None,
) -> None:
    dk = compute_dk_pricing(
        discounted_price=getattr(product_info, "discounted_price", None),
        original_price=getattr(product_info, "original_price", None),
        currency=getattr(product_info, "currency", None) or "KRW",
        krw_per_jpy_market=krw_per_jpy_market,
        req_data=req_data,
        cfg=cfg,
    )
    response_data["dk_pricing"] = dk
