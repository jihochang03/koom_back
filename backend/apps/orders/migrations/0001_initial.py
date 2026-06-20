import apps.orders.models
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name='OrderGroup',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('group_number', models.CharField(default=apps.orders.models._gen_group_number, db_index=True, max_length=50, unique=True)),
                ('customer_id', models.CharField(db_index=True, max_length=255)),
                ('status', models.CharField(choices=[('pending','결제 대기'),('paid','결제 완료'),('partial','일부 처리 중'),('completed','전체 완료'),('cancelled','취소')], db_index=True, default='pending', max_length=30)),
                ('bundle_fee', models.FloatField(default=0)),
                ('coupon_discount', models.FloatField(default=0)),
                ('point_discount', models.FloatField(default=0)),
                ('total_paid', models.FloatField(default=0)),
                ('currency', models.CharField(default='KRW', max_length=10)),
                ('paid_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='Order',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order_number', models.CharField(default=apps.orders.models._gen_order_number, db_index=True, max_length=50, unique=True)),
                ('group', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='orders', to='orders.ordergroup')),
                ('customer_id', models.CharField(db_index=True, max_length=255)),
                ('site_domain', models.CharField(blank=True, db_index=True, max_length=255)),
                ('product_url', models.URLField(max_length=2048)),
                ('title', models.CharField(max_length=1024)),
                ('options', models.JSONField(default=list)),
                ('quantity', models.PositiveIntegerField(default=1)),
                ('price_product', models.FloatField()),
                ('price_domestic_shipping', models.FloatField(default=0)),
                ('price_intl_shipping', models.FloatField(default=0)),
                ('price_tariff', models.FloatField(default=0)),
                ('price_fee', models.FloatField(default=0)),
                ('price_total', models.FloatField()),
                ('currency', models.CharField(default='KRW', max_length=10)),
                ('price_dk_burden', models.FloatField(default=0)),
                ('price_actual', models.FloatField(blank=True, null=True)),
                ('admin_notes', models.TextField(blank=True)),
                ('inspection_notes', models.TextField(blank=True)),
                ('refund_amount', models.FloatField(blank=True, null=True)),
                ('refund_reason', models.TextField(blank=True)),
                ('status', models.CharField(choices=[('pending','주문 대기'),('paid','결제 완료'),('purchasing','현지 구매 중'),('shipping_domestic','현지 배송 중'),('inspection','검수 중'),('shipping_intl','국제 배송 중'),('delivered','배송 완료'),('cancelled','취소'),('refunded','환불 완료'),('partial_refund','부분 환불')], db_index=True, default='pending', max_length=30)),
                ('tracking_number', models.CharField(blank=True, max_length=255)),
                ('estimated_delivery_min', models.IntegerField(blank=True, null=True)),
                ('estimated_delivery_max', models.IntegerField(blank=True, null=True)),
                ('product_snapshot', models.JSONField(default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
