from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name='SupportedSite',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('domain', models.CharField(max_length=255, unique=True)),
                ('icon_url', models.URLField(blank=True, default='')),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('sort_order', models.PositiveIntegerField(db_index=True, default=0)),
                ('product_url_patterns', models.JSONField(default=list)),
                ('search_url_patterns', models.JSONField(default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['sort_order', 'name']},
        ),
    ]
