from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ShippingQuoteLog, load_rate_tables
from .serializers import ShippingQuoteLogSerializer
from .request_serializers import ShippingQuoteRequestSerializer
from .services import determine_mode, estimate_intl_shipping, estimate_weight_from_items
from .utils.japan_shipping import (
    ShippingInput, ServiceProvider, TransportMode, DestinationRegion,
    ExportDeclarationType, PackingType, InboundType, StorageType,
    ServiceClass, build_quote_response,
)


def _to_shipping_input(data: dict) -> ShippingInput:
    def _enum(cls, val, default=None):
        if val is None:
            return default
        return cls(val)

    return ShippingInput(
        service_provider=ServiceProvider(data['service_provider']),
        transport_mode=TransportMode(data['transport_mode']),
        actual_weight_kg=data['actual_weight_kg'],
        width_cm=data.get('width_cm'),
        length_cm=data.get('length_cm'),
        height_cm=data.get('height_cm'),
        thickness_cm=data.get('thickness_cm'),
        longest_side_cm=data.get('longest_side_cm'),
        girth_sum_cm=data.get('girth_sum_cm'),
        box_count=data.get('box_count', 1),
        item_count=data.get('item_count', 1),
        destination_region=DestinationRegion(data.get('destination_region', 'EAST_JAPAN')),
        invoice_value_jpy=data.get('invoice_value_jpy', 0.0),
        export_declaration_type=ExportDeclarationType(data.get('export_declaration_type', 'NONE')),
        vat_rate=data.get('vat_rate'),
        has_battery=data.get('has_battery', False),
        is_alcohol=data.get('is_alcohol', False),
        is_tobacco=data.get('is_tobacco', False),
        is_food_or_quarantine=data.get('is_food_or_quarantine', False),
        is_dangerous_goods=data.get('is_dangerous_goods', False),
        fsc_amount_jpy=data.get('fsc_amount_jpy'),
        requested_service_class=_enum(ServiceClass, data.get('requested_service_class')),
        inbound_type=_enum(InboundType, data.get('inbound_type')),
        storage_type=_enum(StorageType, data.get('storage_type')),
        label_work_count=data.get('label_work_count', 0),
        return_processing_count=data.get('return_processing_count', 0),
    )


class ShippingQuoteView(APIView):
    def post(self, request):
        req = ShippingQuoteRequestSerializer(data=request.data)
        req.is_valid(raise_exception=True)
        data = req.validated_data

        try:
            from apps.shipping.models import load_rate_tables
            from apps.common.models import SiteConfig
            cfg = load_rate_tables() or {}
            cfg.update(SiteConfig.get_group('shipping'))
            inp = _to_shipping_input(data)
            result = build_quote_response(inp, cfg=cfg if cfg else None)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        ShippingQuoteLog.objects.create(
            service_provider=data['service_provider'],
            transport_mode=data['transport_mode'],
            actual_weight_kg=data['actual_weight_kg'],
            result=result,
            is_available=result.get('is_available', False),
        )

        return Response(result, status=status.HTTP_200_OK)


class ShippingQuoteLogListView(APIView):
    def get(self, request):
        qs = ShippingQuoteLog.objects.all()[:50]
        return Response(ShippingQuoteLogSerializer(qs, many=True).data)


class IntlShippingEstimateView(APIView):
    """
    국제 배송비 자동 견적.

    POST /api/shipping/intl-estimate/
    {
        "weight_kg": 1.5,           // 직접 무게 입력 (우선)
        "items": [                   // 또는 카테고리별 수량으로 무게 자동 추정
            {"category": "의류", "quantity": 2}
        ],
        "mode": "AIR"               // optional: AIR | SEA | EMS (미지정 시 전체)
    }

    Response:
    {
        "total_weight_kg": 1.5,
        "weight_source": "direct" | "estimated",
        "carriers": [
            {
                "profile_id": 1,
                "name": "FastBox 항공 VIP",
                "carrier_code": "FB",
                "mode": "AIR",
                "is_default": true,
                "is_available": true,
                "freight_krw": 9160,
                "quote": { ... }
            }
        ]
    }
    """

    def post(self, request):
        data = request.data

        # ── 무게 결정 ─────────────────────────────────────────────────────────
        weight_kg    = data.get('weight_kg')
        items        = data.get('items') or []
        weight_source = 'direct'

        if weight_kg is None:
            if not items:
                return Response(
                    {'error': 'weight_kg 또는 items 중 하나는 필수입니다.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            weight_kg     = estimate_weight_from_items(items)
            weight_source = 'estimated'

        try:
            weight_kg = float(weight_kg)
        except (TypeError, ValueError):
            return Response({'error': 'weight_kg는 숫자여야 합니다.'}, status=400)

        if weight_kg <= 0:
            return Response({'error': 'weight_kg는 0보다 커야 합니다.'}, status=400)

        mode = data.get('mode') or None
        if mode and mode not in ('AIR', 'SEA', 'EMS'):
            return Response({'error': "mode는 AIR | SEA | EMS 중 하나입니다."}, status=400)

        cfg                  = load_rate_tables() or {}
        carriers, mode_applied = estimate_intl_shipping(weight_kg, mode=mode, cfg=cfg)

        return Response({
            'total_weight_kg': weight_kg,
            'weight_source':   weight_source,
            'mode_applied':    mode_applied,
            'carriers':        carriers,
        })
