from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='is_prima',
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name='product',
            name='is_limited',
            field=models.BooleanField(db_index=True, default=False),
        ),
    ]
