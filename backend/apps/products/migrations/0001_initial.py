from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='Product',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source_url', models.URLField(blank=True, default='', max_length=2048)),
                ('url', models.URLField(db_index=True, max_length=2048)),
                ('product_id', models.CharField(blank=True, default='', max_length=255)),
                ('title', models.CharField(blank=True, default='', max_length=1024)),
                ('price_original', models.FloatField(blank=True, null=True)),
                ('price_discounted', models.FloatField(blank=True, null=True)),
                ('currency', models.CharField(default='KRW', max_length=10)),
                ('images', models.JSONField(default=list)),
                ('brand', models.CharField(blank=True, default='', max_length=255)),
                ('rating', models.FloatField(blank=True, null=True)),
                ('review_count', models.IntegerField(blank=True, null=True)),
                ('availability', models.CharField(blank=True, default='', max_length=50)),
                ('category', models.CharField(blank=True, db_index=True, default='', max_length=100)),
                ('detail_data', models.JSONField(default=dict)),
                ('detail_status', models.CharField(
                    choices=[
                        ('pending', '대기'),
                        ('prefetching', '수집중'),
                        ('ready', '완료'),
                        ('failed', '실패'),
                    ],
                    db_index=True,
                    default='pending',
                    max_length=20,
                )),
                ('detail_crawled_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
