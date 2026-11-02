"""Asset and station ratings (Good / Fair / Poor), exactly as in HANDOFF.md 4.2."""
import zoneinfo

from django.utils import timezone

from .models import Asset, AssetCategory, InspectionResponse

GOOD, FAIR, POOR = 'good', 'fair', 'poor'
LAGOS = zoneinfo.ZoneInfo('Africa/Lagos')

_SPECIAL_TYPES = (AssetCategory.DIESEL_GENERATOR, AssetCategory.DIESEL_TANK)


def rating_from_severities(severities):
    """Any Poor defect -> Poor; else any Fair defect -> Fair; else Good (the default)."""
    severities = set(severities)
    if 'poor' in severities:
        return POOR
    if 'fair' in severities:
        return FAIR
    return GOOD


def station_rating_from_assets(assets):
    """`assets` is (asset type name, rating) for every active asset at the station.

    1. Poor if a Diesel Generator is Poor, or a Diesel Tank is Poor, or any two other
       assets are Poor. A station with no generator or tank only has the "two other" part.
    2. Good if no asset is Poor and no more than two are Fair.
    3. Fair otherwise.
    """
    assets = list(assets)
    if any(rating == POOR and name in _SPECIAL_TYPES for name, rating in assets):
        return POOR
    other_poor = sum(1 for name, rating in assets if rating == POOR and name not in _SPECIAL_TYPES)
    if other_poor >= 2:
        return POOR
    poor = sum(1 for _, rating in assets if rating == POOR)
    fair = sum(1 for _, rating in assets if rating == FAIR)
    if poor == 0 and fair <= 2:
        return GOOD
    return FAIR


def visit_date(moment=None):
    """The day the work was done, in Africa/Lagos."""
    return (moment or timezone.now()).astimezone(LAGOS).date()


def complete_asset(ir, moment=None):
    """Mark-complete: store the asset's rating from the defects ticked, then see whether that
    finished the visit."""
    moment = moment or timezone.now()
    ir.rating = rating_from_severities(ir.conditions.values_list('severity', flat=True))
    ir.completed_at = moment
    ir.done = True
    ir.save()
    update_visit(ir.work_order, moment)


def reopen_asset(ir):
    """An asset marked complete is reopened: its rating goes, and so does the visit's."""
    ir.rating = None
    ir.completed_at = None
    ir.done = False
    ir.save()
    update_visit(ir.work_order)


def update_visit(work_order, moment=None):
    """A visit is complete when every active asset at the station is marked complete. Store the
    station rating and visit date then; clear them if the visit is not (or no longer) complete."""
    active = Asset.objects.filter(location__base_station=work_order.base_station, status=Asset.STATUS_ACTIVE)
    responses = {
        ir.asset_id: ir
        for ir in InspectionResponse.objects.filter(work_order=work_order, asset__in=active)
        .select_related('asset__asset_category')
    }
    active_ids = list(active.values_list('id', flat=True))
    complete = bool(active_ids) and all(
        asset_id in responses and responses[asset_id].done and responses[asset_id].rating
        for asset_id in active_ids
    )
    if complete:
        work_order.station_rating = station_rating_from_assets(
            (ir.asset.asset_category.name, ir.rating) for ir in responses.values()
        )
        work_order.visit_date = visit_date(moment)
    else:
        work_order.station_rating = None
        work_order.visit_date = None
    work_order.save(update_fields=['station_rating', 'visit_date', 'updated'])


def current_asset_rating(asset):
    """The rating from the latest completed visit; Good if the asset has none yet."""
    latest = (
        InspectionResponse.objects.filter(asset=asset, done=True, rating__isnull=False)
        .order_by('-completed_at').first()
    )
    return latest.rating if latest else GOOD
