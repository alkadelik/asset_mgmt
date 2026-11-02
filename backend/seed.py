"""
Run with: python manage.py shell < seed.py
Creates reference data only (roles, users, regions/clusters/teams, stations, assets,
the nine Form 1a asset types with their checklists and defects, colour-band settings, parts, vendors, opening regional stock, today's scheduled work
orders). No maintenance, alarms, diesel, safety, part requests or usage.
Safe to re-run — uses get_or_create throughout.
"""
import django
django.setup()

from django.utils import timezone

from assets import app_settings
from assets.reference_data import load_asset_types
from assets.models import (
    Region, ClusterGroup, Cluster, Client, BaseStation, Location,
    AssetCategory, Asset, Condition, Role, Personnel, ClusterTeam,
    PMCategory, AssetCheckList, PMQuestion,
    WorkOrder, Part, PartStock, Setting, StockMovement, Vendor,
)

today = timezone.localdate()

print("Seeding roles...")
role_tech, _ = Role.objects.get_or_create(name=Role.FIELD_TEAM)
role_lead, _ = Role.objects.get_or_create(name=Role.TEAM_LEAD)
role_rm, _ = Role.objects.get_or_create(name=Role.REGIONAL_MANAGER)
role_cm, _ = Role.objects.get_or_create(name=Role.CLUSTER_MANAGER)

print("Seeding org hierarchy...")
region, _ = Region.objects.get_or_create(name="South West")
cg, _ = ClusterGroup.objects.get_or_create(region=region, name="Lagos Cluster Group")
cluster, _ = Cluster.objects.get_or_create(cluster_group=cg, name="Lagos Island")

region_nc, _ = Region.objects.get_or_create(name="North Central")
cg_abuja, _ = ClusterGroup.objects.get_or_create(region=region_nc, name="Abuja Cluster Group")
cluster_abuja, _ = Cluster.objects.get_or_create(cluster_group=cg_abuja, name="Abuja Central")

region_ss, _ = Region.objects.get_or_create(name="South South")
cg_ph, _ = ClusterGroup.objects.get_or_create(region=region_ss, name="Port Harcourt Cluster Group")
cluster_ph, _ = Cluster.objects.get_or_create(cluster_group=cg_ph, name="Port Harcourt Central")

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

station_c, _ = BaseStation.objects.get_or_create(
    site_id="LOS-C023",
    defaults={
        "cluster": cluster,
        "name": "Ikeja City Mall Gamma",
        "address": "Obafemi Awolowo Way, Ikeja, Lagos",
        "state": "Lagos",
        "site_classification": BaseStation.CLASS_PLATINUM,
        "manager": manager,
    },
)
station_c.clients.set([mtn, airtel])

station_d, _ = BaseStation.objects.get_or_create(
    site_id="ABJ-D045",
    defaults={
        "cluster": cluster_abuja,
        "name": "Wuse II Delta",
        "address": "Aminu Kano Crescent, Wuse II, Abuja",
        "state": "FCT",
        "site_classification": BaseStation.CLASS_PLATINUM,
        "manager": manager,
    },
)
station_d.clients.set([airtel])

station_e, _ = BaseStation.objects.get_or_create(
    site_id="PHC-E067",
    defaults={
        "cluster": cluster_ph,
        "name": "GRA Phase 2 Epsilon",
        "address": "Aba Road, GRA Phase 2, Port Harcourt",
        "state": "Rivers",
        "site_classification": BaseStation.CLASS_PLATINUM,
        "manager": manager,
    },
)
station_e.clients.set([mtn])

print("Seeding locations...")
loc_a, _ = Location.objects.get_or_create(
    base_station=station_a, name="Equipment Room A", defaults={"parent_location": None}
)
loc_b, _ = Location.objects.get_or_create(
    base_station=station_b, name="Equipment Room B", defaults={"parent_location": None}
)
loc_c, _ = Location.objects.get_or_create(
    base_station=station_c, name="Equipment Room C", defaults={"parent_location": None}
)
loc_d, _ = Location.objects.get_or_create(
    base_station=station_d, name="Equipment Room D", defaults={"parent_location": None}
)
loc_e, _ = Location.objects.get_or_create(
    base_station=station_e, name="Equipment Room E", defaults={"parent_location": None}
)

print("Seeding asset types, checklists and defects...")
categories = load_asset_types(AssetCategory, Condition, AssetCheckList, PMQuestion)

print("Seeding settings...")
Setting.objects.get_or_create(key=app_settings.COLOUR_BANDS, defaults={"value": app_settings.DEFAULTS[app_settings.COLOUR_BANDS]})

# Each station gets a different mix, so the ratings see stations with and without a
# generator or tank. (type, asset name, tag)
STATION_ASSETS = {
    "A": [
        ("Janitorial Services", "Site Janitorial — Victoria Island Alpha", "JAN-A001"),
        ("Diesel Generator", "Generator Set A", "GEN-A001"),
        ("Diesel Tank", "Diesel Tank A", "TNK-A001"),
        ("AC Control Panel", "AC Control Panel A", "ACP-A001"),
        ("DC Control Panel", "DC Control Panel A", "DCP-A001"),
        ("Tower Structure", "Tower A", "TWR-A001"),
    ],
    "B": [
        ("Janitorial Services", "Site Janitorial — Lekki Phase 1 Beta", "JAN-B001"),
        ("Diesel Generator", "Generator Set B", "GEN-B001"),
        ("Diesel Tank", "Diesel Tank B", "TNK-B001"),
        ("Solar Panels and Structure", "Solar Array B", "SOL-B001"),
        ("Battery Packs", "Battery Packs B", "BAT-B001"),
        ("DC Control Panel", "DC Control Panel B", "DCP-B001"),
    ],
    "C": [
        ("Janitorial Services", "Site Janitorial — Ikeja City Mall Gamma", "JAN-C001"),
        ("Diesel Generator", "Generator Set C", "GEN-C001"),
        ("Diesel Tank", "Diesel Tank C", "TNK-C001"),
        ("Transformer", "Transformer C", "TRF-C001"),
        ("AC Control Panel", "AC Control Panel C", "ACP-C001"),
        ("DC Control Panel", "DC Control Panel C", "DCP-C001"),
    ],
    # No generator or tank: grid and solar only.
    "D": [
        ("Janitorial Services", "Site Janitorial — Wuse II Delta", "JAN-D001"),
        ("Solar Panels and Structure", "Solar Array D", "SOL-D001"),
        ("Battery Packs", "Battery Packs D", "BAT-D001"),
        ("Transformer", "Transformer D", "TRF-D001"),
        ("AC Control Panel", "AC Control Panel D", "ACP-D001"),
        ("DC Control Panel", "DC Control Panel D", "DCP-D001"),
        ("Tower Structure", "Tower D", "TWR-D001"),
    ],
    # A generator but no tank.
    "E": [
        ("Janitorial Services", "Site Janitorial — GRA Phase 2 Epsilon", "JAN-E001"),
        ("Diesel Generator", "Generator Set E", "GEN-E001"),
        ("AC Control Panel", "AC Control Panel E", "ACP-E001"),
        ("Tower Structure", "Tower E", "TWR-E001"),
    ],
}
LOCATIONS = {"A": loc_a, "B": loc_b, "C": loc_c, "D": loc_d, "E": loc_e}
for key, rows in STATION_ASSETS.items():
    print(f"Seeding assets at Station {key}...")
    for type_name, asset_name, tag in rows:
        Asset.objects.get_or_create(
            name=asset_name,
            location=LOCATIONS[key],
            defaults={"asset_category": categories[type_name], "status": Asset.STATUS_ACTIVE, "tag": tag},
        )

team_a, _ = ClusterTeam.objects.get_or_create(name="Lagos Island Team A", defaults={"cluster": cluster})
tech, created = Personnel.objects.get_or_create(username="tech1")
if created:
    tech.set_password("tech1pass")
    tech.first_name = "Chidi"
    tech.last_name = "Obi"
tech.role = role_tech
tech.cluster_team = team_a
tech.save()

print("Seeding Cluster Manager user...")
cluster_manager, created = Personnel.objects.get_or_create(username="cm1")
if created:
    cluster_manager.set_password("cm1pass")
    cluster_manager.first_name = "Bamidele"
    cluster_manager.last_name = "Adebiyi"
cluster_manager.role = role_cm
cluster_manager.cluster = cluster
cluster_manager.save()
tech.stations.set([station_a, station_b, station_c, station_d, station_e])
print(f"  tech1 stations: {list(tech.stations.values_list('site_id', flat=True))}")

print("Seeding today's work orders...")
wo_a, wo_a_created = WorkOrder.objects.get_or_create(
    base_station=station_a,
    type=WorkOrder.TYPE_PREVENTIVE,
    due_date=today,
    defaults={
        "status": WorkOrder.STATUS_OPEN,
        "priority": WorkOrder.PRIORITY_MEDIUM,
        "assigned_to": tech,
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
        "assigned_to": tech,
    },
)
if wo_b_created:
    print(f"  Created WO for {station_b.site_id}")

wo_c, wo_c_created = WorkOrder.objects.get_or_create(
    base_station=station_c,
    type=WorkOrder.TYPE_PREVENTIVE,
    due_date=today,
    defaults={
        "status": WorkOrder.STATUS_OPEN,
        "priority": WorkOrder.PRIORITY_MEDIUM,
        "assigned_to": tech,
    },
)
if wo_c_created:
    print(f"  Created WO for {station_c.site_id}")

wo_d, wo_d_created = WorkOrder.objects.get_or_create(
    base_station=station_d,
    type=WorkOrder.TYPE_PREVENTIVE,
    due_date=today,
    defaults={
        "status": WorkOrder.STATUS_OPEN,
        "priority": WorkOrder.PRIORITY_HIGH,
        "assigned_to": tech,
    },
)
if wo_d_created:
    print(f"  Created WO for {station_d.site_id}")

wo_e, wo_e_created = WorkOrder.objects.get_or_create(
    base_station=station_e,
    type=WorkOrder.TYPE_PREVENTIVE,
    due_date=today,
    defaults={
        "status": WorkOrder.STATUS_OPEN,
        "priority": WorkOrder.PRIORITY_MEDIUM,
        "assigned_to": tech,
    },
)
if wo_e_created:
    print(f"  Created WO for {station_e.site_id}")

print("Seeding vendors and parts...")
diesel_supplier, _ = Vendor.objects.get_or_create(
    name="Lagos Fuel Depot",
    defaults={"type": Vendor.TYPE_SUPPLIER, "phone_number": "08012345678"},
)
part_vendor, _ = Vendor.objects.get_or_create(
    name="AllParts Nigeria",
    defaults={"type": Vendor.TYPE_SUPPLIER, "phone_number": "08087654321"},
)
oil_filter, _ = Part.objects.get_or_create(
    sku="OF-1001", defaults={"name": "Generator Oil Filter", "vendor": part_vendor, "unit_cost": "3500.00",
                             "kind": Part.KIND_CONSUMABLE},
)
ac_filter, _ = Part.objects.get_or_create(
    sku="AF-2002", defaults={"name": "AC Air Filter", "vendor": part_vendor, "unit_cost": "1800.00",
                             "kind": Part.KIND_CONSUMABLE},
)

print("Seeding regional store stock...")
for part, qty in ((oil_filter, 20), (ac_filter, 10)):
    if not PartStock.objects.filter(part=part, region=region).exists():
        PartStock.objects.create(part=part, region=region, qty=qty, reorder_threshold=5)
        StockMovement.objects.create(
            part=part, region=region, change=qty, reason=StockMovement.REASON_ADJUSTMENT,
            note="Opening stock (seed data).",
        )

print("\nDone! Summary:")
print(f"  Stations: {BaseStation.objects.count()}")
print(f"  Assets:   {Asset.objects.count()}")
print(f"  Work orders (today, scheduled): {WorkOrder.objects.filter(due_date=today).count()}")
print(f"  Field Team user: tech1 / tech1pass (Lagos Island Team A)")
print(f"  Cluster Manager user: cm1 / cm1pass (Lagos Island)")
