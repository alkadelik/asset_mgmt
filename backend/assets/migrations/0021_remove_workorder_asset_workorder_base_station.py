from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('assets', '0020_client_remove_basestation_client_basestation_clients'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='workorder',
            name='asset',
        ),
        migrations.AddField(
            model_name='workorder',
            name='base_station',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='work_orders',
                to='assets.basestation',
                default=None,
            ),
            preserve_default=False,
        ),
    ]
