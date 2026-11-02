"""Replace the old asset categories with the nine Form 1a types.

Assets of a type that has a direct equivalent move to it (OLD_TO_NEW). Assets of any other old
type (Air Conditioning, Rectifier, ...) are deleted, along with the old categories, their
checklists and their defects. The database holds only reference data when this runs, so
nothing with history is lost; if an asset being deleted does have history (readings,
inspections), Django raises ProtectedError and the whole migration rolls back untouched.
"""
from django.db import migrations

from assets.reference_data import OLD_TO_NEW, TYPE_NAMES, load_asset_types


def forwards(apps, schema_editor):
    AssetCategory = apps.get_model('assets', 'AssetCategory')
    Asset = apps.get_model('assets', 'Asset')
    Condition = apps.get_model('assets', 'Condition')
    AssetCheckList = apps.get_model('assets', 'AssetCheckList')
    PMQuestion = apps.get_model('assets', 'PMQuestion')

    new = load_asset_types(AssetCategory, Condition, AssetCheckList, PMQuestion)

    for old in AssetCategory.objects.exclude(name__in=TYPE_NAMES):
        target = new.get(OLD_TO_NEW.get(old.name))
        if target is not None:
            Asset.objects.filter(asset_category=old).update(asset_category=target)
        else:
            Asset.objects.filter(asset_category=old).delete()
        AssetCheckList.objects.filter(asset_category=old).delete()
        Condition.objects.filter(asset_category=old).delete()
        old.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('assets', '0033_asset_types_ratings_schema'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
