import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0003_status_log_action_log_error_pg'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProductSnapshot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order_number', models.CharField(db_index=True, max_length=50, unique=True)),
                ('snapshot_uuid', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('product_name', models.CharField(max_length=500)),
                ('purchase_price', models.FloatField()),
                ('product_price_at_purchase', models.FloatField()),
                ('options', models.JSONField(blank=True, null=True)),
                ('quantity', models.IntegerField(default=1)),
                ('seller', models.CharField(blank=True, max_length=255)),
                ('site_domain', models.CharField(blank=True, max_length=255)),
                ('product_url', models.URLField(blank=True, max_length=1000)),
                ('images', models.JSONField(blank=True, null=True)),
                ('html_content', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
