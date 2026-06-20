from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('logistics', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='shippingtracking',
            name='fb_invoice_no',
            field=models.CharField(blank=True, db_index=True, max_length=100),
        ),
        migrations.AddField(
            model_name='shippingtracking',
            name='dhub_ord_bundle_no',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='shippingtracking',
            name='dhub_instruction_no',
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name='shippingtracking',
            name='dhub_delivery_type',
            field=models.CharField(blank=True, max_length=5),
        ),
    ]
