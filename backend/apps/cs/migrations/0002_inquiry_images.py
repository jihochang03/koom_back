from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cs', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='inquiry',
            name='images',
            field=models.JSONField(blank=True, null=True),
        ),
    ]
