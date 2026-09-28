"""
Run with: python manage.py shell < seed.py
Creates a complete set of test data matching the mock data in the mobile app.
Safe to re-run — uses get_or_create throughout.
"""
import django
django.setup()

from django.utils import timezone
from assets.models import (
    Region, ClusterGroup, Cluster, Client, BaseStation, Location,
    AssetCategory, Asset, Condition, Role, Personnel,
    PMCategory, AssetCheckList, PMQuestion,
    WorkOrder, Alarm, AlarmNote, InspectionResponse, WorkOrderChecklistResponse, Issue,
    DieselDelivery, MeterReading, Part, PartRequest, SafetyReport, Vendor,
)

today = timezone.localdate()
now = timezone.now()

print("Seeding roles...")
role_tech, _ = Role.objects.get_or_create(name=Role.TECHNICIAN)
role_rm, _ = Role.objects.get_or_create(name=Role.REGIONAL_MANAGER)

print("Seeding org hierarchy...")
region, _ = Region.objects.get_or_create(name="South West")
cg, _ = ClusterGroup.objects.get_or_create(region=region, name="Lagos Cluster Group")
cluster, _ = Cluster.objects.get_or_create(cluster_group=cg, name="Lagos Island")

print("Seeding clients...")
mtn, _ = Client.objects.get_or_create(name=Client.NAME_MTN)
airtel, _ = Client.objects.get_or_create(name=Client.NAME_AIRTEL)

print("Seeding manager...")
manager, created = Personnel.objects.get_or_create(username="funke.adeyemi")
if created:
    manager.set_password("manager123")
    manager.first_name = "Funke"
    manager.last_name = "Adeyemi"
    manager.role = role_rm
    manager.save()

print("Seeding base stations...")
station_a, _ = BaseStation.objects.get_or_create(
    site_id="LOS-A001",
    defaults={
        "cluster": cluster,
        "name": "Victoria Island Alpha",
        "address": "1 Ozumba Mbadiwe Ave, Victoria Island, Lagos",
        "state": "Lagos",
        "site_classification": BaseStation.CLASS_PLATINUM,
        "manager": manager,
    },
)
station_a.clients.set([mtn, airtel])

station_b, _ = BaseStation.objects.get_or_create(
    site_id="LOS-B012",
    defaults={
        "cluster": cluster,
        "name": "Lekki Phase 1 Beta",
        "address": "14 Admiralty Way, Lekki Phase 1, Lagos",
        "state": "Lagos",
        "site_classification": BaseStation.CLASS_PLATINUM,
        "manager": manager,
    },
)
station_b.clients.set([mtn])

print("Seeding locations...")
loc_a, _ = Location.objects.get_or_create(
    base_station=station_a, name="Equipment Room A", defaults={"parent_location": None}
)
loc_b, _ = Location.objects.get_or_create(
    base_station=station_b, name="Equipment Room B", defaults={"parent_location": None}
)

print("Seeding asset categories...")
cat_gen, _ = AssetCategory.objects.get_or_create(name="Generator")
cat_ac, _ = AssetCategory.objects.get_or_create(name="Air Conditioning")
cat_rect, _ = AssetCategory.objects.get_or_create(name="Rectifier")
cat_battery, _ = AssetCategory.objects.get_or_create(name="Battery Bank")
cat_solar, _ = AssetCategory.objects.get_or_create(name="Solar")
cat_dc, _ = AssetCategory.objects.get_or_create(name="DC Electricals")
cat_ac_elec, _ = AssetCategory.objects.get_or_create(name="AC Electricals")
cat_janitorial, _ = AssetCategory.objects.get_or_create(name="Janitorial")

print("Seeding conditions...")
for name in ["Oil leak detected", "Abnormal vibration", "Overheating", "Unusual noise"]:
    Condition.objects.get_or_create(name=name, asset_category=cat_gen)
for name in ["Coolant low", "Filter blocked", "Compressor fault", "Electrical fault"]:
    Condition.objects.get_or_create(name=name, asset_category=cat_ac)
for name in ["Output voltage low", "Fan failure", "Overtemperature alarm"]:
    Condition.objects.get_or_create(name=name, asset_category=cat_rect)
for name in ["Cell voltage low", "High temperature", "Capacity degraded"]:
    Condition.objects.get_or_create(name=name, asset_category=cat_battery)

print("Seeding checklist questions...")
pm_cat, _ = PMCategory.objects.get_or_create(name="Routine PM")

gen_checklist, _ = AssetCheckList.objects.get_or_create(
    asset_category=cat_gen,
    pm_category=None,
    asset=None,
    defaults={"instructions": "Generator routine inspection", "condition": None},
)
for q_text in [
    "Visual inspection completed — no leaks or damage?",
    "Oil level checked and topped up if required?",
    "Coolant level checked?",
    "Load test performed (minimum 15 minutes)?",
    "Exhaust clear and unrestricted?",
    "Battery terminals clean and secure?",
]:
    PMQuestion.objects.get_or_create(task_template=gen_checklist, question=q_text)

ac_checklist, _ = AssetCheckList.objects.get_or_create(
    asset_category=cat_ac,
    pm_category=None,
    asset=None,
    defaults={"instructions": "AC unit routine inspection", "condition": None},
)
for q_text in [
    "Filter cleaned or replaced?",
    "Coolant/refrigerant level verified OK?",
    "Condenser coils inspected and cleaned?",
    "Drain pan and drain line cleared?",
    "Compressor operating within normal parameters?",
]:
    PMQuestion.objects.get_or_create(task_template=ac_checklist, question=q_text)

rect_checklist, _ = AssetCheckList.objects.get_or_create(
    asset_category=cat_rect,
    pm_category=None,
    asset=None,
    defaults={"instructions": "Rectifier routine inspection", "condition": None},
)
for q_text in [
    "Output voltage within acceptable range?",
    "All module indicator lights green?",
    "Fans operating (no unusual noise)?",
    "Connections and terminals secure?",
]:
    PMQuestion.objects.get_or_create(task_template=rect_checklist, question=q_text)

solar_checklist, _ = AssetCheckList.objects.get_or_create(
    asset_category=cat_solar,
    pm_category=None,
    asset=None,
    defaults={"instructions": "Solar array routine inspection", "condition": None},
)
for q_text in [
    "Panels clean and free of obstruction?",
    "Mounting frame secure, no corrosion?",
    "Charge controller output within range?",
    "Cabling and connectors intact?",
]:
    PMQuestion.objects.get_or_create(task_template=solar_checklist, question=q_text)

dc_checklist, _ = AssetCheckList.objects.get_or_create(
    asset_category=cat_dc,
    pm_category=None,
    asset=None,
    defaults={"instructions": "DC electricals routine inspection", "condition": None},
)
for q_text in [
    "DC distribution board terminals tight and corrosion-free?",
    "Cable insulation intact, no exposed conductors?",
    "Earthing/grounding continuity verified?",
]:
    PMQuestion.objects.get_or_create(task_template=dc_checklist, question=q_text)

ac_elec_checklist, _ = AssetCheckList.objects.get_or_create(
    asset_category=cat_ac_elec,
    pm_category=None,
    asset=None,
    defaults={"instructions": "AC electricals routine inspection", "condition": None},
)
for q_text in [
    "AC distribution board terminals tight and corrosion-free?",
    "Circuit breakers operating correctly?",
    "Surge protection devices intact?",
]:
    PMQuestion.objects.get_or_create(task_template=ac_elec_checklist, question=q_text)

janitorial_checklist, _ = AssetCheckList.objects.get_or_create(
    asset_category=cat_janitorial,
    pm_category=None,
    asset=None,
    defaults={"instructions": "Site janitorial servicing", "condition": None},
)
for q_text in [
    "Equipment room floor swept and mopped?",
    "Waste bins emptied?",
    "Windows/vents free of dust and debris?",
    "Pest control check completed?",
]:
    PMQuestion.objects.get_or_create(task_template=janitorial_checklist, question=q_text)

print("Seeding assets at Station A...")
gen_a, _ = Asset.objects.get_or_create(
    name="Generator Set A",
    location=loc_a,
    defaults={"asset_category": cat_gen, "status": Asset.STATUS_ACTIVE, "tag": "GEN-A001"},
)
ac_a, _ = Asset.objects.get_or_create(
    name="Air Conditioning Unit",
    location=loc_a,
    defaults={"asset_category": cat_ac, "status": Asset.STATUS_ACTIVE, "tag": "AC-A001"},
)
rect_a, _ = Asset.objects.get_or_create(
    name="Rectifier Unit",
    location=loc_a,
    defaults={"asset_category": cat_rect, "status": Asset.STATUS_ACTIVE, "tag": "RECT-A001"},
)
solar_a, _ = Asset.objects.get_or_create(
    name="Solar Array A",
    location=loc_a,
    defaults={"asset_category": cat_solar, "status": Asset.STATUS_ACTIVE, "tag": "SOL-A001"},
)
janitorial_a, _ = Asset.objects.get_or_create(
    name="Site Janitorial — Victoria Island Alpha",
    location=loc_a,
    defaults={"asset_category": cat_janitorial, "status": Asset.STATUS_ACTIVE, "tag": "JAN-A001"},
)

print("Seeding assets at Station B...")
gen_b, _ = Asset.objects.get_or_create(
    name="Generator Set B",
    location=loc_b,
    defaults={"asset_category": cat_gen, "status": Asset.STATUS_ACTIVE, "tag": "GEN-B001"},
)
battery_b, _ = Asset.objects.get_or_create(
    name="Battery Bank",
    location=loc_b,
    defaults={"asset_category": cat_battery, "status": Asset.STATUS_ACTIVE, "tag": "BAT-B001"},
)
dc_b, _ = Asset.objects.get_or_create(
    name="DC Distribution Board B",
    location=loc_b,
    defaults={"asset_category": cat_dc, "status": Asset.STATUS_ACTIVE, "tag": "DC-B001"},
)
ac_elec_b, _ = Asset.objects.get_or_create(
    name="AC Distribution Board B",
    location=loc_b,
    defaults={"asset_category": cat_ac_elec, "status": Asset.STATUS_ACTIVE, "tag": "ACE-B001"},
)
janitorial_b, _ = Asset.objects.get_or_create(
    name="Site Janitorial — Lekki Phase 1 Beta",
    location=loc_b,
    defaults={"asset_category": cat_janitorial, "status": Asset.STATUS_ACTIVE, "tag": "JAN-B001"},
)

print("Seeding technician user...")
tech, created = Personnel.objects.get_or_create(username="tech1")
if created:
    tech.set_password("tech1pass")
    tech.first_name = "Chidi"
    tech.last_name = "Obi"
tech.role = role_tech
tech.save()
tech.stations.set([station_a, station_b])
print(f"  tech1 stations: {list(tech.stations.values_list('site_id', flat=True))}")

print("Seeding today's work orders...")
wo_a, wo_a_created = WorkOrder.objects.get_or_create(
    base_station=station_a,
    type=WorkOrder.TYPE_PREVENTIVE,
    due_date=today,
    defaults={
        "status": WorkOrder.STATUS_IN_PROGRESS,
        "priority": WorkOrder.PRIORITY_MEDIUM,
        "assigned_technician": tech,
        "started_at": now - timezone.timedelta(hours=1),
    },
)
if wo_a_created:
    print(f"  Created WO for {station_a.site_id}")

wo_b, wo_b_created = WorkOrder.objects.get_or_create(
    base_station=station_b,
    type=WorkOrder.TYPE_PREVENTIVE,
    due_date=today,
    defaults={
        "status": WorkOrder.STATUS_OPEN,
        "priority": WorkOrder.PRIORITY_MEDIUM,
        "assigned_technician": tech,
    },
)
if wo_b_created:
    print(f"  Created WO for {station_b.site_id}")

print("Seeding inspection response for Generator Set A (partially complete)...")
ir_gen, ir_created = InspectionResponse.objects.get_or_create(
    work_order=wo_a,
    asset=gen_a,
    defaults={"issues_found": True, "done": True, "comments": "Oil level was low — topped up."},
)
if ir_created:
    # Seed checklist responses
    questions = PMQuestion.objects.filter(task_template=gen_checklist)
    for i, q in enumerate(questions):
        WorkOrderChecklistResponse.objects.get_or_create(
            inspection_response=ir_gen, question=q,
            defaults={"checked": i < 4},  # first 4 checked
        )
    # Add condition and issue
    oil_leak = Condition.objects.filter(name="Oil leak detected", asset_category=cat_gen).first()
    if oil_leak:
        ir_gen.conditions.add(oil_leak)
    Issue.objects.get_or_create(
        inspection_response=ir_gen,
        description="Oil level critically low — refill required",
        defaults={"severity": Issue.SEVERITY_HIGH},
    )
    print(f"  Created IR for {gen_a.name}")

print("Seeding alarms...")
alarm_open, _ = Alarm.objects.get_or_create(
    asset=rect_a,
    resolved_at__isnull=True,
    defaults={"raised_at": now - timezone.timedelta(hours=2)},
)

alarm_resolved, _ = Alarm.objects.get_or_create(
    asset=battery_b,
    resolved_at__isnull=False,
    defaults={
        "raised_at": now - timezone.timedelta(hours=4),
        "resolved_at": now - timezone.timedelta(hours=1),
        "resolved_by": tech,
    },
)
AlarmNote.objects.get_or_create(
    alarm=alarm_resolved,
    defaults={"text": "Battery temperature normalised after cooling."},
)

print("Seeding diesel vendor and parts...")
diesel_supplier, _ = Vendor.objects.get_or_create(
    name="Lagos Fuel Depot",
    defaults={"type": Vendor.TYPE_SUPPLIER, "phone_number": "08012345678"},
)
part_vendor, _ = Vendor.objects.get_or_create(
    name="AllParts Nigeria",
    defaults={"type": Vendor.TYPE_SUPPLIER, "phone_number": "08087654321"},
)
oil_filter, _ = Part.objects.get_or_create(
    sku="OF-1001", defaults={"name": "Generator Oil Filter", "vendor": part_vendor, "unit_cost": "3500.00"},
)
ac_filter, _ = Part.objects.get_or_create(
    sku="AF-2002", defaults={"name": "AC Air Filter", "vendor": part_vendor, "unit_cost": "1800.00"},
)

print("Seeding diesel delivery and meter readings...")
DieselDelivery.objects.get_or_create(
    base_station=station_a,
    delivered_at=timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time().replace(hour=8))),
    defaults={
        "vendor": diesel_supplier,
        "quantity_litres": 200,
        "tank_level_before": 150,
        "tank_level_after": 1500,
        "recorded_by": tech,
        "notes": "Routine top-up delivery.",
    },
)
MeterReading.objects.get_or_create(
    asset=gen_a,
    reading_type=MeterReading.TYPE_RUN_HOURS,
    date=today,
    defaults={"value": 12480, "unit": MeterReading.UNIT_HOURS, "work_order": wo_a, "recorded_by": tech},
)
MeterReading.objects.get_or_create(
    asset=gen_a,
    reading_type=MeterReading.TYPE_DIESEL_LEVEL,
    date=today,
    defaults={"value": 1500, "unit": MeterReading.UNIT_MM, "work_order": wo_a, "recorded_by": tech},
)

print("Seeding part request and usage...")
PartRequest.objects.get_or_create(
    part=oil_filter,
    base_station=station_a,
    defaults={
        "work_order": wo_a,
        "asset": gen_a,
        "quantity": 2,
        "reason": "Oil filter due for replacement during PM.",
        "requested_by": tech,
    },
)
PartUsage.objects.get_or_create(
    work_order=wo_a,
    asset=gen_a,
    part=oil_filter,
    defaults={
        "qty_used": 1,
        "notes": "Replaced during routine PM — old filter was clogged.",
        "recorded_by": tech,
    },
)

print("Seeding safety report...")
SafetyReport.objects.get_or_create(
    base_station=station_a,
    description="Loose cable trunking cover near generator bay — trip hazard.",
    defaults={
        "work_order": wo_a,
        "type": SafetyReport.TYPE_HAZARD,
        "severity": SafetyReport.SEVERITY_MEDIUM,
        "reported_by": tech,
    },
)

print("\nDone! Summary:")
print(f"  Stations: {BaseStation.objects.count()}")
print(f"  Assets:   {Asset.objects.count()}")
print(f"  Work orders (today): {WorkOrder.objects.filter(due_date=today).count()}")
print(f"  Alarms:   {Alarm.objects.count()}")
print(f"  Diesel deliveries: {DieselDelivery.objects.count()}")
print(f"  Part requests: {PartRequest.objects.count()}")
print(f"  Part usages: {PartUsage.objects.count()}")
print(f"  Safety reports: {SafetyReport.objects.count()}")
print(f"  Tech user: tech1 / tech1pass")
