import io
import shutil
import tempfile
import uuid

from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import (
    Alarm, AlarmNote, Asset, AssetCategory, AssetCheckList, BaseStation,
    Cluster, ClusterGroup, Condition, DieselDelivery, InspectionResponse,
    Issue, Location, MeterReading, Part, PartRequest, PartUsage, PMQuestion,
    Personnel, Region, Role, SafetyReport, Vendor, WorkOrder,
    WorkOrderChecklistResponse,
)


class TechnicianAPITestCase(APITestCase):
    """Base fixture: one technician assigned to one base station with one asset."""

    def setUp(self):
        role_tech = Role.objects.create(name=Role.TECHNICIAN)
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


class PartRequestTests(TechnicianAPITestCase):
    def setUp(self):
        super().setUp()
        self.vendor = Vendor.objects.create(name="Parts Co", type=Vendor.TYPE_SUPPLIER)
        self.part = Part.objects.create(vendor=self.vendor, name="Oil Filter", sku="OF-1", unit_cost="10.00")

    def test_create_request(self):
        response = self.client.post('/api/part-requests/', {
            'part': str(self.part.id),
            'base_station': str(self.station.id),
            'quantity': 3,
            'reason': 'Due for replacement',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        pr = PartRequest.objects.get()
        self.assertEqual(pr.status, PartRequest.STATUS_REQUESTED)
        self.assertEqual(pr.requested_by, self.tech)

    def test_receive_marks_received(self):
        pr = PartRequest.objects.create(
            part=self.part, base_station=self.station, quantity=1, requested_by=self.tech,
        )
        response = self.client.post(f'/api/part-requests/{pr.id}/receive/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        pr.refresh_from_db()
        self.assertEqual(pr.status, PartRequest.STATUS_RECEIVED)
        self.assertIsNotNone(pr.received_at)

    def test_receive_twice_rejected(self):
        pr = PartRequest.objects.create(
            part=self.part, base_station=self.station, quantity=1, requested_by=self.tech,
            status=PartRequest.STATUS_RECEIVED, received_at=timezone.now(),
        )
        response = self.client.post(f'/api/part-requests/{pr.id}/receive/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_only_own_requests(self):
        other_tech = Personnel.objects.create_user(username="tech2", password="pass1234")
        PartRequest.objects.create(
            part=self.part, base_station=self.station, quantity=1, requested_by=other_tech,
        )
        response = self.client.get('/api/part-requests/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)


class PartUsageTests(TechnicianAPITestCase):
    def setUp(self):
        super().setUp()
        self.vendor = Vendor.objects.create(name="Parts Co", type=Vendor.TYPE_SUPPLIER)
        self.part = Part.objects.create(vendor=self.vendor, name="Oil Filter", sku="OF-1", unit_cost="10.00")
        self.work_order = WorkOrder.objects.create(base_station=self.station, type=WorkOrder.TYPE_PREVENTIVE)

    def test_log_usage(self):
        response = self.client.post('/api/part-usages/', {
            'work_order': str(self.work_order.id),
            'asset': str(self.asset.id),
            'part': str(self.part.id),
            'qty_used': 1,
            'notes': 'Old filter was clogged.',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        usage = PartUsage.objects.get()
        self.assertEqual(usage.recorded_by, self.tech)
        self.assertEqual(usage.asset, self.asset)

    def test_missing_fields_rejected(self):
        response = self.client.post('/api/part-usages/', {'work_order': str(self.work_order.id)})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_scoped_to_technician_stations(self):
        PartUsage.objects.create(
            work_order=self.work_order, asset=self.asset, part=self.part, qty_used=2,
        )
        response = self.client.get('/api/part-usages/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_list_filtered_by_asset(self):
        other_asset = Asset.objects.create(
            asset_category=self.category, location=self.location, name="Second asset",
        )
        PartUsage.objects.create(work_order=self.work_order, asset=self.asset, part=self.part, qty_used=1)
        PartUsage.objects.create(work_order=self.work_order, asset=other_asset, part=self.part, qty_used=1)
        response = self.client.get(f'/api/part-usages/?asset={self.asset.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['asset']['id'], str(self.asset.id))

    def test_list_filtered_by_work_order(self):
        other_wo = WorkOrder.objects.create(base_station=self.station, type=WorkOrder.TYPE_PREVENTIVE)
        PartUsage.objects.create(work_order=self.work_order, asset=self.asset, part=self.part, qty_used=1)
        PartUsage.objects.create(work_order=other_wo, asset=self.asset, part=self.part, qty_used=1)
        response = self.client.get(f'/api/part-usages/?work_order={self.work_order.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)


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
        role_tech = Role.objects.create(name=Role.TECHNICIAN)
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
        client_id = str(uuid.uuid4())
        payload = {'id': client_id, 'part': str(self.part.id), 'base_station': str(self.station.id), 'quantity': 2}
        first = self.client.post('/api/part-requests/', payload)
        second = self.client.post('/api/part-requests/', payload)
        self.assertEqual(first.data['id'], second.data['id'])
        self.assertEqual(PartRequest.objects.filter(id=client_id).count(), 1)

    def test_part_usage_replay_is_idempotent(self):
        client_id = str(uuid.uuid4())
        payload = {
            'id': client_id, 'work_order': str(self.work_order.id), 'asset': str(self.asset.id),
            'part': str(self.part.id), 'qty_used': 1,
        }
        first = self.client.post('/api/part-usages/', payload)
        second = self.client.post('/api/part-usages/', payload)
        self.assertEqual(first.data['id'], second.data['id'])
        self.assertEqual(PartUsage.objects.filter(id=client_id).count(), 1)

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
