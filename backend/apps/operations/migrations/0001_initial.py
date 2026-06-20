import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name='ErrorCriteria',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('small_error_threshold_pct', models.FloatField(default=2.0)),
                ('small_error_threshold_abs', models.FloatField(default=500.0)),
                ('small_error_per_item', models.BooleanField(default=True)),
                ('large_error_threshold_pct', models.FloatField(default=5.0)),
                ('handling_ai_error', models.CharField(choices=[('company_burden','회사 부담'),('cs_review','CS 수동 검토'),('additional_charge','고객 추가비용 요청'),('cancel','취소'),('partial_refund','부분환불')], default='company_burden', max_length=30)),
                ('handling_price_change', models.CharField(choices=[('company_burden','회사 부담'),('cs_review','CS 수동 검토'),('additional_charge','고객 추가비용 요청'),('cancel','취소'),('partial_refund','부분환불')], default='cs_review', max_length=30)),
                ('handling_shipping_extra', models.CharField(choices=[('company_burden','회사 부담'),('cs_review','CS 수동 검토'),('additional_charge','고객 추가비용 요청'),('cancel','취소'),('partial_refund','부분환불')], default='company_burden', max_length=30)),
                ('handling_tax', models.CharField(choices=[('company_burden','회사 부담'),('cs_review','CS 수동 검토'),('additional_charge','고객 추가비용 요청'),('cancel','취소'),('partial_refund','부분환불')], default='cs_review', max_length=30)),
                ('handling_prima_risk', models.CharField(choices=[('company_burden','회사 부담'),('cs_review','CS 수동 검토'),('additional_charge','고객 추가비용 요청'),('cancel','취소'),('partial_refund','부분환불')], default='cs_review', max_length=30)),
                ('handling_exchange_rate', models.CharField(choices=[('company_burden','회사 부담'),('cs_review','CS 수동 검토'),('additional_charge','고객 추가비용 요청'),('cancel','취소'),('partial_refund','부분환불')], default='company_burden', max_length=30)),
                ('is_current', models.BooleanField(db_index=True, default=True)),
                ('note', models.TextField(blank=True)),
                ('created_by', models.CharField(blank=True, max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='ErrorCriteriaLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('criteria', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='logs', to='operations.errorcriteria')),
                ('changed_field', models.CharField(max_length=100)),
                ('old_value', models.JSONField(blank=True, null=True)),
                ('new_value', models.JSONField(blank=True, null=True)),
                ('changed_by', models.CharField(blank=True, max_length=255)),
                ('changed_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ['-changed_at']},
        ),
    ]
