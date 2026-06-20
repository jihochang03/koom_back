from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name='LogisticsInfo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order_number', models.CharField(db_index=True, max_length=50, unique=True)),
                ('expected_arrival', models.DateTimeField(blank=True, null=True)),
                ('arrived_at', models.DateTimeField(blank=True, null=True)),
                ('inspection_result', models.CharField(choices=[('pending','검수 대기'),('pass','검수 완료'),('issue','검수 이슈')], default='pending', max_length=10)),
                ('inspection_photos', models.JSONField(blank=True, null=True)),
                ('components_match', models.BooleanField(blank=True, null=True)),
                ('has_defect', models.BooleanField(blank=True, null=True)),
                ('issue_reason', models.TextField(blank=True)),
                ('post_inspection_action', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='ShippingTracking',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order_number', models.CharField(db_index=True, max_length=50, unique=True)),
                ('tracking_number', models.CharField(blank=True, max_length=100)),
                ('carrier', models.CharField(blank=True, max_length=100)),
                ('carrier_status', models.CharField(blank=True, max_length=255)),
                ('customer_status', models.CharField(blank=True, max_length=255)),
                ('last_status_changed_at', models.DateTimeField(blank=True, null=True)),
                ('last_api_checked_at', models.DateTimeField(blank=True, null=True)),
                ('next_check_at', models.DateTimeField(blank=True, null=True)),
                ('is_untrackable_segment', models.BooleanField(default=False)),
                ('delay_detected', models.BooleanField(default=False)),
                ('delay_type', models.CharField(choices=[('none','정상'),('24h','24시간 정체'),('48h','48시간 정체'),('extended','장기 지연')], default='none', max_length=10)),
                ('delay_hours', models.IntegerField(blank=True, null=True)),
                ('stagnation_detected_at', models.DateTimeField(blank=True, null=True)),
                ('events', models.JSONField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
