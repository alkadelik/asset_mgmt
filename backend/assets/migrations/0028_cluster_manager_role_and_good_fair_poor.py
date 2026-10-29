from django.db import migrations, models

OLD_TO_NEW = {'very_good': 'good', 'fairly_good': 'fair', 'very_poor': 'poor'}


def forwards(apps, schema_editor):
    AssetChecklist = apps.get_model('assets', 'AssetChecklist')
    for old, new in OLD_TO_NEW.items():
        AssetChecklist.objects.filter(condition=old).update(condition=new)
    Role = apps.get_model('assets', 'Role')
    Role.objects.get_or_create(name='cluster_manager')


def backwards(apps, schema_editor):
    AssetChecklist = apps.get_model('assets', 'AssetChecklist')
    for old, new in OLD_TO_NEW.items():
        AssetChecklist.objects.filter(condition=new).update(condition=old)
    # The cluster_manager Role row is left in place: personnel may reference it.


class Migration(migrations.Migration):

    dependencies = [
        ('assets', '0027_alter_workorderchecklistresponse_options'),
    ]

    operations = [
        migrations.AlterField(
            model_name='role',
            name='name',
            field=models.CharField(choices=[('technician', 'Technician'), ('regional_manager', 'Regional Manager'), ('cluster_group_manager', 'Cluster Group Manager'), ('cluster_manager', 'Cluster Manager')], max_length=50, unique=True),
        ),
        migrations.AlterField(
            model_name='assetchecklist',
            name='condition',
            field=models.CharField(blank=True, choices=[('good', 'Good'), ('fair', 'Fair'), ('poor', 'Poor')], max_length=20, null=True),
        ),
        migrations.RunPython(forwards, backwards),
    ]
