from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('assets', '0015_alter_assetchecklist_options_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='assetchecklistcondition',
            name='checklist',
        ),
        migrations.AddField(
            model_name='assetchecklistcondition',
            name='asset',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='conditions',
                to='assets.asset',
            ),
        ),
    ]
