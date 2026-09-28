from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('assets', '0016_assetchecklistcondition_swap_fk'),
    ]

    operations = [
        migrations.AddField(
            model_name='assetchecklistcondition',
            name='condition',
            field=models.CharField(max_length=255, default=''),
            preserve_default=False,
        ),
    ]
