"""Business rules for part requests, deliveries, stock and usage.

The API views and the Django admin both go through these functions, so the rules hold
whichever one is used. Every stock change writes a StockMovement in the same transaction as
the quantity it changes.

Status of a request line:
    requested -> approved | declined | cancelled
    approved  -> pending   (a delivery confirmed by one side only)
    pending   -> approved  (that delivery completed, more still to come)
              -> delivered (all parts received)
    approved  -> delivered (closed short: the rest won't come)
"""
import datetime

from django.db import transaction
from django.utils import timezone

from .models import (
    Notification, PartDelivery, PartRequest, PartRequestLine, PartStock, Personnel, Role,
    StockMovement,
)


class PartsError(Exception):
    """A rule was broken. The message is safe to show the person who made the request."""


# ── Who is who ────────────────────────────────────────────────────────────────

def region_for_station(base_station):
    return base_station.cluster.cluster_group.region


def cluster_managers(cluster):
    return list(Personnel.objects.filter(role__name=Role.CLUSTER_MANAGER, cluster=cluster))


def regional_managers(region):
    """Regional Managers whose own station record is this region's office."""
    return list(Personnel.objects.filter(role__name=Role.REGIONAL_MANAGER, station__region=region))


def notify(recipients, event, message, **links):
    seen = set()
    for person in recipients:
        if person is None or person.pk in seen:
            continue
        seen.add(person.pk)
        Notification.objects.create(recipient=person, event=event, message=message, **links)


def _requester_and_lead(part_request):
    return [part_request.requested_by, part_request.team_lead]


# ── Stock ─────────────────────────────────────────────────────────────────────

def _locked_stock_row(part, region=None, team=None):
    lookup = {'part': part, 'region': region} if region is not None else {'part': part, 'cluster_team': team}
    row, _ = PartStock.objects.get_or_create(**lookup)
    return PartStock.objects.select_for_update().get(pk=row.pk)


def apply_movement(part, change, reason, *, region=None, team=None, delivery=None, usage=None,
                   note='', by=None):
    """Change one stock record by `change` and log it. Refuses to go below zero.
    Returns the StockMovement; its `stock_row` is the updated PartStock."""
    if (region is None) == (team is None):
        raise ValueError('Exactly one of region or team is required.')
    if change == 0:
        raise ValueError('A stock movement must change the quantity.')
    row = _locked_stock_row(part, region=region, team=team)
    if row.qty + change < 0:
        where = f'{region} regional store' if region is not None else f'team {team}'
        raise PartsError(f'{where} holds {row.qty} of {part.name}; it can\'t give {-change}.')
    row.qty += change
    row.save(update_fields=['qty', 'updated'])
    movement = StockMovement.objects.create(
        part=part, region=region, cluster_team=team, change=change, reason=reason,
        delivery=delivery, usage=usage, note=note, created_by=by,
    )
    movement.stock_row = row
    if region is not None and change < 0 and row.reorder_threshold and row.qty < row.reorder_threshold:
        notify(
            regional_managers(region), Notification.EVENT_LOW_STOCK,
            f'{part.name} at the {region} regional store is down to {row.qty} '
            f'(reorder level {row.reorder_threshold}).',
        )
    return movement


@transaction.atomic
def adjust_stock(part, change, *, region=None, team=None, note='', by=None):
    """A manual stock count, write-off or new stock in."""
    if not note.strip():
        raise PartsError('An adjustment needs a reason.')
    return apply_movement(
        part, change, StockMovement.REASON_ADJUSTMENT, region=region, team=team, note=note, by=by,
    )


# ── Requests ──────────────────────────────────────────────────────────────────

def _parse_quantity(value):
    try:
        qty = int(value)
    except (TypeError, ValueError):
        raise PartsError('Quantity must be a whole number.')
    if qty < 1:
        raise PartsError('Quantity must be at least 1.')
    return qty


def _parse_date(value):
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value))
    except ValueError:
        raise PartsError('Required date must be a date (YYYY-MM-DD).')


@transaction.atomic
def create_request(*, user, base_station, lines, request_id=None, work_order=None, asset=None, notes=''):
    """Create a request with all its lines, or nothing. Returns (request, created)."""
    if request_id:
        existing = PartRequest.objects.filter(pk=request_id).first()
        if existing:
            return existing, False
    if not user.cluster_team_id:
        raise PartsError('You need to be in a cluster team to request parts. Ask an admin to add you to one.')
    if not lines:
        raise PartsError('Add at least one part.')

    from .models import Part
    today = timezone.localdate()
    parsed, seen = [], set()
    for raw in lines:
        part = Part.objects.filter(pk=raw.get('part')).first() if raw.get('part') else None
        if part is None:
            raise PartsError('Each line needs a valid part.')
        if part.pk in seen:
            raise PartsError(f'{part.name} is listed twice; put the total on one line.')
        seen.add(part.pk)
        if not raw.get('required_date'):
            raise PartsError(f'{part.name} needs a required date.')
        parsed.append((part, _parse_quantity(raw.get('quantity')), _parse_date(raw['required_date'])))

    team = user.cluster_team
    req = PartRequest.objects.create(
        **({'id': request_id} if request_id else {}),
        base_station=base_station, work_order=work_order, asset=asset, notes=notes,
        requested_by=user, cluster_team=team, team_lead=team.team_lead,
    )
    for part, qty, required in parsed:
        PartRequestLine.objects.create(
            request=req, part=part, quantity=qty, required_date=required,
            is_backdated=required < today,
        )

    region = region_for_station(base_station)
    notify(
        regional_managers(region) + cluster_managers(base_station.cluster),
        Notification.EVENT_NEW_REQUEST,
        f'{user.name} requested {len(parsed)} part(s) for {base_station.site_id}.',
        part_request=req,
    )
    return req, True


@transaction.atomic
def cancel_request(part_request, *, by):
    lines = list(part_request.lines.select_for_update())
    if any(line.status != PartRequestLine.STATUS_REQUESTED for line in lines):
        raise PartsError('This request can\'t be cancelled: a part has already been decided on.')
    PartRequestLine.objects.filter(request=part_request).update(
        status=PartRequestLine.STATUS_CANCELLED, updated=timezone.now(),
    )
    notify(
        regional_managers(region_for_station(part_request.base_station)),
        Notification.EVENT_REQUEST_CANCELLED,
        f'{by.name} cancelled a request for {part_request.base_station.site_id}.',
        part_request=part_request,
    )


@transaction.atomic
def approve_line(line, *, by):
    if line.status != PartRequestLine.STATUS_REQUESTED:
        raise PartsError(f'Only a requested part can be approved (this one is {line.get_status_display()}).')
    line.status = PartRequestLine.STATUS_APPROVED
    line.decided_by, line.decided_at = by, timezone.now()
    line.save(update_fields=['status', 'decided_by', 'decided_at', 'updated'])
    notify(
        _requester_and_lead(line.request), Notification.EVENT_LINE_APPROVED,
        f'{line.quantity}x {line.part.name} for {line.request.base_station.site_id} was approved.',
        part_request=line.request, part_request_line=line,
    )


@transaction.atomic
def decline_line(line, *, by, reason):
    if not (reason or '').strip():
        raise PartsError('Declining needs a reason.')
    if line.status != PartRequestLine.STATUS_REQUESTED:
        raise PartsError(f'Only a requested part can be declined (this one is {line.get_status_display()}).')
    line.status = PartRequestLine.STATUS_DECLINED
    line.decline_reason = reason.strip()
    line.decided_by, line.decided_at = by, timezone.now()
    line.save(update_fields=['status', 'decline_reason', 'decided_by', 'decided_at', 'updated'])
    notify(
        _requester_and_lead(line.request), Notification.EVENT_LINE_DECLINED,
        f'{line.quantity}x {line.part.name} for {line.request.base_station.site_id} was declined: {line.decline_reason}',
        part_request=line.request, part_request_line=line,
    )


# ── Deliveries ────────────────────────────────────────────────────────────────

def _outstanding(line):
    return line.quantity - sum(d.quantity for d in line.deliveries.all())


def _check_deliverable(line, quantity):
    if line.status not in (PartRequestLine.STATUS_APPROVED, PartRequestLine.STATUS_PENDING):
        raise PartsError(f'Only an approved part can be delivered (this one is {line.get_status_display()}).')
    outstanding = _outstanding(line)
    if quantity > outstanding:
        raise PartsError(f'Only {outstanding} of {line.part.name} are still to be delivered.')


def _check_regional_store(line, quantity):
    """The regional store must hold enough, counting deliveries recorded but not yet received."""
    region = region_for_station(line.request.base_station)
    on_hand = PartStock.objects.filter(part=line.part, region=region).values_list('qty', flat=True).first() or 0
    promised = sum(
        d.quantity for d in PartDelivery.objects.filter(
            line__part=line.part, line__request__base_station__cluster__cluster_group__region=region,
            stock_moved=False, marked_delivered_at__isnull=False,
        )
    )
    if quantity > on_hand - promised:
        raise PartsError(
            f'The {region} regional store has {max(on_hand - promised, 0)} of {line.part.name} available; '
            f'add stock before delivering {quantity}.'
        )


def refresh_line_status(line):
    if line.status in (PartRequestLine.STATUS_DECLINED, PartRequestLine.STATUS_CANCELLED,
                       PartRequestLine.STATUS_REQUESTED):
        return line
    deliveries = list(line.deliveries.all())
    if line.closed_short:
        status = PartRequestLine.STATUS_DELIVERED
    elif any(d.is_pending for d in deliveries):
        status = PartRequestLine.STATUS_PENDING
    elif sum(d.quantity for d in deliveries if d.is_complete) >= line.quantity:
        status = PartRequestLine.STATUS_DELIVERED
    else:
        status = PartRequestLine.STATUS_APPROVED
    if status != line.status:
        line.status = status
        line.save(update_fields=['status', 'updated'])
    return line


def _complete_if_ready(delivery, by):
    if not delivery.is_complete or delivery.stock_moved:
        return
    line = delivery.line
    req = line.request
    if req.cluster_team is None:
        raise PartsError('This request has no cluster team to receive the parts.')
    region = region_for_station(req.base_station)
    apply_movement(line.part, -delivery.quantity, StockMovement.REASON_DELIVERY, region=region,
                   delivery=delivery, by=by)
    apply_movement(line.part, delivery.quantity, StockMovement.REASON_DELIVERY, team=req.cluster_team,
                   delivery=delivery, by=by)
    delivery.stock_moved = True
    delivery.save(update_fields=['stock_moved', 'updated'])


def check_can_record_delivery(line, quantity):
    quantity = _parse_quantity(quantity)
    _check_deliverable(line, quantity)
    _check_regional_store(line, quantity)


@transaction.atomic
def record_delivery(line, *, by, quantity, pickup_location=''):
    """The approver's side: parts handed over from the regional store."""
    line = PartRequestLine.objects.select_for_update().get(pk=line.pk)
    quantity = _parse_quantity(quantity)
    _check_deliverable(line, quantity)
    _check_regional_store(line, quantity)
    delivery = PartDelivery.objects.create(
        line=line, quantity=quantity, pickup_location=pickup_location,
        marked_delivered_by=by, marked_delivered_at=timezone.now(),
    )
    refresh_line_status(line)
    notify(
        _requester_and_lead(line.request), Notification.EVENT_DELIVERY_RECORDED,
        f'{quantity}x {line.part.name} for {line.request.base_station.site_id} is ready; confirm when you have it.',
        part_request=line.request, part_request_line=line, part_delivery=delivery,
    )
    return delivery


@transaction.atomic
def record_receipt(line, *, by, quantity, delivery_id=None):
    """The Field Team's side, when they confirm receipt before the delivery is recorded."""
    if delivery_id:
        existing = PartDelivery.objects.filter(pk=delivery_id).first()
        if existing:
            return existing
    line = PartRequestLine.objects.select_for_update().get(pk=line.pk)
    quantity = _parse_quantity(quantity)
    _check_deliverable(line, quantity)
    delivery = PartDelivery.objects.create(
        **({'id': delivery_id} if delivery_id else {}),
        line=line, quantity=quantity, received_by=by, received_at=timezone.now(),
    )
    refresh_line_status(line)
    _notify_received(delivery, by)
    return delivery


@transaction.atomic
def confirm_received(delivery, *, by):
    """The Field Team confirms a delivery the approver recorded."""
    delivery = PartDelivery.objects.select_for_update().get(pk=delivery.pk)
    if delivery.received_at:
        raise PartsError('This delivery has already been confirmed as received.')
    delivery.received_by, delivery.received_at = by, timezone.now()
    delivery.save(update_fields=['received_by', 'received_at', 'updated'])
    _complete_if_ready(delivery, by)
    refresh_line_status(delivery.line)
    _notify_received(delivery, by)
    return delivery


@transaction.atomic
def mark_delivered(delivery, *, by, pickup_location=None):
    """The approver confirms a delivery the Field Team already said they received."""
    delivery = PartDelivery.objects.select_for_update().get(pk=delivery.pk)
    if delivery.marked_delivered_at:
        raise PartsError('This delivery is already marked as delivered.')
    _check_regional_store(delivery.line, delivery.quantity)
    delivery.marked_delivered_by, delivery.marked_delivered_at = by, timezone.now()
    if pickup_location is not None:
        delivery.pickup_location = pickup_location
    delivery.save(update_fields=['marked_delivered_by', 'marked_delivered_at', 'pickup_location', 'updated'])
    _complete_if_ready(delivery, by)
    refresh_line_status(delivery.line)
    return delivery


def _notify_received(delivery, by):
    line = delivery.line
    notify(
        regional_managers(region_for_station(line.request.base_station)),
        Notification.EVENT_DELIVERY_RECEIVED,
        f'{by.name} received {delivery.quantity}x {line.part.name} for {line.request.base_station.site_id}.',
        part_request=line.request, part_request_line=line, part_delivery=delivery,
    )


@transaction.atomic
def close_short(line, *, by):
    """End a partly delivered line when the rest won't come. The shortfall is kept on record."""
    line = PartRequestLine.objects.select_for_update().get(pk=line.pk)
    if line.status != PartRequestLine.STATUS_APPROVED:
        raise PartsError('Only a partly delivered part with no delivery awaiting confirmation can be closed short.')
    if line.delivered_qty == 0:
        raise PartsError('Nothing has been delivered yet; decline or cancel instead.')
    if line.delivered_qty >= line.quantity:
        raise PartsError('Everything has been delivered; there is nothing to close.')
    line.closed_short = True
    line.closed_short_by, line.closed_short_at = by, timezone.now()
    line.save(update_fields=['closed_short', 'closed_short_by', 'closed_short_at', 'updated'])
    refresh_line_status(line)
    return line


# ── Usage ─────────────────────────────────────────────────────────────────────

def take_usage_from_stock(usage, *, by):
    """Take a usage log's quantity off the logging person's team stock.

    If the team holds too few, the shortfall is first added as "added at site", so stock
    never goes negative. A person in no team has no stock to draw from; nothing moves.
    """
    team = usage.cluster_team
    if team is None:
        return
    row = _locked_stock_row(usage.part, team=team)
    shortfall = usage.qty_used - row.qty
    if shortfall > 0:
        apply_movement(
            usage.part, shortfall, StockMovement.REASON_ADDED_AT_SITE, team=team, usage=usage, by=by,
            note=f'Logged {usage.qty_used} used at {usage.base_station.site_id}; team held {row.qty}.',
        )
        cluster = team.cluster
        notify(
            cluster_managers(cluster) + regional_managers(cluster.cluster_group.region),
            Notification.EVENT_ADDED_AT_SITE,
            f'{shortfall}x {usage.part.name} was added at site at {usage.base_station.site_id} '
            f'({team} held {row.qty}, used {usage.qty_used}).',
            part_usage=usage,
        )
    apply_movement(usage.part, -usage.qty_used, StockMovement.REASON_USAGE, team=team, usage=usage, by=by)
