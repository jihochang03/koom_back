"""
한국 → 일본 B2C 배송비 계산 엔진
지원 서비스: KSE (Sea / Air / SDEX), CJL Door to Door

설계 기준:
- 일본 고객 청구 금액(JPY)과 내부 원가/부가비용(KRW)을 분리
- 미확정 항목은 null 반환 + isEstimateComplete=False 플래그
- 문서 기반으로만 구현, 미기재 사항은 별도 표기
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Enum 정의
# ─────────────────────────────────────────────────────────────────────────────

class ServiceProvider(str, Enum):
    KSE = "KSE"
    CJL = "CJL"
    FB  = "FB"   # FastBox (DHUB) 항공 특송
    EMS = "EMS"  # 한국우편 EMS → 일본


class FbTier(str, Enum):
    STANDARD = "STANDARD"   # 표준
    VIP      = "VIP"        # 월 1,000건 이상
    SVIP     = "SVIP"       # 월 3,000건 이상
    SSVIP    = "SSVIP"      # 월 7,000건 이상


class FbTaxMode(str, Enum):
    DDU = "DDU"   # 구매자 납부 (건당 20엔 신청료 추가)
    DDP = "DDP"   # 판매자 납부


class TransportMode(str, Enum):
    SEA          = "SEA"
    AIR          = "AIR"
    SDEX         = "SDEX"
    DOOR_TO_DOOR = "DOOR_TO_DOOR"


class ServiceClass(str, Enum):
    LIGHT        = "LIGHT"
    STANDARD     = "STANDARD"
    OVERSIZE     = "OVERSIZE"
    DOOR_TO_DOOR = "DOOR_TO_DOOR"


class DestinationRegion(str, Enum):
    EAST_JAPAN = "EAST_JAPAN"
    WEST_JAPAN = "WEST_JAPAN"
    JEJU       = "JEJU"


class ExportDeclarationType(str, Enum):
    NONE            = "NONE"
    MANIFEST        = "MANIFEST"          # 목록통관 (무료)
    SIMPLIFIED      = "SIMPLIFIED"        # 간이수출신고 200원 + VAT
    LIST_CONVERSION = "LIST_CONVERSION"   # 수출목록변환신고 150원 + VAT


class PackingType(str, Enum):
    BOX         = "BOX"
    POUCH       = "POUCH"
    PAPER_BAG   = "PAPER_BAG"
    ROUND_SHAPED = "ROUND_SHAPED"
    OTHER       = "OTHER"


class InboundType(str, Enum):
    PALLET = "PALLET"
    BOX    = "BOX"


class StorageType(str, Enum):
    PALLET = "PALLET"
    SHELF  = "SHELF"


class CjlVolumetricPolicy(str, Enum):
    ACTUAL_ONLY    = "ACTUAL_ONLY"     # 실제무게만 사용 (기본값, 문서 미기재)
    USE_SAME_AS_KSE = "USE_SAME_AS_KSE"  # KSE와 동일하게 /6000 적용


# ─────────────────────────────────────────────────────────────────────────────
# 요율표 (문서 원본 그대로, 생략 없음)
# key: 구간 무게(kg), value: 운임
# ─────────────────────────────────────────────────────────────────────────────

KSE_RATE_TABLES: Dict[tuple, Dict[float, int]] = {
    # ── KSE 해상 Standard (JPY) ──────────────────────────────────────────────
    (TransportMode.SEA, ServiceClass.STANDARD): {
        0.10: 440,  0.25: 515,  0.50: 570,  0.75: 650,
        1.00: 690,  1.25: 740,  1.50: 780,  1.75: 840,
        2.00: 890,  2.50: 920,  3.00: 980,  3.50: 1040,
        4.00: 1100, 4.50: 1150, 5.00: 1260, 5.50: 1370,
        6.00: 1460, 6.50: 1550, 7.00: 1625, 7.50: 1700,
        8.00: 1750, 8.50: 1820, 9.00: 1900, 9.50: 1960,
        10.00: 2040, 10.50: 2120, 11.00: 2200, 11.50: 2250,
        12.00: 2350, 12.50: 2430, 13.00: 2500, 13.50: 2560,
        14.00: 2640, 14.50: 2710, 15.00: 2780, 15.50: 2850,
        16.00: 2940, 16.50: 3020, 17.00: 3090, 17.50: 3170,
    },
    # ── KSE 해상 Light (JPY) ─────────────────────────────────────────────────
    (TransportMode.SEA, ServiceClass.LIGHT): {
        0.10: 350, 0.30: 400, 0.55: 460, 0.75: 490, 1.00: 530,
    },
    # ── KSE 항공 Standard (JPY) ──────────────────────────────────────────────
    (TransportMode.AIR, ServiceClass.STANDARD): {
        0.10: 475,  0.25: 550,  0.50: 610,  0.75: 670,
        1.00: 720,  1.25: 760,  1.50: 800,  1.75: 860,
        2.00: 920,  2.50: 1070, 3.00: 1177, 3.50: 1268,
        4.00: 1368, 4.50: 1461, 5.00: 1554, 5.50: 1759,
        6.00: 1859, 6.50: 1952, 7.00: 2045, 7.50: 2138,
        8.00: 2230, 8.50: 2333, 9.00: 2426, 9.50: 2519,
        10.00: 2616, 10.50: 2836, 11.00: 2929, 11.50: 3025,
        12.00: 3125, 12.50: 3218, 13.00: 3310, 13.50: 3403,
        14.00: 3503, 14.50: 3596, 15.00: 3689, 15.50: 3782,
        16.00: 3874, 16.50: 3977, 17.00: 4070, 17.50: 4163,
    },
    # ── KSE 항공 Light (JPY) ─────────────────────────────────────────────────
    # 2번째 구간: 0.30kg (SDEX Light와 다름)
    (TransportMode.AIR, ServiceClass.LIGHT): {
        0.10: 350, 0.30: 400, 0.55: 460, 0.75: 490, 1.00: 530,
    },
    # ── KSE SDEX Standard (JPY) ──────────────────────────────────────────────
    # ※ 8.00kg 구간에서 ¥1,525 → ¥2,230 급등 (문서 원본 그대로 반영, 확인 필요)
    (TransportMode.SDEX, ServiceClass.STANDARD): {
        0.10: 515,  0.25: 575,  0.50: 645,  0.75: 695,
        1.00: 715,  1.25: 755,  1.50: 795,  1.75: 825,
        2.00: 865,  2.50: 935,  3.00: 995,  3.50: 1055,
        4.00: 1105, 4.50: 1165, 5.00: 1215, 5.50: 1275,
        6.00: 1355, 6.50: 1415, 7.00: 1465, 7.50: 1525,
        8.00: 2230, 8.50: 2333, 9.00: 2426, 9.50: 2519,
        10.00: 2616, 10.50: 2836, 11.00: 2929, 11.50: 3025,
        12.00: 3125, 12.50: 3218, 13.00: 3310, 13.50: 3403,
        14.00: 3503, 14.50: 3596, 15.00: 3689, 15.50: 3782,
        16.00: 3874, 16.50: 3977, 17.00: 4070, 17.50: 4163,
    },
    # ── KSE SDEX Light (JPY) ─────────────────────────────────────────────────
    # ※ 2번째 구간: 0.25kg (Sea/Air Light의 0.30kg과 다름 — 문서 원본 반영)
    (TransportMode.SDEX, ServiceClass.LIGHT): {
        0.10: 350, 0.25: 400, 0.55: 460, 0.75: 490, 1.00: 530,
    },
}

# ── FastBox (DHUB) 항공 특송 (KRW) ─────────────────────────────────────────
# 유류할증료(FSC) 별도, 최대 20kg, 부피무게 = W×L×H/6000
# 출처: FastBox 서비스 요율표 (2025년 기준)
FB_RATE_TABLES: Dict[FbTier, Dict[float, int]] = {
    FbTier.STANDARD: {
        0.3: 6610,  0.5: 7210,  0.7: 7510,  1.0: 7960,
        1.5: 8710,  2.0: 9460,  2.5: 10810, 3.0: 11560,
        3.5: 12610, 4.0: 13360, 4.5: 14110, 5.0: 14860,
        5.5: 16410, 6.0: 17160, 6.5: 18310, 7.0: 19060,
        7.5: 19810, 8.0: 20560, 8.5: 21310, 9.0: 22060,
        9.5: 22810, 10.0: 23560, 10.5: 27010, 11.0: 27760,
        11.5: 28510, 12.0: 29260, 12.5: 30010, 13.0: 30760,
        13.5: 31510, 14.0: 32260, 14.5: 33010, 15.0: 33760,
        15.5: 34810, 16.0: 35560, 16.5: 36310, 17.0: 37060,
        17.5: 37810, 18.0: 38560, 18.5: 39310, 19.0: 40060,
        19.5: 40810, 20.0: 41560,
    },
    FbTier.VIP: {
        0.3: 6410,  0.5: 6910,  0.7: 7210,  1.0: 7660,
        1.5: 8410,  2.0: 9160,  2.5: 10510, 3.0: 11260,
        3.5: 12310, 4.0: 13060, 4.5: 13810, 5.0: 14560,
        5.5: 16110, 6.0: 16860, 6.5: 17910, 7.0: 18660,
        7.5: 19410, 8.0: 20160, 8.5: 20910, 9.0: 21660,
        9.5: 22410, 10.0: 23160, 10.5: 26510, 11.0: 27260,
        11.5: 28010, 12.0: 28760, 12.5: 29510, 13.0: 30260,
        13.5: 31010, 14.0: 31760, 14.5: 32510, 15.0: 33260,
        15.5: 34210, 16.0: 34960, 16.5: 35710, 17.0: 36460,
        17.5: 37210, 18.0: 37960, 18.5: 38710, 19.0: 39460,
        19.5: 40210, 20.0: 40960,
    },
    FbTier.SVIP: {
        0.3: 6210,  0.5: 6710,  0.7: 7010,  1.0: 7460,
        1.5: 8210,  2.0: 8960,  2.5: 10310, 3.0: 11060,
        3.5: 12010, 4.0: 12760, 4.5: 13510, 5.0: 14260,
        5.5: 15810, 6.0: 16560, 6.5: 17460, 7.0: 18210,
        7.5: 18960, 8.0: 19710, 8.5: 20460, 9.0: 21210,
        9.5: 21960, 10.0: 22710, 10.5: 26010, 11.0: 26760,
        11.5: 27510, 12.0: 28260, 12.5: 29010, 13.0: 29760,
        13.5: 30510, 14.0: 31260, 14.5: 32010, 15.0: 32760,
        15.5: 33810, 16.0: 34560, 16.5: 35310, 17.0: 36060,
        17.5: 36810, 18.0: 37560, 18.5: 38310, 19.0: 39060,
        19.5: 39810, 20.0: 40560,
    },
    FbTier.SSVIP: {
        0.3: 6010,  0.5: 6410,  0.7: 6710,  1.0: 7160,
        1.5: 7910,  2.0: 8660,  2.5: 10010, 3.0: 10760,
        3.5: 11710, 4.0: 12460, 4.5: 13210, 5.0: 13960,
        5.5: 15510, 6.0: 16260, 6.5: 17210, 7.0: 17960,
        7.5: 18710, 8.0: 19460, 8.5: 20210, 9.0: 20960,
        9.5: 21710, 10.0: 22460, 10.5: 25810, 11.0: 26560,
        11.5: 27310, 12.0: 28060, 12.5: 28810, 13.0: 29560,
        13.5: 30310, 14.0: 31060, 14.5: 31810, 15.0: 32560,
        15.5: 33510, 16.0: 34260, 16.5: 35010, 17.0: 35760,
        17.5: 36510, 18.0: 37260, 18.5: 38010, 19.0: 38760,
        19.5: 39510, 20.0: 40260,
    },
}

# FastBox 제약
FB_MAX_WEIGHT_KG    = 20.0
FB_MAX_GIRTH_CM     = 160.0   # 세 변의 합
FB_MAX_SIDE_CM      = 100.0   # 한 변 최대
FB_DDU_SURCHARGE_JPY = 20     # DDU 선택 시 건당 추가 신청료(엔)
FB_RETURN_FEE_JPY   = 550     # 영업소 미수령 반송 수수료(엔)

# ── 한국우편 EMS → 일본 (KRW) ───────────────────────────────────────────────
# 요율은 Admin의 ShippingRateTable(table_key='EMS_JP_STANDARD')에서 관리.
# 하드코딩 값이 없으므로 DB 미등록 시 is_available=False 반환.
EMS_RATE_TABLE: Dict[float, int] = {}  # Admin에서 입력 (EMS_JP_STANDARD 요율표)

EMS_MAX_WEIGHT_KG = 30.0   # EMS 최대 30kg
EMS_MAX_GIRTH_CM  = 300.0  # EMS 최대 세 변의 합 300cm (한 변 최대 150cm)
EMS_MAX_SIDE_CM   = 150.0

# ── CJL Door to Door (KRW) ───────────────────────────────────────────────────
CJL_RATE_TABLE: Dict[float, int] = {
    0.5: 8500,   1.0: 9100,   1.5: 9600,   2.0: 10100,
    2.5: 11500,  3.0: 12200,  3.5: 12700,  4.0: 13200,
    4.5: 13800,  5.0: 14300,  5.5: 15700,  6.0: 16300,
    6.5: 16800,  7.0: 17300,  7.5: 17900,  8.0: 18400,
    8.5: 18900,  9.0: 19500,  9.5: 20000,  10.0: 20500,
    10.5: 24800, 11.0: 25400, 11.5: 25900, 12.0: 26400,
    12.5: 26900, 13.0: 27500, 13.5: 28000, 14.0: 28500,
    14.5: 29100, 15.0: 29600, 15.5: 30100, 16.0: 30700,
    16.5: 31200, 17.0: 31700, 17.5: 32300, 18.0: 32800,
    18.5: 33300, 19.0: 33900, 19.5: 34400, 20.0: 34900,
}

# CJL 면세/상한 기준 (JPY) — 문서상 확정
CJL_TAX_EXEMPT_THRESHOLD_JPY = 10_000
CJL_MAX_INVOICE_JPY          = 300_000

# CJL 지역 추가비 (JPY/BOX) — 문서상 확정
CJL_REGIONAL_FEE_GENERAL_JPY = 1_800
CJL_REGIONAL_FEE_JEJU_JPY    = 3_500

# KSE 수출신고 단가 (KRW) — 문서상 확정
EXPORT_FEE_SIMPLIFIED_KRW      = 200
EXPORT_FEE_LIST_CONVERSION_KRW = 150

# KSE 3PL 단가 (KRW) — 문서상 확정
FULFILLMENT_PICKING_BASE_KRW    = 900
FULFILLMENT_COMBINED_PER_KRW    = 50
FULFILLMENT_INBOUND_PALLET_KRW  = 6_000
FULFILLMENT_INBOUND_BOX_KRW     = 1_000
FULFILLMENT_STORAGE_KRW         = 30_000   # PALLET, SHELF 동일
FULFILLMENT_LABEL_PER_KRW       = 100
FULFILLMENT_RETURN_PROC_KRW     = 500
FULFILLMENT_PALLET_DISPOSE_KRW  = 7_000


# ─────────────────────────────────────────────────────────────────────────────
# 입력 데이터클래스
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ShippingInput:
    # ── 서비스 선택 ──────────────────────────────────────────────────────────
    service_provider: ServiceProvider
    transport_mode: TransportMode

    # ── 패키지 물리 정보 ─────────────────────────────────────────────────────
    actual_weight_kg: float
    width_cm: Optional[float]  = None
    length_cm: Optional[float] = None
    height_cm: Optional[float] = None
    thickness_cm: Optional[float] = None   # KSE Light 판정용 (≤3cm)
    longest_side_cm: Optional[float] = None
    girth_sum_cm: Optional[float] = None   # None이면 width+length+height 자동 계산
    box_count: int = 1
    item_count: int = 1

    # ── 지역 ─────────────────────────────────────────────────────────────────
    destination_region: DestinationRegion = DestinationRegion.EAST_JAPAN

    # ── 통관 ─────────────────────────────────────────────────────────────────
    invoice_value_jpy: float = 0.0
    export_declaration_type: ExportDeclarationType = ExportDeclarationType.NONE
    vat_rate: Optional[float] = None       # 수출신고비 VAT율, configurable

    # ── 화물 특성 ─────────────────────────────────────────────────────────────
    packing_type: PackingType = PackingType.BOX
    is_combined_packing: bool = False
    has_battery: bool = False
    is_dangerous_goods: bool = False
    is_alcohol: bool = False
    is_tobacco: bool = False
    is_food_or_quarantine: bool = False
    is_copyright_sensitive: bool = False
    is_plant_or_animal: bool = False
    is_narcotics: bool = False
    is_child_pornography: bool = False
    is_ip_infringement: bool = False
    is_return_shipment: bool = False

    # ── FSC (AIR 전용) ────────────────────────────────────────────────────────
    fsc_amount_jpy: Optional[float] = None  # AIR 선택 시 필요, 미확정이면 None

    # ── FastBox 전용 ──────────────────────────────────────────────────────────
    fb_tier: FbTier = FbTier.STANDARD
    fb_tax_mode: FbTaxMode = FbTaxMode.DDU
    fb_fsc_krw: Optional[float] = None   # 유류할증료(KRW), 미입력 시 견적 불완전

    # ── CJL 부피무게 정책 ─────────────────────────────────────────────────────
    cjl_volumetric_policy: CjlVolumetricPolicy = CjlVolumetricPolicy.ACTUAL_ONLY

    # ── KSE 서비스 클래스 힌트 ────────────────────────────────────────────────
    requested_service_class: Optional[ServiceClass] = None  # None=AUTO

    # ── 3PL 비용 ──────────────────────────────────────────────────────────────
    inbound_type: Optional[InboundType] = None
    storage_type: Optional[StorageType] = None
    label_work_count: int = 0
    return_processing_count: int = 0
    pallet_disposal_count: int = 0
    packing_material_provided_by_client: bool = False
    extra_packing_fee_krw: Optional[float] = None

    # ── 수동 조정 ─────────────────────────────────────────────────────────────
    manual_oversize_fee: Optional[float] = None  # 금액 미정 시 None


# ─────────────────────────────────────────────────────────────────────────────
# 커스텀 예외
# ─────────────────────────────────────────────────────────────────────────────

class WeightExceedsTableError(Exception):
    pass

class InvalidExportDeclarationTypeError(Exception):
    pass

class VatRateNotProvidedError(Exception):
    pass


# ─────────────────────────────────────────────────────────────────────────────
# 핵심 계산 함수
# ─────────────────────────────────────────────────────────────────────────────

def calculate_volumetric_weight(
    width_cm: Optional[float],
    length_cm: Optional[float],
    height_cm: Optional[float],
) -> Optional[float]:
    """
    KSE 부피무게 = (W × L × H) / 6000 [문서상 확정]
    치수 중 하나라도 None이면 None 반환.
    """
    if width_cm is None or length_cm is None or height_cm is None:
        return None
    return (width_cm * length_cm * height_cm) / 6000.0


def resolve_girth_sum(inp: ShippingInput) -> Optional[float]:
    """girth_sum_cm 직접 입력 없으면 세 변 합산 자동 계산."""
    if inp.girth_sum_cm is not None:
        return inp.girth_sum_cm
    if inp.width_cm and inp.length_cm and inp.height_cm:
        return inp.width_cm + inp.length_cm + inp.height_cm
    return None


def is_eligible_for_kse_light(
    girth_sum_cm: Optional[float],
    longest_side_cm: Optional[float],
    thickness_cm: Optional[float],
    actual_weight_kg: float,
) -> bool:
    """
    KSE Light (YU-PACKET) 판정 — 4가지 조건 모두 AND [문서상 확정]
    입력 중 하나라도 None이면 False (보수적 판정).
    """
    if any(v is None for v in [girth_sum_cm, longest_side_cm, thickness_cm]):
        return False
    return (
        girth_sum_cm <= 60        # 세 변의 합 60cm 이내
        and longest_side_cm <= 34 # 한 변 최대 34cm 이내
        and thickness_cm <= 3     # 두께 3cm 이하
        and actual_weight_kg <= 1.0
    )


def is_eligible_for_kse_standard(
    girth_sum_cm: Optional[float],
    actual_weight_kg: float,
) -> bool:
    """
    KSE Standard (YU-PACK) 판정 [문서상 확정]
    girth_sum_cm None이면 치수 미입력 → 무게 조건만 체크 (합리적 구현안, 검증 필요)
    """
    weight_ok = actual_weight_kg <= 30
    if girth_sum_cm is None:
        return weight_ok
    return girth_sum_cm <= 160 and weight_ok


def find_ceil_weight_break(
    chargeable_weight_kg: float,
    rate_table: Dict[float, int],
) -> float:
    """
    chargeable_weight_kg 이상인 최소 구간 반환 (올림 적용).
    [합리적 구현안 / 검증 필요]

    예) 0.62kg → 0.75kg 구간
    예) 0.55kg → 0.55kg 구간 (정확히 일치)
    """
    for break_kg in sorted(rate_table.keys()):
        if chargeable_weight_kg <= break_kg + 1e-9:  # 부동소수점 허용
            return break_kg
    max_break = max(rate_table.keys())
    raise WeightExceedsTableError(
        f"과금무게 {chargeable_weight_kg:.3f}kg이 요율표 최대 구간 {max_break}kg을 초과합니다. "
        f"별도 견적이 필요합니다."
    )


# ─────────────────────────────────────────────────────────────────────────────
# 품목 검증
# ─────────────────────────────────────────────────────────────────────────────

def validate_restricted_items(inp: ShippingInput) -> tuple[List[dict], List[dict]]:
    """
    반환: (rejection_reasons, warnings)
    rejection_reasons가 비어 있지 않으면 즉시 거절.
    """
    rejections: List[dict] = []
    warnings:   List[dict] = []

    # 금지품목 (즉시 거절)
    if inp.is_narcotics:
        rejections.append({"code": "PROHIBITED_NARCOTICS",
                            "message": "마약/향정신성/대마 등 금지품목"})
    if inp.is_child_pornography:
        rejections.append({"code": "PROHIBITED_CHILD_PORNOGRAPHY",
                            "message": "아동포르노 금지품목"})
    if inp.is_ip_infringement:
        rejections.append({"code": "PROHIBITED_IP_INFRINGEMENT",
                            "message": "지재권 침해물 금지품목"})

    # 주의품목 (경고 후 수동 검토)
    if inp.has_battery:
        warnings.append({"code": "BATTERY_REQUIRES_REVIEW",
                          "message": "배터리류 포함 — 수동 검토 필요"})
    if inp.is_dangerous_goods:
        warnings.append({"code": "DANGEROUS_GOODS_REQUIRES_REVIEW",
                          "message": "위험물 포함 — 수동 검토 필요"})
    if inp.is_alcohol:
        warnings.append({"code": "ALCOHOL_REQUIRES_REVIEW",
                          "message": "주류 포함 — 수동 검토 필요"})
    if inp.is_tobacco:
        warnings.append({"code": "TOBACCO_REQUIRES_REVIEW",
                          "message": "담배 포함 — 수동 검토 필요"})
    if inp.is_food_or_quarantine:
        warnings.append({"code": "FOOD_QUARANTINE_REQUIRES_REVIEW",
                          "message": "식검 대상 식품/성분/식물/동물 — 수동 검토 필요"})
    if inp.is_copyright_sensitive:
        warnings.append({"code": "COPYRIGHT_ITEM_REQUIRES_REVIEW",
                          "message": "CD/DVD 등 저작권 민감 품목 — 수동 검토 필요"})
    if inp.is_plant_or_animal:
        warnings.append({"code": "PLANT_ANIMAL_REQUIRES_REVIEW",
                          "message": "식물/동물 포함 — 수동 검토 필요"})

    return rejections, warnings


# ─────────────────────────────────────────────────────────────────────────────
# KSE 운송비 계산
# ─────────────────────────────────────────────────────────────────────────────

def calculate_kse_freight(inp: ShippingInput, cfg: Optional[dict] = None) -> dict:
    """
    KSE 운송비 계산.
    cfg: {'kse_rate_tables': {...}} 형태로 DB 요율표 override 가능.
    """
    warnings: List[dict] = []
    rejections: List[dict] = []

    _kse_tables = (cfg or {}).get('kse_rate_tables', KSE_RATE_TABLES)

    girth_sum = resolve_girth_sum(inp)

    # ── 부피무게 & 과금무게 ───────────────────────────────────────────────────
    volumetric_weight = calculate_volumetric_weight(
        inp.width_cm, inp.length_cm, inp.height_cm
    )
    if volumetric_weight is None:
        warnings.append({"code": "VOLUMETRIC_NOT_CALCULATED",
                          "message": "치수 미입력으로 부피무게 계산 불가, 실제무게로 계산"})
        chargeable_weight = inp.actual_weight_kg
    else:
        chargeable_weight = max(inp.actual_weight_kg, volumetric_weight)

    # ── 서비스 클래스 판정 ────────────────────────────────────────────────────
    light_ok    = is_eligible_for_kse_light(
        girth_sum, inp.longest_side_cm, inp.thickness_cm, inp.actual_weight_kg
    )
    standard_ok = is_eligible_for_kse_standard(girth_sum, inp.actual_weight_kg)

    requested = inp.requested_service_class
    if requested == ServiceClass.LIGHT:
        if light_ok:
            service_class = ServiceClass.LIGHT
        else:
            warnings.append({"code": "KSE_LIGHT_DOWNGRADED_TO_STANDARD",
                              "message": "Light 규격 미충족 → Standard로 자동 변경"})
            service_class = ServiceClass.STANDARD
    elif requested == ServiceClass.STANDARD:
        service_class = ServiceClass.STANDARD
    else:
        service_class = ServiceClass.LIGHT if light_ok else ServiceClass.STANDARD

    # ── Standard 규격 초과 체크 ───────────────────────────────────────────────
    if service_class == ServiceClass.STANDARD and not standard_ok:
        return {
            "is_available": False,
            "rejections": [{"code": "KSE_OVERSIZE_NO_POLICY",
                             "message": "세 변의 합 160cm 초과 또는 30kg 초과 — 별도 확인 필요"}],
            "warnings": warnings,
        }

    # ── 요율표 선택 & 구간 조회 ───────────────────────────────────────────────
    table_key = (inp.transport_mode, service_class)
    rate_table = _kse_tables.get(table_key)
    if rate_table is None:
        return {
            "is_available": False,
            "rejections": [{"code": "INVALID_RATE_TABLE_KEY",
                             "message": f"요율표 없음: {table_key}"}],
            "warnings": warnings,
        }

    try:
        weight_break = find_ceil_weight_break(chargeable_weight, rate_table)
    except WeightExceedsTableError as e:
        return {
            "is_available": False,
            "rejections": [{"code": "KSE_WEIGHT_EXCEEDS_RATE_TABLE",
                             "message": str(e)}],
            "warnings": warnings,
        }

    base_freight_jpy = rate_table[weight_break]

    # ── FSC 처리 ──────────────────────────────────────────────────────────────
    if inp.transport_mode == TransportMode.AIR:
        if inp.fsc_amount_jpy is None:
            fsc_jpy = None
            warnings.append({"code": "FSC_NOT_PROVIDED_ESTIMATE_INCOMPLETE",
                              "message": "AIR FSC 미입력 — 총액 불완전. FSC 금액 확인 필요"})
        else:
            fsc_jpy = inp.fsc_amount_jpy
    elif inp.transport_mode == TransportMode.SDEX:
        fsc_jpy = 0  # SDEX: FSC 포함된 요율표
    else:
        fsc_jpy = 0  # SEA: FSC 없음

    # SDEX 8kg 급등 구간 경고
    if inp.transport_mode == TransportMode.SDEX and weight_break >= 8.0:
        warnings.append({"code": "SDEX_RATE_8KG_JUMP_VERIFY",
                          "message": "SDEX Standard 8.00kg 구간 급등(¥1,525→¥2,230) — 원본 문서 확인 권장"})

    total_freight_jpy = (
        base_freight_jpy + fsc_jpy if fsc_jpy is not None else None
    )

    return {
        "is_available": True,
        "rejections": rejections,
        "warnings": warnings,
        "service_class": service_class,
        "selected_rate_table": f"{inp.transport_mode.value}_{service_class.value}",
        "actual_weight_kg": inp.actual_weight_kg,
        "volumetric_weight_kg": volumetric_weight,
        "chargeable_weight_kg": chargeable_weight,
        "weight_break_applied_kg": weight_break,
        "base_freight_jpy": base_freight_jpy,
        "fsc_jpy": fsc_jpy,
        "total_freight_jpy": total_freight_jpy,
        "currency": "JPY",
        "fsc_note": (
            "SEA: FSC 없음" if inp.transport_mode == TransportMode.SEA
            else "SDEX: FSC 포함 요율표" if inp.transport_mode == TransportMode.SDEX
            else "AIR: FSC 별도 (수동 입력)"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# CJL 운송비 계산
# ─────────────────────────────────────────────────────────────────────────────

def calculate_cjl_freight(inp: ShippingInput, cfg: Optional[dict] = None) -> dict:
    """
    CJL Door to Door 운송비 계산.
    cfg: {'cjl_rate_table': {...}, 'CJL_TAX_EXEMPT_THRESHOLD_JPY': ..., ...} override 가능.
    """
    warnings: List[dict] = []
    rejections: List[dict] = []

    c = cfg or {}
    _CJL_TABLE          = c.get('cjl_rate_table',                CJL_RATE_TABLE)
    _CJL_EXEMPT         = c.get('CJL_TAX_EXEMPT_THRESHOLD_JPY',  CJL_TAX_EXEMPT_THRESHOLD_JPY)
    _CJL_MAX_INVOICE    = c.get('CJL_MAX_INVOICE_JPY',           CJL_MAX_INVOICE_JPY)
    _CJL_FEE_GENERAL    = c.get('CJL_REGIONAL_FEE_GENERAL_JPY',  CJL_REGIONAL_FEE_GENERAL_JPY)
    _CJL_FEE_JEJU       = c.get('CJL_REGIONAL_FEE_JEJU_JPY',     CJL_REGIONAL_FEE_JEJU_JPY)

    girth_sum = resolve_girth_sum(inp)

    # ── 포장 제한 ─────────────────────────────────────────────────────────────
    if inp.packing_type == PackingType.PAPER_BAG:
        return {
            "is_available": False,
            "rejections": [{"code": "CJL_PAPER_BAG_NOT_ACCEPTED",
                             "message": "종이봉투 포장 접수 불가"}],
            "warnings": warnings,
        }
    if inp.is_combined_packing:
        return {
            "is_available": False,
            "rejections": [{"code": "CJL_COMBINED_PACKING_NOT_ACCEPTED",
                             "message": "컨바인 포장(박스 2개를 1개로 묶기) 불가"}],
            "warnings": warnings,
        }
    if inp.packing_type == PackingType.ROUND_SHAPED:
        warnings.append({"code": "CJL_ROUND_SHAPE_CHECK_REQUIRED",
                          "message": "원형/원형 근사 포장 — 접수 가능 여부 별도 확인 필요"})

    # ── 치수 제한 ─────────────────────────────────────────────────────────────
    if inp.longest_side_cm is not None and inp.longest_side_cm >= 100:
        return {
            "is_available": False,
            "rejections": [{"code": "CJL_MAX_SINGLE_SIDE_EXCEEDED",
                             "message": f"한 변 {inp.longest_side_cm}cm ≥ 100cm 초과 불가"}],
            "warnings": warnings,
        }

    oversize_fee: Optional[float] = None
    if girth_sum is not None and girth_sum >= 160:
        oversize_fee = inp.manual_oversize_fee
        warnings.append({"code": "CJL_OVERSIZE_SURCHARGE_REQUIRED",
                          "message": (
                              f"160사이즈 초과({girth_sum}cm) — OVER SIZE 요금 별도 확인 필요. "
                              f"manual_oversize_fee {'입력됨' if oversize_fee is not None else '미입력(견적 불완전)'}"
                          )})

    # ── Invoice 상한 ──────────────────────────────────────────────────────────
    if inp.invoice_value_jpy > _CJL_MAX_INVOICE:
        return {
            "is_available": False,
            "rejections": [{"code": "CJL_INVOICE_EXCEEDS_300K_JPY",
                             "message": f"Invoice {inp.invoice_value_jpy:,.0f}엔 > {_CJL_MAX_INVOICE:,.0f}엔 상한 초과"}],
            "warnings": warnings,
        }

    # ── 부피무게 정책 ─────────────────────────────────────────────────────────
    if inp.cjl_volumetric_policy == CjlVolumetricPolicy.USE_SAME_AS_KSE:
        vol_w = calculate_volumetric_weight(inp.width_cm, inp.length_cm, inp.height_cm)
        chargeable_weight = max(inp.actual_weight_kg, vol_w) if vol_w else inp.actual_weight_kg
    else:
        vol_w = None
        chargeable_weight = inp.actual_weight_kg

    # ── 요율표 조회 ───────────────────────────────────────────────────────────
    try:
        weight_break = find_ceil_weight_break(chargeable_weight, _CJL_TABLE)
    except WeightExceedsTableError as e:
        return {
            "is_available": False,
            "rejections": [{"code": "CJL_WEIGHT_EXCEEDS_RATE_TABLE", "message": str(e)}],
            "warnings": warnings,
        }

    base_freight_krw = _CJL_TABLE[weight_break]

    # ── 지역 추가비 ───────────────────────────────────────────────────────────
    regional_fee_jpy = (
        _CJL_FEE_JEJU if inp.destination_region == DestinationRegion.JEJU
        else _CJL_FEE_GENERAL
    ) * inp.box_count

    # ── 반송 ──────────────────────────────────────────────────────────────────
    return_fee: Optional[float] = None
    if inp.is_return_shipment:
        return_fee = None
        warnings.append({"code": "CJL_RETURN_FEE_REQUIRES_CONFIRMATION",
                          "message": "반품/반송(적戻し) — 이유서 작성 필요, 요금 별도 확인"})

    # ── 면세/과세 판정 ────────────────────────────────────────────────────────
    is_tax_exempt = inp.invoice_value_jpy <= _CJL_EXEMPT
    customs_note = (
        f"면세 범위 이내 (Invoice {inp.invoice_value_jpy:,.0f}엔 ≤ {_CJL_EXEMPT:,}엔)"
        if is_tax_exempt
        else f"과세 대상 (Invoice {inp.invoice_value_jpy:,.0f}엔 > {_CJL_EXEMPT:,}엔) — 관부가세 수령인 부담 가능"
    )
    if not is_tax_exempt:
        warnings.append({"code": "CJL_CUSTOMS_TAXABLE", "message": customs_note})

    # ── 집계 ──────────────────────────────────────────────────────────────────
    total_freight_krw = base_freight_krw + (oversize_fee or 0)
    is_estimate_complete = oversize_fee is not None or (girth_sum is None or girth_sum < 160)
    is_estimate_complete = is_estimate_complete and return_fee is not None if inp.is_return_shipment else is_estimate_complete

    return {
        "is_available": True,
        "rejections": rejections,
        "warnings": warnings,
        "actual_weight_kg": inp.actual_weight_kg,
        "volumetric_weight_kg": vol_w,
        "chargeable_weight_kg": chargeable_weight,
        "volumetric_policy": inp.cjl_volumetric_policy.value,
        "weight_break_applied_kg": weight_break,
        "base_freight_krw": base_freight_krw,
        "regional_fee_jpy": regional_fee_jpy,
        "regional_fee_note": "지역추가비 단위: ¥(JPY)/BOX — 실제 정산 통화 별도 확인 필요",
        "oversize_fee": oversize_fee,
        "return_exception_fee": return_fee,
        "total_freight_krw": total_freight_krw,
        "is_tax_exempt": is_tax_exempt,
        "customs_note": customs_note,
        "payment_terms": "월말 마감, 익월말 지급",
        "is_estimate_complete": is_estimate_complete,
        "currency_note": "기본 운임: KRW / 지역추가비: JPY — 혼합 통화",
    }


# ─────────────────────────────────────────────────────────────────────────────
# 수출신고 비용 계산
# ─────────────────────────────────────────────────────────────────────────────

def calculate_export_declaration_fee(
    export_type: ExportDeclarationType,
    vat_rate: Optional[float],
    cfg: Optional[dict] = None,
) -> dict:
    """
    수출신고 유형별 비용 계산 (KRW).
    cfg: {'EXPORT_FEE_SIMPLIFIED_KRW': ..., 'EXPORT_FEE_LIST_CONVERSION_KRW': ...} override 가능.
    """
    c = cfg or {}
    _FEE_SIMPLIFIED      = int(c.get('EXPORT_FEE_SIMPLIFIED_KRW',      EXPORT_FEE_SIMPLIFIED_KRW))
    _FEE_LIST_CONVERSION = int(c.get('EXPORT_FEE_LIST_CONVERSION_KRW',  EXPORT_FEE_LIST_CONVERSION_KRW))

    if export_type in (ExportDeclarationType.NONE, ExportDeclarationType.MANIFEST):
        return {
            "type": export_type.value,
            "base_fee_krw": 0,
            "vat_rate": 0.0,
            "total_fee_krw": 0,
            "notes": (
                "목록통관: 신고비용 무료, 수출실적 불인정"
                if export_type == ExportDeclarationType.MANIFEST
                else "수출신고 없음"
            ),
        }

    if vat_rate is None:
        raise VatRateNotProvidedError(
            "SIMPLIFIED/LIST_CONVERSION 신고는 vat_rate 입력이 필수입니다."
        )

    if export_type == ExportDeclarationType.SIMPLIFIED:
        base = _FEE_SIMPLIFIED
        notes = "간이수출신고: 수출실적 인정, 관세환급 가능, FOB 200만원 이하"
    elif export_type == ExportDeclarationType.LIST_CONVERSION:
        base = _FEE_LIST_CONVERSION
        notes = "수출목록변환신고: 수출실적 인정, 반품/재수입 면세, FOB 200만원 이하"
    else:
        raise InvalidExportDeclarationTypeError(f"알 수 없는 신고 유형: {export_type}")

    total = base * (1 + vat_rate)
    return {
        "type": export_type.value,
        "base_fee_krw": base,
        "vat_rate": vat_rate,
        "total_fee_krw": round(total, 2),
        "notes": notes,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3PL / 풀필먼트 비용 계산
# ─────────────────────────────────────────────────────────────────────────────

def calculate_fulfillment_fee(inp: ShippingInput, cfg: Optional[dict] = None) -> dict:
    """
    KSE 3PL/풀필먼트 비용 계산 (KRW).
    cfg: fulfillment 단가 override 가능.
    """
    warnings: List[dict] = []

    c = cfg or {}
    _PICKING       = int(c.get('FULFILLMENT_PICKING_BASE_KRW',    FULFILLMENT_PICKING_BASE_KRW))
    _COMBINED      = int(c.get('FULFILLMENT_COMBINED_PER_KRW',    FULFILLMENT_COMBINED_PER_KRW))
    _INBOUND_PAL   = int(c.get('FULFILLMENT_INBOUND_PALLET_KRW',  FULFILLMENT_INBOUND_PALLET_KRW))
    _INBOUND_BOX   = int(c.get('FULFILLMENT_INBOUND_BOX_KRW',     FULFILLMENT_INBOUND_BOX_KRW))
    _STORAGE       = int(c.get('FULFILLMENT_STORAGE_KRW',         FULFILLMENT_STORAGE_KRW))
    _LABEL         = int(c.get('FULFILLMENT_LABEL_PER_KRW',       FULFILLMENT_LABEL_PER_KRW))
    _RETURN        = int(c.get('FULFILLMENT_RETURN_PROC_KRW',     FULFILLMENT_RETURN_PROC_KRW))
    _PAL_DISPOSE   = int(c.get('FULFILLMENT_PALLET_DISPOSE_KRW',  FULFILLMENT_PALLET_DISPOSE_KRW))

    # 피킹/포장비
    picking_fee  = _PICKING if inp.item_count >= 1 else 0
    combined_fee = max(0, inp.item_count - 1) * _COMBINED

    # 입고비
    inbound_fee = {
        InboundType.PALLET: _INBOUND_PAL,
        InboundType.BOX:    _INBOUND_BOX,
    }.get(inp.inbound_type, 0)

    # 보관비
    storage_fee = _STORAGE if inp.storage_type else 0

    # 부가서비스
    label_fee       = inp.label_work_count * _LABEL
    return_proc_fee = inp.return_processing_count * _RETURN
    pallet_disp_fee = inp.pallet_disposal_count * _PAL_DISPOSE

    # 부자재비 — 문서상 미확정
    if inp.packing_material_provided_by_client:
        packing_material_fee: Optional[float] = 0.0
    elif inp.extra_packing_fee_krw is not None:
        packing_material_fee = inp.extra_packing_fee_krw
    else:
        packing_material_fee = None
        warnings.append({"code": "PACKING_MATERIAL_FEE_NOT_DETERMINED",
                          "message": "부자재비(박스/안전봉투) 미확정 — 고객사 제공 여부 또는 단가 확인 필요"})

    subtotal = sum([
        picking_fee, combined_fee, inbound_fee, storage_fee,
        label_fee, return_proc_fee, pallet_disp_fee,
    ])
    total_fulfillment = (
        subtotal + packing_material_fee
        if packing_material_fee is not None
        else None
    )

    return {
        "warnings": warnings,
        "picking_fee_krw": picking_fee,
        "combined_packing_fee_krw": combined_fee,
        "inbound_fee_krw": inbound_fee,
        "storage_fee_krw": storage_fee,
        "label_fee_krw": label_fee,
        "return_processing_fee_krw": return_proc_fee,
        "pallet_disposal_fee_krw": pallet_disp_fee,
        "packing_material_fee_krw": packing_material_fee,
        "total_fulfillment_krw": total_fulfillment,
    }


# ─────────────────────────────────────────────────────────────────────────────
# EMS 운송비 계산
# ─────────────────────────────────────────────────────────────────────────────

def calculate_ems_freight(inp: ShippingInput, cfg: Optional[dict] = None) -> dict:
    """
    한국우편 EMS → 일본 운송비 계산 (KRW).
    요율표는 Admin에서 ShippingRateTable(table_key='EMS_JP_STANDARD')으로 관리.
    cfg: {'ems_rate_table': {float: int}} override 가능.
    """
    warnings:   List[dict] = []
    rejections: List[dict] = []

    _ems_table = (cfg or {}).get('ems_rate_table', EMS_RATE_TABLE)

    if not _ems_table:
        return {
            "is_available": False,
            "rejections": [{"code": "EMS_RATE_TABLE_EMPTY",
                             "message": "EMS 요율표 미등록 — Admin > 배송 요율표 > EMS_JP_STANDARD에 입력 필요"}],
            "warnings": warnings,
        }

    # ── 치수·무게 제한 ────────────────────────────────────────────────────────
    if inp.actual_weight_kg > EMS_MAX_WEIGHT_KG:
        return {
            "is_available": False,
            "rejections": [{"code": "EMS_WEIGHT_EXCEEDED",
                             "message": f"실측 무게 {inp.actual_weight_kg}kg > EMS 최대 {EMS_MAX_WEIGHT_KG}kg"}],
            "warnings": warnings,
        }

    if inp.longest_side_cm is not None and inp.longest_side_cm > EMS_MAX_SIDE_CM:
        return {
            "is_available": False,
            "rejections": [{"code": "EMS_SIDE_EXCEEDED",
                             "message": f"한 변 {inp.longest_side_cm}cm > EMS 최대 {EMS_MAX_SIDE_CM}cm"}],
            "warnings": warnings,
        }

    girth_sum = resolve_girth_sum(inp)
    if girth_sum is not None and girth_sum > EMS_MAX_GIRTH_CM:
        return {
            "is_available": False,
            "rejections": [{"code": "EMS_GIRTH_EXCEEDED",
                             "message": f"세 변의 합 {girth_sum}cm > EMS 최대 {EMS_MAX_GIRTH_CM}cm"}],
            "warnings": warnings,
        }

    # ── 부피무게 & 과금무게 ───────────────────────────────────────────────────
    volumetric_weight = calculate_volumetric_weight(
        inp.width_cm, inp.length_cm, inp.height_cm
    )
    if volumetric_weight is None:
        chargeable_weight = inp.actual_weight_kg
    else:
        chargeable_weight = max(inp.actual_weight_kg, volumetric_weight)

    # ── 요율표 조회 ───────────────────────────────────────────────────────────
    try:
        weight_break = find_ceil_weight_break(chargeable_weight, _ems_table)
    except WeightExceedsTableError as e:
        return {
            "is_available": False,
            "rejections": [{"code": "EMS_WEIGHT_EXCEEDS_RATE_TABLE", "message": str(e)}],
            "warnings": warnings,
        }

    base_freight_krw = _ems_table[weight_break]

    return {
        "is_available": True,
        "rejections": rejections,
        "warnings": warnings,
        "actual_weight_kg": inp.actual_weight_kg,
        "volumetric_weight_kg": volumetric_weight,
        "chargeable_weight_kg": chargeable_weight,
        "weight_break_applied_kg": weight_break,
        "base_freight_krw": base_freight_krw,
        "total_freight_krw": base_freight_krw,
        "is_estimate_complete": True,
        "currency_note": "KRW 기준 (한국우편 EMS 국내 발송요금)",
        "lead_time_note": "한국 → 일본 3-5 영업일 (일본우편 EMS 배달)",
    }


# ─────────────────────────────────────────────────────────────────────────────
# FastBox 운송비 계산
# ─────────────────────────────────────────────────────────────────────────────

def calculate_fb_freight(inp: ShippingInput, cfg: Optional[dict] = None) -> dict:
    """
    FastBox (DHUB) 항공 특송 운송비 계산 (KRW).
    - 유류할증료(FSC) 별도 (fb_fsc_krw 미입력 시 is_estimate_complete=False)
    - 부피무게 = W×L×H / 6,000
    - 최대 20kg, 세 변 합 160cm 이하, 한 변 100cm 이하
    cfg: {'fb_rate_tables': {FbTier: {float: int}}} override 가능.
    """
    warnings:   List[dict] = []
    rejections: List[dict] = []

    _fb_tables = (cfg or {}).get('fb_rate_tables', FB_RATE_TABLES)

    # ── 치수 제한 ─────────────────────────────────────────────────────────────
    if inp.actual_weight_kg > FB_MAX_WEIGHT_KG:
        return {
            "is_available": False,
            "rejections": [{"code": "FB_WEIGHT_EXCEEDED",
                             "message": f"실측 무게 {inp.actual_weight_kg}kg > 최대 {FB_MAX_WEIGHT_KG}kg 발송 불가"}],
            "warnings": warnings,
        }

    if inp.longest_side_cm is not None and inp.longest_side_cm > FB_MAX_SIDE_CM:
        return {
            "is_available": False,
            "rejections": [{"code": "FB_SIDE_EXCEEDED",
                             "message": f"한 변 {inp.longest_side_cm}cm > 최대 {FB_MAX_SIDE_CM}cm 발송 불가"}],
            "warnings": warnings,
        }

    girth_sum = resolve_girth_sum(inp)
    if girth_sum is not None and girth_sum > FB_MAX_GIRTH_CM:
        return {
            "is_available": False,
            "rejections": [{"code": "FB_GIRTH_EXCEEDED",
                             "message": f"세 변의 합 {girth_sum}cm > 최대 {FB_MAX_GIRTH_CM}cm 발송 불가"}],
            "warnings": warnings,
        }

    # ── 부피무게 & 과금무게 ───────────────────────────────────────────────────
    volumetric_weight = calculate_volumetric_weight(
        inp.width_cm, inp.length_cm, inp.height_cm
    )
    if volumetric_weight is None:
        warnings.append({"code": "FB_VOLUMETRIC_NOT_CALCULATED",
                          "message": "치수 미입력으로 부피무게 계산 불가, 실제무게로 계산"})
        chargeable_weight = inp.actual_weight_kg
    else:
        chargeable_weight = max(inp.actual_weight_kg, volumetric_weight)

    if chargeable_weight > FB_MAX_WEIGHT_KG:
        return {
            "is_available": False,
            "rejections": [{"code": "FB_CHARGEABLE_WEIGHT_EXCEEDED",
                             "message": f"과금무게 {chargeable_weight:.3f}kg > 최대 {FB_MAX_WEIGHT_KG}kg (부피무게 초과)"}],
            "warnings": warnings,
        }

    # ── 요율표 조회 ───────────────────────────────────────────────────────────
    rate_table = _fb_tables.get(inp.fb_tier)
    if rate_table is None:
        return {
            "is_available": False,
            "rejections": [{"code": "FB_INVALID_TIER",
                             "message": f"요율표 없음: {inp.fb_tier}"}],
            "warnings": warnings,
        }

    try:
        weight_break = find_ceil_weight_break(chargeable_weight, rate_table)
    except WeightExceedsTableError as e:
        return {
            "is_available": False,
            "rejections": [{"code": "FB_WEIGHT_EXCEEDS_RATE_TABLE", "message": str(e)}],
            "warnings": warnings,
        }

    base_freight_krw = rate_table[weight_break]

    # ── FSC (유류할증료) ──────────────────────────────────────────────────────
    fsc_krw = inp.fb_fsc_krw
    is_estimate_complete = True
    if fsc_krw is None:
        is_estimate_complete = False
        warnings.append({"code": "FB_FSC_NOT_PROVIDED",
                          "message": "유류할증료(FSC) 미입력 — 항공사 공시 요금 확인 후 추가 필요. 총액 불완전."})

    total_freight_krw = (
        base_freight_krw + fsc_krw if fsc_krw is not None else None
    )

    # ── DDU 신청료 (JPY) ──────────────────────────────────────────────────────
    ddu_surcharge_jpy = FB_DDU_SURCHARGE_JPY if inp.fb_tax_mode == FbTaxMode.DDU else 0

    return {
        "is_available": True,
        "rejections": rejections,
        "warnings": warnings,
        "tier": inp.fb_tier.value,
        "tax_mode": inp.fb_tax_mode.value,
        "actual_weight_kg": inp.actual_weight_kg,
        "volumetric_weight_kg": volumetric_weight,
        "chargeable_weight_kg": chargeable_weight,
        "weight_break_applied_kg": weight_break,
        "base_freight_krw": base_freight_krw,
        "fsc_krw": fsc_krw,
        "total_freight_krw": total_freight_krw,
        "ddu_surcharge_jpy": ddu_surcharge_jpy,
        "ddu_note": (
            f"DDU: 건당 {FB_DDU_SURCHARGE_JPY}엔 신청료 추가 (FastBox→고객사 청구). "
            "수취인이 배달 시 세금+대납수수료 직접 지불."
            if inp.fb_tax_mode == FbTaxMode.DDU
            else "DDP: 판매자(귀사) 선납 방식."
        ),
        "is_estimate_complete": is_estimate_complete,
        "currency_note": "기본 운임: KRW / DDU 신청료: JPY",
        "lead_time_note": "패스트박스 출고일로부터 3-5일 소요 (배송 이슈 없는 경우에 한함)",
        "caution": [
            "본 요금은 유류할증료(항공사 변동)가 제외된 금액",
            "월 출고량 기준 등급 적용 (1일~31일 패스트박스 출고건)",
            "수입 통관 필요 상품별 HS-CODE 및 상품 정보 필수 제공",
            "분실/파손 보상 한도: 상품가 최대 30만원 + 배송비 + 관세",
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# 메인 엔트리포인트
# ─────────────────────────────────────────────────────────────────────────────

def build_quote_response(inp: ShippingInput, cfg: Optional[dict] = None) -> dict:
    """
    배송비 견적 응답 생성 메인 함수.
    cfg: DB에서 로드한 요율/상수 override dict. None이면 모듈 기본값 사용.
    """
    all_rejections: List[dict] = []
    all_warnings:   List[dict] = []

    # ── Step 1: 금지/주의 품목 검사 ──────────────────────────────────────────
    rejections, warnings = validate_restricted_items(inp)
    all_rejections.extend(rejections)
    all_warnings.extend(warnings)

    if all_rejections:
        return _build_response(
            inp=inp,
            is_available=False,
            is_estimate_complete=False,
            requires_manual_review=False,
            rejections=all_rejections,
            warnings=all_warnings,
        )

    requires_manual_review = bool(all_warnings)

    # ── Step 2: Provider별 분기 ───────────────────────────────────────────────
    freight_breakdown: dict = {}
    selected_rate_table: Optional[str] = None
    selected_service_class: Optional[ServiceClass] = None
    is_available = True
    is_estimate_complete = True

    if inp.service_provider == ServiceProvider.KSE:
        if inp.transport_mode not in (
            TransportMode.SEA, TransportMode.AIR, TransportMode.SDEX
        ):
            all_rejections.append({
                "code": "INVALID_TRANSPORT_MODE_FOR_KSE",
                "message": f"KSE는 SEA/AIR/SDEX만 지원합니다. 입력값: {inp.transport_mode}",
            })
            return _build_response(
                inp=inp,
                is_available=False,
                is_estimate_complete=False,
                requires_manual_review=requires_manual_review,
                rejections=all_rejections,
                warnings=all_warnings,
            )

        kse_result = calculate_kse_freight(inp, cfg=cfg)
        all_warnings.extend(kse_result.get("warnings", []))
        all_rejections.extend(kse_result.get("rejections", []))

        if not kse_result.get("is_available", True):
            return _build_response(
                inp=inp,
                is_available=False,
                is_estimate_complete=False,
                requires_manual_review=requires_manual_review,
                rejections=all_rejections,
                warnings=all_warnings,
            )

        freight_breakdown = {"provider": "KSE", "kse": kse_result}
        selected_rate_table   = kse_result.get("selected_rate_table")
        selected_service_class = kse_result.get("service_class")
        if kse_result.get("total_freight_jpy") is None:
            is_estimate_complete = False

        # 수출신고비
        try:
            export_fee = calculate_export_declaration_fee(
                inp.export_declaration_type, inp.vat_rate, cfg=cfg
            )
        except VatRateNotProvidedError as e:
            all_warnings.append({"code": "VAT_RATE_NOT_PROVIDED",
                                   "message": str(e)})
            export_fee = None
            is_estimate_complete = False

        # 3PL 비용
        fulfillment = calculate_fulfillment_fee(inp, cfg=cfg)
        all_warnings.extend(fulfillment.get("warnings", []))
        if fulfillment.get("total_fulfillment_krw") is None:
            is_estimate_complete = False

    elif inp.service_provider == ServiceProvider.CJL:
        if inp.transport_mode != TransportMode.DOOR_TO_DOOR:
            all_rejections.append({
                "code": "INVALID_TRANSPORT_MODE_FOR_CJL",
                "message": "CJL은 DOOR_TO_DOOR만 지원합니다.",
            })
            return _build_response(
                inp=inp,
                is_available=False,
                is_estimate_complete=False,
                requires_manual_review=requires_manual_review,
                rejections=all_rejections,
                warnings=all_warnings,
            )

        cjl_result = calculate_cjl_freight(inp, cfg=cfg)
        all_warnings.extend(cjl_result.get("warnings", []))
        all_rejections.extend(cjl_result.get("rejections", []))

        if not cjl_result.get("is_available", True):
            return _build_response(
                inp=inp,
                is_available=False,
                is_estimate_complete=False,
                requires_manual_review=requires_manual_review,
                rejections=all_rejections,
                warnings=all_warnings,
            )

        freight_breakdown      = {"provider": "CJL", "cjl": cjl_result}
        selected_rate_table    = "CJL_DOOR_TO_DOOR"
        selected_service_class = ServiceClass.DOOR_TO_DOOR
        export_fee             = None  # CJL은 수출신고비 별도
        fulfillment            = {}    # CJL은 3PL 별도
        if not cjl_result.get("is_estimate_complete", True):
            is_estimate_complete = False

    elif inp.service_provider == ServiceProvider.EMS:
        ems_result = calculate_ems_freight(inp, cfg=cfg)
        all_warnings.extend(ems_result.get("warnings", []))
        all_rejections.extend(ems_result.get("rejections", []))

        if not ems_result.get("is_available", True):
            return _build_response(
                inp=inp,
                is_available=False,
                is_estimate_complete=False,
                requires_manual_review=requires_manual_review,
                rejections=all_rejections,
                warnings=all_warnings,
            )

        freight_breakdown      = {"provider": "EMS", "ems": ems_result}
        selected_rate_table    = "EMS_JP_STANDARD"
        selected_service_class = None
        export_fee             = None
        fulfillment            = {}
        if not ems_result.get("is_estimate_complete", True):
            is_estimate_complete = False

    elif inp.service_provider == ServiceProvider.FB:
        fb_result = calculate_fb_freight(inp, cfg=cfg)
        all_warnings.extend(fb_result.get("warnings", []))
        all_rejections.extend(fb_result.get("rejections", []))

        if not fb_result.get("is_available", True):
            return _build_response(
                inp=inp,
                is_available=False,
                is_estimate_complete=False,
                requires_manual_review=requires_manual_review,
                rejections=all_rejections,
                warnings=all_warnings,
            )

        freight_breakdown      = {"provider": "FB", "fb": fb_result}
        selected_rate_table    = f"FB_AIR_{inp.fb_tier.value}"
        selected_service_class = None
        export_fee             = None
        fulfillment            = {}
        if not fb_result.get("is_estimate_complete", True):
            is_estimate_complete = False

    else:
        all_rejections.append({
            "code": "UNKNOWN_SERVICE_PROVIDER",
            "message": f"알 수 없는 serviceProvider: {inp.service_provider}",
        })
        return _build_response(
            inp=inp,
            is_available=False,
            is_estimate_complete=False,
            requires_manual_review=False,
            rejections=all_rejections,
            warnings=all_warnings,
        )

    requires_manual_review = bool(all_warnings)

    # ── Step 3: 응답 조립 ────────────────────────────────────────────────────
    girth_sum = resolve_girth_sum(inp)

    return {
        "request_id": str(uuid.uuid4()),
        "calculated_at": datetime.now(timezone.utc).isoformat(),
        "is_available": is_available,
        "requires_manual_review": requires_manual_review,
        "is_estimate_complete": is_estimate_complete,
        "rejection_reasons": all_rejections,
        "warnings": all_warnings,
        "selected_rate_table": selected_rate_table,
        "selected_service_class": (
            selected_service_class.value if selected_service_class else None
        ),
        "selected_service_provider": inp.service_provider.value,
        "selected_transport_mode": inp.transport_mode.value,
        "dimension_check": {
            "girth_sum_cm": girth_sum,
            "longest_side_cm": inp.longest_side_cm,
            "thickness_cm": inp.thickness_cm,
            "passed_light_check": is_eligible_for_kse_light(
                girth_sum, inp.longest_side_cm, inp.thickness_cm, inp.actual_weight_kg
            ) if inp.service_provider == ServiceProvider.KSE else None,
            "passed_standard_check": is_eligible_for_kse_standard(
                girth_sum, inp.actual_weight_kg
            ) if inp.service_provider == ServiceProvider.KSE else None,
        },
        "customs_check": {
            "invoice_value_jpy": inp.invoice_value_jpy,
            "tax_exempt_threshold_jpy": CJL_TAX_EXEMPT_THRESHOLD_JPY,
            "is_tax_exempt": inp.invoice_value_jpy <= CJL_TAX_EXEMPT_THRESHOLD_JPY,
            "max_invoice_limit_jpy": CJL_MAX_INVOICE_JPY,
        },
        "freight_breakdown": freight_breakdown,
        "export_declaration_breakdown": export_fee,
        "fulfillment_breakdown": fulfillment if fulfillment else None,
        "lead_time_estimate": {
            "min_days": 3,
            "max_days": 5,
            "delay_risks": [
                "메가와리/블랙프라이데이 시즌 지연 가능",
                "태풍/날씨 불안정 시 항공기 지연 가능",
            ],
        },
        "notes": [
            "KSE 운송요금: JPY 기준 / 통관·3PL 비용: KRW 기준 (혼합 통화)",
            "CJL 지역추가비: JPY(¥)/BOX 기준 — 실제 정산 통화 별도 확인 필요",
            "운임표 구간 올림(ceiling) 방식 적용 — KSE 계약 내용으로 최종 확인 필요",
        ],
    }


def _build_response(
    inp: ShippingInput,
    is_available: bool,
    is_estimate_complete: bool,
    requires_manual_review: bool,
    rejections: List[dict],
    warnings: List[dict],
) -> dict:
    """거절/에러 케이스 공통 응답 빌더."""
    return {
        "request_id": str(uuid.uuid4()),
        "calculated_at": datetime.now(timezone.utc).isoformat(),
        "is_available": is_available,
        "requires_manual_review": requires_manual_review,
        "is_estimate_complete": is_estimate_complete,
        "rejection_reasons": rejections,
        "warnings": warnings,
        "selected_rate_table": None,
        "selected_service_class": None,
        "selected_service_provider": inp.service_provider.value,
        "selected_transport_mode": inp.transport_mode.value,
        "dimension_check": None,
        "customs_check": None,
        "freight_breakdown": None,
        "export_declaration_breakdown": None,
        "fulfillment_breakdown": None,
        "lead_time_estimate": None,
        "notes": [],
    }
