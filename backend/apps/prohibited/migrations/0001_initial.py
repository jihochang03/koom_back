from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name='ProhibitedKeyword',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('keyword', models.CharField(max_length=255, unique=True)),
                ('category', models.CharField(blank=True, max_length=100)),
                ('risk_level', models.CharField(choices=[('prohibited','수입 금지'),('restricted','수입 제한'),('warning','주의')], db_index=True, max_length=20)),
                ('description', models.TextField(blank=True)),
                ('customs_reference', models.URLField(blank=True)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['risk_level', 'keyword']},
        ),
    ]
