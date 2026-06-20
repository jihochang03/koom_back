# Manually authored migration (avoids interactive rename prompt from makemigrations)
# Changes:
#   - ShippingCarrierProfile: rename carrier_code → engine, expand choices, add rate_table FK + currency
#   - New model: ShippingModeConfig (무게 기반 자동 운송 방식 결정)
#   - New model: FuelSurcharge (월별 유류할증료)
#   - ShippingRateTable: add CUSTOM_1..5 table_key choices

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shipping', '0004_categoryweightpreset_shippingcarrierprofile_and_more'),
    ]

    operations = [
        # 1. ShippingCarrierProfile.carrier_code → engine
        migrations.RenameField(
            model_name='shippingcarrierprofile',
            old_name='carrier_code',
            new_name='engine',
        ),
        migrations.AlterField(
            model_name='shippingcarrierprofile',
            name='engine',
            field=models.CharField(
                choices=[
                    ('FB',       'FastBox (DHUB) 항공특송'),
                    ('KSE_AIR',  'KSE 항공'),
                    ('KSE_SEA',  'KSE 해운'),
                    ('KSE_SDEX', 'KSE SDEX'),
                    ('CJL',      'CJL Door to Door'),
                    ('EMS',      '한국우편 EMS'),
                    ('TABLE',    '커스텀 요율표 (신규 배송사)'),
                ],
                max_length=15,
                verbose_name='계산 엔진',
                help_text='운임 계산에 사용할 엔진. TABLE 선택 시 아래 요율표를 지정하세요.',
            ),
        ),

        # 2. Add rate_table FK to ShippingCarrierProfile
        migrations.AddField(
            model_name='shippingcarrierprofile',
            name='rate_table',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to='shipping.shippingratetable',
                verbose_name='요율표',
                help_text='TABLE 엔진 선택 시 필수. 다른 엔진은 생략 가능.',
            ),
        ),

        # 3. Add currency field to ShippingCarrierProfile
        migrations.AddField(
            model_name='shippingcarrierprofile',
            name='currency',
            field=models.CharField(
                default='KRW', max_length=5,
                verbose_name='통화',
                help_text='TABLE 엔진일 때 요율표 통화 (KRW 또는 JPY)',
            ),
        ),

        # 4. Update ShippingCarrierProfile ordering meta
        migrations.AlterModelOptions(
            name='shippingcarrierprofile',
            options={
                'ordering': ['sort_order', 'engine'],
                'verbose_name': '배송사 프로필',
                'verbose_name_plural': '배송사 프로필',
            },
        ),

        # 5. Extend ShippingRateTable table_key choices with CUSTOM slots
        migrations.AlterField(
            model_name='shippingratetable',
            name='table_key',
            field=models.CharField(
                choices=[
                    ('KSE_SEA_STANDARD',  'KSE 해상 Standard (JPY)'),
                    ('KSE_SEA_LIGHT',     'KSE 해상 Light (JPY)'),
                    ('KSE_AIR_STANDARD',  'KSE 항공 Standard (JPY)'),
                    ('KSE_AIR_LIGHT',     'KSE 항공 Light (JPY)'),
                    ('KSE_SDEX_STANDARD', 'KSE SDEX Standard (JPY)'),
                    ('KSE_SDEX_LIGHT',    'KSE SDEX Light (JPY)'),
                    ('CJL_DOOR_TO_DOOR',  'CJL Door to Door (KRW)'),
                    ('FB_AIR_STANDARD',   'FastBox 항공 Standard (KRW)'),
                    ('FB_AIR_VIP',        'FastBox 항공 VIP — 월 1,000건+ (KRW)'),
                    ('FB_AIR_SVIP',       'FastBox 항공 SVIP — 월 3,000건+ (KRW)'),
                    ('FB_AIR_SSVIP',      'FastBox 항공 SSVIP — 월 7,000건+ (KRW)'),
                    ('EMS_JP_STANDARD',   '한국우편 EMS → 일본 Standard (KRW)'),
                    ('CUSTOM_1', '커스텀 요율표 1'),
                    ('CUSTOM_2', '커스텀 요율표 2'),
                    ('CUSTOM_3', '커스텀 요율표 3'),
                    ('CUSTOM_4', '커스텀 요율표 4'),
                    ('CUSTOM_5', '커스텀 요율표 5'),
                ],
                max_length=30, unique=True, verbose_name='요율표 종류',
            ),
        ),

        # 6. Create ShippingModeConfig
        migrations.CreateModel(
            name='ShippingModeConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('mode_selection', models.CharField(
                    choices=[
                        ('AUTO',     '무게 기반 자동 (항공 ↔ 해운)'),
                        ('AIR_ONLY', '항공만'),
                        ('SEA_ONLY', '해운만'),
                    ],
                    default='AUTO', max_length=10, verbose_name='운송 방식 선택',
                )),
                ('air_max_weight_kg', models.FloatField(
                    default=3.0, verbose_name='항공 최대 무게 (kg)',
                    help_text='AUTO일 때: 이 무게 이하 → 항공, 초과 → 해운. 기본값 3.0 kg.',
                )),
                ('is_current', models.BooleanField(default=True, verbose_name='현재 적용')),
                ('note', models.TextField(blank=True, verbose_name='비고')),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': '배송 방식 규칙',
                'verbose_name_plural': '배송 방식 규칙',
                'ordering': ['-is_current', '-updated_at'],
            },
        ),

        # 7. Create FuelSurcharge
        migrations.CreateModel(
            name='FuelSurcharge',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('carrier_name', models.CharField(
                    max_length=60, verbose_name='배송사명',
                    help_text='배송사 프로필의 배송사명과 맞춰 입력',
                )),
                ('year_month', models.CharField(
                    max_length=7, verbose_name='적용 월',
                    help_text='YYYY-MM 형식 (예: 2025-06)',
                )),
                ('amount', models.IntegerField(verbose_name='유류할증료 금액')),
                ('currency', models.CharField(
                    choices=[('KRW', 'KRW (원)'), ('JPY', 'JPY (엔)')],
                    default='KRW', max_length=5, verbose_name='통화',
                )),
                ('note', models.TextField(blank=True, verbose_name='비고')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': '월별 유류할증료',
                'verbose_name_plural': '월별 유류할증료',
                'ordering': ['-year_month', 'carrier_name'],
            },
        ),
        migrations.AlterUniqueTogether(
            name='fuelsurcharge',
            unique_together={('carrier_name', 'year_month')},
        ),
    ]
