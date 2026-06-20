"""
국제 배송비 자동 견적 서비스.

흐름:
  카테고리별 수량 → CategoryWeightPreset → 총 무게 추정
  → ShippingModeConfig 로 운송 방식(AIR/SEA/EMS) 자동 결정
  → ShippingCarrierProfile 목록 조회
  → 배송사별 운임 계산 (엔진별 분기)
  → 견적 목록 반환
"""
from __future__ import annotations

from typing import Optional

from apps.shipping.models import (
    CategoryWeightPreset,
    FuelSurcharge,
    ShippingCarrierProfile,
    ShippingModeConfig,
    load_rate_tables,
)
from apps.shipping.utils.japan_shipping import (
    FbTaxMode,
    FbTier,
    ServiceProvider,
    ShippingInput,
    TransportMode,
    build_quote_response,
)

DEFAULT_WEIGHT_KG = 0.5  # 카테고리 미설정 시 기본값


# ── 무게 기반 운송 방식 결정 ────────────────────────────────────────────────

def determine_mode(weight_kg: float, requested_mode: Optional[str] = None) -> str:
    """
    운송 방식을 결정합니다.

    1) requested_mode가 지정되면 그대로 사용.
    2) ShippingModeConfig(is_current=True)에 따라:
       - AUTO     : air_max_weight_kg 이하 → AIR, 초과 → SEA
       - AIR_ONLY : 항상 AIR
       - SEA_ONLY : 항상 SEA
    3) 설정 레코드 없으면 기본값 3.0 kg 적용.
    """
    if requested_mode:
        return requested_mode

    config = ShippingModeConfig.objects.filter(is_current=True).first()
    if config is None:
        return 'AIR' if weight_kg <= 3.0 else 'SEA'

    if config.mode_selection == 'AIR_ONLY':
        return 'AIR'
    if config.mode_selection == 'SEA_ONLY':
        return 'SEA'
    # AUTO
    return 'AIR' if weight_kg <= config.air_max_weight_kg else 'SEA'


# ── 월별 유류할증료 조회 ─────────────────────────────────────────────────────

def get_current_fsc(carrier_name: str, currency: str = 'KRW') -> Optional[int]:
    """현재 월의 유류할증료 조회. 없으면 None."""
    from datetime import date
    year_month = date.today().strftime('%Y-%m')
    surcharge = FuelSurcharge.objects.filter(
        carrier_name=carrier_name,
        year_month=year_month,
        currency=currency,
    ).first()
    return surcharge.amount if surcharge else None


# ── 카테고리 → 무게 추정 ─────────────────────────────────────────────────────

def estimate_weight_from_items(items: list[dict]) -> float:
    """
    items: [{'category': str, 'quantity': int}, ...]
    CategoryWeightPreset에서 카테고리별 평균 무게를 조회해 총 무게를 반환.
    미등록 카테고리는 DEFAULT_WEIGHT_KG 적용.
    """
    if not items:
        return DEFAULT_WEIGHT_KG

    category_names = [i['category'] for i in items if i.get('category')]
    presets = {
        p.category_name: p.avg_weight_kg
        for p in CategoryWeightPreset.objects.filter(category_name__in=category_names)
    }

    total = 0.0
    for item in items:
        cat    = item.get('category', '')
        qty    = max(int(item.get('quantity', 1)), 1)
        weight = presets.get(cat, DEFAULT_WEIGHT_KG)
        total += weight * qty

    return max(round(total, 3), 0.1)


# ── 자동 견적 메인 ───────────────────────────────────────────────────────────

def estimate_intl_shipping(
    weight_kg: float,
    mode: Optional[str] = None,
    cfg: Optional[dict] = None,
) -> tuple[list[dict], str]:
    """
    무게를 기반으로 활성화된 배송사 전체 견적을 반환합니다.

    weight_kg      : 과금 무게 (kg)
    mode           : 'AIR' | 'SEA' | 'EMS' — None 이면 ShippingModeConfig 자동 결정
    cfg            : load_rate_tables() 결과 (None 이면 자동 로드)

    Returns:
        (carriers: list[dict], mode_applied: str)
    """
    if cfg is None:
        cfg = load_rate_tables() or {}

    effective_mode = determine_mode(weight_kg, mode)

    qs = (
        ShippingCarrierProfile.objects
        .filter(is_active=True, mode=effective_mode)
        .select_related('rate_table')
        .order_by('sort_order', 'engine')
    )

    results = []
    for profile in qs:
        if profile.engine == 'TABLE':
            table_result = _calculate_table_freight(profile, weight_kg)
            results.append({
                'profile_id':   profile.id,
                'name':         profile.name,
                'engine':       'TABLE',
                'mode':         profile.mode,
                'is_default':   profile.is_default,
                'is_available': table_result.get('is_available', False),
                'freight_krw':  table_result.get('freight_krw'),
                'rejections':   table_result.get('rejections', []),
            })
            continue

        inp = _build_shipping_input(profile, weight_kg)
        if inp is None:
            continue

        quote = build_quote_response(inp, cfg=cfg)

        results.append({
            'profile_id':   profile.id,
            'name':         profile.name,
            'engine':       profile.engine,
            'mode':         profile.mode,
            'is_default':   profile.is_default,
            'is_available': quote.get('is_available', False),
            'freight_krw':  _extract_freight_krw(quote),
            'quote':        quote,
        })

    return results, effective_mode


def get_default_estimate(
    weight_kg: float,
    mode: str = 'AIR',
    cfg: Optional[dict] = None,
) -> Optional[dict]:
    """
    특정 mode의 기본 배송사(is_default=True) 견적만 반환.
    기본 배송사 없으면 첫 번째 활성 배송사 반환.
    """
    if cfg is None:
        cfg = load_rate_tables() or {}

    profile = (
        ShippingCarrierProfile.objects
        .filter(is_active=True, mode=mode, is_default=True)
        .select_related('rate_table')
        .order_by('sort_order')
        .first()
    )
    if profile is None:
        profile = (
            ShippingCarrierProfile.objects
            .filter(is_active=True, mode=mode)
            .select_related('rate_table')
            .order_by('sort_order')
            .first()
        )
    if profile is None:
        return None

    if profile.engine == 'TABLE':
        table_result = _calculate_table_freight(profile, weight_kg)
        return {
            'profile_id':   profile.id,
            'name':         profile.name,
            'engine':       'TABLE',
            'mode':         profile.mode,
            'is_default':   profile.is_default,
            'is_available': table_result.get('is_available', False),
            'freight_krw':  table_result.get('freight_krw'),
            'rejections':   table_result.get('rejections', []),
        }

    inp = _build_shipping_input(profile, weight_kg)
    if inp is None:
        return None

    quote = build_quote_response(inp, cfg=cfg)
    return {
        'profile_id':   profile.id,
        'name':         profile.name,
        'engine':       profile.engine,
        'mode':         profile.mode,
        'is_default':   profile.is_default,
        'is_available': quote.get('is_available', False),
        'freight_krw':  _extract_freight_krw(quote),
        'quote':        quote,
    }


# ── 내부 헬퍼 ────────────────────────────────────────────────────────────────

def _build_shipping_input(
    profile: ShippingCarrierProfile,
    weight_kg: float,
) -> Optional[ShippingInput]:
    """ShippingCarrierProfile → ShippingInput 변환. TABLE 엔진은 None 반환."""
    try:
        if profile.engine == 'FB':
            fsc = get_current_fsc(profile.name)
            return ShippingInput(
                service_provider=ServiceProvider.FB,
                transport_mode=TransportMode.AIR,
                actual_weight_kg=weight_kg,
                fb_tier=FbTier(profile.fb_tier or 'STANDARD'),
                fb_tax_mode=FbTaxMode(profile.fb_tax_mode or 'DDU'),
                fb_fsc_krw=fsc,
            )

        if profile.engine == 'KSE_AIR':
            return ShippingInput(
                service_provider=ServiceProvider.KSE,
                transport_mode=TransportMode.AIR,
                actual_weight_kg=weight_kg,
            )

        if profile.engine == 'KSE_SEA':
            return ShippingInput(
                service_provider=ServiceProvider.KSE,
                transport_mode=TransportMode.SEA,
                actual_weight_kg=weight_kg,
            )

        if profile.engine == 'KSE_SDEX':
            return ShippingInput(
                service_provider=ServiceProvider.KSE,
                transport_mode=TransportMode.SDEX,
                actual_weight_kg=weight_kg,
            )

        if profile.engine == 'CJL':
            return ShippingInput(
                service_provider=ServiceProvider.CJL,
                transport_mode=TransportMode.DOOR_TO_DOOR,
                actual_weight_kg=weight_kg,
            )

        if profile.engine == 'EMS':
            return ShippingInput(
                service_provider=ServiceProvider.EMS,
                transport_mode=TransportMode.AIR,
                actual_weight_kg=weight_kg,
            )

    except Exception:
        pass

    return None


def _calculate_table_freight(
    profile: ShippingCarrierProfile,
    weight_kg: float,
) -> dict:
    """TABLE 엔진: rate_table에서 무게 구간을 직접 조회해 운임 반환."""
    if not profile.rate_table:
        return {
            'is_available': False,
            'freight_krw':  None,
            'rejections':   [{'code': 'NO_RATE_TABLE', 'message': '요율표가 설정되지 않았습니다.'}],
        }

    rate_dict = profile.rate_table.to_dict()
    if not rate_dict:
        return {
            'is_available': False,
            'freight_krw':  None,
            'rejections':   [{'code': 'EMPTY_RATE_TABLE', 'message': '요율표 구간이 없습니다.'}],
        }

    breaks = sorted(rate_dict.keys())
    matched = next((b for b in breaks if b >= weight_kg), None)
    if matched is None:
        return {
            'is_available': False,
            'freight_krw':  None,
            'rejections':   [{'code': 'WEIGHT_EXCEEDS',
                              'message': f'요율표 최대 무게({max(breaks)} kg) 초과'}],
        }

    freight  = rate_dict[matched]
    currency = profile.rate_table.currency
    return {
        'is_available':            True,
        'freight_krw':             freight if currency == 'KRW' else None,
        'freight_raw':             freight,
        'currency':                currency,
        'weight_break_applied_kg': matched,
        'rejections':              [],
    }


def _extract_freight_krw(quote: dict) -> Optional[int]:
    """quote 응답에서 KRW 운임을 추출 (배송사별 구조가 다름)."""
    if not quote.get('is_available'):
        return None
    bd = quote.get('freight_breakdown') or {}

    if 'fb' in bd:
        return bd['fb'].get('base_freight_krw')
    if 'cjl' in bd:
        return bd['cjl'].get('base_freight_krw')
    if 'ems' in bd:
        return bd['ems'].get('base_freight_krw')
    # KSE는 JPY 기준 → None (환율 변환은 호출측에서 처리)
    return None
