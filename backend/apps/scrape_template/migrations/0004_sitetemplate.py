from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scrape_template', '0003_templatebuildlog_category'),
    ]

    operations = [
        migrations.CreateModel(
            name='SiteTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('domain', models.CharField(db_index=True, max_length=255, unique=True)),
                ('filename', models.CharField(blank=True, default='', max_length=255)),
                ('code', models.TextField()),
                ('page_type', models.CharField(default='both', max_length=20)),
                ('category', models.CharField(db_index=True, default='shopping', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['-updated_at'],
            },
        ),
    ]
