import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name='UserAddress',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('customer_id', models.CharField(db_index=True, max_length=255)),
                ('name', models.CharField(max_length=100)),
                ('phone', models.CharField(max_length=20)),
                ('zipcode', models.CharField(max_length=10)),
                ('address1', models.CharField(max_length=500)),
                ('address2', models.CharField(blank=True, max_length=500)),
                ('is_default', models.BooleanField(db_index=True, default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['-is_default', '-created_at']},
        ),
        migrations.CreateModel(
            name='Coupon',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=100, unique=True)),
                ('name', models.CharField(max_length=255)),
                ('discount_type', models.CharField(choices=[('fixed','정액 할인'),('percent','정률 할인')], max_length=10)),
                ('discount_value', models.FloatField()),
                ('min_order_amount', models.FloatField(default=0)),
                ('max_discount_amount', models.FloatField(blank=True, null=True)),
                ('valid_from', models.DateTimeField()),
                ('valid_until', models.DateTimeField()),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('usage_limit', models.IntegerField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='UserCoupon',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('customer_id', models.CharField(db_index=True, max_length=255)),
                ('coupon', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='user_coupons', to='mypage.coupon')),
                ('order_number', models.CharField(blank=True, max_length=50)),
                ('used_at', models.DateTimeField(blank=True, null=True)),
                ('issued_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ['-issued_at']},
        ),
        migrations.CreateModel(
            name='PointLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('customer_id', models.CharField(db_index=True, max_length=255)),
                ('delta', models.IntegerField()),
                ('reason', models.CharField(choices=[('earn_order','주문 적립'),('earn_event','이벤트 적립'),('earn_admin','관리자 지급'),('use_order','주문 사용'),('expire','만료'),('refund','환불 복원')], max_length=30)),
                ('order_number', models.CharField(blank=True, max_length=50)),
                ('balance_after', models.IntegerField()),
                ('note', models.CharField(blank=True, max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='NotificationSetting',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('customer_id', models.CharField(max_length=255, unique=True)),
                ('order_status_push', models.BooleanField(default=True)),
                ('order_status_email', models.BooleanField(default=True)),
                ('marketing_push', models.BooleanField(default=False)),
                ('marketing_email', models.BooleanField(default=False)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
