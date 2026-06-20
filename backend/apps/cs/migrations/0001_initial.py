from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name='Inquiry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('customer_id', models.CharField(db_index=True, max_length=255)),
                ('order_number', models.CharField(blank=True, db_index=True, max_length=50)),
                ('inquiry_type', models.CharField(choices=[('general','일반 문의'),('cancel','취소 문의'),('refund','환불 문의'),('exchange','교환 문의'),('return','반품 문의'),('shipping','배송 문의'),('other','기타')], db_index=True, default='general', max_length=20)),
                ('title', models.CharField(max_length=255)),
                ('content', models.TextField()),
                ('status', models.CharField(choices=[('open','접수'),('in_progress','처리 중'),('resolved','해결됨'),('closed','종료')], db_index=True, default='open', max_length=20)),
                ('admin_reply', models.TextField(blank=True)),
                ('replied_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='CancelRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order_number', models.CharField(db_index=True, max_length=50, unique=True)),
                ('customer_id', models.CharField(db_index=True, max_length=255)),
                ('reason', models.TextField()),
                ('status', models.CharField(choices=[('pending','취소 요청'),('approved','취소 승인'),('rejected','취소 반려'),('completed','취소 완료')], db_index=True, default='pending', max_length=20)),
                ('shipping_fee_burden', models.BooleanField(default=False)),
                ('admin_notes', models.TextField(blank=True)),
                ('processed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='RefundRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order_number', models.CharField(db_index=True, max_length=50, unique=True)),
                ('customer_id', models.CharField(db_index=True, max_length=255)),
                ('reason', models.TextField()),
                ('requested_amount', models.FloatField()),
                ('approved_amount', models.FloatField(blank=True, null=True)),
                ('status', models.CharField(choices=[('pending','환불 요청'),('approved','환불 승인'),('partial_approved','부분 환불 승인'),('rejected','환불 반려'),('completed','환불 완료')], db_index=True, default='pending', max_length=20)),
                ('admin_notes', models.TextField(blank=True)),
                ('processed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
