"""공통 데이터 모델."""
from typing import Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, model_validator, field_validator


class ProductOption(BaseModel):
    """상품 옵션 정보."""
    option_type: str = Field(description="옵션 타입 (예: '색상', '사이즈', '용량')")
    available_values: list[str] = Field(default_factory=list, description="사용 가능한 옵션 값 목록")
    selected_value: Optional[str] = Field(None, description="현재 선택된 옵션 값 (있는 경우)")
    option_prices: Optional[Dict[str, float]] = Field(None, description="옵션별 가격 (예: {'3개': 5360, '12개': 18440})")
    option_images: Optional[Dict[str, str]] = Field(None, description="옵션별 썸네일 이미지 URL (예: 지마켓 미니샵)")
    option_titles: Optional[Dict[str, str]] = Field(None, description="옵션값별 상품 제목 (옵션마다 다른 상품명이 있을 때만, 예: {'밀크화이트': '유팡 시그니처2 밀크화이트'})")
    soldout_values: Optional[list[str]] = Field(None, description="품절(일시품절) 옵션 값 목록")

    @field_validator('available_values', mode='before')
    @classmethod
    def _coerce_available_values(cls, v):
        """Claude API가 null을 반환하는 경우 빈 리스트로 변환."""
        return v if v is not None else []

    @field_validator('option_prices', mode='before')
    @classmethod
    def _coerce_option_prices(cls, v):
        """dict 값 중 None인 항목을 제거하고, 빈 dict이면 None으로 변환."""
        if not isinstance(v, dict):
            return v
        filtered = {k: val for k, val in v.items() if val is not None}
        return filtered if filtered else None


class ProductInfo(BaseModel):
    """파싱된 상품 정보."""
    title: Optional[str] = Field(None, description="상품 제목")
    original_price: Optional[float] = Field(None, description="원래 가격 (할인 전)")
    discounted_price: Optional[float] = Field(None, description="할인된 가격")
    discount_rate: Optional[int] = Field(None, description="할인율 (%, 정수)")
    main_image_url: Optional[str] = Field(None, description="메인 상품 이미지 URL")
    shipping_period: Optional[str] = Field(None, description="배송기간 (예: '1-2일', '당일배송')")
    shipping_fee: Optional[float] = Field(None, description="배송비 (KRW). 0 = 무료배송, null = 알 수 없음")
    product_options: list[ProductOption] = Field(default_factory=list, description="상품 옵션 목록 (타입별로 구분)")
    product_weight: Optional[str] = Field(None, description="상품 무게")
    currency: str = Field(default="KRW", description="통화")
    hs_code: Optional[str] = Field(None, description="HS 코드 (4자리, 관세 분류용)")

    # ── 포장 치수 추정 (shipping calculator 연동용) ──────────────────────────
    # Claude가 상품 제목+무게+hs_code 기반으로 포장 후 예상 치수를 추정.
    # 물류센터 실측 전 예비 견적용. 실측 후 override 필요.
    est_width_cm: Optional[float] = Field(None, description="예상 가로 (cm, 포장 포함)")
    est_length_cm: Optional[float] = Field(None, description="예상 세로 (cm, 포장 포함)")
    est_height_cm: Optional[float] = Field(None, description="예상 높이 (cm, 포장 포함)")
    est_thickness_cm: Optional[float] = Field(None, description="예상 두께 (cm, 포장 포함) — KSE Light 판정용")
    est_longest_side_cm: Optional[float] = Field(None, description="예상 최장변 (cm)")
    est_girth_sum_cm: Optional[float] = Field(None, description="예상 세 변의 합 (cm)")
    dimension_confidence: Optional[Literal["HIGH", "MEDIUM", "LOW"]] = Field(
        None, description="치수 추정 신뢰도. HIGH=상품 유형 명확, MEDIUM=유사 품목 추정, LOW=불확실"
    )
    dimension_note: Optional[str] = Field(None, description="치수 추정 근거 또는 주의사항")

    # ── 품목 플래그 (shipping calculator 연동용) ─────────────────────────────
    has_battery: Optional[bool] = Field(None, description="배터리 포함 여부")
    is_alcohol: Optional[bool] = Field(None, description="주류 여부")
    is_tobacco: Optional[bool] = Field(None, description="담배 여부")
    is_food_or_quarantine: Optional[bool] = Field(None, description="식검 대상 식품/성분/식물/동물 여부")
    is_copyright_sensitive: Optional[bool] = Field(None, description="CD/DVD 등 저작권 민감 품목 여부")
    may_exceed_120cm: Optional[bool] = Field(None, description="포장 후 가장 긴 변이 120cm를 초과할 가능성 여부")

    sold_out: Optional[bool] = Field(None, description="품절 여부")
    used_condition: Optional[str] = Field(None, description="중고/반품 상태 (예: '반품-중', '중고', '리퍼'). 신상품이면 None")
    raw_data: Optional[Dict[str, Any]] = Field(None, description="원본 파싱 데이터")

    @field_validator('discount_rate', mode='before')
    @classmethod
    def coerce_discount_rate(cls, v):
        if v is not None:
            return int(round(float(v)))
        return v

    @model_validator(mode="after")
    def _fill_derived_fields(self) -> "ProductInfo":
        # 할인율 자동 계산
        if self.discount_rate is None:
            o, d = self.original_price, self.discounted_price
            if o and d and o > d:
                self.discount_rate = int(round((o - d) / o * 100))

        # 치수 파생값 자동 계산 (Claude가 W/L/H를 줬을 때)
        w, l, h = self.est_width_cm, self.est_length_cm, self.est_height_cm
        if w and l and h:
            if self.est_girth_sum_cm is None:
                self.est_girth_sum_cm = round(w + l + h, 1)
            if self.est_longest_side_cm is None:
                self.est_longest_side_cm = round(max(w, l, h), 1)
            # thickness = 가장 짧은 변 (KSE Light 판정: 두께 3cm 이하)
            if self.est_thickness_cm is None:
                self.est_thickness_cm = round(min(w, l, h), 1)

        return self
