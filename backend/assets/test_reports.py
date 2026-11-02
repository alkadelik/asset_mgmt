"""Cluster Manager report endpoints (HANDOFF.md 4.3 and 4.5)."""
import datetime
from unittest import mock

from django.utils import timezone
from rest_framework import status

from . import ratings
from . import tests as base
from .models import (
    Alarm, Asset, AssetCategory, BaseStation, ClusterTeam, DieselDelivery, InspectionResponse,
    Location, MeterReading, Personnel, Role, Setting, WorkOrder,
)

MONDAY = datetime.date(2026, 11, 2)
THURSDAY = MONDAY + datetime.timedelta(days=3)


def day(offset):
    return MONDAY + datetime.timedelta(days=offset)


def at_noon(date):
    return datetime.datetime.combine(date, datetime.time(12), tzinfo=ratings.LAGOS)


class ReportTestCase(base.TechnicianAPITestCase):
    """A cluster with the manager, one station with a generator and a tank, and a second empty one."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch('assets.reports.lagos_today', return_value=THURSDAY)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.tank_type = AssetCategory.objects.get(name=AssetCategory.DIESEL_TANK)
        self.panel_type = AssetCategory.objects.get(name='AC Control Panel')
        self.tank = Asset.objects.create(asset_category=self.tank_type, location=self.location, name='Tank')
        self.panel = Asset.objects.create(asset_category=self.panel_type, location=self.location, name='Panel')

        manager_role = Role.objects.get_or_create(name=Role.CLUSTER_MANAGER)[0]
        self.manager = Personnel.objects.create_user(username='cm', password='pass1234', first_name='Cora', last_name='Manager')
        self.manager.role = manager_role
        self.manager.cluster = self.station.cluster
        self.manager.save()

        self.second = BaseStation.objects.create(
            cluster=self.station.cluster, name='Second Station', address='2 Road', site_id='TST-002',
            site_classification=BaseStation.CLASS_PLATINUM,
        )
        second_location = Location.objects.create(base_station=self.second, name='Room')
        self.second_panel = Asset.objects.create(
            asset_category=self.panel_type, location=second_location, name='Second Panel',
        )
        self.client.force_authenticate(user=self.manager)

    def visit(self, station, due, rating_by_asset=None, done_on=None, complete=True, only=None):
        """A visit due on `due`. Completing marks every active asset at the station done (Good unless
        `rating_by_asset` says otherwise), on `done_on` (defaults to `due`)."""
        work_order = WorkOrder.objects.create(
            base_station=station, type=WorkOrder.TYPE_PREVENTIVE, due_date=due, assigned_to=self.tech,
        )
        if complete or only:
            moment = at_noon(done_on or due)
            assets = Asset.objects.filter(location__base_station=station, status=Asset.STATUS_ACTIVE)
            for asset in assets:
                if only and asset not in only:
                    continue
                InspectionResponse.objects.create(
                    work_order=work_order, asset=asset, done=True, completed_at=moment,
                    rating=(rating_by_asset or {}).get(asset, 'good'),
                )
            ratings.update_visit(work_order, moment)
        return work_order

    def get(self, url, **params):
        return self.client.get(url, params)


class OverviewTests(ReportTestCase):
    def cells(self, response, station):
        row = next(r for r in response.data['stations'] if r['id'] == str(station.id))
        return dict(zip(response.data['days'], row['cells']))

    def test_week_runs_monday_to_sunday_and_lists_every_station(self):
        response = self.get('/api/reports/overview/', week='2026-11-04')  # a Wednesday
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['week_start'], '2026-11-02')
        self.assertEqual(response.data['days'][0], '2026-11-02')
        self.assertEqual(response.data['days'][-1], '2026-11-08')
        self.assertEqual({r['name'] for r in response.data['stations']}, {'Test Station', 'Second Station'})

    def test_cells_follow_the_rules(self):
        poor = {self.asset: 'poor'}
        self.visit(self.station, day(0), poor)  # complete, generator Poor -> station Poor
        self.visit(self.station, day(1))  # complete, all Good
        self.visit(self.station, day(2), complete=False)  # scheduled, nothing done -> Missed
        self.visit(self.station, day(3), complete=False)  # today, not done yet -> empty
        self.visit(self.station, day(5), complete=False)  # in the future -> empty
        response = self.get('/api/reports/overview/', week='2026-11-02')
        cells = self.cells(response, self.station)
        self.assertEqual(cells['2026-11-02'], 'poor')
        self.assertEqual(cells['2026-11-03'], 'good')
        self.assertEqual(cells['2026-11-04'], 'missed')
        self.assertIsNone(cells['2026-11-05'])
        self.assertIsNone(cells['2026-11-06'])  # nothing scheduled
        self.assertIsNone(cells['2026-11-07'])  # future schedule not shown

    def test_partly_done_visit_is_missed(self):
        self.visit(self.station, day(0), complete=False, only=[self.asset])
        cells = self.cells(self.get('/api/reports/overview/', week='2026-11-02'), self.station)
        self.assertEqual(cells['2026-11-02'], 'missed')

    def test_a_visit_sits_on_the_day_it_was_done(self):
        self.visit(self.station, day(0), done_on=day(1))  # due Monday, done Tuesday
        cells = self.cells(self.get('/api/reports/overview/', week='2026-11-02'), self.station)
        self.assertEqual(cells['2026-11-02'], 'missed')
        self.assertEqual(cells['2026-11-03'], 'good')

    def test_cancelled_visits_are_ignored(self):
        work_order = self.visit(self.station, day(0), complete=False)
        work_order.status = WorkOrder.STATUS_CANCELLED
        work_order.save()
        cells = self.cells(self.get('/api/reports/overview/', week='2026-11-02'), self.station)
        self.assertIsNone(cells['2026-11-02'])

    def test_tiles(self):
        self.visit(self.station, day(0))
        self.visit(self.station, day(1), complete=False)  # Missed
        self.visit(self.second, day(0))
        self.visit(self.second, day(-7))  # last week: not in "this week"
        tiles = self.get('/api/reports/overview/', week='2026-11-02').data['tiles']
        self.assertEqual(tiles['stations'], 2)
        self.assertEqual(tiles['visits_this_week'], 2)
        # Test Station 1 of 2 done = 50%; Second Station 2 of 2 = 100% -> average 75
        self.assertEqual(tiles['average_sla_percent'], 75.0)
        self.assertEqual(tiles['average_sla_colour'], 'red')

    def test_average_sla_is_empty_when_nothing_was_scheduled(self):
        tiles = self.get('/api/reports/overview/', week='2026-11-02').data['tiles']
        self.assertIsNone(tiles['average_sla_percent'])
        self.assertIsNone(tiles['average_sla_colour'])

    def test_only_my_cluster(self):
        elsewhere = BaseStation.objects.create(
            cluster=self.station.cluster.cluster_group.clusters.create(name='Other'),
            name='Far Station', address='x', site_id='FAR-1', site_classification=BaseStation.CLASS_PLATINUM,
        )
        names = {r['name'] for r in self.get('/api/reports/overview/').data['stations']}
        self.assertNotIn(elsewhere.name, names)

    def test_bad_week_is_rejected(self):
        self.assertEqual(self.get('/api/reports/overview/', week='nope').status_code, 400)

    def test_defaults_to_the_current_week(self):
        self.assertEqual(self.get('/api/reports/overview/').data['week_start'], '2026-11-02')


class SlaTests(ReportTestCase):
    def sla(self, station=None, **params):
        return self.get(f'/api/reports/stations/{(station or self.station).id}/', **params).data

    def test_sla_is_complete_visits_over_scheduled_in_the_month(self):
        self.visit(self.station, day(0))
        self.visit(self.station, day(1), complete=False)
        data = self.sla()
        self.assertEqual(data['sla_percent'], 50.0)
        self.assertEqual(data['month'], '2026-11')

    def test_partial_visit_does_not_count(self):
        self.visit(self.station, day(0), complete=False, only=[self.asset])
        self.assertEqual(self.sla()['sla_percent'], 0.0)

    def test_visits_not_yet_due_do_not_count_against_the_station(self):
        self.visit(self.station, day(0))
        self.visit(self.station, day(5), complete=False)  # Saturday, still ahead
        self.assertEqual(self.sla()['sla_percent'], 100.0)

    def test_todays_visit_counts_only_once_done(self):
        today_visit = self.visit(self.station, THURSDAY, complete=False)
        self.assertIsNone(self.sla()['sla_percent'])  # the day is not over
        self.visit(self.station, day(0))
        self.assertEqual(self.sla()['sla_percent'], 100.0)
        today_visit.delete()
        self.visit(self.station, THURSDAY)
        self.assertEqual(self.sla()['sla_percent'], 100.0)

    def test_a_late_visit_does_not_count_for_the_day_it_was_due(self):
        self.visit(self.station, day(0), done_on=day(1))
        self.assertEqual(self.sla()['sla_percent'], 0.0)

    def test_other_months_are_not_counted(self):
        self.visit(self.station, datetime.date(2026, 10, 30))
        self.visit(self.station, day(0), complete=False)
        self.assertEqual(self.sla()['sla_percent'], 0.0)
        self.assertEqual(self.sla(month='2026-10')['sla_percent'], 100.0)

    def test_no_scheduled_visits_gives_no_percentage(self):
        data = self.sla()
        self.assertIsNone(data['sla_percent'])
        self.assertIsNone(data['sla_colour'])

    def test_colour_uses_the_saved_bands(self):
        self.visit(self.station, day(0))
        self.assertEqual(self.sla()['sla_colour'], 'green')
        Setting.objects.create(key='colour_bands', value={'green_min': 100.5, 'amber_min': 100})
        self.assertEqual(self.sla()['sla_colour'], 'amber')

    def test_bad_month_is_rejected(self):
        response = self.get(f'/api/reports/stations/{self.station.id}/', month='2026-13')
        self.assertEqual(response.status_code, 400)


class StationDetailTests(ReportTestCase):
    def detail(self, station=None, **params):
        response = self.get(f'/api/reports/stations/{(station or self.station).id}/', **params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data

    def test_overall_rating_is_the_latest_complete_visit_and_good_when_none(self):
        self.assertEqual(self.detail()['overall_rating'], 'good')
        self.visit(self.station, day(0), {self.asset: 'poor'})
        self.visit(self.station, day(1), {self.panel: 'fair'})
        self.assertEqual(self.detail()['overall_rating'], 'good')  # Tuesday: one Fair -> Good
        self.visit(self.station, day(2), {self.tank: 'poor'})
        self.assertEqual(self.detail()['overall_rating'], 'poor')

    def test_assets_show_their_current_rating(self):
        self.visit(self.station, day(0), {self.tank: 'fair', self.panel: 'poor'})
        rows = {a['name']: a for a in self.detail()['assets']}
        self.assertEqual(rows['Tank']['rating'], 'fair')
        self.assertEqual(rows['Panel']['rating'], 'poor')
        self.assertEqual(rows['Generator Set 1']['rating'], 'good')
        self.assertEqual(rows['Tank']['type'], 'Diesel Tank')

    def test_diesel_at_last_check_gives_litres_and_mm(self):
        MeterReading.objects.create(
            asset=self.asset, reading_type='diesel_level', date=day(0), value=300, unit='mm', value_litres=900,
        )
        MeterReading.objects.create(
            asset=self.asset, reading_type='diesel_level', date=day(2), value=250, unit='mm', value_litres=750,
        )
        diesel = self.detail()['diesel']
        self.assertEqual((diesel['value_mm'], diesel['value_litres'], diesel['date']), (250, 750, '2026-11-04'))

    def test_diesel_is_empty_without_a_reading(self):
        self.assertIsNone(self.detail()['diesel'])

    def test_urgent_items_are_open_alarms_only(self):
        Alarm.objects.create(asset=self.asset, raised_at=at_noon(day(0)))
        Alarm.objects.create(asset=self.tank, raised_at=at_noon(day(0)), resolved_at=at_noon(day(1)))
        data = self.detail()
        self.assertEqual([a['asset_name'] for a in data['urgent']], ['Generator Set 1'])
        self.assertEqual(len(data['alarms']), 2)  # history keeps the resolved one

    def test_visit_history_shows_who_and_the_rating(self):
        self.visit(self.station, day(0), {self.asset: 'poor'})
        self.visit(self.station, day(1), complete=False)  # not done: not in history
        history = self.detail()['visits']
        self.assertEqual(len(history), 1)
        self.assertEqual((history[0]['date'], history[0]['rating'], history[0]['by']), ('2026-11-02', 'poor', 'tech1'))

    def test_delivery_log(self):
        DieselDelivery.objects.create(
            base_station=self.station, quantity_litres=500, delivered_at=at_noon(day(1)),
            tank_level_before=100, tank_level_after=400, tank_level_before_litres=300, tank_level_after_litres=800,
            recorded_by=self.tech,
        )
        delivery = self.detail()['deliveries'][0]
        self.assertEqual(delivery['quantity_litres'], 500)
        self.assertEqual((delivery['before_mm'], delivery['before_litres']), (100, 300))
        self.assertEqual((delivery['after_mm'], delivery['after_litres']), (400, 800))
        self.assertEqual(delivery['by'], 'tech1')

    def test_station_outside_my_cluster_is_not_found(self):
        elsewhere = BaseStation.objects.create(
            cluster=self.station.cluster.cluster_group.clusters.create(name='Other'),
            name='Far Station', address='x', site_id='FAR-1', site_classification=BaseStation.CLASS_PLATINUM,
        )
        self.assertEqual(self.get(f'/api/reports/stations/{elsewhere.id}/').status_code, 404)


class AssetDetailTests(ReportTestCase):
    def detail(self, asset=None):
        response = self.get(f'/api/reports/assets/{(asset or self.asset).id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data

    def test_rating_run_hours_and_diesel(self):
        self.visit(self.station, day(0), {self.asset: 'fair'})
        MeterReading.objects.create(asset=self.asset, reading_type='run_hours', date=day(0), value=120, unit='hours')
        MeterReading.objects.create(asset=self.asset, reading_type='run_hours', date=day(2), value=150, unit='hours')
        MeterReading.objects.create(
            asset=self.asset, reading_type='diesel_level', date=day(2), value=250, unit='mm', value_litres=750,
        )
        data = self.detail()
        self.assertEqual(data['rating'], 'fair')
        self.assertEqual(data['run_hours']['value'], 150)
        self.assertEqual((data['diesel']['value_mm'], data['diesel']['value_litres']), (250, 750))
        self.assertEqual(data['type'], 'Diesel Generator')
        self.assertEqual(data['station']['name'], 'Test Station')

    def test_no_history_means_good_and_no_readings(self):
        data = self.detail(self.panel)
        self.assertEqual(data['rating'], 'good')
        self.assertIsNone(data['run_hours'])
        self.assertIsNone(data['diesel'])
        self.assertEqual(data['history'], [])

    def test_history_lists_completed_checks_with_who(self):
        self.visit(self.station, day(0), {self.asset: 'poor'})
        self.visit(self.station, day(1), {self.asset: 'good'})
        history = self.detail()['history']
        self.assertEqual([h['rating'] for h in history], ['good', 'poor'])  # newest first
        self.assertEqual(history[0]['by'], 'tech1')

    def test_asset_outside_my_cluster_is_not_found(self):
        elsewhere = BaseStation.objects.create(
            cluster=self.station.cluster.cluster_group.clusters.create(name='Other'),
            name='Far Station', address='x', site_id='FAR-1', site_classification=BaseStation.CLASS_PLATINUM,
        )
        far = Asset.objects.create(
            asset_category=self.panel_type, name='Far panel',
            location=Location.objects.create(base_station=elsewhere, name='Room'),
        )
        self.assertEqual(self.get(f'/api/reports/assets/{far.id}/').status_code, 404)


class AssetTypeTests(ReportTestCase):
    def test_every_type_with_its_count_in_my_cluster(self):
        response = self.get('/api/reports/asset-types/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows = {r['name']: r for r in response.data['results']}
        self.assertEqual(len(rows), 9)
        self.assertEqual(rows['AC Control Panel']['count'], 2)
        self.assertEqual(rows['Diesel Tank']['count'], 1)
        self.assertEqual(rows['Transformer']['count'], 0)
        self.assertEqual(rows['Diesel Generator']['group'], '2. Generator Power Supply')

    def test_retired_assets_are_not_counted(self):
        self.panel.status = Asset.STATUS_RETIRED
        self.panel.save()
        rows = {r['name']: r for r in self.get('/api/reports/asset-types/').data['results']}
        self.assertEqual(rows['AC Control Panel']['count'], 1)

    def test_single_type_grid_uses_that_assets_rating_per_day(self):
        self.visit(self.station, day(0), {self.panel: 'poor'})
        self.visit(self.station, day(1), {self.panel: 'fair'})
        self.visit(self.station, day(2), complete=False)
        response = self.get(f'/api/reports/asset-types/{self.panel_type.id}/grid/', week='2026-11-02')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['type']['name'], 'AC Control Panel')
        rows = {r['name']: dict(zip(response.data['days'], r['cells'])) for r in response.data['stations']}
        self.assertEqual(set(rows), {'Test Station', 'Second Station'})  # only stations with the type
        self.assertEqual(rows['Test Station']['2026-11-02'], 'poor')
        self.assertEqual(rows['Test Station']['2026-11-03'], 'fair')
        self.assertEqual(rows['Test Station']['2026-11-04'], 'missed')
        self.assertIsNone(rows['Test Station']['2026-11-06'])

    def test_grid_leaves_out_stations_without_that_type(self):
        response = self.get(f'/api/reports/asset-types/{self.tank_type.id}/grid/', week='2026-11-02')
        self.assertEqual([r['name'] for r in response.data['stations']], ['Test Station'])

    def test_unknown_type_is_not_found(self):
        import uuid
        self.assertEqual(self.get(f'/api/reports/asset-types/{uuid.uuid4()}/grid/').status_code, 404)


class StaffTests(ReportTestCase):
    def test_field_team_and_team_leads_in_my_cluster_by_name_only(self):
        team = ClusterTeam.objects.create(name='Team 1', cluster=self.station.cluster)
        lead_role = Role.objects.get_or_create(name=Role.TEAM_LEAD)[0]
        lead = Personnel.objects.create_user(username='lead', password='x', first_name='Lee', last_name='Lead')
        lead.role, lead.cluster_team = lead_role, team
        lead.save()
        self.tech.cluster_team = team
        self.tech.save()

        other_cluster = self.station.cluster.cluster_group.clusters.create(name='Other')
        other_team = ClusterTeam.objects.create(name='Team X', cluster=other_cluster)
        stranger = Personnel.objects.create_user(username='stranger', password='x')
        stranger.role, stranger.cluster_team = lead_role, other_team
        stranger.save()

        response = self.get('/api/reports/staff/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([r['name'] for r in response.data['results']], ['Lee Lead', 'tech1'])
        self.assertEqual(set(response.data['results'][0]), {'id', 'name'})


class AccessTests(ReportTestCase):
    URLS = (
        '/api/reports/overview/', '/api/reports/asset-types/', '/api/reports/staff/',
        '/api/manager/part-requests/', '/api/manager/part-usages/', '/api/manager/stock/',
        '/api/manager/requests-summary/', '/api/manager/usage-summary/',
    )

    def test_field_team_is_refused(self):
        self.client.force_authenticate(user=self.tech)
        for url in self.URLS:
            self.assertEqual(self.client.get(url).status_code, status.HTTP_403_FORBIDDEN, url)
        self.assertEqual(self.client.get(f'/api/reports/stations/{self.station.id}/').status_code, 403)
        self.assertEqual(self.client.get(f'/api/reports/assets/{self.asset.id}/').status_code, 403)
        self.assertEqual(self.client.get(f'/api/reports/asset-types/{self.panel_type.id}/grid/').status_code, 403)

    def test_cluster_manager_is_allowed(self):
        for url in self.URLS:
            self.assertEqual(self.client.get(url).status_code, status.HTTP_200_OK, url)

    def test_signed_out_is_refused(self):
        self.client.force_authenticate(user=None)
        for url in self.URLS:
            self.assertIn(self.client.get(url).status_code, (401, 403), url)
