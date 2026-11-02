"""Numbers and grids behind the Cluster Manager's Maintenance reports (HANDOFF.md 4.2, 4.3, 4.5).

A visit is a station-level preventive/inspection work order. It is scheduled on its due date and
complete once every active asset is marked complete (see ratings.update_visit). Visits sit on the day
they were done; a scheduled day with no complete visit that day is Missed once the day has passed.
"""
import datetime

from django.db.models import Q

from . import ratings
from .app_settings import colour_for_percent
from .models import Asset, InspectionResponse, WorkOrder

MISSED = 'missed'
_SEVERITY = {ratings.GOOD: 0, ratings.FAIR: 1, ratings.POOR: 2}
_VISIT_TYPES = (WorkOrder.TYPE_PREVENTIVE, WorkOrder.TYPE_INSPECTION)


def lagos_today():
    return ratings.visit_date()


def week_start(date):
    """Weeks run Monday to Sunday."""
    return date - datetime.timedelta(days=date.weekday())


def week_days(start):
    return [start + datetime.timedelta(days=i) for i in range(7)]


def month_bounds(date):
    first = date.replace(day=1)
    last = (first.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1)
    return first, last


def worst(*given):
    given = [r for r in given if r]
    return max(given, key=_SEVERITY.__getitem__) if given else None


def scheduled_visits(stations):
    return WorkOrder.objects.filter(base_station__in=stations, type__in=_VISIT_TYPES).exclude(
        status=WorkOrder.STATUS_CANCELLED,
    )


def station_grid(stations, start, end):
    """{station id: [cell for each day from start to end]}. A cell is good / fair / poor (a complete
    visit done that day), 'missed' (scheduled, the day has passed, no complete visit), or None."""
    today = lagos_today()
    days = [start + datetime.timedelta(days=i) for i in range((end - start).days + 1)]
    visits = scheduled_visits(stations).filter(
        Q(due_date__range=(start, end)) | Q(visit_date__range=(start, end)),
    )
    done, due = {}, set()
    for visit in visits:
        if visit.visit_date and start <= visit.visit_date <= end:
            key = (visit.base_station_id, visit.visit_date)
            done[key] = worst(done.get(key), visit.station_rating)
        if visit.due_date and start <= visit.due_date <= end:
            due.add((visit.base_station_id, visit.due_date))

    def cell(station_id, date):
        if (station_id, date) in done:
            return done[(station_id, date)]
        return MISSED if (station_id, date) in due and date < today else None

    return {station.id: [cell(station.id, d) for d in days] for station in stations}


def asset_type_grid(stations, asset_type, start, end):
    """Like station_grid, but each cell is the rating of this asset type's check that day."""
    today = lagos_today()
    days = [start + datetime.timedelta(days=i) for i in range((end - start).days + 1)]
    responses = InspectionResponse.objects.filter(
        asset__asset_category=asset_type, asset__location__base_station__in=stations,
        done=True, rating__isnull=False,
    ).select_related('asset__location')
    done = {}
    for response in responses:
        date = ratings.visit_date(response.completed_at)
        if start <= date <= end:
            key = (response.asset.location.base_station_id, date)
            done[key] = worst(done.get(key), response.rating)
    due = {
        (v.base_station_id, v.due_date)
        for v in scheduled_visits(stations).filter(due_date__range=(start, end))
    }

    def cell(station_id, date):
        if (station_id, date) in done:
            return done[(station_id, date)]
        return MISSED if (station_id, date) in due and date < today else None

    return {station.id: [cell(station.id, d) for d in days] for station in stations}


def sla_percent(stations, month_start, month_end):
    """Complete visits ÷ scheduled visits in the period, as {station id: percent or None}.
    A visit counts only if it was completed on the day it was scheduled; visits still ahead of
    today are not counted either way. Today's visit counts only once it is done."""
    today = lagos_today()
    cutoff = min(month_end, today)
    scheduled, complete = {}, {}
    for visit in scheduled_visits(stations).filter(due_date__range=(month_start, cutoff)):
        if visit.due_date == today and visit.visit_date != today:
            continue
        scheduled[visit.base_station_id] = scheduled.get(visit.base_station_id, 0) + 1
        if visit.visit_date == visit.due_date:
            complete[visit.base_station_id] = complete.get(visit.base_station_id, 0) + 1
    return {
        station.id: (
            round(100 * complete.get(station.id, 0) / scheduled[station.id], 1)
            if scheduled.get(station.id) else None
        )
        for station in stations
    }


def colour(percent):
    return None if percent is None else colour_for_percent(percent)


def complete_visits_in(stations, start, end):
    return scheduled_visits(stations).filter(visit_date__range=(start, end)).count()


def overall_rating(station):
    """The station's rating at its latest complete visit; Good if it has none."""
    latest = (
        scheduled_visits([station]).filter(visit_date__isnull=False, station_rating__isnull=False)
        .order_by('-visit_date', '-updated').first()
    )
    return latest.station_rating if latest else ratings.GOOD


def active_assets(stations):
    return Asset.objects.filter(
        location__base_station__in=stations, status=Asset.STATUS_ACTIVE,
    ).select_related('asset_category', 'location__base_station')
