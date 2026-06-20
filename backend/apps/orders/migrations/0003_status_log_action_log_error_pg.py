from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0002_order_detail_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='OrderStatusLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order_number', models.CharField(db_index=True, max_length=50)),
                ('stage', models.CharField(choices=[('order_received','주문 접수'),('purchase_review','구매 검토'),('purchase_complete','구매 완료'),('pre_arrival','입고 대기'),('arrived','입고 완료'),('inspection_in_progress','검수 중'),('inspection_complete','검수 완료'),('preparing_dispatch','출고 준비'),('intl_shipping','국제 배송 중'),('jp_carrier_handover','일본 배송사 인계'),('delivered','배송 완료'),('cancelled_or_refunded','취소/반품/환불')], db_index=True, max_length=30)),
                ('changed_at', models.DateTimeField()),
                ('responsible_party', models.CharField(choices=[('dk','DK(당사)'),('seller','판매처'),('logistics','물류센터'),('carrier','배송사'),('system','시스템'),('customer','고객')], default='system', max_length=20)),
                ('memo', models.TextField(blank=True)),
                ('available_actions', models.JSONField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ['changed_at']},
        ),
        migrations.CreateModel(
            name='AdminActionLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order_number', models.CharField(db_index=True, max_length=50)),
                ('changed_field', models.CharField(max_length=100)),
                ('old_value', models.JSONField(blank=True, null=True)),
                ('new_value', models.JSONField(blank=True, null=True)),
                ('actor_type', models.CharField(choices=[('system','시스템'),('operator','운영자'),('logistics','물류센터'),('pg','PG'),('carrier_api','배송사 API')], default='operator', max_length=20)),
                ('actor_id', models.CharField(blank=True, max_length=255)),
                ('reason', models.TextField(blank=True)),
                ('changed_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ['-changed_at']},
        ),
        migrations.CreateModel(
            name='ErrorInfo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order_number', models.CharField(db_index=True, max_length=50, unique=True)),
                ('error_rate', models.FloatField(blank=True, null=True)),
                ('error_amount', models.FloatField(blank=True, null=True)),
                ('error_causes', models.JSONField(blank=True, null=True)),
                ('handling_method', models.CharField(blank=True, choices=[('company_burden','회사 부담'),('cs_review','CS 수동 검토'),('additional_charge','고객 추가비용 요청'),('cancel','취소'),('partial_refund','부분환불')], max_length=30)),
                ('auto_processed', models.BooleanField(default=False)),
                ('cs_review_reason', models.TextField(blank=True)),
                ('additional_charge_amount', models.FloatField(blank=True, null=True)),
                ('additional_charge_sent_at', models.DateTimeField(blank=True, null=True)),
                ('additional_charge_accepted_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='PGTransaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order_number', models.CharField(db_index=True, max_length=50)),
                ('pg_transaction_id', models.CharField(max_length=255, unique=True)),
                ('auth_status', models.CharField(choices=[('pending','인증 대기'),('auth_complete','결제 인증 완료'),('capture_pending','매출 확정 대기'),('captured','매출 확정 완료'),('cancel_in_progress','취소/환불 진행 중'),('cancelled','취소 완료'),('refunded','환불 완료'),('failed','실패')], default='pending', max_length=30)),
                ('refund_amount', models.FloatField(blank=True, null=True)),
                ('refund_requested_at', models.DateTimeField(blank=True, null=True)),
                ('refund_completed_at', models.DateTimeField(blank=True, null=True)),
                ('failure_reason', models.TextField(blank=True)),
                ('raw_payload', models.JSONField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
