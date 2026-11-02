"""Maintenance report endpoints for the Cluster Manager, scoped to the stations they can access."""
import datetime

from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from . import ratings, reports
from .permissions import IsClusterManager
from .models import (
    Alarm, Asset, AssetCategory, DieselDelivery, InspectionResponse, MeterReading, Personnel, Role,
)


def _week(request):
    """The Monday of the requested week (any date in it will do), or this week."""
    raw = request.query_params.get('week')
    if not raw:
        return reports.week_start(reports.lagos_today())
    try:
        return reports.week_start(datetime.date.fromisoformat(raw))
    except ValueError:
        return None


def _month(request):
    raw = request.query_params.get('month')
    if not raw:
        return reports.month_bounds(reports.lagos_today())
    try:
        year, number = (int(x) for x in raw.split('-'))
        if len(raw) != 7 or not 1 <= number <= 12:
            raise ValueError
        return reports.month_bounds(datetime.date(year, number, 1))
    except ValueError:
        return None


def _bad(message):
    return Response({'detail': message}, status=status.HTTP_400_BAD_REQUEST)


def _stations(request):
    return list(request.user.accessible_stations().order_by('name'))


def _diesel(asset_ids):
    reading = MeterReading.objects.filter(
        asset_id__in=asset_ids, reading_type=MeterReading.TYPE_DIESEL_LEVEL,
    ).order_by('-date', '-created').first()
    if not reading:
        return None
    return {'value_mm': reading.value, 'value_litres': reading.value_litres, 'date': reading.date.isoformat()}


def _name(person):
    return person.name if person else None


@api_view(['GET'])
@permission_classes([IsClusterManager])
def overview(request):
    """Base stations overview: tiles and the week grid."""
    start = _week(request)
    if start is None:
        return _bad('week must be a date like 2026-11-02.')
    month_start, month_end = reports.month_bounds(reports.lagos_today())
    stations = _stations(request)
    end = start + datetime.timedelta(days=6)
    grid = reports.station_grid(stations, start, end)
    sla = [p for p in reports.sla_percent(stations, month_start, month_end).values() if p is not None]
    average = round(sum(sla) / len(sla), 1) if sla else None
    return Response({
        'week_start': start.isoformat(),
        'week_end': end.isoformat(),
        'days': [d.isoformat() for d in reports.week_days(start)],
        'month': month_start.strftime('%Y-%m'),
        'tiles': {
            'stations': len(stations),
            'visits_this_week': reports.complete_visits_in(stations, start, end),
            'average_sla_percent': average,
            'average_sla_colour': reports.colour(average),
        },
        'stations': [
            {'id': str(s.id), 'name': s.name, 'site_id': s.site_id, 'cells': grid[s.id]} for s in stations
        ],
    })


@api_view(['GET'])
@permission_classes([IsClusterManager])
def station_detail(request, pk):
    station = get_object_or_404(request.user.accessible_stations(), pk=pk)
    month = _month(request)
    if month is None:
        return _bad('month must look like 2026-11.')
    percent = reports.sla_percent([station], *month)[station.id]
    assets = list(reports.active_assets([station]).order_by('asset_category__group', 'name'))
    alarms = Alarm.objects.filter(asset__location__base_station=station).select_related('asset').order_by('-raised_at')
    visits = (
        reports.scheduled_visits([station]).filter(visit_date__isnull=False)
        .select_related('assigned_to').order_by('-visit_date', '-updated')[:20]
    )
    deliveries = DieselDelivery.objects.filter(base_station=station).select_related(
        'recorded_by', 'vendor',
    ).order_by('-delivered_at')[:20]

    def alarm_row(alarm):
        return {
            'id': str(alarm.id), 'asset_id': str(alarm.asset_id), 'asset_name': alarm.asset.name,
            'raised_at': alarm.raised_at.isoformat(),
            'resolved_at': alarm.resolved_at.isoformat() if alarm.resolved_at else None,
        }

    return Response({
        'id': str(station.id), 'name': station.name, 'site_id': station.site_id, 'address': station.address,
        'month': month[0].strftime('%Y-%m'),
        'overall_rating': reports.overall_rating(station),
        'sla_percent': percent,
        'sla_colour': reports.colour(percent),
        'diesel': _diesel([a.id for a in assets]),
        'urgent': [alarm_row(a) for a in alarms if a.resolved_at is None],
        'assets': [
            {
                'id': str(a.id), 'name': a.name, 'tag': a.tag, 'type': a.asset_category.name,
                'rating': ratings.current_asset_rating(a),
            }
            for a in assets
        ],
        'visits': [
            {
                'id': str(v.id), 'date': v.visit_date.isoformat(), 'rating': v.station_rating,
                'by': _name(v.assigned_to),
            }
            for v in visits
        ],
        'alarms': [alarm_row(a) for a in alarms[:20]],
        'deliveries': [
            {
                'id': str(d.id), 'delivered_at': d.delivered_at.isoformat(), 'quantity_litres': d.quantity_litres,
                'vendor': d.vendor.name if d.vendor else None,
                'before_mm': d.tank_level_before, 'before_litres': d.tank_level_before_litres,
                'after_mm': d.tank_level_after, 'after_litres': d.tank_level_after_litres,
                'by': _name(d.recorded_by),
            }
            for d in deliveries
        ],
    })


@api_view(['GET'])
@permission_classes([IsClusterManager])
def asset_detail(request, pk):
    asset = get_object_or_404(
        Asset.objects.select_related('asset_category', 'location__base_station'),
        pk=pk, location__base_station__in=request.user.accessible_stations(),
    )
    run_hours = MeterReading.objects.filter(
        asset=asset, reading_type=MeterReading.TYPE_RUN_HOURS,
    ).order_by('-date', '-created').first()
    checks = (
        InspectionResponse.objects.filter(asset=asset, done=True, rating__isnull=False)
        .select_related('work_order__assigned_to').order_by('-completed_at')[:30]
    )
    station = asset.location.base_station
    return Response({
        'id': str(asset.id), 'name': asset.name, 'tag': asset.tag, 'type': asset.asset_category.name,
        'station': {'id': str(station.id), 'name': station.name},
        'rating': ratings.current_asset_rating(asset),
        'run_hours': (
            {'value': run_hours.value, 'date': run_hours.date.isoformat()} if run_hours else None
        ),
        'diesel': _diesel([asset.id]),
        'history': [
            {
                'id': str(c.id), 'date': ratings.visit_date(c.completed_at).isoformat(), 'rating': c.rating,
                'by': _name(c.work_order.assigned_to), 'comments': c.comments,
            }
            for c in checks
        ],
    })


@api_view(['GET'])
@permission_classes([IsClusterManager])
def asset_types(request):
    stations = _stations(request)
    counts = dict(
        reports.active_assets(stations).values_list('asset_category_id').annotate(n=Count('id'))
    )
    return Response({'results': [
        {'id': str(t.id), 'name': t.name, 'group': t.group, 'count': counts.get(t.id, 0)}
        for t in AssetCategory.objects.order_by('group', 'name')
    ]})


@api_view(['GET'])
@permission_classes([IsClusterManager])
def asset_type_grid(request, pk):
    asset_type = get_object_or_404(AssetCategory, pk=pk)
    start = _week(request)
    if start is None:
        return _bad('week must be a date like 2026-11-02.')
    end = start + datetime.timedelta(days=6)
    having = {
        a.location.base_station_id
        for a in reports.active_assets(_stations(request)).filter(asset_category=asset_type)
    }
    stations = [s for s in _stations(request) if s.id in having]
    grid = reports.asset_type_grid(stations, asset_type, start, end)
    return Response({
        'type': {'id': str(asset_type.id), 'name': asset_type.name},
        'week_start': start.isoformat(),
        'week_end': end.isoformat(),
        'days': [d.isoformat() for d in reports.week_days(start)],
        'stations': [{'id': str(s.id), 'name': s.name, 'cells': grid[s.id]} for s in stations],
    })


@api_view(['GET'])
@permission_classes([IsClusterManager])
def staff(request):
    people = Personnel.objects.filter(
        cluster_team__cluster_id=request.user.cluster_id, role__name__in=Role.FIELD_ROLES, is_active=True,
    ) if request.user.cluster_id else Personnel.objects.none()
    rows = sorted(({'id': str(p.id), 'name': p.name} for p in people), key=lambda r: r['name'].lower())
    return Response({'results': rows})
