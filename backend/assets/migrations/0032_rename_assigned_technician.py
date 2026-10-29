from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('assets', '0031_remove_legacy_request_and_stock_fields'),
    ]

    operations = [
        migrations.RenameField(
            model_name='workorder',
            old_name='assigned_technician',
            new_name='assigned_to',
        ),
        migrations.AlterField(
            model_name='personnel',
            name='stations',
            field=models.ManyToManyField(blank=True, related_name='assigned_field_team', to='assets.basestation'),
        ),
    ]
