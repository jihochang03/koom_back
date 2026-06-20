from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0001_initial'),
    ]

    operations = [
        migrations.AddField(model_name='order', name='product_copy_url', field=models.CharField(blank=True, max_length=500)),
        migrations.AddField(model_name='order', name='product_category', field=models.CharField(blank=True, max_length=200)),
        migrations.AddField(model_name='order', name='prohibited_review', field=models.JSONField(blank=True, null=True)),
        migrations.AddField(model_name='order', name='price_initial_payment', field=models.FloatField(blank=True, null=True)),
        migrations.AddField(model_name='order', name='price_discount', field=models.FloatField(default=0)),
        migrations.AddField(model_name='order', name='price_points_used', field=models.FloatField(default=0)),
        migrations.AddField(model_name='order', name='price_final_charged', field=models.FloatField(blank=True, null=True)),
        migrations.AddField(model_name='order', name='company_burden_tariff', field=models.FloatField(default=0)),
        migrations.AddField(model_name='order', name='company_burden_error_small', field=models.FloatField(default=0)),
        migrations.AddField(model_name='order', name='company_burden_shipping_error', field=models.FloatField(default=0)),
        migrations.AddField(model_name='order', name='company_burden_other', field=models.FloatField(default=0)),
        migrations.AddField(model_name='order', name='refund_partial_error', field=models.FloatField(default=0)),
        migrations.AddField(model_name='order', name='refund_customer_request', field=models.FloatField(default=0)),
        migrations.AddField(model_name='order', name='refund_inspection', field=models.FloatField(default=0)),
        migrations.AddField(model_name='order', name='refund_cancellation', field=models.FloatField(default=0)),
    ]
