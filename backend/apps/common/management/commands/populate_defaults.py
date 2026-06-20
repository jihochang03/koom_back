"""
관세·배송·가격 정책 기본값을 DB에 등록한다.
이미 있는 키는 건너뛰고, 없는 키만 추가한다.

사용법:
    python manage.py populate_defaults
    python manage.py populate_defaults --overwrite   # 기존 값도 강제 덮어쓰기
"""
from django.core.management.base import BaseCommand
from apps.common.models import SiteConfig
from apps.shipping.models import ShippingRateTable, ShippingRateEntry


SITE_CONFIG_DEFAULTS = [
    # (key, value, group, description)

    # ── 구매대행 수수료 ─────────────────────────────────────────────────────────
    ('DK_AGENCY_FEE_LOW_JPY',          '300',    'pricing', '구매대행 수수료 — 상품가 10,000엔 이하 (엔)'),
    ('DK_AGENCY_FEE_HIGH_JPY',         '500',    'pricing', '구매대행 수수료 — 상품가 10,000엔 초과 (엔)'),
    ('DK_AGENCY_THRESHOLD_JPY',        '10000',  'pricing', '구매대행 수수료 구간 기준선 (엔)'),

    # ── 통관 / 세금 ─────────────────────────────────────────────────────────────
    ('DK_CUSTOMS_RATIO',               '0.6',    'pricing', '통관 면세 판정 비율 (CIF × 이 값 ≤ 면세기준선이면 면세)'),
    ('DK_CUSTOMS_EXEMPT_JPY',          '10000',  'pricing', '통관 면세 기준선 (엔)'),
    ('DK_CONSUMPTION_TAX_RATE',        '0.10',   'pricing', '일본 소비세율 (예: 0.10 = 10%)'),
    ('DK_DEFAULT_TARIFF_RATE',         '0.05',   'pricing', '관세율 조회 실패 시 기본 관세율 (예: 0.05 = 5%)'),
    ('DK_TAX_ADVANCE_FEE_RATE',        '0.05',   'pricing', '세금 대납 수수료율 (예: 0.05 = 5%, 숨김 항목)'),

    # ── 환율 / 마진 ─────────────────────────────────────────────────────────────
    ('DK_EXCHANGE_MARGIN_RATE',        '0.04',   'pricing', '환율 마진율 — 고객환율 = 시장환율 / (1 + 이 값) (예: 0.04 = 4%)'),
    ('DK_INTL_SHIPPING_MARKUP_RATE',   '1.4',    'pricing', '국제 배송비 마크업 배율 (예: 1.4 = 원가의 140% 청구)'),

    # ── 부가 옵션 ───────────────────────────────────────────────────────────────
    ('DK_BUNDLE_FEE_JPY',              '200',    'pricing', '합배송 처리비 (엔)'),
    ('DK_PHOTO_INSPECTION_JPY',        '300',    'pricing', '사진 검수 서비스 (엔)'),
    ('DK_SPEED_SHIP_JPY',              '500',    'pricing', '스피드 출하 서비스 (엔)'),
    ('DK_POINTS_RATE',                 '0.01',   'pricing', '포인트 적립률 (예: 0.01 = 1%, 합계 미포함)'),

    # ── 배송 상수 ───────────────────────────────────────────────────────────────
    ('CJL_TAX_EXEMPT_THRESHOLD_JPY',   '10000',  'shipping', 'CJL 면세 기준 Invoice 금액 (엔)'),
    ('CJL_MAX_INVOICE_JPY',            '300000', 'shipping', 'CJL 최대 Invoice 금액 (엔)'),
    ('CJL_REGIONAL_FEE_GENERAL_JPY',   '1800',   'shipping', 'CJL 일반 지역 추가비 (엔/박스)'),
    ('CJL_REGIONAL_FEE_JEJU_JPY',      '3500',   'shipping', 'CJL 제주 지역 추가비 (엔/박스)'),
    ('EXPORT_FEE_SIMPLIFIED_KRW',      '200',    'shipping', '간이수출신고 기본 수수료 (원, VAT 별도)'),
    ('EXPORT_FEE_LIST_CONVERSION_KRW', '150',    'shipping', '수출목록변환신고 기본 수수료 (원, VAT 별도)'),
    ('FULFILLMENT_PICKING_BASE_KRW',   '900',    'shipping', '3PL 피킹·포장 기본 단가 (원/건)'),
    ('FULFILLMENT_COMBINED_PER_KRW',   '50',     'shipping', '3PL 합포장 추가 단가 (원/아이템)'),
    ('FULFILLMENT_INBOUND_PALLET_KRW', '6000',   'shipping', '3PL 팔레트 입고 단가 (원)'),
    ('FULFILLMENT_INBOUND_BOX_KRW',    '1000',   'shipping', '3PL 박스 입고 단가 (원)'),
    ('FULFILLMENT_STORAGE_KRW',        '30000',  'shipping', '3PL 보관료 (원/팔레트 또는 선반)'),
    ('FULFILLMENT_LABEL_PER_KRW',      '100',    'shipping', '3PL 라벨 작업 단가 (원/건)'),
    ('FULFILLMENT_RETURN_PROC_KRW',    '500',    'shipping', '3PL 반품 처리 단가 (원/건)'),
    ('FULFILLMENT_PALLET_DISPOSE_KRW', '7000',   'shipping', '3PL 팔레트 폐기 단가 (원)'),

    # ── 관세 설정 ───────────────────────────────────────────────────────────────
    ('TARIFF_CACHE_TTL_HOURS',         '24',     'tariff',   '관세율 조회 결과 캐시 유효 시간 (시간)'),

    # ── 환율 설정 ───────────────────────────────────────────────────────────────
    ('EXCHANGE_CACHE_MINUTES',         '60',     'exchange', '환율 조회 결과 캐시 유효 시간 (분)'),
]


KSE_RATE_DATA = {
    'KSE_SEA_STANDARD': {
        'currency': 'JPY',
        'entries': {
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
    },
    'KSE_SEA_LIGHT': {
        'currency': 'JPY',
        'entries': {0.10: 350, 0.30: 400, 0.55: 460, 0.75: 490, 1.00: 530},
    },
    'KSE_AIR_STANDARD': {
        'currency': 'JPY',
        'entries': {
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
    },
    'KSE_AIR_LIGHT': {
        'currency': 'JPY',
        'entries': {0.10: 350, 0.30: 400, 0.55: 460, 0.75: 490, 1.00: 530},
    },
    'KSE_SDEX_STANDARD': {
        'currency': 'JPY',
        'entries': {
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
    },
    'KSE_SDEX_LIGHT': {
        'currency': 'JPY',
        'entries': {0.10: 350, 0.25: 400, 0.55: 460, 0.75: 490, 1.00: 530},
    },
    'CJL_DOOR_TO_DOOR': {
        'currency': 'KRW',
        'entries': {
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
        },
    },
}


class Command(BaseCommand):
    help = '관세·배송·가격 정책 기본값을 DB에 등록합니다. 기존 값은 건너뜁니다.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--overwrite',
            action='store_true',
            help='기존 설정값도 기본값으로 덮어씁니다.',
        )

    def handle(self, *args, **options):
        overwrite = options['overwrite']

        # ── SiteConfig 등록 ────────────────────────────────────────────────────
        created = updated = skipped = 0
        for key, value, group, desc in SITE_CONFIG_DEFAULTS:
            obj, is_new = SiteConfig.objects.get_or_create(
                key=key,
                defaults={'value': value, 'group': group, 'description': desc},
            )
            if is_new:
                created += 1
            elif overwrite:
                obj.value = value
                obj.group = group
                obj.description = desc
                obj.save()
                updated += 1
            else:
                skipped += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'SiteConfig: {created}개 생성, {updated}개 갱신, {skipped}개 건너뜀'
            )
        )

        # ── ShippingRateTable 등록 ─────────────────────────────────────────────
        t_created = t_skipped = e_created = 0
        for table_key, data in KSE_RATE_DATA.items():
            table, is_new = ShippingRateTable.objects.get_or_create(
                table_key=table_key,
                defaults={'currency': data['currency']},
            )
            if is_new:
                t_created += 1
                for weight, freight in data['entries'].items():
                    ShippingRateEntry.objects.create(
                        table=table,
                        weight_break_kg=weight,
                        freight=freight,
                    )
                    e_created += 1
            elif overwrite:
                table.entries.all().delete()
                for weight, freight in data['entries'].items():
                    ShippingRateEntry.objects.create(
                        table=table,
                        weight_break_kg=weight,
                        freight=freight,
                    )
                    e_created += 1
            else:
                t_skipped += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'ShippingRateTable: {t_created}개 생성, {t_skipped}개 건너뜀 | '
                f'ShippingRateEntry: {e_created}개 생성'
            )
        )
