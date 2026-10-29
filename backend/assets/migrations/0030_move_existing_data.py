"""Moves existing data onto the new structures before 0031 removes the old fields.

- The `technician` role row becomes `field_team`; a `team_lead` role row is created.
- Stock held per cluster group becomes stock in that cluster group's regional store
  (rows for the same part in one region are added together).
- Each single-part request gets one line. A request already marked Received gets a delivery
  confirmed by both sides, so it shows as Delivered. No stock moves for these: they predate
  stock tracking.
"""
from django.db import migrations


def forwards(apps, schema_editor):
    Role = apps.get_model('assets', 'Role')
    if not Role.objects.filter(name='field_team').exists():
        Role.objects.filter(name='technician').update(name='field_team')
    Role.objects.get_or_create(name='field_team')
    Role.objects.get_or_create(name='team_lead')

    PartStock = apps.get_model('assets', 'PartStock')
    for stock in list(PartStock.objects.filter(cluster_group__isnull=False, region__isnull=True)):
        region_id = stock.cluster_group.region_id
        existing = PartStock.objects.filter(part_id=stock.part_id, region_id=region_id).first()
        if existing:
            existing.qty += stock.qty
            existing.reorder_threshold = max(existing.reorder_threshold, stock.reorder_threshold)
            existing.save(update_fields=['qty', 'reorder_threshold'])
            stock.delete()
        else:
            stock.region_id = region_id
            stock.cluster_group_id = None
            stock.save(update_fields=['region', 'cluster_group'])

    PartRequest = apps.get_model('assets', 'PartRequest')
    PartRequestLine = apps.get_model('assets', 'PartRequestLine')
    PartDelivery = apps.get_model('assets', 'PartDelivery')
    for req in PartRequest.objects.filter(part__isnull=False):
        if PartRequestLine.objects.filter(request=req).exists():
            continue
        received = req.status == 'received'
        line = PartRequestLine.objects.create(
            request=req,
            part_id=req.part_id,
            quantity=req.quantity or 1,
            required_date=req.requested_at.date(),
            status='delivered' if received else 'requested',
        )
        if received:
            when = req.received_at or req.updated
            PartDelivery.objects.create(
                line=line,
                quantity=line.quantity,
                marked_delivered_at=when,
                received_by_id=req.requested_by_id,
                received_at=when,
                stock_moved=True,
            )


def backwards(apps, schema_editor):
    """Best-effort undo. Team-held stock has no old equivalent and is dropped; regional stock goes
    to the region's first cluster group; a request with several lines keeps only its first."""
    Role = apps.get_model('assets', 'Role')
    if not Role.objects.filter(name='technician').exists():
        Role.objects.filter(name='field_team').update(name='technician')

    PartStock = apps.get_model('assets', 'PartStock')
    ClusterGroup = apps.get_model('assets', 'ClusterGroup')
    PartStock.objects.filter(cluster_team__isnull=False).delete()
    for stock in PartStock.objects.filter(region__isnull=False, cluster_group__isnull=True):
        group = ClusterGroup.objects.filter(region_id=stock.region_id).order_by('name').first()
        if group is None:
            stock.delete()
            continue
        stock.cluster_group_id = group.id
        stock.region_id = None
        stock.save(update_fields=['cluster_group', 'region'])

    PartRequestLine = apps.get_model('assets', 'PartRequestLine')
    for line in PartRequestLine.objects.select_related('request'):
        req = line.request
        if req.part_id is None:
            req.part_id = line.part_id
            req.quantity = line.quantity
            req.status = 'received' if line.status == 'delivered' else 'requested'
            req.save(update_fields=['part', 'quantity', 'status'])


class Migration(migrations.Migration):

    dependencies = [
        ('assets', '0029_parts_stock_requests_phase_a'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
