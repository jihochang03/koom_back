from django.core.management.base import BaseCommand
from apps.shipping.models import ShippingRateTable, ShippingRateEntry
from apps.shipping.utils.japan_shipping import FB_RATE_TABLES, FbTier

TABLE_META = {
    FbTier.STANDARD: {
        "key":      "FB_AIR_STANDARD",
        "currency": "KRW",
        "note": (
            "FastBox 항공 특송 표준 요금 (유류할증료 별도)\n"
            "적용 조건: 월 출고량 기준, 1일~31일 패스트박스 출고건\n"
            "제한: 20kg 이하, 세 변의 합 160cm 이하, 한 변 100cm 이하\n"
            "부피무게 = 가로×세로×높이(cm) / 6,000\n"
            "DDU: 건당 20엔 신청료 추가 | DDP 선택 가능\n"
            "배송 소요일: 3-5일 (이슈 없는 경우)\n"
            "분실/파손 보상 한도: 상품가 최대 30만원 + 배송비 + 관세"
        ),
    },
    FbTier.VIP: {
        "key":      "FB_AIR_VIP",
        "currency": "KRW",
        "note":     "FastBox 항공 VIP — 월 1,000건 이상 (유류할증료 별도)",
    },
    FbTier.SVIP: {
        "key":      "FB_AIR_SVIP",
        "currency": "KRW",
        "note":     "FastBox 항공 SVIP — 월 3,000건 이상 (유류할증료 별도)",
    },
    FbTier.SSVIP: {
        "key":      "FB_AIR_SSVIP",
        "currency": "KRW",
        "note":     "FastBox 항공 SSVIP — 월 7,000건 이상 (유류할증료 별도)",
    },
}


class Command(BaseCommand):
    help = "FastBox 항공 특송 요율표 4개(Standard/VIP/SVIP/SSVIP)를 DB에 적재합니다."

    def handle(self, *args, **options):
        created_tables = 0
        updated_tables = 0
        total_entries  = 0

        for tier, rate_dict in FB_RATE_TABLES.items():
            meta = TABLE_META[tier]
            table, created = ShippingRateTable.objects.update_or_create(
                table_key=meta["key"],
                defaults={
                    "currency":  meta["currency"],
                    "is_active": True,
                    "note":      meta["note"],
                },
            )
            if created:
                created_tables += 1
            else:
                updated_tables += 1

            for weight_kg, freight in rate_dict.items():
                _, entry_created = ShippingRateEntry.objects.update_or_create(
                    table=table,
                    weight_break_kg=weight_kg,
                    defaults={"freight": freight},
                )
                total_entries += 1

            self.stdout.write(
                f"  {'생성' if created else '업데이트'}: {meta['key']} "
                f"({len(rate_dict)}개 구간)"
            )

        self.stdout.write(self.style.SUCCESS(
            f"\nFastBox 요율표 적재 완료: "
            f"신규 {created_tables}개 / 업데이트 {updated_tables}개 / "
            f"총 구간 {total_entries}개"
        ))
