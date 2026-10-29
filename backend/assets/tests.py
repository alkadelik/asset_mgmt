import io
import shutil
import tempfile
import uuid

import datetime

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from .models import (
    Alarm, AlarmNote, Asset, AssetCategory, AssetCheckList, BaseStation,
    Cluster, ClusterGroup, Condition, DieselDelivery, InspectionResponse,
    Issue, Location, MeterReading, Notification, Part, PartDelivery, PartRequest, PartRequestLine,
    PartStock, PartUsage, PMQuestion, Personnel, Region, Role, SafetyReport, StockMovement, Vendor,
    WorkOrder, WorkOrderChecklistResponse, ClusterTeam,
)
from . import parts as parts_rules


def make_jpeg(name='part.jpg', fmt='JPEG', size=(64, 48)):
    buffer = io.BytesIO()
    Image.new('RGB', size, (120, 80, 40)).save(buffer, format=fmt)
    content_type = 'image/jpeg' if fmt == 'JPEG' else 'image/png'
    return SimpleUploadedFile(name, buffer.getvalue(), content_type=content_type)


class TechnicianAPITestCase(APITestCase):
    """Base fixture: one technician assigned to one base station with one asset."""

    def setUp(self):
        role_tech = Role.objects.get_or_create(name=Role.FIELD_TEAM)[0]
        region = Region.objects.create(name="Test Region")
        cluster_group = ClusterGroup.objects.create(region=region, name="Test Cluster Group")
        cluster = Cluster.objects.create(cluster_group=cluster_group, name="Test Cluster")
        self.station = BaseStation.objects.create(
            cluster=cluster,
            name="Test Station",
            address="1 Test Street",
            site_id="TST-001",
            site_classification=BaseStation.CLASS_PLATINUM,
        )
        self.location = Location.objects.create(base_station=self.station, name="Equipment Room")
        self.category = AssetCategory.objects.create(name="Generator")
        self.asset = Asset.objects.create(
            asset_category=self.category, location=self.location, name="Generator Set 1",
        )

        self.tech = Personnel.objects.create_user(username="tech1", password="pass1234")
        self.tech.role = role_tech
        self.tech.save()
        self.tech.stations.set([self.station])

        self.client.force_authenticate(user=self.tech)


class MeterReadingTests(TechnicianAPITestCase):
    def test_create_run_hours_reading(self):
        response = self.client.post('/api/meter-readings/', {
            'asset': str(self.asset.id),
            'reading_type': MeterReading.TYPE_RUN_HOURS,
            'value': 1000,
            'unit': MeterReading.UNIT_HOURS,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(MeterReading.objects.count(), 1)
        reading = MeterReading.objects.first()
        self.assertEqual(reading.recorded_by, self.tech)
        self.assertEqual(reading.asset, self.asset)

    def test_create_diesel_level_reading(self):
        response = self.client.post('/api/meter-readings/', {
            'asset': str(self.asset.id),
            'reading_type': MeterReading.TYPE_DIESEL_LEVEL,
            'value': 75,
            'unit': MeterReading.UNIT_LITRES,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_missing_fields_rejected(self):
        response = self.client.post('/api/meter-readings/', {'asset': str(self.asset.id)})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_reading_type_rejected(self):
        response = self.client.post('/api/meter-readings/', {
            'asset': str(self.asset.id), 'reading_type': 'bogus', 'value': 1, 'unit': MeterReading.UNIT_HOURS,
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_scoped_to_technician_stations(self):
        MeterReading.objects.create(
            asset=self.asset, reading_type=MeterReading.TYPE_RUN_HOURS,
            date=timezone.localdate(), value=500, unit=MeterReading.UNIT_HOURS,
        )
        response = self.client.get('/api/meter-readings/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_run_hours_lower_than_previous_rejected(self):
        MeterReading.objects.create(
            asset=self.asset, reading_type=MeterReading.TYPE_RUN_HOURS,
            date=timezone.localdate(), value=1000, unit=MeterReading.UNIT_HOURS,
        )
        response = self.client.post('/api/meter-readings/', {
            'asset': str(self.asset.id), 'reading_type': MeterReading.TYPE_RUN_HOURS,
            'value': 999, 'unit': MeterReading.UNIT_HOURS,
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_run_hours_equal_or_higher_than_previous_accepted(self):
        MeterReading.objects.create(
            asset=self.asset, reading_type=MeterReading.TYPE_RUN_HOURS,
            date=timezone.localdate(), value=1000, unit=MeterReading.UNIT_HOURS,
        )
        response = self.client.post('/api/meter-readings/', {
            'asset': str(self.asset.id), 'reading_type': MeterReading.TYPE_RUN_HOURS,
            'value': 1000, 'unit': MeterReading.UNIT_HOURS,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_diesel_level_higher_than_previous_rejected(self):
        MeterReading.objects.create(
            asset=self.asset, reading_type=MeterReading.TYPE_DIESEL_LEVEL,
            date=timezone.localdate(), value=500, unit=MeterReading.UNIT_MM,
        )
        response = self.client.post('/api/meter-readings/', {
            'asset': str(self.asset.id), 'reading_type': MeterReading.TYPE_DIESEL_LEVEL,
            'value': 501, 'unit': MeterReading.UNIT_MM,
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_diesel_level_lower_than_previous_accepted(self):
        MeterReading.objects.create(
            asset=self.asset, reading_type=MeterReading.TYPE_DIESEL_LEVEL,
            date=timezone.localdate(), value=500, unit=MeterReading.UNIT_MM,
        )
        response = self.client.post('/api/meter-readings/', {
            'asset': str(self.asset.id), 'reading_type': MeterReading.TYPE_DIESEL_LEVEL,
            'value': 480, 'unit': MeterReading.UNIT_MM,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class DieselDeliveryTests(TechnicianAPITestCase):
    def setUp(self):
        super().setUp()
        self.vendor = Vendor.objects.create(name="Test Fuel Co", type=Vendor.TYPE_SUPPLIER)

    def test_create_delivery(self):
        response = self.client.post('/api/diesel-deliveries/', {
            'base_station': str(self.station.id),
            'vendor': str(self.vendor.id),
            'quantity_litres': 150,
            'tank_level_before': 10,
            'tank_level_after': 80,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        delivery = DieselDelivery.objects.get()
        self.assertEqual(delivery.recorded_by, self.tech)
        self.assertEqual(delivery.quantity_litres, 150)

    def test_missing_fields_rejected(self):
        response = self.client.post('/api/diesel-deliveries/', {'base_station': str(self.station.id)})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_scoped_to_technician_stations(self):
        DieselDelivery.objects.create(
            base_station=self.station, quantity_litres=100, delivered_at=timezone.now(),
        )
        response = self.client.get('/api/diesel-deliveries/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_delivery_updates_generators_diesel_level_reading(self):
        # self.asset (base fixture) is category "Generator" at self.station.
        MeterReading.objects.create(
            asset=self.asset, reading_type=MeterReading.TYPE_DIESEL_LEVEL,
            date=timezone.localdate() - timezone.timedelta(days=1), value=100, unit=MeterReading.UNIT_MM,
        )
        response = self.client.post('/api/diesel-deliveries/', {
            'base_station': str(self.station.id), 'quantity_litres': 200,
            'tank_level_before': 100, 'tank_level_after': 1500,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        latest = MeterReading.objects.filter(
            asset=self.asset, reading_type=MeterReading.TYPE_DIESEL_LEVEL,
        ).order_by('-date', '-created').first()
        self.assertEqual(latest.value, 1500)
        self.assertEqual(latest.date, timezone.localdate())

    def test_delivery_without_tank_level_after_does_not_create_reading(self):
        response = self.client.post('/api/diesel-deliveries/', {
            'base_station': str(self.station.id), 'quantity_litres': 200,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(MeterReading.objects.count(), 0)


class PartsFixtureMixin:
    """A cluster team (with the base fixture's technician in it), a Team Lead, a Cluster Manager
    and a Regional Manager, plus two parts with regional store stock."""

    def setUp(self):
        super().setUp()
        self.cluster = self.station.cluster
        self.region = self.cluster.cluster_group.region
        self.team = ClusterTeam.objects.create(name="Team A", cluster=self.cluster)
        self.tech.cluster_team = self.team
        self.tech.save()
        self.lead = Personnel.objects.create_user(
            username="lead1", password="pass1234", cluster_team=self.team,
            role=Role.objects.get_or_create(name=Role.TEAM_LEAD)[0],
        )
        self.cluster_manager = Personnel.objects.create_user(
            username="cm1", password="pass1234", cluster=self.cluster,
            role=Role.objects.get_or_create(name=Role.CLUSTER_MANAGER)[0],
        )
        from .models import Station
        regional_office = Station.objects.create(type=Station.TYPE_REGION, region=self.region, address="1 Region Rd")
        self.regional_manager = Personnel.objects.create_user(
            username="rm1", password="pass1234", station=regional_office,
            role=Role.objects.get_or_create(name=Role.REGIONAL_MANAGER)[0],
        )
        self.vendor = Vendor.objects.create(name="Parts Co", type=Vendor.TYPE_SUPPLIER)
        self.part = Part.objects.create(
            vendor=self.vendor, name="Oil Filter", sku="OF-1", unit_cost="10.00", kind=Part.KIND_CONSUMABLE,
        )
        self.part2 = Part.objects.create(vendor=self.vendor, name="Fan Belt", sku="FB-1", unit_cost="20.00")
        parts_rules.adjust_stock(self.part, 10, region=self.region, note="Opening stock")
        parts_rules.adjust_stock(self.part2, 4, region=self.region, note="Opening stock")
        self.work_order = WorkOrder.objects.create(base_station=self.station, type=WorkOrder.TYPE_PREVENTIVE)

    def stock(self, part, region=None, team=None):
        lookup = {'region': region} if region else {'cluster_team': team}
        return PartStock.objects.filter(part=part, **lookup).values_list('qty', flat=True).first() or 0

    def make_request(self, lines=None, **extra):
        payload = {
            'base_station': str(self.station.id),
            'lines': lines or [{'part': str(self.part.id), 'quantity': 3, 'required_date': '2099-01-10'}],
            **extra,
        }
        return self.client.post('/api/part-requests/', payload, format='json')

    def approved_line(self, quantity=3, part=None):
        resp = self.make_request([{'part': str((part or self.part).id), 'quantity': quantity,
                                   'required_date': '2099-01-10'}])
        line = PartRequestLine.objects.get(pk=resp.data['lines'][0]['id'])
        parts_rules.approve_line(line, by=self.regional_manager)
        line.refresh_from_db()
        return line


class PartRequestTests(PartsFixtureMixin, TechnicianAPITestCase):
    def test_create_request_with_several_lines(self):
        response = self.make_request([
            {'part': str(self.part.id), 'quantity': 3, 'required_date': '2099-01-10'},
            {'part': str(self.part2.id), 'quantity': 1, 'required_date': '2099-01-12'},
        ], notes='Due for replacement')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        req = PartRequest.objects.get()
        self.assertEqual(req.requested_by, self.tech)
        self.assertEqual(req.cluster_team, self.team)
        self.assertEqual(req.team_lead, self.lead)
        self.assertEqual(req.lines.count(), 2)
        self.assertEqual(set(req.lines.values_list('status', flat=True)), {PartRequestLine.STATUS_REQUESTED})
        self.assertEqual(response.data['team_lead']['name'], 'lead1')

    def test_backdated_line_is_flagged_but_allowed(self):
        yesterday = (timezone.localdate() - datetime.timedelta(days=1)).isoformat()
        response = self.make_request([{'part': str(self.part.id), 'quantity': 1, 'required_date': yesterday}])
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['lines'][0]['is_backdated'])

    def test_same_part_twice_rejected(self):
        line = {'part': str(self.part.id), 'quantity': 1, 'required_date': '2099-01-10'}
        response = self.make_request([line, line])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(PartRequest.objects.count(), 0)

    def test_bad_line_rejects_whole_request(self):
        response = self.make_request([
            {'part': str(self.part.id), 'quantity': 1, 'required_date': '2099-01-10'},
            {'part': str(self.part2.id), 'quantity': 0, 'required_date': '2099-01-10'},
        ])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(PartRequest.objects.count(), 0)

    def test_requester_must_be_in_a_team(self):
        self.tech.cluster_team = None
        self.tech.save()
        response = self.make_request()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_new_request_notifies_cluster_and_regional_managers(self):
        self.make_request()
        recipients = set(Notification.objects.filter(event=Notification.EVENT_NEW_REQUEST)
                         .values_list('recipient__username', flat=True))
        self.assertEqual(recipients, {'cm1', 'rm1'})

    def test_list_only_own_requests(self):
        self.make_request()
        other = Personnel.objects.create_user(username="tech2", password="pass1234", cluster_team=self.team)
        self.client.force_authenticate(user=other)
        response = self.client.get('/api/part-requests/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_cancel_while_all_requested(self):
        req_id = self.make_request().data['id']
        response = self.client.post(f'/api/part-requests/{req_id}/cancel/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['lines'][0]['status'], PartRequestLine.STATUS_CANCELLED)

    def test_cancel_refused_once_a_line_is_decided(self):
        line = self.approved_line()
        response = self.client.post(f'/api/part-requests/{line.request_id}/cancel/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class RequestLifecycleTests(PartsFixtureMixin, TechnicianAPITestCase):
    def test_decline_needs_reason_and_notifies(self):
        resp = self.make_request()
        line = PartRequestLine.objects.get(pk=resp.data['lines'][0]['id'])
        with self.assertRaises(parts_rules.PartsError):
            parts_rules.decline_line(line, by=self.regional_manager, reason='  ')
        parts_rules.decline_line(line, by=self.regional_manager, reason='Not on the approved list')
        line.refresh_from_db()
        self.assertEqual(line.status, PartRequestLine.STATUS_DECLINED)
        self.assertEqual(
            set(Notification.objects.filter(event=Notification.EVENT_LINE_DECLINED)
                .values_list('recipient__username', flat=True)),
            {'tech1', 'lead1'},
        )

    def test_delivery_then_receipt_moves_stock_and_completes(self):
        line = self.approved_line(quantity=3)
        delivery = parts_rules.record_delivery(line, by=self.regional_manager, quantity=3)
        line.refresh_from_db()
        self.assertEqual(line.status, PartRequestLine.STATUS_PENDING)
        self.assertEqual(self.stock(self.part, region=self.region), 10)  # nothing moves until both confirm

        response = self.client.post(f'/api/part-deliveries/{delivery.id}/confirm-received/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['lines'][0]['status'], PartRequestLine.STATUS_DELIVERED)
        self.assertEqual(self.stock(self.part, region=self.region), 7)
        self.assertEqual(self.stock(self.part, team=self.team), 3)
        self.assertEqual(StockMovement.objects.filter(delivery=delivery).count(), 2)
        self.assertIsNotNone(response.data['lines'][0]['deliveries'][0]['received_at'])

    def test_receipt_first_then_marked_delivered(self):
        line = self.approved_line(quantity=2)
        response = self.client.post(f'/api/part-request-lines/{line.id}/receipts/', {'quantity': 2})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        line.refresh_from_db()
        self.assertEqual(line.status, PartRequestLine.STATUS_PENDING)
        delivery = line.deliveries.get()
        parts_rules.mark_delivered(delivery, by=self.regional_manager)
        line.refresh_from_db()
        self.assertEqual(line.status, PartRequestLine.STATUS_DELIVERED)
        self.assertEqual(self.stock(self.part, team=self.team), 2)

    def test_partial_delivery_returns_line_to_approved(self):
        line = self.approved_line(quantity=3)
        delivery = parts_rules.record_delivery(line, by=self.regional_manager, quantity=2)
        parts_rules.confirm_received(delivery, by=self.tech)
        line.refresh_from_db()
        self.assertEqual(line.status, PartRequestLine.STATUS_APPROVED)
        self.assertEqual(line.delivered_qty, 2)
        with self.assertRaises(parts_rules.PartsError):
            parts_rules.record_delivery(line, by=self.regional_manager, quantity=2)  # only 1 outstanding

    def test_close_short(self):
        line = self.approved_line(quantity=3)
        delivery = parts_rules.record_delivery(line, by=self.regional_manager, quantity=2)
        parts_rules.confirm_received(delivery, by=self.tech)
        parts_rules.close_short(line, by=self.regional_manager)
        line.refresh_from_db()
        self.assertEqual(line.status, PartRequestLine.STATUS_DELIVERED)
        self.assertTrue(line.closed_short)
        self.assertEqual(line.shortfall, 1)

    def test_close_short_refused_with_nothing_delivered(self):
        line = self.approved_line(quantity=3)
        with self.assertRaises(parts_rules.PartsError):
            parts_rules.close_short(line, by=self.regional_manager)

    def test_delivery_cannot_exceed_regional_store(self):
        line = self.approved_line(quantity=5, part=self.part2)  # store holds 4
        with self.assertRaises(parts_rules.PartsError):
            parts_rules.record_delivery(line, by=self.regional_manager, quantity=5)
        delivery = parts_rules.record_delivery(line, by=self.regional_manager, quantity=4)
        self.assertEqual(delivery.quantity, 4)

    def test_promised_stock_is_held_for_pending_deliveries(self):
        first = self.approved_line(quantity=3, part=self.part2)
        parts_rules.record_delivery(first, by=self.regional_manager, quantity=3)
        self.make_request([{'part': str(self.part2.id), 'quantity': 2, 'required_date': '2099-02-01'}])
        second = PartRequestLine.objects.filter(part=self.part2, status=PartRequestLine.STATUS_REQUESTED).get()
        parts_rules.approve_line(second, by=self.regional_manager)
        with self.assertRaises(parts_rules.PartsError):
            parts_rules.record_delivery(second, by=self.regional_manager, quantity=2)  # 4 held, 3 promised

    def test_cannot_deliver_unapproved_line(self):
        resp = self.make_request()
        line = PartRequestLine.objects.get(pk=resp.data['lines'][0]['id'])
        with self.assertRaises(parts_rules.PartsError):
            parts_rules.record_delivery(line, by=self.regional_manager, quantity=1)

    def test_confirm_twice_rejected(self):
        line = self.approved_line(quantity=1)
        delivery = parts_rules.record_delivery(line, by=self.regional_manager, quantity=1)
        self.client.post(f'/api/part-deliveries/{delivery.id}/confirm-received/')
        response = self.client.post(f'/api/part-deliveries/{delivery.id}/confirm-received/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.stock(self.part, team=self.team), 1)

    def test_one_team_lead_per_team(self):
        from django.core.exceptions import ValidationError
        second = Personnel(username="lead2", cluster_team=self.team,
                           role=Role.objects.get(name=Role.TEAM_LEAD))
        with self.assertRaises(ValidationError):
            second.clean()


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class PartUsageTests(PartsFixtureMixin, TechnicianAPITestCase):
    def post_usage(self, qty=1, photo=True, **extra):
        payload = {
            'work_order': str(self.work_order.id), 'asset': str(self.asset.id),
            'part': str(self.part.id), 'qty_used': qty, **extra,
        }
        if photo:
            payload['photo'] = make_jpeg() if photo is True else photo
        return self.client.post('/api/part-usages/', payload, format='multipart')

    def test_log_usage_with_photo_takes_team_stock(self):
        parts_rules.adjust_stock(self.part, 3, team=self.team, note='Count')
        response = self.post_usage(qty=2, notes='Old filter was clogged.', part_identifier='')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        usage = PartUsage.objects.get()
        self.assertEqual(usage.recorded_by, self.tech)
        self.assertEqual(usage.cluster_team, self.team)
        self.assertTrue(usage.photo.name.endswith(f'{usage.id}.jpg'))
        self.assertIn('/media/part_usages/', response.data['photo_url'])
        self.assertEqual(self.stock(self.part, team=self.team), 1)
        self.assertFalse(Notification.objects.filter(event=Notification.EVENT_ADDED_AT_SITE).exists())

    def test_shortfall_is_added_at_site(self):
        parts_rules.adjust_stock(self.part, 1, team=self.team, note='Count')
        self.post_usage(qty=3)
        self.assertEqual(self.stock(self.part, team=self.team), 0)
        added = StockMovement.objects.get(reason=StockMovement.REASON_ADDED_AT_SITE)
        self.assertEqual(added.change, 2)
        self.assertEqual(
            set(Notification.objects.filter(event=Notification.EVENT_ADDED_AT_SITE)
                .values_list('recipient__username', flat=True)),
            {'cm1', 'rm1'},
        )

    def test_photo_required(self):
        response = self.post_usage(photo=False)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(PartUsage.objects.count(), 0)

    @override_settings(PART_USAGE_PHOTO_REQUIRED=False)
    def test_photo_requirement_can_be_switched_off(self):
        response = self.post_usage(photo=False)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_non_jpeg_rejected(self):
        response = self.post_usage(photo=make_jpeg('part.png', fmt='PNG'))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @override_settings(PART_USAGE_PHOTO_MAX_BYTES=100)
    def test_oversized_photo_rejected(self):
        response = self.post_usage()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_fields_rejected(self):
        response = self.client.post('/api/part-usages/', {'work_order': str(self.work_order.id)})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_person_in_no_team_moves_no_stock(self):
        self.tech.cluster_team = None
        self.tech.save()
        response = self.post_usage()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(StockMovement.objects.filter(usage__isnull=False).exists())

    def test_list_scoped_to_technician_stations(self):
        PartUsage.objects.create(work_order=self.work_order, asset=self.asset, part=self.part, qty_used=2)
        response = self.client.get('/api/part-usages/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_list_filtered_by_asset(self):
        other_asset = Asset.objects.create(asset_category=self.category, location=self.location, name="Second asset")
        PartUsage.objects.create(work_order=self.work_order, asset=self.asset, part=self.part, qty_used=1)
        PartUsage.objects.create(work_order=self.work_order, asset=other_asset, part=self.part, qty_used=1)
        response = self.client.get(f'/api/part-usages/?asset={self.asset.id}')
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['asset']['id'], str(self.asset.id))

    def test_list_filtered_by_work_order(self):
        other_wo = WorkOrder.objects.create(base_station=self.station, type=WorkOrder.TYPE_PREVENTIVE)
        PartUsage.objects.create(work_order=self.work_order, asset=self.asset, part=self.part, qty_used=1)
        PartUsage.objects.create(work_order=other_wo, asset=self.asset, part=self.part, qty_used=1)
        response = self.client.get(f'/api/part-usages/?work_order={self.work_order.id}')
        self.assertEqual(len(response.data), 1)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ManagerListTests(PartsFixtureMixin, TechnicianAPITestCase):
    def setUp(self):
        super().setUp()
        other_cluster = Cluster.objects.create(cluster_group=self.cluster.cluster_group, name="Elsewhere")
        self.other_station = BaseStation.objects.create(
            cluster=other_cluster, name="Far Station", address="x", site_id="FAR-1",
            site_classification=BaseStation.CLASS_PLATINUM,
        )

    def test_requests_list_is_one_row_per_line_in_my_cluster(self):
        self.make_request([
            {'part': str(self.part.id), 'quantity': 3, 'required_date': '2099-01-10'},
            {'part': str(self.part2.id), 'quantity': 1, 'required_date': '2099-01-12'},
        ])
        self.client.post('/api/part-requests/', {
            'base_station': str(self.other_station.id),
            'lines': [{'part': str(self.part.id), 'quantity': 1, 'required_date': '2099-01-10'}],
        }, format='json')
        self.client.force_authenticate(user=self.cluster_manager)
        response = self.client.get('/api/manager/part-requests/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        row = response.data[0]
        for key in ('requested_date', 'part', 'base_station', 'requested_by', 'required_date', 'team_lead',
                    'quantity', 'status', 'pickup_location', 'pickup_date'):
            self.assertIn(key, row)
        self.assertEqual(row['base_station']['site_id'], 'TST-001')

    def test_requests_list_filters(self):
        self.make_request([
            {'part': str(self.part.id), 'quantity': 3, 'required_date': '2099-01-10'},
            {'part': str(self.part2.id), 'quantity': 1, 'required_date': '2099-01-12'},
        ])
        self.client.force_authenticate(user=self.cluster_manager)
        self.assertEqual(len(self.client.get(f'/api/manager/part-requests/?part={self.part2.id}').data), 1)
        self.assertEqual(len(self.client.get('/api/manager/part-requests/?status=approved').data), 0)

    def test_pickup_date_comes_from_receipt(self):
        line = self.approved_line(quantity=1)
        delivery = parts_rules.record_delivery(line, by=self.regional_manager, quantity=1)
        parts_rules.confirm_received(delivery, by=self.tech)
        self.client.force_authenticate(user=self.cluster_manager)
        row = self.client.get('/api/manager/part-requests/').data[0]
        self.assertIsNotNone(row['pickup_date'])
        self.assertEqual(row['delivered_qty'], 1)

    def test_usage_list_scoped_to_my_cluster(self):
        self.client.post('/api/part-usages/', {
            'work_order': str(self.work_order.id), 'asset': str(self.asset.id),
            'part': str(self.part.id), 'qty_used': 1, 'photo': make_jpeg(),
        }, format='multipart')
        far_wo = WorkOrder.objects.create(base_station=self.other_station, type=WorkOrder.TYPE_PREVENTIVE)
        PartUsage.objects.create(work_order=far_wo, asset=self.asset, part=self.part, qty_used=1)
        self.client.force_authenticate(user=self.cluster_manager)
        response = self.client.get('/api/manager/part-usages/')
        self.assertEqual(len(response.data), 1)
        row = response.data[0]
        self.assertEqual(row['recorded_by']['name'], 'tech1')
        self.assertIsNotNone(row['photo_url'])
        self.assertIn('part_identifier', row)

    def test_manager_without_cluster_sees_nothing(self):
        self.make_request()
        self.cluster_manager.cluster = None
        self.cluster_manager.save()
        self.client.force_authenticate(user=self.cluster_manager)
        self.assertEqual(self.client.get('/api/manager/part-requests/').data, [])

    def test_stock_by_team_and_cluster_total(self):
        team_b = ClusterTeam.objects.create(name="Team B", cluster=self.cluster)
        parts_rules.adjust_stock(self.part, 2, team=self.team, note='Count')
        parts_rules.adjust_stock(self.part, 5, team=team_b, note='Count')
        self.client.force_authenticate(user=self.cluster_manager)
        response = self.client.get('/api/manager/stock/')
        self.assertEqual(len(response.data['teams']), 2)
        self.assertEqual(response.data['totals'][0]['qty'], 7)

    def test_team_stock_for_field_team(self):
        parts_rules.adjust_stock(self.part, 2, team=self.team, note='Count')
        response = self.client.get('/api/team-stock/')
        self.assertEqual(response.data['cluster_team']['name'], 'Team A')
        self.assertEqual(response.data['items'][0]['qty'], 2)


class StockRuleTests(PartsFixtureMixin, TechnicianAPITestCase):
    def test_adjustment_needs_reason(self):
        with self.assertRaises(parts_rules.PartsError):
            parts_rules.adjust_stock(self.part, 1, region=self.region, note='')

    def test_cannot_go_below_zero(self):
        with self.assertRaises(parts_rules.PartsError):
            parts_rules.adjust_stock(self.part, -11, region=self.region, note='Write-off')
        self.assertEqual(self.stock(self.part, region=self.region), 10)

    def test_every_change_is_logged(self):
        parts_rules.adjust_stock(self.part, -3, region=self.region, note='Write-off')
        total = sum(StockMovement.objects.filter(part=self.part, region=self.region).values_list('change', flat=True))
        self.assertEqual(total, self.stock(self.part, region=self.region))

    def test_low_stock_alerts_regional_manager(self):
        PartStock.objects.filter(part=self.part, region=self.region).update(reorder_threshold=8)
        parts_rules.adjust_stock(self.part, -3, region=self.region, note='Write-off')
        self.assertTrue(Notification.objects.filter(
            event=Notification.EVENT_LOW_STOCK, recipient=self.regional_manager).exists())


class NotificationTests(PartsFixtureMixin, TechnicianAPITestCase):
    def test_list_and_mark_read(self):
        line = self.approved_line()
        response = self.client.get('/api/notifications/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['unread'], 1)
        note_id = response.data['results'][0]['id']
        self.assertEqual(response.data['results'][0]['event'], Notification.EVENT_LINE_APPROVED)
        self.client.post(f'/api/notifications/{note_id}/read/')
        self.assertEqual(self.client.get('/api/notifications/').data['unread'], 0)
        self.assertIsNotNone(line)

    def test_cannot_read_someone_elses(self):
        note = Notification.objects.create(recipient=self.cluster_manager, event=Notification.EVENT_NEW_REQUEST,
                                           message='x')
        response = self.client.post(f'/api/notifications/{note.id}/read/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class MeReportsTeamAndClusterTests(PartsFixtureMixin, TechnicianAPITestCase):
    def test_me_includes_team_and_cluster(self):
        self.assertEqual(self.client.get('/api/auth/me/').data['cluster_team']['name'], 'Team A')
        self.client.force_authenticate(user=self.cluster_manager)
        data = self.client.get('/api/auth/me/').data
        self.assertEqual(data['role'], 'cluster_manager')
        self.assertEqual(data['cluster']['id'], str(self.cluster.id))


class SafetyReportTests(TechnicianAPITestCase):
    def test_create_report(self):
        response = self.client.post('/api/safety-reports/', {
            'base_station': str(self.station.id),
            'type': SafetyReport.TYPE_HAZARD,
            'severity': SafetyReport.SEVERITY_MEDIUM,
            'description': 'Loose cable trunking cover.',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        report = SafetyReport.objects.get()
        self.assertEqual(report.reported_by, self.tech)

    def test_invalid_type_rejected(self):
        response = self.client.post('/api/safety-reports/', {
            'base_station': str(self.station.id),
            'type': 'bogus',
            'severity': SafetyReport.SEVERITY_LOW,
            'description': 'x',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_description_rejected(self):
        response = self.client.post('/api/safety-reports/', {
            'base_station': str(self.station.id),
            'type': SafetyReport.TYPE_INCIDENT,
            'severity': SafetyReport.SEVERITY_LOW,
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class VendorPartLookupTests(TechnicianAPITestCase):
    def test_list_vendors_filtered_by_type(self):
        Vendor.objects.create(name="Supplier Co", type=Vendor.TYPE_SUPPLIER)
        Vendor.objects.create(name="Contractor Co", type=Vendor.TYPE_CONTRACTOR)
        response = self.client.get('/api/vendors/?type=supplier')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['name'], "Supplier Co")

    def test_search_parts_by_name(self):
        vendor = Vendor.objects.create(name="Parts Co", type=Vendor.TYPE_SUPPLIER)
        Part.objects.create(vendor=vendor, name="Oil Filter", sku="OF-1", unit_cost="10.00")
        Part.objects.create(vendor=vendor, name="Air Filter", sku="AF-1", unit_cost="8.00")
        response = self.client.get('/api/parts/?search=oil')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['name'], "Oil Filter")


class AttachmentUploadTests(TechnicianAPITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_root = tempfile.mkdtemp()
        cls._media_root_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_root_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_root_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()

    def test_upload_attachment_for_asset(self):
        upload = io.BytesIO(b'fake-image-bytes')
        upload.name = 'photo.jpg'
        response = self.client.post('/api/attachments/', {
            'file': upload,
            'type': 'photo',
            'asset': str(self.asset.id),
        }, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['file_url'].endswith('.jpg') or '.jpg' in response.data['file_url'])

    def test_requires_exactly_one_owner(self):
        upload = io.BytesIO(b'fake-image-bytes')
        upload.name = 'photo.jpg'
        response = self.client.post('/api/attachments/', {
            'file': upload,
            'type': 'photo',
        }, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class AuthTests(APITestCase):
    def setUp(self):
        role_tech = Role.objects.get_or_create(name=Role.FIELD_TEAM)[0]
        self.tech = Personnel.objects.create_user(username="tech1", password="pass1234")
        self.tech.role = role_tech
        self.tech.save()

    def test_login_success(self):
        response = self.client.post('/api/auth/login/', {'username': 'tech1', 'password': 'pass1234'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertEqual(response.data['user']['username'], 'tech1')

    def test_login_invalid_credentials_rejected(self):
        response = self.client.post('/api/auth/login/', {'username': 'tech1', 'password': 'wrong'})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_requires_auth(self):
        response = self.client.get('/api/auth/me/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_returns_current_user(self):
        self.client.force_authenticate(user=self.tech)
        response = self.client.get('/api/auth/me/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['username'], 'tech1')

    def test_logout_returns_204(self):
        login = self.client.post('/api/auth/login/', {'username': 'tech1', 'password': 'pass1234'})
        response = self.client.post('/api/auth/logout/', {'refresh': login.data['refresh']})
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)


class TodayTests(TechnicianAPITestCase):
    def setUp(self):
        super().setUp()
        self.work_order = WorkOrder.objects.create(
            base_station=self.station, type=WorkOrder.TYPE_PREVENTIVE, due_date=timezone.localdate(),
        )
        self.alarm = Alarm.objects.create(asset=self.asset, raised_at=timezone.now())

    def test_today_includes_routine_and_alarms(self):
        response = self.client.get('/api/today/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['routine']), 1)
        self.assertEqual(response.data['routine'][0]['track_status'], 'not_started')
        self.assertEqual(len(response.data['alarms']), 1)
        self.assertEqual(response.data['alarms'][0]['track_status'], 'triggered')

    def test_today_scoped_to_own_stations(self):
        other_tech = Personnel.objects.create_user(username="tech2", password="pass1234")
        self.client.force_authenticate(user=other_tech)
        response = self.client.get('/api/today/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['routine']), 0)
        self.assertEqual(len(response.data['alarms']), 0)


class WorkOrderFlowTests(TechnicianAPITestCase):
    def setUp(self):
        super().setUp()
        self.work_order = WorkOrder.objects.create(
            base_station=self.station, type=WorkOrder.TYPE_PREVENTIVE, due_date=timezone.localdate(),
        )

    def test_detail(self):
        response = self.client.get(f'/api/work-orders/{self.work_order.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['base_station']['site_id'], 'TST-001')

    def test_start_sets_started_at_and_status(self):
        response = self.client.post(f'/api/work-orders/{self.work_order.id}/start/', {'geofence_verified': True})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.work_order.refresh_from_db()
        self.assertIsNotNone(self.work_order.started_at)
        self.assertTrue(self.work_order.geofence_verified)
        self.assertEqual(self.work_order.status, WorkOrder.STATUS_IN_PROGRESS)

    def test_start_creates_inspection_response_for_every_active_asset(self):
        second_category = AssetCategory.objects.create(name="Air Conditioning")
        second_asset = Asset.objects.create(
            asset_category=second_category, location=self.location, name="AC Unit 1",
        )
        inactive_asset = Asset.objects.create(
            asset_category=second_category, location=self.location, name="Retired unit",
            status=Asset.STATUS_RETIRED,
        )
        response = self.client.post(f'/api/work-orders/{self.work_order.id}/start/', {'geofence_verified': True})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            InspectionResponse.objects.filter(work_order=self.work_order, asset=self.asset).exists()
        )
        self.assertTrue(
            InspectionResponse.objects.filter(work_order=self.work_order, asset=second_asset).exists()
        )
        self.assertFalse(
            InspectionResponse.objects.filter(work_order=self.work_order, asset=inactive_asset).exists()
        )

    def test_start_is_idempotent_with_existing_inspection_response(self):
        # An InspectionResponse created ahead of /start/ (e.g. via the gap-filling endpoint)
        # must not be duplicated or reset by /start/.
        ir = InspectionResponse.objects.create(work_order=self.work_order, asset=self.asset, done=True)
        self.client.post(f'/api/work-orders/{self.work_order.id}/start/', {'geofence_verified': True})
        self.assertEqual(
            InspectionResponse.objects.filter(work_order=self.work_order, asset=self.asset).count(), 1
        )
        ir.refresh_from_db()
        self.assertTrue(ir.done)

    def test_start_twice_rejected(self):
        self.client.post(f'/api/work-orders/{self.work_order.id}/start/', {'geofence_verified': True})
        response = self.client.post(f'/api/work-orders/{self.work_order.id}/start/', {'geofence_verified': True})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_end_without_start_rejected(self):
        response = self.client.post(f'/api/work-orders/{self.work_order.id}/end/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_end_does_not_force_complete_unfinished_inspection_responses(self):
        # Completion is triggered explicitly via the "Maintenance complete" button
        # (PATCH .../done), not inferred when the whole work order session ends.
        self.client.post(f'/api/work-orders/{self.work_order.id}/start/', {'geofence_verified': True})
        ir = InspectionResponse.objects.get(work_order=self.work_order, asset=self.asset)
        response = self.client.post(f'/api/work-orders/{self.work_order.id}/end/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.work_order.refresh_from_db()
        ir.refresh_from_db()
        self.assertIsNotNone(self.work_order.ended_at)
        self.assertEqual(self.work_order.status, WorkOrder.STATUS_COMPLETE)
        self.assertFalse(ir.done)


class AlarmFlowTests(TechnicianAPITestCase):
    def setUp(self):
        super().setUp()
        self.alarm = Alarm.objects.create(asset=self.asset, raised_at=timezone.now())

    def test_detail(self):
        response = self.client.get(f'/api/alarms/{self.alarm.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data['resolved_at'])

    def test_resolve(self):
        response = self.client.post(f'/api/alarms/{self.alarm.id}/resolve/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.alarm.refresh_from_db()
        self.assertIsNotNone(self.alarm.resolved_at)
        self.assertEqual(self.alarm.resolved_by, self.tech)

    def test_resolve_twice_rejected(self):
        self.client.post(f'/api/alarms/{self.alarm.id}/resolve/')
        response = self.client.post(f'/api/alarms/{self.alarm.id}/resolve/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_note(self):
        response = self.client.post(f'/api/alarms/{self.alarm.id}/notes/', {'text': 'Checked, still active.'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(AlarmNote.objects.count(), 1)

    def test_add_note_empty_text_rejected(self):
        response = self.client.post(f'/api/alarms/{self.alarm.id}/notes/', {'text': '  '})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_alarm_on_own_asset(self):
        response = self.client.post('/api/alarms/', {'asset': str(self.asset.id)})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.data['resolved_at'])
        self.assertEqual(Alarm.objects.filter(asset=self.asset, resolved_at__isnull=True).count(), 2)

    def test_create_alarm_requires_asset(self):
        response = self.client.post('/api/alarms/', {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_alarm_rejected_for_asset_outside_assigned_stations(self):
        other_station = BaseStation.objects.create(
            cluster=self.station.cluster, name="Other Station", address="2 Other Street",
            site_id="OTH-001", site_classification=BaseStation.CLASS_PLATINUM,
        )
        other_location = Location.objects.create(base_station=other_station, name="Room")
        other_asset = Asset.objects.create(
            asset_category=self.category, location=other_location, name="Unassigned Generator",
        )
        response = self.client.post('/api/alarms/', {'asset': str(other_asset.id)})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class BaseStationAndAssetPickerTests(TechnicianAPITestCase):
    def test_base_stations_scoped_to_technician(self):
        BaseStation.objects.create(
            cluster=self.station.cluster, name="Unassigned Station", address="3 Other Street",
            site_id="OTH-002", site_classification=BaseStation.CLASS_PLATINUM,
        )
        response = self.client.get('/api/base-stations/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['site_id'], 'TST-001')

    def test_assets_scoped_to_base_station(self):
        response = self.client.get(f'/api/assets/?base_station={self.station.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['name'], 'Generator Set 1')

    def test_assets_requires_base_station(self):
        response = self.client.get('/api/assets/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class InspectionResponseTests(TechnicianAPITestCase):
    def setUp(self):
        super().setUp()
        self.work_order = WorkOrder.objects.create(
            base_station=self.station, type=WorkOrder.TYPE_PREVENTIVE, due_date=timezone.localdate(),
        )
        self.checklist = AssetCheckList.objects.create(
            asset_category=self.category, instructions="Routine inspection",
        )
        self.question = PMQuestion.objects.create(task_template=self.checklist, question="Oil level OK?")

    def test_create_generates_checklist_responses(self):
        response = self.client.post('/api/inspection-responses/', {
            'work_order': str(self.work_order.id), 'asset': str(self.asset.id),
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.data['checklist_responses']), 1)
        self.assertEqual(WorkOrderChecklistResponse.objects.count(), 1)

    def test_create_is_idempotent(self):
        first = self.client.post('/api/inspection-responses/', {
            'work_order': str(self.work_order.id), 'asset': str(self.asset.id),
        })
        second = self.client.post('/api/inspection-responses/', {
            'work_order': str(self.work_order.id), 'asset': str(self.asset.id),
        })
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data['id'], second.data['id'])
        self.assertEqual(InspectionResponse.objects.count(), 1)

    def test_list_scoped_to_technician_stations(self):
        InspectionResponse.objects.create(work_order=self.work_order, asset=self.asset)
        response = self.client.get('/api/inspection-responses/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_patch_updates_issues_found_and_conditions(self):
        ir = InspectionResponse.objects.create(work_order=self.work_order, asset=self.asset)
        condition = Condition.objects.create(name="Leaking", asset_category=self.category)
        response = self.client.patch(f'/api/inspection-responses/{ir.id}/', {
            'issues_found': True, 'comments': 'Needs attention', 'conditions': [str(condition.id)],
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ir.refresh_from_db()
        self.assertTrue(ir.issues_found)
        self.assertEqual(ir.comments, 'Needs attention')
        self.assertEqual(list(ir.conditions.all()), [condition])

    def test_patch_done_rejected_when_checklist_incomplete(self):
        created = self.client.post('/api/inspection-responses/', {
            'work_order': str(self.work_order.id), 'asset': str(self.asset.id),
        })
        ir_id = created.data['id']
        response = self.client.patch(f'/api/inspection-responses/{ir_id}/', {'done': True}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(InspectionResponse.objects.get(pk=ir_id).done)

    def _seed_todays_generator_readings(self):
        # self.asset's category is "Generator" (base fixture) — required for `done` since
        # generators must have today's run-hours and diesel-level readings, no exception.
        today = timezone.localdate()
        MeterReading.objects.create(
            asset=self.asset, reading_type=MeterReading.TYPE_RUN_HOURS,
            value=100, unit=MeterReading.UNIT_HOURS, date=today,
        )
        MeterReading.objects.create(
            asset=self.asset, reading_type=MeterReading.TYPE_DIESEL_LEVEL,
            value=500, unit=MeterReading.UNIT_MM, date=today,
        )

    def test_patch_done_accepted_when_checklist_complete(self):
        self._seed_todays_generator_readings()
        response = self.client.post('/api/inspection-responses/', {
            'work_order': str(self.work_order.id), 'asset': str(self.asset.id),
        })
        ir_id = response.data['id']
        cr_id = response.data['checklist_responses'][0]['id']
        self.client.patch(f'/api/checklist-responses/{cr_id}/', {'checked': True}, format='json')
        response = self.client.patch(f'/api/inspection-responses/{ir_id}/', {'done': True}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(InspectionResponse.objects.get(pk=ir_id).done)

    def test_patch_done_accepted_with_comment_when_checklist_incomplete(self):
        self._seed_todays_generator_readings()
        created = self.client.post('/api/inspection-responses/', {
            'work_order': str(self.work_order.id), 'asset': str(self.asset.id),
        })
        ir_id = created.data['id']
        self.client.patch(f'/api/inspection-responses/{ir_id}/', {
            'comments': 'Skipped coolant check — technician arriving with part tomorrow.',
        }, format='json')
        response = self.client.patch(f'/api/inspection-responses/{ir_id}/', {'done': True}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(InspectionResponse.objects.get(pk=ir_id).done)

    def test_patch_done_rejected_for_generator_without_todays_readings(self):
        created = self.client.post('/api/inspection-responses/', {
            'work_order': str(self.work_order.id), 'asset': str(self.asset.id),
        })
        ir_id = created.data['id']
        self.client.patch(f'/api/inspection-responses/{ir_id}/', {
            'comments': 'No time for readings today.',
        }, format='json')
        response = self.client.patch(f'/api/inspection-responses/{ir_id}/', {'done': True}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_done_rejected_for_generator_missing_one_reading(self):
        MeterReading.objects.create(
            asset=self.asset, reading_type=MeterReading.TYPE_RUN_HOURS,
            value=100, unit=MeterReading.UNIT_HOURS, date=timezone.localdate(),
        )
        created = self.client.post('/api/inspection-responses/', {
            'work_order': str(self.work_order.id), 'asset': str(self.asset.id),
        })
        ir_id = created.data['id']
        self.client.patch(f'/api/inspection-responses/{ir_id}/', {'comments': 'Ran out of time.'}, format='json')
        response = self.client.patch(f'/api/inspection-responses/{ir_id}/', {'done': True}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_done_rejected_with_blank_comment_when_checklist_incomplete(self):
        created = self.client.post('/api/inspection-responses/', {
            'work_order': str(self.work_order.id), 'asset': str(self.asset.id),
        })
        ir_id = created.data['id']
        response = self.client.patch(f'/api/inspection-responses/{ir_id}/', {
            'comments': '   ', 'done': True,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(InspectionResponse.objects.get(pk=ir_id).done)


class ChecklistResponseTests(TechnicianAPITestCase):
    def test_toggle_checked(self):
        work_order = WorkOrder.objects.create(
            base_station=self.station, type=WorkOrder.TYPE_PREVENTIVE, due_date=timezone.localdate(),
        )
        checklist = AssetCheckList.objects.create(asset_category=self.category, instructions="Inspection")
        question = PMQuestion.objects.create(task_template=checklist, question="Oil level OK?")
        ir = InspectionResponse.objects.create(work_order=work_order, asset=self.asset)
        cr = WorkOrderChecklistResponse.objects.create(inspection_response=ir, question=question)

        response = self.client.patch(f'/api/checklist-responses/{cr.id}/', {'checked': True}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        cr.refresh_from_db()
        self.assertTrue(cr.checked)

    def test_order_stable_after_toggling(self):
        # Checking an item must not reorder the list — items should never appear to
        # "jump" position after a tap.
        work_order = WorkOrder.objects.create(
            base_station=self.station, type=WorkOrder.TYPE_PREVENTIVE, due_date=timezone.localdate(),
        )
        checklist = AssetCheckList.objects.create(asset_category=self.category, instructions="Inspection")
        ir = InspectionResponse.objects.create(work_order=work_order, asset=self.asset)
        responses = [
            WorkOrderChecklistResponse.objects.create(
                inspection_response=ir,
                question=PMQuestion.objects.create(task_template=checklist, question=f"Q{i}?"),
            )
            for i in range(5)
        ]
        ids_before = [str(r.id) for r in responses]

        self.client.patch(f'/api/checklist-responses/{responses[2].id}/', {'checked': True}, format='json')
        self.client.patch(f'/api/checklist-responses/{responses[0].id}/', {'checked': True}, format='json')

        response = self.client.get(f'/api/inspection-responses/{ir.id}/')
        ids_after = [c['id'] for c in response.data['checklist_responses']]
        self.assertEqual(ids_before, ids_after)


class IssueFlowTests(TechnicianAPITestCase):
    def setUp(self):
        super().setUp()
        work_order = WorkOrder.objects.create(
            base_station=self.station, type=WorkOrder.TYPE_PREVENTIVE, due_date=timezone.localdate(),
        )
        self.ir = InspectionResponse.objects.create(work_order=work_order, asset=self.asset)

    def test_create_issue(self):
        response = self.client.post('/api/issues/', {
            'inspection_response': str(self.ir.id), 'description': 'Oil leak', 'severity': Issue.SEVERITY_HIGH,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Issue.objects.count(), 1)

    def test_missing_fields_rejected(self):
        response = self.client.post('/api/issues/', {'inspection_response': str(self.ir.id)})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_severity_rejected(self):
        response = self.client.post('/api/issues/', {
            'inspection_response': str(self.ir.id), 'description': 'Oil leak', 'severity': 'urgent',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete_issue(self):
        issue = Issue.objects.create(inspection_response=self.ir, description="Oil leak", severity=Issue.SEVERITY_LOW)
        response = self.client.delete(f'/api/issues/{issue.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Issue.objects.count(), 0)


class AssetCategoryCheckpointTests(TechnicianAPITestCase):
    def test_list_includes_existing_checklist_questions(self):
        checklist = AssetCheckList.objects.create(asset_category=self.category, instructions="Routine")
        PMQuestion.objects.create(task_template=checklist, question="Oil level OK?")
        response = self.client.get('/api/asset-categories/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        row = next(c for c in response.data if c['id'] == str(self.category.id))
        self.assertEqual(len(row['questions']), 1)
        self.assertEqual(row['questions'][0]['question'], 'Oil level OK?')

    def test_create_category(self):
        response = self.client.post('/api/asset-categories/', {'name': 'Battery Bank'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(AssetCategory.objects.filter(name='Battery Bank').exists())
        self.assertEqual(response.data['questions'], [])

    def test_create_category_requires_name(self):
        response = self.client.post('/api/asset-categories/', {'name': '  '})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rename_category(self):
        response = self.client.patch(f'/api/asset-categories/{self.category.id}/', {'name': 'Genset'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.category.refresh_from_db()
        self.assertEqual(self.category.name, 'Genset')

    def test_add_question_creates_checklist_if_missing(self):
        self.assertFalse(AssetCheckList.objects.filter(asset_category=self.category).exists())
        response = self.client.post('/api/checklist-questions/', {
            'asset_category': str(self.category.id), 'question': 'Coolant topped up?',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        checklist = AssetCheckList.objects.get(asset_category=self.category)
        self.assertEqual(checklist.questions.count(), 1)

    def test_add_question_reuses_existing_checklist(self):
        checklist = AssetCheckList.objects.create(asset_category=self.category, instructions="Routine")
        self.client.post('/api/checklist-questions/', {
            'asset_category': str(self.category.id), 'question': 'Q1',
        })
        self.assertEqual(AssetCheckList.objects.filter(asset_category=self.category).count(), 1)
        self.assertEqual(checklist.questions.count(), 1)

    def test_edit_question(self):
        checklist = AssetCheckList.objects.create(asset_category=self.category, instructions="Routine")
        question = PMQuestion.objects.create(task_template=checklist, question="Old text")
        response = self.client.patch(f'/api/checklist-questions/{question.id}/', {'question': 'New text'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        question.refresh_from_db()
        self.assertEqual(question.question, 'New text')

    def test_delete_question(self):
        checklist = AssetCheckList.objects.create(asset_category=self.category, instructions="Routine")
        question = PMQuestion.objects.create(task_template=checklist, question="Remove me")
        response = self.client.delete(f'/api/checklist-questions/{question.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(PMQuestion.objects.filter(pk=question.id).exists())

    def test_new_question_applies_to_existing_assets_of_that_category(self):
        # Confirms the "shows up on every base station checklist" behavior: no per-station
        # provisioning needed, since checklists are derived from asset_category at /start/ time.
        work_order = WorkOrder.objects.create(
            base_station=self.station, type=WorkOrder.TYPE_PREVENTIVE, due_date=timezone.localdate(),
        )
        self.client.post('/api/checklist-questions/', {
            'asset_category': str(self.category.id), 'question': 'New checkpoint',
        })
        self.client.post(f'/api/work-orders/{work_order.id}/start/', {'geofence_verified': True})
        ir = InspectionResponse.objects.get(work_order=work_order, asset=self.asset)
        self.assertEqual(ir.checklist_responses.count(), 1)
        self.assertEqual(ir.checklist_responses.first().question.question, 'New checkpoint')


class OfflineSyncTests(TechnicianAPITestCase):
    """Covers the offline-sync-safety changes: client-supplied ids make queued
    creates safe to replay, and base_updated_at makes queued edits detect a
    real conflict instead of silently overwriting."""

    def setUp(self):
        super().setUp()
        self.alarm = Alarm.objects.create(asset=self.asset, raised_at=timezone.now())
        self.work_order = WorkOrder.objects.create(
            base_station=self.station, type=WorkOrder.TYPE_PREVENTIVE, due_date=timezone.localdate(),
        )
        self.ir = InspectionResponse.objects.create(work_order=self.work_order, asset=self.asset)
        self.vendor = Vendor.objects.create(name="Parts Co", type=Vendor.TYPE_SUPPLIER)
        self.part = Part.objects.create(vendor=self.vendor, name="Oil Filter", sku="OF-1", unit_cost="10.00")

    def test_create_alarm_replay_is_idempotent(self):
        client_id = str(uuid.uuid4())
        first = self.client.post('/api/alarms/', {'id': client_id, 'asset': str(self.asset.id)})
        second = self.client.post('/api/alarms/', {'id': client_id, 'asset': str(self.asset.id)})
        self.assertEqual(first.data['id'], second.data['id'])
        self.assertEqual(Alarm.objects.filter(id=client_id).count(), 1)

    def test_add_note_replay_is_idempotent(self):
        client_id = str(uuid.uuid4())
        first = self.client.post(f'/api/alarms/{self.alarm.id}/notes/', {'id': client_id, 'text': 'Checked.'})
        second = self.client.post(f'/api/alarms/{self.alarm.id}/notes/', {'id': client_id, 'text': 'Checked.'})
        self.assertEqual(first.data['id'], second.data['id'])
        self.assertEqual(AlarmNote.objects.filter(id=client_id).count(), 1)

    def test_create_issue_replay_is_idempotent(self):
        client_id = str(uuid.uuid4())
        payload = {
            'id': client_id, 'inspection_response': str(self.ir.id),
            'description': 'Oil leak', 'severity': Issue.SEVERITY_HIGH,
        }
        first = self.client.post('/api/issues/', payload)
        second = self.client.post('/api/issues/', payload)
        self.assertEqual(first.data['id'], second.data['id'])
        self.assertEqual(Issue.objects.filter(id=client_id).count(), 1)

    def test_meter_reading_replay_is_idempotent(self):
        client_id = str(uuid.uuid4())
        payload = {
            'id': client_id, 'asset': str(self.asset.id), 'reading_type': MeterReading.TYPE_RUN_HOURS,
            'value': 1000, 'unit': MeterReading.UNIT_HOURS,
        }
        first = self.client.post('/api/meter-readings/', payload)
        second = self.client.post('/api/meter-readings/', payload)
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(MeterReading.objects.filter(id=client_id).count(), 1)

    def test_meter_reading_replay_does_not_re_run_monotonicity_check(self):
        # A reading valid when first queued must not be rejected on replay just because a
        # later, different reading has since raised the bar.
        client_id = str(uuid.uuid4())
        payload = {
            'id': client_id, 'asset': str(self.asset.id), 'reading_type': MeterReading.TYPE_RUN_HOURS,
            'value': 1000, 'unit': MeterReading.UNIT_HOURS,
        }
        self.client.post('/api/meter-readings/', payload)
        self.client.post('/api/meter-readings/', {
            'asset': str(self.asset.id), 'reading_type': MeterReading.TYPE_RUN_HOURS,
            'value': 2000, 'unit': MeterReading.UNIT_HOURS,
        })
        replay = self.client.post('/api/meter-readings/', payload)
        self.assertEqual(replay.status_code, status.HTTP_200_OK)
        self.assertEqual(replay.data['value'], 1000)

    def test_diesel_delivery_replay_is_idempotent_and_does_not_duplicate_reading(self):
        client_id = str(uuid.uuid4())
        payload = {
            'id': client_id, 'base_station': str(self.station.id), 'quantity_litres': 200,
            'tank_level_before': 100, 'tank_level_after': 1500,
        }
        first = self.client.post('/api/diesel-deliveries/', payload)
        second = self.client.post('/api/diesel-deliveries/', payload)
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(DieselDelivery.objects.filter(id=client_id).count(), 1)
        self.assertEqual(
            MeterReading.objects.filter(asset=self.asset, reading_type=MeterReading.TYPE_DIESEL_LEVEL).count(), 1,
        )

    def test_part_request_replay_is_idempotent(self):
        self.tech.cluster_team = ClusterTeam.objects.create(name="Team A", cluster=self.station.cluster)
        self.tech.save()
        client_id = str(uuid.uuid4())
        payload = {'id': client_id, 'base_station': str(self.station.id),
                   'lines': [{'part': str(self.part.id), 'quantity': 2, 'required_date': '2099-01-10'}]}
        first = self.client.post('/api/part-requests/', payload, format='json')
        second = self.client.post('/api/part-requests/', payload, format='json')
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data['id'], second.data['id'])
        self.assertEqual(PartRequestLine.objects.filter(request_id=client_id).count(), 1)

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp())
    def test_part_usage_replay_is_idempotent(self):
        self.tech.cluster_team = ClusterTeam.objects.create(name="Team A", cluster=self.station.cluster)
        self.tech.save()
        client_id = str(uuid.uuid4())

        def post():
            return self.client.post('/api/part-usages/', {
                'id': client_id, 'work_order': str(self.work_order.id), 'asset': str(self.asset.id),
                'part': str(self.part.id), 'qty_used': 1, 'photo': make_jpeg(),
            }, format='multipart')

        first, second = post(), post()
        self.assertEqual(first.data['id'], second.data['id'])
        self.assertEqual(PartUsage.objects.filter(id=client_id).count(), 1)
        # Stock is taken once: one "added at site" and one usage movement.
        self.assertEqual(StockMovement.objects.filter(usage_id=client_id).count(), 2)

    def test_safety_report_replay_is_idempotent(self):
        client_id = str(uuid.uuid4())
        payload = {
            'id': client_id, 'base_station': str(self.station.id), 'type': SafetyReport.TYPE_HAZARD,
            'severity': SafetyReport.SEVERITY_MEDIUM, 'description': 'Loose cover.',
        }
        first = self.client.post('/api/safety-reports/', payload)
        second = self.client.post('/api/safety-reports/', payload)
        self.assertEqual(first.data['id'], second.data['id'])
        self.assertEqual(SafetyReport.objects.filter(id=client_id).count(), 1)

    def test_checklist_patch_with_stale_base_updated_at_is_a_conflict(self):
        checklist = AssetCheckList.objects.create(asset_category=self.category, instructions="Inspection")
        question = PMQuestion.objects.create(task_template=checklist, question="Oil OK?")
        cr = WorkOrderChecklistResponse.objects.create(inspection_response=self.ir, question=question)
        stale = cr.updated.isoformat()
        # Someone/something else's edit lands first.
        self.client.patch(f'/api/checklist-responses/{cr.id}/', {'checked': True}, format='json')

        response = self.client.patch(f'/api/checklist-responses/{cr.id}/', {
            'checked': False, 'base_updated_at': stale,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        cr.refresh_from_db()
        self.assertTrue(cr.checked)  # the stale queued write was NOT applied

    def test_checklist_patch_with_current_base_updated_at_is_accepted(self):
        checklist = AssetCheckList.objects.create(asset_category=self.category, instructions="Inspection")
        question = PMQuestion.objects.create(task_template=checklist, question="Oil OK?")
        cr = WorkOrderChecklistResponse.objects.create(inspection_response=self.ir, question=question)
        current = cr.updated.isoformat()

        response = self.client.patch(f'/api/checklist-responses/{cr.id}/', {
            'checked': True, 'base_updated_at': current,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        cr.refresh_from_db()
        self.assertTrue(cr.checked)

    def test_inspection_response_patch_with_stale_base_updated_at_is_a_conflict(self):
        stale = self.ir.updated.isoformat()
        self.client.patch(
            f'/api/inspection-responses/{self.ir.id}/', {'comments': 'Someone else edited this.'}, format='json',
        )

        response = self.client.patch(f'/api/inspection-responses/{self.ir.id}/', {
            'comments': 'My queued edit.', 'base_updated_at': stale,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.ir.refresh_from_db()
        self.assertEqual(self.ir.comments, 'Someone else edited this.')

    def test_inspection_response_patch_with_current_base_updated_at_is_accepted(self):
        current = self.ir.updated.isoformat()
        response = self.client.patch(f'/api/inspection-responses/{self.ir.id}/', {
            'comments': 'My edit.', 'base_updated_at': current,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.ir.refresh_from_db()
        self.assertEqual(self.ir.comments, 'My edit.')


class ClusterManagerRoleTests(APITestCase):
    def test_cluster_manager_role_exists_and_is_reported_by_me(self):
        # Migration 0028 creates the role row, so it exists without seeding.
        role = Role.objects.get(name=Role.CLUSTER_MANAGER)
        self.assertEqual(str(role), 'Cluster Manager')
        manager = Personnel.objects.create_user(username='cm1', password='pass1234', role=role)
        self.client.force_authenticate(user=manager)
        resp = self.client.get('/api/auth/me/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['role'], 'cluster_manager')


class ConditionGoodFairPoorTests(APITestCase):
    def test_choices_are_good_fair_poor(self):
        self.assertEqual(
            [label for _, label in AssetCheckList.CONDITION_CHOICES], ['Good', 'Fair', 'Poor']
        )

    def test_migration_maps_old_values(self):
        import importlib
        from django.apps import apps
        mig = importlib.import_module('assets.migrations.0028_cluster_manager_role_and_good_fair_poor')
        category = AssetCategory.objects.create(name='Generator')
        old = {'very_good': 'good', 'fairly_good': 'fair', 'very_poor': 'poor'}
        rows = {
            v: AssetCheckList.objects.create(asset_category=category, instructions=v, condition=v)
            for v in old
        }
        mig.forwards(apps, None)
        for v, row in rows.items():
            row.refresh_from_db()
            self.assertEqual(row.condition, old[v])
        mig.backwards(apps, None)
        for v, row in rows.items():
            row.refresh_from_db()
            self.assertEqual(row.condition, v)


class MoveExistingDataMigrationTests(TransactionTestCase):
    """Migration 0030 moves old single-part requests, cluster-group stock and the technician role."""
    migrate_from = [('assets', '0029_parts_stock_requests_phase_a')]
    migrate_to = [('assets', '0030_move_existing_data')]

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old = executor.loader.project_state(self.migrate_from).apps
        Role = old.get_model('assets', 'Role')
        Role.objects.filter(name='field_team').delete()
        Role.objects.get_or_create(name='technician')
        region = old.get_model('assets', 'Region').objects.create(name='R')
        cg = old.get_model('assets', 'ClusterGroup').objects.create(region=region, name='CG')
        cluster = old.get_model('assets', 'Cluster').objects.create(cluster_group=cg, name='C')
        station = old.get_model('assets', 'BaseStation').objects.create(
            cluster=cluster, name='S', address='a', site_id='S-1', site_classification='platinum')
        vendor = old.get_model('assets', 'Vendor').objects.create(name='V', type='supplier')
        Part = old.get_model('assets', 'Part')
        part = Part.objects.create(vendor=vendor, name='P', sku='P-1', unit_cost='1.00')
        PartStock = old.get_model('assets', 'PartStock')
        cg2 = old.get_model('assets', 'ClusterGroup').objects.create(region=region, name='CG2')
        PartStock.objects.create(part=part, cluster_group=cg, qty=3)
        PartStock.objects.create(part=part, cluster_group=cg2, qty=4)
        PartRequest = old.get_model('assets', 'PartRequest')
        PartRequest.objects.create(part=part, base_station=station, quantity=2, status='requested')
        PartRequest.objects.create(part=part, base_station=station, quantity=1, status='received',
                                   received_at=timezone.now())
        self.region_id, self.part_id = region.id, part.id
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.migrate_to)
        self.apps = executor.loader.project_state(self.migrate_to).apps

    def tearDown(self):
        MigrationExecutor(connection).migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())

    def test_data_moved(self):
        Role = self.apps.get_model('assets', 'Role')
        self.assertTrue(Role.objects.filter(name='field_team').exists())
        self.assertFalse(Role.objects.filter(name='technician').exists())
        self.assertTrue(Role.objects.filter(name='team_lead').exists())

        PartStock = self.apps.get_model('assets', 'PartStock')
        rows = PartStock.objects.filter(part_id=self.part_id)
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.get().region_id, self.region_id)
        self.assertEqual(rows.get().qty, 7)

        Line = self.apps.get_model('assets', 'PartRequestLine')
        self.assertEqual(sorted(Line.objects.values_list('status', flat=True)), ['delivered', 'requested'])
        delivered = Line.objects.get(status='delivered')
        Delivery = self.apps.get_model('assets', 'PartDelivery')
        self.assertEqual(Delivery.objects.get(line=delivered).quantity, 1)
