"""
Run with: python manage.py shell < demo_visits.py
DEV ONLY. Fills the Maintenance reports with sample history: three weeks of weekday visits at every
station (a mix of Good / Fair / Poor, some Missed days), diesel and run-hours readings, a diesel
delivery and one open alarm. Never touches today. Safe to re-run (skips days that already have a visit).
Undo with: python manage.py shell < clear_demo_data.py
"""
import datetime

import django
django.setup()

from assets import ratings
from assets.models import (
    Alarm, Asset, BaseStation, DieselDelivery, InspectionResponse, MeterReading, Personnel, WorkOrder,
)

tech = Personnel.objects.get(username="tech1")
today = ratings.visit_date()
PATTERN = ["good", "good", "fair", "good", "poor", "good", "missed", "good", "fair"]
made = 0

for s_index, station in enumerate(BaseStation.objects.order_by("name")):
    assets = list(Asset.objects.filter(location__base_station=station, status=Asset.STATUS_ACTIVE))
    for back in range(21, 0, -1):
        day = today - datetime.timedelta(days=back)
        if day.weekday() > 4 or WorkOrder.objects.filter(base_station=station, due_date=day).exists():
            continue
        outcome = PATTERN[(s_index * 3 + day.toordinal()) % len(PATTERN)]
        wo = WorkOrder.objects.create(
            base_station=station, type=WorkOrder.TYPE_PREVENTIVE, due_date=day, assigned_to=tech,
            status=WorkOrder.STATUS_COMPLETE if outcome != "missed" else WorkOrder.STATUS_OPEN,
        )
        if outcome == "missed":
            continue
        moment = datetime.datetime.combine(day, datetime.time(12), tzinfo=ratings.LAGOS)
        for i, asset in enumerate(assets):
            rating = "good"
            if outcome == "poor" and i == 1:
                rating = "poor"  # the second asset (the generator where there is one)
            elif outcome == "fair" and i in (0, 2, 3):
                rating = "fair"
            InspectionResponse.objects.create(
                work_order=wo, asset=asset, done=True, rating=rating, completed_at=moment,
            )
        ratings.update_visit(wo, moment)
        for asset in assets:
            name = asset.asset_category.name
            if name == "Diesel Generator":
                MeterReading.objects.create(
                    asset=asset, reading_type="run_hours", date=day, unit="hours", recorded_by=tech,
                    value=1000 + 8 * (day.toordinal() % 400) + 40 * s_index, work_order=wo,
                )
            if name == "Diesel Tank":
                mm = 300 - 6 * (21 - back)
                MeterReading.objects.create(
                    asset=asset, reading_type="diesel_level", date=day, unit="mm", recorded_by=tech,
                    value=mm, value_litres=mm * 3, work_order=wo,
                )
        made += 1

    tank = next((a for a in assets if a.asset_category.name == "Diesel Tank"), None)
    if tank and not DieselDelivery.objects.filter(base_station=station).exists():
        DieselDelivery.objects.create(
            base_station=station, quantity_litres=500, recorded_by=tech,
            delivered_at=datetime.datetime.combine(today - datetime.timedelta(days=9), datetime.time(10), tzinfo=ratings.LAGOS),
            tank_level_before=90, tank_level_before_litres=270, tank_level_after=255, tank_level_after_litres=765,
        )

first = Asset.objects.filter(asset_category__name="Diesel Generator").first()
if first and not Alarm.objects.filter(asset=first, resolved_at__isnull=True).exists():
    Alarm.objects.create(asset=first, raised_at=datetime.datetime.now(tz=ratings.LAGOS))

print(f"Visits added: {made}")
