from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name='WishlistItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('customer_id', models.CharField(db_index=True, max_length=255)),
                ('product_url', models.URLField(max_length=2048)),
                ('site_domain', models.CharField(blank=True, db_index=True, max_length=255)),
                ('title', models.CharField(blank=True, max_length=1024)),
                ('images', models.JSONField(default=list)),
                ('price_snapshot', models.FloatField(blank=True, null=True)),
                ('currency', models.CharField(default='KRW', max_length=10)),
                ('options', models.JSONField(default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ['-created_at'], 'unique_together': {('customer_id', 'product_url')}},
        ),
    ]
