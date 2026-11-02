import io
import shutil
import tempfile
import uuid

import datetime

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from .models import (
    Alarm, AlarmNote, Asset, AssetCategory, AssetCheckList, BaseStation,
    Cluster, ClusterGroup, Condition, DieselDelivery, InspectionResponse,
    Issue, Location, MeterReading, Notification, Part, PartDelivery, PartRequest, PartRequestLine,
    PartStock, PartUsage, PMQuestion, Personnel, Region, Role, SafetyReport, Setting, StockMovement, Vendor,
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
        self.category = AssetCategory.objects.get_or_create(name=AssetCategory.DIESEL_GENERATOR)[0]
        # The real type arrives with its Form 1a checklist and defects; these tests build their own.
        AssetCheckList.objects.filter(asset_category=self.category).delete()
        self.category.conditions.all().delete()
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
        # self.asset (base fixture) is category "Diesel Generator" at self.station.
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

    def test_usage_rows_say_how_much_was_added_at_site(self):
        parts_rules.adjust_stock(self.part, 3, team=self.team, note='Count')
        self.client.post('/api/part-usages/', {
            'work_order': str(self.work_order.id), 'asset': str(self.asset.id),
            'part': str(self.part.id), 'qty_used': 5, 'photo': make_jpeg(),
        }, format='multipart')  # team held 3, used 5 -> 2 added at site
        self.client.post('/api/part-usages/', {
            'work_order': str(self.work_order.id), 'asset': str(self.asset.id),
            'part': str(self.part2.id), 'qty_used': 1, 'photo': make_jpeg(),
        }, format='multipart')  # team held 0 of this one -> 1 added at site
        parts_rules.adjust_stock(self.part, 10, team=self.team, note='Restock')
        self.client.post('/api/part-usages/', {
            'work_order': str(self.work_order.id), 'asset': str(self.asset.id),
            'part': str(self.part.id), 'qty_used': 1, 'photo': make_jpeg(),
        }, format='multipart')  # plenty held -> nothing added
        self.client.force_authenticate(user=self.cluster_manager)
        rows = self.client.get('/api/manager/part-usages/').data
        added = sorted((r['part']['name'], r['qty_used'], r['added_at_site']) for r in rows)
        self.assertEqual(added, [('Fan Belt', 1, 1), ('Oil Filter', 1, 0), ('Oil Filter', 5, 2)])

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
        # self.asset's category is "Diesel Generator" (base fixture) — required for `done` since
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


class ManagerSummaryTests(PartsFixtureMixin, TechnicianAPITestCase):
    """The two summary tables on the Cluster Manager's Consumables screens."""

    def setUp(self):
        super().setUp()
        other_cluster = Cluster.objects.create(cluster_group=self.cluster.cluster_group, name="Elsewhere")
        self.other_station = BaseStation.objects.create(
            cluster=other_cluster, name="Far Station", address="x", site_id="FAR-1",
            site_classification=BaseStation.CLASS_PLATINUM,
        )

    def line_for(self, part, quantity, **kwargs):
        resp = self.make_request([{'part': str(part.id), 'quantity': quantity, 'required_date': '2099-01-10'}])
        return PartRequestLine.objects.get(pk=resp.data['lines'][0]['id'])

    def rows(self, url):
        self.client.force_authenticate(user=self.cluster_manager)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return {r['part']['id']: r for r in response.data['results']}

    def deliver_fully(self, line, quantity):
        parts_rules.approve_line(line, by=self.regional_manager)
        delivery = parts_rules.record_delivery(line, by=self.regional_manager, quantity=quantity)
        parts_rules.confirm_received(delivery, by=self.tech)
        return delivery

    # ── requests-summary ──

    def test_requested_approved_and_total_per_part(self):
        self.line_for(self.part, 3)  # Requested
        partly = self.line_for(self.part, 4)  # Approved, 1 of 4 delivered -> 3 still to receive
        self.deliver_fully(partly, 1)
        awaiting = self.line_for(self.part2, 2)  # Pending: recorded by approver, not yet confirmed
        parts_rules.approve_line(awaiting, by=self.regional_manager)
        parts_rules.record_delivery(awaiting, by=self.regional_manager, quantity=2)

        rows = self.rows('/api/manager/requests-summary/')
        oil = rows[str(self.part.id)]
        self.assertEqual((oil['requested'], oil['approved'], oil['total']), (3, 3, 6))
        belt = rows[str(self.part2.id)]
        self.assertEqual((belt['requested'], belt['approved'], belt['total']), (0, 2, 2))
        self.assertEqual(oil['part']['name'], 'Oil Filter')

    def test_declined_cancelled_and_delivered_lines_are_excluded(self):
        declined = self.line_for(self.part, 5)
        parts_rules.decline_line(declined, by=self.regional_manager, reason='No stock')
        cancelled = self.make_request([{'part': str(self.part.id), 'quantity': 6, 'required_date': '2099-01-10'}])
        self.client.post(f"/api/part-requests/{cancelled.data['id']}/cancel/")
        done = self.line_for(self.part, 2)
        self.deliver_fully(done, 2)

        self.assertEqual(self.rows('/api/manager/requests-summary/'), {})

    def test_requests_summary_only_counts_my_cluster(self):
        self.client.post('/api/part-requests/', {
            'base_station': str(self.other_station.id),
            'lines': [{'part': str(self.part.id), 'quantity': 9, 'required_date': '2099-01-10'}],
        }, format='json')
        self.assertEqual(self.rows('/api/manager/requests-summary/'), {})

    def test_requests_summary_for_a_manager_without_a_cluster_is_empty(self):
        self.line_for(self.part, 1)
        self.cluster_manager.cluster = None
        self.cluster_manager.save()
        self.assertEqual(self.rows('/api/manager/requests-summary/'), {})

    # ── usage-summary ──

    def log_usage(self, quantity):
        response = self.client.post('/api/part-usages/', {
            'work_order': str(self.work_order.id), 'asset': str(self.asset.id),
            'part': str(self.part.id), 'qty_used': quantity, 'photo': make_jpeg(),
        }, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        return PartUsage.objects.get(pk=response.data['id'])

    def test_delivered_and_used_this_month_by_default(self):
        line = self.line_for(self.part, 5)
        self.deliver_fully(line, 4)
        self.log_usage(1)
        self.log_usage(2)

        data = self.rows('/api/manager/usage-summary/')[str(self.part.id)]
        self.assertEqual((data['delivered'], data['used']), (4, 3))
        month = self.client.get('/api/manager/usage-summary/').data['month']
        self.assertEqual(month, timezone.localdate().strftime('%Y-%m'))

    def test_other_months_are_excluded_and_selectable(self):
        line = self.line_for(self.part, 5)
        delivery = self.deliver_fully(line, 4)
        last_month = timezone.now() - datetime.timedelta(days=40)
        type(delivery).objects.filter(pk=delivery.pk).update(received_at=last_month)
        old = self.log_usage(2)
        PartUsage.objects.filter(pk=old.pk).update(created=last_month)
        self.log_usage(1)

        this_month = self.rows('/api/manager/usage-summary/')[str(self.part.id)]
        self.assertEqual((this_month['delivered'], this_month['used']), (0, 1))

        key = last_month.strftime('%Y-%m')
        earlier = self.rows(f'/api/manager/usage-summary/?month={key}')[str(self.part.id)]
        self.assertEqual((earlier['delivered'], earlier['used']), (4, 2))

    def test_unconfirmed_deliveries_do_not_count_as_delivered(self):
        line = self.line_for(self.part, 5)
        parts_rules.approve_line(line, by=self.regional_manager)
        parts_rules.record_delivery(line, by=self.regional_manager, quantity=3)  # field team has not confirmed
        self.assertEqual(self.rows('/api/manager/usage-summary/'), {})

    def test_usage_summary_only_counts_my_cluster(self):
        far_wo = WorkOrder.objects.create(base_station=self.other_station, type=WorkOrder.TYPE_PREVENTIVE)
        PartUsage.objects.create(work_order=far_wo, asset=self.asset, part=self.part, qty_used=7)
        self.assertEqual(self.rows('/api/manager/usage-summary/'), {})

    def test_invalid_month_is_rejected(self):
        self.client.force_authenticate(user=self.cluster_manager)
        for bad in ('2026-13', 'november', '2026-1'):
            response = self.client.get(f'/api/manager/usage-summary/?month={bad}')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, bad)

    # ── usage list defaults to this month ──

    def test_usage_list_defaults_to_this_month(self):
        old = self.log_usage(2)
        PartUsage.objects.filter(pk=old.pk).update(created=timezone.now() - datetime.timedelta(days=40))
        self.log_usage(1)
        self.client.force_authenticate(user=self.cluster_manager)

        self.assertEqual(len(self.client.get('/api/manager/part-usages/').data), 1)
        everything = self.client.get('/api/manager/part-usages/?date_from=2000-01-01')
        self.assertEqual(len(everything.data), 2)


class ClusterManagerStationAccessTests(PartsFixtureMixin, TechnicianAPITestCase):
    """A Cluster Manager needs no station assignments: every station in their cluster is theirs."""

    def setUp(self):
        super().setUp()
        other_cluster = Cluster.objects.create(cluster_group=self.cluster.cluster_group, name="Elsewhere")
        self.other_station = BaseStation.objects.create(
            cluster=other_cluster, name="Far Station", address="x", site_id="FAR-1",
            site_classification=BaseStation.CLASS_PLATINUM,
        )
        self.other_location = Location.objects.create(base_station=self.other_station, name="Room")
        self.other_asset = Asset.objects.create(
            asset_category=self.category, location=self.other_location, name="Far Generator",
        )
        today = timezone.localdate()
        WorkOrder.objects.filter(pk=self.work_order.pk).update(due_date=today)
        WorkOrder.objects.create(base_station=self.other_station, type=WorkOrder.TYPE_PREVENTIVE, due_date=today)
        self.assertEqual(self.cluster_manager.stations.count(), 0)
        self.client.force_authenticate(user=self.cluster_manager)

    def test_today_lists_work_in_my_cluster_only(self):
        response = self.client.get('/api/today/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        sites = [row['base_station']['site_id'] for row in response.data['routine']]
        self.assertEqual(sites, ['TST-001'])

    def test_base_station_list_is_my_cluster(self):
        sites = [s['site_id'] for s in self.client.get('/api/base-stations/').data]
        self.assertEqual(sites, ['TST-001'])

    def test_assets_at_my_stations_only(self):
        mine = self.client.get(f'/api/assets/?base_station={self.station.id}')
        self.assertEqual(len(mine.data), 1)
        theirs = self.client.get(f'/api/assets/?base_station={self.other_station.id}')
        self.assertEqual(len(theirs.data), 0)

    def test_a_manager_without_a_cluster_sees_no_stations(self):
        self.cluster_manager.cluster = None
        self.cluster_manager.save()
        self.assertEqual(self.client.get('/api/base-stations/').data, [])
        self.assertEqual(self.client.get('/api/today/').data['routine'], [])

    def test_field_team_still_see_only_assigned_stations(self):
        second = BaseStation.objects.create(
            cluster=self.cluster, name="Second", address="y", site_id="TST-002",
            site_classification=BaseStation.CLASS_PLATINUM,
        )
        self.assertIsNotNone(second)
        self.client.force_authenticate(user=self.tech)
        sites = [s['site_id'] for s in self.client.get('/api/base-stations/').data]
        self.assertEqual(sites, ['TST-001'])


class AssetTypeDataTests(TestCase):
    """The nine Form 1a types, loaded by migration 0034 into every database."""

    def test_nine_types_with_groups(self):
        from .reference_data import TYPE_NAMES
        names = set(AssetCategory.objects.values_list('name', flat=True))
        self.assertEqual(names, set(TYPE_NAMES))
        self.assertEqual(len(TYPE_NAMES), 9)
        for removed in ('Air Conditioning', 'Rectifier', 'Hybrid DC Power', 'Generator'):
            self.assertNotIn(removed, names)
        tank = AssetCategory.objects.get(name='Diesel Tank')
        self.assertEqual(tank.group, '2. Generator Power Supply')
        self.assertEqual(AssetCategory.objects.get(name='Tower Structure').group, '6. Telecoms Tower')

    def test_each_type_has_a_checklist_and_defects(self):
        for category in AssetCategory.objects.all():
            checklist = AssetCheckList.objects.get(asset_category=category)
            self.assertGreater(checklist.questions.count(), 0, category.name)
            if category.name != 'Battery Packs':
                self.assertGreater(category.conditions.filter(severity='poor').count(), 0, category.name)
                self.assertGreater(category.conditions.filter(severity='fair').count(), 0, category.name)

    def test_battery_packs_have_no_defects_yet(self):
        battery = AssetCategory.objects.get(name='Battery Packs')
        self.assertEqual(battery.conditions.count(), 0)
        self.assertEqual(AssetCheckList.objects.get(asset_category=battery).questions.count(), 1)

    def test_generator_defects_are_tagged_poor_or_fair(self):
        gen = AssetCategory.objects.get(name='Diesel Generator')
        self.assertEqual(gen.conditions.get(name='Generator earthing').severity, 'poor')
        self.assertEqual(gen.conditions.get(name='Generator not installed on plinth').severity, 'fair')
        self.assertEqual(gen.conditions.filter(severity='poor').count(), 6)
        self.assertEqual(gen.conditions.filter(severity='fair').count(), 4)

    def test_control_panels_share_defects(self):
        ac = AssetCategory.objects.get(name='AC Control Panel')
        dc = AssetCategory.objects.get(name='DC Control Panel')
        self.assertEqual(
            sorted(ac.conditions.values_list('name', 'severity')),
            sorted(dc.conditions.values_list('name', 'severity')),
        )

    def test_loading_twice_does_not_duplicate(self):
        from .reference_data import load_asset_types
        before = (Condition.objects.count(), PMQuestion.objects.count(), AssetCategory.objects.count())
        load_asset_types(AssetCategory, Condition, AssetCheckList, PMQuestion)
        after = (Condition.objects.count(), PMQuestion.objects.count(), AssetCategory.objects.count())
        self.assertEqual(before, after)

    def test_new_fields_default_sensibly(self):
        gen = AssetCategory.objects.get(name='Diesel Generator')
        self.assertIsNone(gen.service_interval_hours)
        self.assertIsNone(gen.service_interval_days)
        self.assertFalse(hasattr(AssetCheckList, 'CONDITION_CHOICES'))


class AppSettingsTests(TestCase):
    def test_colour_band_defaults(self):
        from . import app_settings
        self.assertEqual(app_settings.get_setting(app_settings.COLOUR_BANDS), {'green_min': 95, 'amber_min': 90})
        self.assertEqual(app_settings.colour_for_percent(95), 'green')
        self.assertEqual(app_settings.colour_for_percent(94), 'amber')
        self.assertEqual(app_settings.colour_for_percent(90), 'amber')
        self.assertEqual(app_settings.colour_for_percent(89), 'red')

    def test_saved_bands_override_defaults(self):
        from . import app_settings
        Setting.objects.create(key=app_settings.COLOUR_BANDS, value={'green_min': 80, 'amber_min': 60})
        self.assertEqual(app_settings.colour_for_percent(85), 'green')
        self.assertEqual(app_settings.colour_for_percent(70), 'amber')
        self.assertEqual(app_settings.colour_for_percent(59), 'red')


class DataFieldTests(TechnicianAPITestCase):
    """Litres sit beside mm; ratings start empty."""

    def test_meter_reading_can_hold_litres_beside_mm(self):
        reading = MeterReading.objects.create(
            asset=self.asset, reading_type=MeterReading.TYPE_DIESEL_LEVEL, date=timezone.localdate(),
            value=1500, unit=MeterReading.UNIT_MM, value_litres=2400,
        )
        reading.refresh_from_db()
        self.assertEqual((reading.value, reading.value_litres), (1500, 2400))

    def test_diesel_delivery_can_hold_litres_levels(self):
        delivery = DieselDelivery.objects.create(
            base_station=self.station, quantity_litres=200, tank_level_before=150, tank_level_after=1500,
            tank_level_before_litres=240, tank_level_after_litres=2400, delivered_at=timezone.now(),
        )
        delivery.refresh_from_db()
        self.assertEqual((delivery.tank_level_before_litres, delivery.tank_level_after_litres), (240, 2400))

    def test_ratings_start_empty(self):
        work_order = WorkOrder.objects.create(base_station=self.station, type=WorkOrder.TYPE_PREVENTIVE)
        ir = InspectionResponse.objects.create(work_order=work_order, asset=self.asset)
        self.assertIsNone(ir.rating)
        self.assertIsNone(ir.completed_at)
        self.assertIsNone(work_order.station_rating)
        self.assertIsNone(work_order.visit_date)


class AssetTypeMigrationTests(TransactionTestCase):
    """Migration 0034 moves assets of equivalent old types and removes the rest."""
    migrate_from = [('assets', '0033_asset_types_ratings_schema')]
    migrate_to = [('assets', '0034_load_asset_types')]

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old = executor.loader.project_state(self.migrate_from).apps
        Category = old.get_model('assets', 'AssetCategory')
        old.get_model('assets', 'Condition').objects.all().delete()
        old.get_model('assets', 'AssetCheckList').objects.all().delete()
        old.get_model('assets', 'Asset').objects.all().delete()
        Category.objects.all().delete()

        region = old.get_model('assets', 'Region').objects.create(name='R')
        cg = old.get_model('assets', 'ClusterGroup').objects.create(region=region, name='CG')
        cluster = old.get_model('assets', 'Cluster').objects.create(cluster_group=cg, name='C')
        station = old.get_model('assets', 'BaseStation').objects.create(
            cluster=cluster, name='S', address='a', site_id='S-1', site_classification='platinum')
        location = old.get_model('assets', 'Location').objects.create(base_station=station, name='Room')
        Asset = old.get_model('assets', 'Asset')
        for name in ('Generator', 'Solar', 'Battery Bank', 'DC Electricals', 'AC Electricals', 'Janitorial',
                     'Air Conditioning', 'Rectifier'):
            category = Category.objects.create(name=name)
            old.get_model('assets', 'Condition').objects.create(name=f'{name} defect', asset_category=category)
            Asset.objects.create(asset_category=category, location=location, name=f'{name} asset')
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.migrate_to)
        self.apps = executor.loader.project_state(self.migrate_to).apps

    def tearDown(self):
        MigrationExecutor(connection).migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())

    def test_assets_move_to_equivalent_types_and_others_go(self):
        Asset = self.apps.get_model('assets', 'Asset')
        moved = {a.name: a.asset_category.name for a in Asset.objects.select_related('asset_category')}
        self.assertEqual(moved, {
            'Generator asset': 'Diesel Generator',
            'Solar asset': 'Solar Panels and Structure',
            'Battery Bank asset': 'Battery Packs',
            'DC Electricals asset': 'DC Control Panel',
            'AC Electricals asset': 'AC Control Panel',
            'Janitorial asset': 'Janitorial Services',
        })

    def test_old_categories_and_their_defects_are_removed(self):
        Category = self.apps.get_model('assets', 'AssetCategory')
        names = set(Category.objects.values_list('name', flat=True))
        self.assertEqual(len(names), 9)
        self.assertFalse(names & {'Generator', 'Solar', 'Battery Bank', 'Air Conditioning', 'Rectifier'})
        Condition = self.apps.get_model('assets', 'Condition')
        self.assertFalse(Condition.objects.filter(name__endswith=' defect').exists())


class AssetRatingRuleTests(TestCase):
    """HANDOFF.md 4.2: the asset rating comes from the defects ticked."""

    def test_no_defects_is_good(self):
        from .ratings import rating_from_severities
        self.assertEqual(rating_from_severities([]), 'good')

    def test_a_fair_defect_makes_it_fair(self):
        from .ratings import rating_from_severities
        self.assertEqual(rating_from_severities(['fair']), 'fair')
        self.assertEqual(rating_from_severities(['fair', 'fair', 'fair']), 'fair')

    def test_a_poor_defect_makes_it_poor(self):
        from .ratings import rating_from_severities
        self.assertEqual(rating_from_severities(['poor']), 'poor')

    def test_poor_wins_over_fair(self):
        from .ratings import rating_from_severities
        self.assertEqual(rating_from_severities(['fair', 'poor', 'fair']), 'poor')


class StationRatingRuleTests(TestCase):
    """HANDOFF.md 4.2, rule by rule."""

    GEN, TANK = 'Diesel Generator', 'Diesel Tank'

    def rate(self, *assets):
        from .ratings import station_rating_from_assets
        return station_rating_from_assets(assets)

    # Rule 1: Poor
    def test_poor_generator_makes_the_station_poor(self):
        self.assertEqual(self.rate((self.GEN, 'poor'), (self.TANK, 'good'), ('AC Control Panel', 'good')), 'poor')

    def test_poor_tank_makes_the_station_poor(self):
        self.assertEqual(self.rate((self.GEN, 'good'), (self.TANK, 'poor'), ('AC Control Panel', 'good')), 'poor')

    def test_poor_generator_alone_is_enough_even_if_everything_else_is_good(self):
        self.assertEqual(self.rate((self.GEN, 'poor')), 'poor')

    def test_two_other_poor_assets_make_the_station_poor(self):
        self.assertEqual(self.rate(
            (self.GEN, 'good'), (self.TANK, 'good'),
            ('AC Control Panel', 'poor'), ('Tower Structure', 'poor'), ('Janitorial Services', 'good'),
        ), 'poor')

    def test_three_other_poor_assets_also_make_it_poor(self):
        self.assertEqual(self.rate(
            ('AC Control Panel', 'poor'), ('DC Control Panel', 'poor'), ('Tower Structure', 'poor'),
        ), 'poor')

    def test_generator_and_tank_poor_counts_do_not_need_the_two_other_rule(self):
        self.assertEqual(self.rate((self.GEN, 'poor'), (self.TANK, 'poor')), 'poor')

    # The "two other assets" rule does not count the generator or tank
    def test_one_poor_other_plus_a_fair_generator_is_not_poor(self):
        self.assertEqual(self.rate(
            (self.GEN, 'fair'), (self.TANK, 'good'), ('AC Control Panel', 'poor'),
        ), 'fair')

    def test_one_poor_other_asset_is_only_fair(self):
        self.assertEqual(self.rate(
            (self.GEN, 'good'), (self.TANK, 'good'), ('AC Control Panel', 'poor'), ('Tower Structure', 'good'),
        ), 'fair')

    # Rule 2: Good
    def test_all_good_is_good(self):
        self.assertEqual(self.rate((self.GEN, 'good'), (self.TANK, 'good'), ('Tower Structure', 'good')), 'good')

    def test_one_or_two_fair_is_still_good(self):
        self.assertEqual(self.rate((self.GEN, 'fair'), (self.TANK, 'good'), ('Tower Structure', 'good')), 'good')
        self.assertEqual(self.rate((self.GEN, 'fair'), (self.TANK, 'fair'), ('Tower Structure', 'good')), 'good')

    # Rule 3: Fair
    def test_three_fair_is_fair(self):
        self.assertEqual(self.rate(
            (self.GEN, 'fair'), (self.TANK, 'fair'), ('Tower Structure', 'fair'), ('AC Control Panel', 'good'),
        ), 'fair')

    def test_one_poor_other_with_two_fair_is_fair(self):
        self.assertEqual(self.rate(
            ('AC Control Panel', 'poor'), ('Tower Structure', 'fair'), ('DC Control Panel', 'fair'),
        ), 'fair')

    # Stations with no generator or tank
    def test_station_without_generator_or_tank_uses_only_the_other_assets(self):
        self.assertEqual(self.rate(('Transformer', 'good'), ('Tower Structure', 'good')), 'good')
        self.assertEqual(self.rate(('Transformer', 'poor'), ('Tower Structure', 'good')), 'fair')
        self.assertEqual(self.rate(('Transformer', 'poor'), ('Tower Structure', 'poor')), 'poor')
        self.assertEqual(self.rate(
            ('Transformer', 'fair'), ('Tower Structure', 'fair'), ('AC Control Panel', 'fair'),
        ), 'fair')

    def test_station_with_a_generator_but_no_tank(self):
        self.assertEqual(self.rate((self.GEN, 'good'), ('Tower Structure', 'poor')), 'fair')
        self.assertEqual(self.rate((self.GEN, 'poor'), ('Tower Structure', 'good')), 'poor')

    def test_station_with_a_tank_but_no_generator(self):
        self.assertEqual(self.rate((self.TANK, 'poor'), ('Tower Structure', 'good')), 'poor')

    def test_two_generators_one_poor_makes_the_station_poor(self):
        self.assertEqual(self.rate((self.GEN, 'good'), (self.GEN, 'poor')), 'poor')


class RatingOnCompleteTests(TechnicianAPITestCase):
    """Marking an asset complete stores its rating; completing the last one stores the station's."""

    def setUp(self):
        super().setUp()
        self.work_order = WorkOrder.objects.create(
            base_station=self.station, type=WorkOrder.TYPE_PREVENTIVE, due_date=timezone.localdate(),
        )
        self.tank_type = AssetCategory.objects.get(name=AssetCategory.DIESEL_TANK)
        self.panel_type = AssetCategory.objects.get(name='AC Control Panel')
        self.tank = Asset.objects.create(asset_category=self.tank_type, location=self.location, name='Tank')
        self.panel = Asset.objects.create(asset_category=self.panel_type, location=self.location, name='Panel')
        self.poor_gen = Condition.objects.create(name='Engine problems', asset_category=self.category, severity='poor')
        self.fair_gen = Condition.objects.create(name='Generator housing', asset_category=self.category, severity='fair')
        self.fair_tank = Condition.objects.create(name='Minor rust', asset_category=self.tank_type, severity='fair')
        self.poor_panel = Condition.objects.create(name='Exposed terminals', asset_category=self.panel_type, severity='poor')

    def ir(self, asset):
        return InspectionResponse.objects.get_or_create(work_order=self.work_order, asset=asset)[0]

    def give_generator_readings(self):
        today = timezone.localdate()
        for kind, unit in ((MeterReading.TYPE_RUN_HOURS, 'hours'), (MeterReading.TYPE_DIESEL_LEVEL, 'mm')):
            MeterReading.objects.create(asset=self.asset, reading_type=kind, date=today, value=100, unit=unit)

    def complete(self, asset, *conditions):
        ir = self.ir(asset)
        ir.conditions.set(conditions)
        if asset == self.asset:
            self.give_generator_readings()
        return self.client.patch(
            f'/api/inspection-responses/{ir.id}/', {'done': True, 'comments': 'ok'}, format='json',
        )

    def test_rating_is_stored_from_the_defects_ticked(self):
        self.assertEqual(self.complete(self.panel).status_code, 200)
        self.assertEqual(self.ir(self.panel).rating, 'good')

        self.assertEqual(self.complete(self.tank, self.fair_tank).status_code, 200)
        self.assertEqual(self.ir(self.tank).rating, 'fair')

        self.assertEqual(self.complete(self.asset, self.fair_gen, self.poor_gen).status_code, 200)
        self.assertEqual(self.ir(self.asset).rating, 'poor')

    def test_rating_and_time_are_in_the_response(self):
        response = self.complete(self.panel, self.poor_panel)
        self.assertEqual(response.data['rating'], 'poor')
        self.assertIsNotNone(response.data['completed_at'])

    def test_rating_is_not_set_before_the_asset_is_complete(self):
        ir = self.ir(self.panel)
        ir.conditions.set([self.poor_panel])
        self.client.patch(f'/api/inspection-responses/{ir.id}/', {'comments': 'x'}, format='json')
        self.assertIsNone(self.ir(self.panel).rating)

    def test_stored_rating_does_not_change_if_defects_are_edited_later(self):
        self.complete(self.panel, self.poor_panel)
        ir = self.ir(self.panel)
        self.client.patch(f'/api/inspection-responses/{ir.id}/', {'conditions': []}, format='json')
        self.assertEqual(self.ir(self.panel).rating, 'poor')

    def test_failed_complete_stores_no_rating(self):
        ir = self.ir(self.asset)  # generator with no readings: refused
        response = self.client.patch(f'/api/inspection-responses/{ir.id}/', {'done': True, 'comments': 'x'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(self.ir(self.asset).rating)

    def test_partial_visit_has_no_station_rating(self):
        self.ir(self.tank), self.ir(self.asset), self.ir(self.panel)
        self.complete(self.panel)
        self.complete(self.tank)
        self.work_order.refresh_from_db()
        self.assertIsNone(self.work_order.station_rating)
        self.assertIsNone(self.work_order.visit_date)

    def test_station_rating_is_stored_when_the_last_asset_completes(self):
        self.ir(self.tank), self.ir(self.asset), self.ir(self.panel)
        self.complete(self.panel, self.poor_panel)
        self.complete(self.tank)
        self.complete(self.asset, self.fair_gen)
        self.work_order.refresh_from_db()
        # one Poor other asset, no poor generator/tank -> Fair
        self.assertEqual(self.work_order.station_rating, 'fair')
        self.assertEqual(self.work_order.visit_date, timezone.localdate())

    def test_poor_generator_makes_the_visit_poor(self):
        self.ir(self.tank), self.ir(self.asset), self.ir(self.panel)
        self.complete(self.panel)
        self.complete(self.tank)
        self.complete(self.asset, self.poor_gen)
        self.work_order.refresh_from_db()
        self.assertEqual(self.work_order.station_rating, 'poor')

    def test_two_other_poor_assets_make_the_visit_poor(self):
        second_panel = Asset.objects.create(asset_category=self.panel_type, location=self.location, name='Panel 2')
        for a in (self.tank, self.asset, self.panel, second_panel):
            self.ir(a)
        self.complete(self.tank)
        self.complete(self.asset)
        self.complete(self.panel, self.poor_panel)
        self.complete(second_panel, self.poor_panel)
        self.work_order.refresh_from_db()
        self.assertEqual(self.work_order.station_rating, 'poor')

    def test_station_without_generator_or_tank(self):
        Asset.objects.filter(pk__in=[self.asset.pk]).update(status=Asset.STATUS_RETIRED)
        self.tank.delete()
        self.complete(self.panel, self.poor_panel)
        self.work_order.refresh_from_db()
        self.assertEqual(self.work_order.station_rating, 'fair')

    def test_inactive_assets_do_not_block_the_visit(self):
        Asset.objects.filter(pk=self.tank.pk).update(status=Asset.STATUS_RETIRED)
        self.ir(self.asset), self.ir(self.panel)
        self.complete(self.panel)
        self.complete(self.asset)
        self.work_order.refresh_from_db()
        self.assertEqual(self.work_order.station_rating, 'good')

    def test_an_asset_with_no_inspection_yet_keeps_the_visit_open(self):
        self.ir(self.panel)
        self.complete(self.panel)  # generator and tank have no inspection response
        self.work_order.refresh_from_db()
        self.assertIsNone(self.work_order.station_rating)

    def test_reopening_an_asset_clears_its_rating_and_the_visit_rating(self):
        for a in (self.tank, self.asset, self.panel):
            self.ir(a)
        self.complete(self.panel)
        self.complete(self.tank)
        self.complete(self.asset)
        self.work_order.refresh_from_db()
        self.assertEqual(self.work_order.station_rating, 'good')

        ir = self.ir(self.panel)
        self.client.patch(f'/api/inspection-responses/{ir.id}/', {'done': False}, format='json')
        ir.refresh_from_db()
        self.work_order.refresh_from_db()
        self.assertIsNone(ir.rating)
        self.assertIsNone(self.work_order.station_rating)
        self.assertIsNone(self.work_order.visit_date)

    def test_visit_date_is_the_lagos_day(self):
        from unittest import mock
        self.ir(self.panel)
        Asset.objects.filter(pk__in=[self.asset.pk, self.tank.pk]).update(status=Asset.STATUS_RETIRED)
        # 23:30 UTC on 4 Nov is already 00:30 on 5 Nov in Lagos (UTC+1).
        late = datetime.datetime(2026, 11, 4, 23, 30, tzinfo=datetime.timezone.utc)
        with mock.patch('assets.ratings.timezone.now', return_value=late):
            self.complete(self.panel)
        self.work_order.refresh_from_db()
        self.assertEqual(self.work_order.visit_date, datetime.date(2026, 11, 5))

    def test_current_rating_is_the_latest_completed_visit_and_good_if_none(self):
        from .ratings import current_asset_rating
        self.assertEqual(current_asset_rating(self.panel), 'good')

        self.complete(self.panel, self.poor_panel)
        self.assertEqual(current_asset_rating(self.panel), 'poor')

        later = WorkOrder.objects.create(base_station=self.station, type=WorkOrder.TYPE_PREVENTIVE)
        InspectionResponse.objects.create(
            work_order=later, asset=self.panel, done=True, rating='fair',
            completed_at=timezone.now() + datetime.timedelta(days=1),
        )
        self.assertEqual(current_asset_rating(self.panel), 'fair')

        InspectionResponse.objects.create(work_order=later, asset=self.tank, rating=None)  # not complete
        self.assertEqual(current_asset_rating(self.tank), 'good')


class LitresAndDefectsApiTests(TechnicianAPITestCase):
    """Diesel levels take litres beside mm; saying "no issues" clears ticked defects."""

    def post_level(self, **extra):
        payload = {
            'asset': str(self.asset.id), 'reading_type': MeterReading.TYPE_DIESEL_LEVEL,
            'value': 1500, 'unit': MeterReading.UNIT_MM, **extra,
        }
        return self.client.post('/api/meter-readings/', payload)

    def test_diesel_level_stores_and_returns_litres_beside_mm(self):
        response = self.post_level(value_litres=2400)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual((response.data['value'], response.data['value_litres']), (1500, 2400))
        self.assertEqual(MeterReading.objects.get().value_litres, 2400)

    def test_litres_are_optional_for_older_clients(self):
        response = self.post_level()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.data['value_litres'])

    def test_litres_must_be_a_whole_number(self):
        for bad in ('abc', -5, 1.5):
            self.assertEqual(self.post_level(value_litres=bad).status_code, status.HTTP_400_BAD_REQUEST, bad)

    def test_run_hours_ignore_litres(self):
        response = self.client.post('/api/meter-readings/', {
            'asset': str(self.asset.id), 'reading_type': MeterReading.TYPE_RUN_HOURS,
            'value': 100, 'unit': MeterReading.UNIT_HOURS, 'value_litres': 50,
        })
        self.assertIsNone(response.data['value_litres'])

    def test_replayed_reading_keeps_its_litres(self):
        rid = str(uuid.uuid4())
        self.post_level(id=rid, value_litres=2400)
        again = self.post_level(id=rid, value_litres=9999)
        self.assertEqual(again.data['value_litres'], 2400)

    def test_delivery_stores_litres_levels_and_passes_them_to_the_reading(self):
        response = self.client.post('/api/diesel-deliveries/', {
            'base_station': str(self.station.id), 'quantity_litres': 200,
            'tank_level_before': 150, 'tank_level_after': 1500,
            'tank_level_before_litres': 240, 'tank_level_after_litres': 2400,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['tank_level_before_litres'], 240)
        self.assertEqual(response.data['tank_level_after_litres'], 2400)
        reading = MeterReading.objects.get(reading_type=MeterReading.TYPE_DIESEL_LEVEL)
        self.assertEqual((reading.value, reading.value_litres), (1500, 2400))

    def test_delivery_litres_levels_are_optional_and_validated(self):
        ok = self.client.post('/api/diesel-deliveries/', {
            'base_station': str(self.station.id), 'quantity_litres': 200,
        })
        self.assertEqual(ok.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(ok.data['tank_level_after_litres'])
        bad = self.client.post('/api/diesel-deliveries/', {
            'base_station': str(self.station.id), 'quantity_litres': 200, 'tank_level_after_litres': 'lots',
        })
        self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST)

    def test_saying_no_issues_clears_the_ticked_defects(self):
        work_order = WorkOrder.objects.create(base_station=self.station, type=WorkOrder.TYPE_PREVENTIVE)
        ir = InspectionResponse.objects.create(work_order=work_order, asset=self.asset, issues_found=True)
        defect = Condition.objects.create(name='Engine problems', asset_category=self.category, severity='poor')
        ir.conditions.set([defect])
        response = self.client.patch(f'/api/inspection-responses/{ir.id}/', {'issues_found': False}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['conditions'], [])
        self.assertEqual(ir.conditions.count(), 0)

    def test_conditions_in_the_response_carry_their_severity(self):
        work_order = WorkOrder.objects.create(base_station=self.station, type=WorkOrder.TYPE_PREVENTIVE)
        ir = InspectionResponse.objects.create(work_order=work_order, asset=self.asset, issues_found=True)
        defect = Condition.objects.create(name='Engine problems', asset_category=self.category, severity='poor')
        response = self.client.patch(
            f'/api/inspection-responses/{ir.id}/', {'conditions': [str(defect.id)]}, format='json',
        )
        self.assertEqual(response.data['conditions'][0]['severity'], 'poor')
        listed = self.client.get(f'/api/conditions/?asset_category={self.category.id}')
        self.assertEqual(listed.data[0]['severity'], 'poor')
