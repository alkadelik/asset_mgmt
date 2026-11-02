"""
Run with: python manage.py shell < clear_demo_data.py
Deletes transactional/demo records and keeps reference data. Back up first (pg_dump).
"""
import django
django.setup()

from django.db import transaction
from django.utils import timezone
from assets.models import (
    Alarm, AlarmNote, Attachment, DieselDelivery, InspectionResponse, Issue, MeterReading,
    Notification, PartDelivery, PartRequest, PartRequestLine, PartUsage, SafetyReport,
    StockMovement, WorkOrder, WorkOrderChecklistResponse,
)

with transaction.atomic():
    for model in (
        Notification, Attachment, AlarmNote, Alarm, Issue, MeterReading, DieselDelivery,
        SafetyReport, PartUsage, PartDelivery, PartRequestLine, PartRequest, StockMovement,
        WorkOrderChecklistResponse, InspectionResponse,
    ):
        n, _ = model.objects.all().delete()
        print(f"{model.__name__}: deleted {n}")
    # Keep only today's work orders, reset to scheduled-but-not-started
    WorkOrder.objects.exclude(due_date=timezone.localdate()).delete()
    for wo in WorkOrder.objects.exclude(status=WorkOrder.STATUS_OPEN):
        wo.status = WorkOrder.STATUS_OPEN
        wo.started_at = None
        wo.ended_at = None
        wo.save()
    print(f"Work orders kept: {WorkOrder.objects.count()}")
