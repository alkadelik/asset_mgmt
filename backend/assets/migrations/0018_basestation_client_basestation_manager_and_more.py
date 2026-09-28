from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('assets', '0017_assetchecklistcondition_condition'),
    ]

    operations = [
        migrations.AddField(
            model_name='basestation',
            name='client',
            field=models.CharField(
                choices=[('mtn', 'MTN'), ('airtel', 'Airtel'), ('huawei', 'Huawei')],
                max_length=20,
                default='mtn',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='basestation',
            name='site_classification',
            field=models.CharField(
                choices=[('platinum', 'Platinum')],
                max_length=20,
                default='platinum',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='basestation',
            name='manager',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='managed_stations',
                to='assets.personnel',
            ),
        ),
    ]
