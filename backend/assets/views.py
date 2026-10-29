import datetime
import json
import uuid

from django.conf import settings
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from .models import (
    WorkOrder, Alarm, AlarmNote, InspectionResponse,
    WorkOrderChecklistResponse, Issue, Condition, Asset,
    PMQuestion, AssetCheckList, AssetCategory, Attachment, BaseStation, DieselDelivery,
    MeterReading, Notification, Part, PartDelivery, PartRequest, PartRequestLine, PartStock,
    PartUsage, SafetyReport, Vendor,
)
from . import parts as parts_rules
from .serializers import (
    PersonnelSerializer, WorkOrderDetailSerializer, AlarmDetailSerializer,
    AlarmNoteSerializer, InspectionResponseDetailSerializer,
    ChecklistResponseSerializer, IssueSerializer, ConditionSerializer,
    BaseStationSummarySerializer, WorkOrderSummarySerializer,
    AlarmSummarySerializer, AssetSummarySerializer,
    AttachmentSerializer, DieselDeliverySerializer, MeterReadingSerializer,
    PartRequestSerializer, PartSerializer, PartUsageSerializer, ManagerRequestRowSerializer,
    NotificationSerializer, PartStockSerializer,
    SafetyReportSerializer, VendorSerializer,
    AssetCategorySerializer, PMQuestionSerializer,
)


# ── Auth ──────────────────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    from django.contrib.auth import authenticate
    username = request.data.get('username', '')
    password = request.data.get('password', '')
    user = authenticate(request, username=username, password=password)
    if not user:
        return Response({'detail': 'Invalid credentials.'}, status=status.HTTP_401_UNAUTHORIZED)
    refresh = RefreshToken.for_user(user)
    return Response({
        'access': str(refresh.access_token),
        'refresh': str(refresh),
        'user': PersonnelSerializer(user).data,
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def logout(request):
    try:
        token = RefreshToken(request.data.get('refresh'))
        token.blacklist()
    except (TokenError, Exception):
        pass
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['GET'])
def me(request):
    return Response(PersonnelSerializer(request.user).data)


# ── Today ─────────────────────────────────────────────────────────────────────

@api_view(['GET'])
def today(request):
    user = request.user
    today_date = timezone.localdate()

    assigned_stations = user.stations.prefetch_related('clients', 'manager').all()

    # Routine: today's preventive work orders for this technician's stations
    routine_wos = WorkOrder.objects.filter(
        base_station__in=assigned_stations,
        type=WorkOrder.TYPE_PREVENTIVE,
        due_date=today_date,
    ).select_related('base_station__manager').prefetch_related('base_station__clients')

    def wo_track_status(wo):
        if wo.submitted:
            return 'submitted'
        if wo.ended_at:
            return 'complete'
        if wo.started_at:
            return 'ongoing'
        return 'not_started'

    routine = [
        {
            'base_station': BaseStationSummarySerializer(wo.base_station).data,
            'work_order': WorkOrderSummarySerializer(wo).data,
            'track_status': wo_track_status(wo),
        }
        for wo in routine_wos
    ]

    # Alarms: open alarms + alarms resolved today for the technician's stations
    station_ids = [s.id for s in assigned_stations]

    open_alarms = Alarm.objects.filter(
        asset__location__base_station_id__in=station_ids,
        resolved_at__isnull=True,
    ).select_related(
        'asset__location__base_station__manager',
        'asset__asset_category',
    ).prefetch_related('asset__location__base_station__clients')

    resolved_today = Alarm.objects.filter(
        asset__location__base_station_id__in=station_ids,
        resolved_at__date=today_date,
    ).select_related(
        'asset__location__base_station__manager',
        'asset__asset_category',
    ).prefetch_related('asset__location__base_station__clients')

    seen_ids = set()
    all_alarms = []
    for a in list(open_alarms) + list(resolved_today):
        if a.id not in seen_ids:
            seen_ids.add(a.id)
            all_alarms.append(a)

    alarms = [
        {
            'base_station': BaseStationSummarySerializer(
                a.asset.location.base_station
            ).data if a.asset.location else {},
            'asset': AssetSummarySerializer(a.asset).data,
            'alarm': AlarmSummarySerializer(a).data,
            'track_status': 'resolved' if a.resolved_at else 'triggered',
        }
        for a in all_alarms
        if a.asset.location
    ]

    routine_complete = sum(1 for r in routine if r['track_status'] in ('complete', 'submitted'))
    alarms_resolved = sum(1 for a in alarms if a['track_status'] == 'resolved')

    return Response({
        'summary': {
            'maintenance': {'complete': routine_complete, 'total': len(routine)},
            'alarms': {'resolved': alarms_resolved, 'total': len(alarms)},
        },
        'routine': routine,
        'alarms': alarms,
    })


# ── Work Orders ───────────────────────────────────────────────────────────────

@api_view(['GET'])
def work_order_detail(request, pk):
    try:
        wo = WorkOrder.objects.select_related(
            'base_station__manager'
        ).prefetch_related(
            'base_station__clients',
            'inspection_responses__issues',
        ).get(pk=pk)
    except WorkOrder.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    return Response(WorkOrderDetailSerializer(wo).data)


def _get_or_create_inspection_response(wo, asset):
    """Create an InspectionResponse (and its checklist rows) for one asset within a work order, if missing."""
    ir, created = InspectionResponse.objects.get_or_create(work_order=wo, asset=asset)
    if created:
        checklists = AssetCheckList.objects.filter(asset_category=asset.asset_category)
        questions = PMQuestion.objects.filter(task_template__in=checklists)
        WorkOrderChecklistResponse.objects.bulk_create([
            WorkOrderChecklistResponse(inspection_response=ir, question=q)
            for q in questions
        ])
    return ir, created


@api_view(['POST'])
def work_order_start(request, pk):
    try:
        wo = WorkOrder.objects.get(pk=pk)
    except WorkOrder.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    if wo.started_at:
        return Response({'detail': 'Already started.'}, status=status.HTTP_400_BAD_REQUEST)

    geofence_verified = request.data.get('geofence_verified', False)
    wo.started_at = timezone.now()
    wo.geofence_verified = geofence_verified
    wo.status = WorkOrder.STATUS_IN_PROGRESS
    wo.save(update_fields=['started_at', 'geofence_verified', 'status', 'updated'])

    if wo.base_station_id:
        assets = Asset.objects.filter(
            location__base_station=wo.base_station, status=Asset.STATUS_ACTIVE
        ).select_related('asset_category')
        for asset in assets:
            _get_or_create_inspection_response(wo, asset)

    return Response({'started_at': wo.started_at, 'geofence_verified': wo.geofence_verified})


@api_view(['POST'])
def work_order_end(request, pk):
    try:
        wo = WorkOrder.objects.get(pk=pk)
    except WorkOrder.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    if not wo.started_at:
        return Response({'detail': 'Work order not started.'}, status=status.HTTP_400_BAD_REQUEST)

    # Completion is triggered explicitly per asset (the "Maintenance complete" button
    # on Asset Maintenance), not inferred here — ending the session no longer force-marks
    # anything done.
    wo.ended_at = timezone.now()
    wo.status = WorkOrder.STATUS_COMPLETE
    wo.save(update_fields=['ended_at', 'status', 'updated'])
    return Response({'ended_at': wo.ended_at})


# ── Alarms ────────────────────────────────────────────────────────────────────

@api_view(['POST'])
def alarms(request):
    """Dev/admin tool: manually raise a test alarm on an asset at one of the
    technician's assigned stations, for testing the alarm flow end to end."""
    asset_id = request.data.get('asset')
    if not asset_id:
        return Response({'detail': 'asset is required.'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        asset = Asset.objects.select_related('location__base_station').get(
            pk=asset_id, location__base_station__in=request.user.stations.all()
        )
    except Asset.DoesNotExist:
        return Response({'detail': 'Asset not found.'}, status=status.HTTP_404_NOT_FOUND)

    alarm, _ = Alarm.objects.get_or_create(
        id=request.data.get('id') or uuid.uuid4(),
        defaults={'asset': asset, 'raised_at': timezone.now()},
    )
    alarm = Alarm.objects.select_related(
        'asset__location__base_station__manager', 'resolved_by',
    ).prefetch_related('asset__location__base_station__clients', 'notes').get(pk=alarm.pk)
    return Response(AlarmDetailSerializer(alarm).data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
def alarm_detail(request, pk):
    try:
        alarm = Alarm.objects.select_related(
            'asset__location__base_station__manager',
            'resolved_by',
        ).prefetch_related(
            'asset__location__base_station__clients',
            'notes',
        ).get(pk=pk)
    except Alarm.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    return Response(AlarmDetailSerializer(alarm).data)


@api_view(['POST'])
def alarm_resolve(request, pk):
    try:
        alarm = Alarm.objects.get(pk=pk)
    except Alarm.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    if alarm.resolved_at:
        return Response({'detail': 'Already resolved.'}, status=status.HTTP_400_BAD_REQUEST)

    alarm.resolved_at = timezone.now()
    alarm.resolved_by = request.user
    alarm.save(update_fields=['resolved_at', 'resolved_by', 'updated'])
    return Response({
        'resolved_at': alarm.resolved_at,
        'resolved_by': {'id': str(request.user.id), 'name': request.user.name},
    })


@api_view(['POST'])
def alarm_add_note(request, pk):
    try:
        alarm = Alarm.objects.get(pk=pk)
    except Alarm.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    text = request.data.get('text', '').strip()
    if not text:
        return Response({'detail': 'text is required.'}, status=status.HTTP_400_BAD_REQUEST)

    note, _ = AlarmNote.objects.get_or_create(
        id=request.data.get('id') or uuid.uuid4(),
        defaults={'alarm': alarm, 'text': text},
    )
    return Response(AlarmNoteSerializer(note).data, status=status.HTTP_201_CREATED)


# ── Inspection Responses ──────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
def inspection_responses(request):
    if request.method == 'GET':
        qs = InspectionResponse.objects.filter(
            work_order__base_station__in=request.user.stations.all()
        ).prefetch_related('conditions', 'checklist_responses__question', 'issues')
        return Response(InspectionResponseDetailSerializer(qs, many=True).data)

    work_order_id = request.data.get('work_order')
    asset_id = request.data.get('asset')
    if not work_order_id or not asset_id:
        return Response(
            {'detail': 'work_order and asset are required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        wo = WorkOrder.objects.get(pk=work_order_id)
        asset = Asset.objects.select_related('asset_category').get(pk=asset_id)
    except (WorkOrder.DoesNotExist, Asset.DoesNotExist):
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    ir, created = _get_or_create_inspection_response(wo, asset)

    ir = InspectionResponse.objects.prefetch_related(
        'conditions', 'checklist_responses__question', 'issues'
    ).get(pk=ir.pk)
    return Response(
        InspectionResponseDetailSerializer(ir).data,
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


@api_view(['GET', 'PATCH'])
def inspection_response_detail(request, pk):
    try:
        ir = InspectionResponse.objects.prefetch_related(
            'conditions', 'checklist_responses__question', 'issues'
        ).get(pk=pk)
    except InspectionResponse.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response(InspectionResponseDetailSerializer(ir).data)

    base_updated_at = request.data.get('base_updated_at')
    if base_updated_at:
        base_dt = parse_datetime(base_updated_at)
        if base_dt and ir.updated > base_dt:
            return Response(InspectionResponseDetailSerializer(ir).data, status=status.HTTP_409_CONFLICT)

    if 'issues_found' in request.data:
        ir.issues_found = request.data['issues_found']
    if 'comments' in request.data:
        ir.comments = request.data['comments']
    if 'conditions' in request.data:
        ir.conditions.set(request.data['conditions'])
    if 'done' in request.data:
        done = request.data['done']
        if done:
            all_checked = not ir.checklist_responses.filter(checked=False).exists()
            has_comment = bool(ir.comments.strip())
            if not all_checked and not has_comment:
                return Response(
                    {'detail': 'Checklist is not fully checked, and no comment was given explaining why.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # Generators must have today's run-hours and diesel-level readings — no exception.
            if ir.asset.asset_category and ir.asset.asset_category.name == 'Generator':
                today = timezone.localdate()
                has_run_hours = ir.asset.meter_readings.filter(
                    reading_type=MeterReading.TYPE_RUN_HOURS, date=today
                ).exists()
                has_diesel_level = ir.asset.meter_readings.filter(
                    reading_type=MeterReading.TYPE_DIESEL_LEVEL, date=today
                ).exists()
                if not (has_run_hours and has_diesel_level):
                    return Response(
                        {'detail': "Today's run hours and diesel level readings are required for generators."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
        ir.done = done
    ir.save()

    ir = InspectionResponse.objects.prefetch_related(
        'conditions', 'checklist_responses__question', 'issues'
    ).get(pk=pk)
    return Response(InspectionResponseDetailSerializer(ir).data)


@api_view(['PATCH'])
def checklist_response_detail(request, pk):
    try:
        cr = WorkOrderChecklistResponse.objects.select_related('question').get(pk=pk)
    except WorkOrderChecklistResponse.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    base_updated_at = request.data.get('base_updated_at')
    if base_updated_at:
        base_dt = parse_datetime(base_updated_at)
        if base_dt and cr.updated > base_dt:
            return Response(ChecklistResponseSerializer(cr).data, status=status.HTTP_409_CONFLICT)

    if 'checked' in request.data:
        cr.checked = request.data['checked']
        cr.save(update_fields=['checked', 'updated'])
    return Response(ChecklistResponseSerializer(cr).data)


# ── Issues ────────────────────────────────────────────────────────────────────

@api_view(['POST'])
def issues(request):
    ir_id = request.data.get('inspection_response')
    description = request.data.get('description', '').strip()
    severity = request.data.get('severity')

    if not ir_id or not description or not severity:
        return Response(
            {'detail': 'inspection_response, description, and severity are required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if severity not in dict(Issue.SEVERITY_CHOICES):
        return Response({'detail': 'Invalid severity.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        ir = InspectionResponse.objects.get(pk=ir_id)
    except InspectionResponse.DoesNotExist:
        return Response({'detail': 'Inspection response not found.'}, status=status.HTTP_404_NOT_FOUND)

    issue, _ = Issue.objects.get_or_create(
        id=request.data.get('id') or uuid.uuid4(),
        defaults={'inspection_response': ir, 'description': description, 'severity': severity},
    )
    return Response(IssueSerializer(issue).data, status=status.HTTP_201_CREATED)


@api_view(['DELETE'])
def issue_detail(request, pk):
    try:
        issue = Issue.objects.get(pk=pk)
    except Issue.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    issue.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


# ── Conditions ────────────────────────────────────────────────────────────────

@api_view(['GET'])
def conditions(request):
    asset_category_id = request.query_params.get('asset_category')
    qs = Condition.objects.all()
    if asset_category_id:
        qs = qs.filter(asset_category_id=asset_category_id)
    return Response(ConditionSerializer(qs, many=True).data)


# ── Meter Readings ────────────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
def meter_readings(request):
    if request.method == 'GET':
        qs = MeterReading.objects.filter(asset__location__base_station__in=request.user.stations.all())
        asset_id = request.query_params.get('asset')
        if asset_id:
            qs = qs.filter(asset_id=asset_id)
        return Response(MeterReadingSerializer(qs, many=True).data)

    asset_id = request.data.get('asset')
    reading_type = request.data.get('reading_type')
    value = request.data.get('value')
    unit = request.data.get('unit')

    if not asset_id or not reading_type or value is None or not unit:
        return Response(
            {'detail': 'asset, reading_type, value, and unit are required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if reading_type not in dict(MeterReading.TYPE_CHOICES):
        return Response({'detail': 'Invalid reading_type.'}, status=status.HTTP_400_BAD_REQUEST)

    client_id = request.data.get('id')
    if client_id:
        existing = MeterReading.objects.filter(pk=client_id).first()
        if existing:
            # Already recorded (e.g. a queued offline write being replayed) — return it
            # as-is rather than re-running monotonicity checks against a since-changed
            # "most recent reading", which could reject a reading that already succeeded.
            return Response(MeterReadingSerializer(existing).data, status=status.HTTP_200_OK)

    try:
        asset = Asset.objects.get(pk=asset_id)
    except Asset.DoesNotExist:
        return Response({'detail': 'Asset not found.'}, status=status.HTTP_404_NOT_FOUND)

    try:
        value = int(value)
    except (TypeError, ValueError):
        return Response({'detail': 'value must be a number.'}, status=status.HTTP_400_BAD_REQUEST)

    previous = MeterReading.objects.filter(
        asset=asset, reading_type=reading_type
    ).order_by('-date', '-created').first()
    if previous:
        if reading_type == MeterReading.TYPE_RUN_HOURS and value < previous.value:
            return Response(
                {'detail': f'Run hours ({value}) cannot be less than the previous reading ({previous.value}).'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if reading_type == MeterReading.TYPE_DIESEL_LEVEL and value > previous.value:
            return Response(
                {
                    'detail': (
                        f'Diesel level ({value}mm) cannot be higher than the previous reading '
                        f'({previous.value}mm) — only a diesel delivery can raise it.'
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    reading = MeterReading.objects.create(
        id=client_id or uuid.uuid4(),
        asset=asset,
        reading_type=reading_type,
        value=value,
        unit=unit,
        date=request.data.get('date') or timezone.localdate(),
        work_order_id=request.data.get('work_order') or None,
        recorded_by=request.user,
    )
    return Response(MeterReadingSerializer(reading).data, status=status.HTTP_201_CREATED)


# ── Base Stations & Assets (pickers) ──────────────────────────────────────────

@api_view(['GET'])
def base_stations(request):
    qs = request.user.stations.select_related('manager').prefetch_related('clients')
    return Response(BaseStationSummarySerializer(qs, many=True).data)


@api_view(['GET'])
def assets(request):
    base_station_id = request.query_params.get('base_station')
    if not base_station_id:
        return Response({'detail': 'base_station is required.'}, status=status.HTTP_400_BAD_REQUEST)
    qs = Asset.objects.filter(
        location__base_station_id=base_station_id,
        location__base_station__in=request.user.stations.all(),
        status=Asset.STATUS_ACTIVE,
    ).order_by('name')
    return Response(AssetSummarySerializer(qs, many=True).data)


# ── Vendors & Parts ───────────────────────────────────────────────────────────

@api_view(['GET'])
def vendors(request):
    qs = Vendor.objects.all()
    vendor_type = request.query_params.get('type')
    if vendor_type:
        qs = qs.filter(type=vendor_type)
    return Response(VendorSerializer(qs, many=True).data)


@api_view(['GET'])
def parts(request):
    qs = Part.objects.all()
    search = request.query_params.get('search')
    if search:
        qs = qs.filter(name__icontains=search)
    kind = request.query_params.get('kind')
    if kind:
        qs = qs.filter(kind=kind)
    return Response(PartSerializer(qs, many=True).data)


# ── Diesel Deliveries ─────────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
def diesel_deliveries(request):
    if request.method == 'GET':
        qs = DieselDelivery.objects.filter(
            base_station__in=request.user.stations.all()
        ).select_related('base_station__manager', 'vendor').prefetch_related(
            'base_station__clients', 'attachments'
        )
        base_station_id = request.query_params.get('base_station')
        if base_station_id:
            qs = qs.filter(base_station_id=base_station_id)
        return Response(DieselDeliverySerializer(qs, many=True).data)

    base_station_id = request.data.get('base_station')
    quantity_litres = request.data.get('quantity_litres')

    if not base_station_id or not quantity_litres:
        return Response(
            {'detail': 'base_station and quantity_litres are required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    client_id = request.data.get('id')
    if client_id:
        existing = DieselDelivery.objects.filter(pk=client_id).first()
        if existing:
            # Already recorded — return as-is rather than re-running the diesel-level
            # side effect below a second time.
            return Response(DieselDeliverySerializer(existing).data, status=status.HTTP_200_OK)

    try:
        base_station = BaseStation.objects.get(pk=base_station_id)
    except BaseStation.DoesNotExist:
        return Response({'detail': 'Base station not found.'}, status=status.HTTP_404_NOT_FOUND)

    tank_level_after = request.data.get('tank_level_after') or None

    delivery = DieselDelivery.objects.create(
        id=client_id or uuid.uuid4(),
        base_station=base_station,
        work_order_id=request.data.get('work_order') or None,
        vendor_id=request.data.get('vendor') or None,
        quantity_litres=quantity_litres,
        tank_level_before=request.data.get('tank_level_before') or None,
        tank_level_after=tank_level_after,
        delivered_at=request.data.get('delivered_at') or timezone.now(),
        recorded_by=request.user,
        notes=request.data.get('notes', ''),
    )

    # A delivery is the one thing allowed to raise a generator's diesel level — record it
    # as a fresh reading so the Readings section and future validation see the new level.
    if tank_level_after is not None:
        generator = Asset.objects.filter(
            location__base_station=base_station, asset_category__name='Generator',
            status=Asset.STATUS_ACTIVE,
        ).first()
        if generator:
            MeterReading.objects.create(
                asset=generator,
                reading_type=MeterReading.TYPE_DIESEL_LEVEL,
                value=tank_level_after,
                unit=MeterReading.UNIT_MM,
                date=timezone.localdate(),
                work_order_id=request.data.get('work_order') or None,
                recorded_by=request.user,
            )

    return Response(DieselDeliverySerializer(delivery).data, status=status.HTTP_201_CREATED)


# ── Part Requests ─────────────────────────────────────────────────────────────

def _parts_error(exc):
    return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


def _request_queryset():
    return PartRequest.objects.select_related(
        'base_station__manager', 'requested_by', 'team_lead', 'cluster_team',
    ).prefetch_related('base_station__clients', 'lines__part', 'lines__deliveries__received_by',
                       'lines__deliveries__marked_delivered_by')


@api_view(['GET', 'POST'])
def part_requests(request):
    if request.method == 'GET':
        qs = _request_queryset().filter(requested_by=request.user)
        return Response(PartRequestSerializer(qs, many=True).data)

    base_station = BaseStation.objects.filter(pk=request.data.get('base_station')).first() \
        if request.data.get('base_station') else None
    if base_station is None:
        return Response({'detail': 'base_station is required.'}, status=status.HTTP_400_BAD_REQUEST)
    lines = request.data.get('lines') or []
    if isinstance(lines, str):
        try:
            lines = json.loads(lines)
        except ValueError:
            return Response({'detail': 'lines must be a list.'}, status=status.HTTP_400_BAD_REQUEST)
    if not isinstance(lines, list):
        return Response({'detail': 'lines must be a list.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        part_request, created = parts_rules.create_request(
            user=request.user,
            base_station=base_station,
            lines=lines,
            request_id=request.data.get('id') or None,
            work_order=WorkOrder.objects.filter(pk=request.data.get('work_order')).first()
            if request.data.get('work_order') else None,
            asset=Asset.objects.filter(pk=request.data.get('asset')).first()
            if request.data.get('asset') else None,
            notes=request.data.get('notes', ''),
        )
    except parts_rules.PartsError as exc:
        return _parts_error(exc)
    part_request = _request_queryset().get(pk=part_request.pk)
    return Response(
        PartRequestSerializer(part_request).data,
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


@api_view(['POST'])
def part_request_cancel(request, pk):
    part_request = PartRequest.objects.filter(pk=pk, requested_by=request.user).first()
    if part_request is None:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    try:
        parts_rules.cancel_request(part_request, by=request.user)
    except parts_rules.PartsError as exc:
        return _parts_error(exc)
    return Response(PartRequestSerializer(_request_queryset().get(pk=pk)).data)


@api_view(['POST'])
def part_request_line_receipts(request, pk):
    """The Field Team confirms they received parts before the delivery has been recorded."""
    line = PartRequestLine.objects.select_related('request').filter(pk=pk).first()
    if line is None:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    try:
        parts_rules.record_receipt(
            line, by=request.user, quantity=request.data.get('quantity'),
            delivery_id=request.data.get('id') or None,
        )
    except parts_rules.PartsError as exc:
        return _parts_error(exc)
    return Response(PartRequestSerializer(_request_queryset().get(pk=line.request_id)).data,
                    status=status.HTTP_201_CREATED)


@api_view(['POST'])
def part_delivery_confirm_received(request, pk):
    delivery = PartDelivery.objects.select_related('line__request').filter(pk=pk).first()
    if delivery is None:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    try:
        parts_rules.confirm_received(delivery, by=request.user)
    except parts_rules.PartsError as exc:
        return _parts_error(exc)
    return Response(PartRequestSerializer(_request_queryset().get(pk=delivery.line.request_id)).data)


# ── Part Usage ────────────────────────────────────────────────────────────────

def _usage_queryset():
    return PartUsage.objects.select_related(
        'part', 'asset', 'recorded_by', 'cluster_team', 'work_order__base_station',
    )


def _check_photo(upload):
    """Returns an error message, or None if the upload is an acceptable JPEG."""
    if upload.size > settings.PART_USAGE_PHOTO_MAX_BYTES:
        limit_mb = settings.PART_USAGE_PHOTO_MAX_BYTES / (1024 * 1024)
        return f'The photo is too large; the limit is {limit_mb:g} MB.'
    try:
        from PIL import Image
        image = Image.open(upload)
        image_format = image.format
        image.verify()
    except Exception:
        return 'The photo could not be read as an image.'
    finally:
        upload.seek(0)
    if image_format != 'JPEG':
        return 'The photo must be a JPEG.'
    return None


@api_view(['GET', 'POST'])
def part_usages(request):
    if request.method == 'GET':
        qs = _usage_queryset().filter(asset__location__base_station__in=request.user.stations.all())
        work_order_id = request.query_params.get('work_order')
        if work_order_id:
            qs = qs.filter(work_order_id=work_order_id)
        asset_id = request.query_params.get('asset')
        if asset_id:
            qs = qs.filter(asset_id=asset_id)
        return Response(PartUsageSerializer(qs, many=True, context={'request': request}).data)

    client_id = request.data.get('id')
    if client_id:
        existing = _usage_queryset().filter(pk=client_id).first()
        if existing:
            # Already recorded (an offline log replayed): return it without taking stock again.
            return Response(PartUsageSerializer(existing, context={'request': request}).data)

    work_order_id = request.data.get('work_order')
    asset_id = request.data.get('asset')
    part_id = request.data.get('part')
    qty_used = request.data.get('qty_used')

    if not work_order_id or not asset_id or not part_id or not qty_used:
        return Response(
            {'detail': 'work_order, asset, part, and qty_used are required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    photo = request.FILES.get('photo')
    if photo is None and settings.PART_USAGE_PHOTO_REQUIRED:
        return Response({'detail': 'A photo of the part is required.'}, status=status.HTTP_400_BAD_REQUEST)
    if photo is not None:
        problem = _check_photo(photo)
        if problem:
            return Response({'detail': problem}, status=status.HTTP_400_BAD_REQUEST)

    try:
        qty_used = int(qty_used)
    except (TypeError, ValueError):
        return Response({'detail': 'qty_used must be a whole number.'}, status=status.HTTP_400_BAD_REQUEST)
    if qty_used < 1:
        return Response({'detail': 'qty_used must be at least 1.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        wo = WorkOrder.objects.get(pk=work_order_id)
        asset = Asset.objects.get(pk=asset_id)
        part = Part.objects.get(pk=part_id)
    except (WorkOrder.DoesNotExist, Asset.DoesNotExist, Part.DoesNotExist):
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    taken_at = request.data.get('photo_taken_at')
    with transaction.atomic():
        usage = PartUsage(
            id=client_id or uuid.uuid4(),
            work_order=wo,
            asset=asset,
            part=part,
            qty_used=qty_used,
            notes=request.data.get('notes', ''),
            part_identifier=request.data.get('part_identifier', ''),
            photo_taken_at=parse_datetime(taken_at) if taken_at else None,
            cluster_team=request.user.cluster_team,
            recorded_by=request.user,
        )
        if photo is not None:
            usage.photo.save(f'{usage.id}.jpg', photo, save=False)
        usage.save()
        parts_rules.take_usage_from_stock(usage, by=request.user)
    return Response(
        PartUsageSerializer(_usage_queryset().get(pk=usage.pk), context={'request': request}).data,
        status=status.HTTP_201_CREATED,
    )


# ── Stock ─────────────────────────────────────────────────────────────────────

@api_view(['GET'])
def team_stock(request):
    """What the logged-in person's cluster team holds."""
    team = request.user.cluster_team
    if team is None:
        return Response({'cluster_team': None, 'items': []})
    qs = PartStock.objects.filter(cluster_team=team).select_related('part', 'cluster_team').order_by('part__name')
    return Response({
        'cluster_team': {'id': str(team.id), 'name': team.name},
        'items': PartStockSerializer(qs, many=True).data,
    })


# ── Cluster Manager lists ─────────────────────────────────────────────────────
# Scoped to the cluster the manager is assigned to. Role checks come with API enforcement later.

def _date_param(request, name):
    value = request.query_params.get(name)
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return None


@api_view(['GET'])
def manager_part_requests(request):
    qs = PartRequestLine.objects.filter(
        request__base_station__cluster_id=request.user.cluster_id,
    ).select_related(
        'part', 'request__base_station', 'request__requested_by', 'request__team_lead',
    ).prefetch_related('deliveries').order_by('-request__requested_at', 'created')
    params = request.query_params
    if params.get('base_station'):
        qs = qs.filter(request__base_station_id=params['base_station'])
    if params.get('part'):
        qs = qs.filter(part_id=params['part'])
    if params.get('status'):
        qs = qs.filter(status=params['status'])
    if params.get('backdated') in ('true', '1'):
        qs = qs.filter(is_backdated=True)
    date_from, date_to = _date_param(request, 'date_from'), _date_param(request, 'date_to')
    if date_from:
        qs = qs.filter(request__requested_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(request__requested_at__date__lte=date_to)
    return Response(ManagerRequestRowSerializer(qs, many=True).data)


@api_view(['GET'])
def manager_part_usages(request):
    qs = _usage_queryset().filter(work_order__base_station__cluster_id=request.user.cluster_id)
    params = request.query_params
    if params.get('base_station'):
        qs = qs.filter(work_order__base_station_id=params['base_station'])
    if params.get('part'):
        qs = qs.filter(part_id=params['part'])
    if params.get('recorded_by'):
        qs = qs.filter(recorded_by_id=params['recorded_by'])
    date_from, date_to = _date_param(request, 'date_from'), _date_param(request, 'date_to')
    if date_from:
        qs = qs.filter(created__date__gte=date_from)
    if date_to:
        qs = qs.filter(created__date__lte=date_to)
    return Response(PartUsageSerializer(qs, many=True, context={'request': request}).data)


@api_view(['GET'])
def manager_stock(request):
    """Stock held by each team in the manager's cluster, plus the cluster total per part."""
    rows = PartStock.objects.filter(
        cluster_team__cluster_id=request.user.cluster_id,
    ).select_related('part', 'cluster_team').order_by('cluster_team__name', 'part__name')
    totals = (
        rows.values('part_id', 'part__name', 'part__sku').annotate(qty=Sum('qty')).order_by('part__name')
    )
    return Response({
        'teams': PartStockSerializer(rows, many=True).data,
        'totals': [
            {'part': {'id': str(t['part_id']), 'name': t['part__name'], 'sku': t['part__sku']}, 'qty': t['qty']}
            for t in totals
        ],
    })


# ── Notifications ─────────────────────────────────────────────────────────────

@api_view(['GET'])
def notifications(request):
    qs = Notification.objects.filter(recipient=request.user)
    return Response({
        'unread': qs.filter(read_at__isnull=True).count(),
        'results': NotificationSerializer(qs[:100], many=True).data,
    })


@api_view(['POST'])
def notification_read(request, pk):
    notification = Notification.objects.filter(pk=pk, recipient=request.user).first()
    if notification is None:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
    if notification.read_at is None:
        notification.read_at = timezone.now()
        notification.save(update_fields=['read_at'])
    return Response(NotificationSerializer(notification).data)


# ── Safety Reports ────────────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
def safety_reports(request):
    if request.method == 'GET':
        qs = SafetyReport.objects.filter(
            base_station__in=request.user.stations.all()
        ).select_related('base_station__manager').prefetch_related(
            'base_station__clients', 'attachments'
        )
        return Response(SafetyReportSerializer(qs, many=True).data)

    base_station_id = request.data.get('base_station')
    report_type = request.data.get('type')
    severity = request.data.get('severity')
    description = request.data.get('description', '').strip()

    if not base_station_id or not report_type or not severity or not description:
        return Response(
            {'detail': 'base_station, type, severity, and description are required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if report_type not in dict(SafetyReport.TYPE_CHOICES):
        return Response({'detail': 'Invalid type.'}, status=status.HTTP_400_BAD_REQUEST)
    if severity not in dict(SafetyReport.SEVERITY_CHOICES):
        return Response({'detail': 'Invalid severity.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        base_station = BaseStation.objects.get(pk=base_station_id)
    except BaseStation.DoesNotExist:
        return Response({'detail': 'Base station not found.'}, status=status.HTTP_404_NOT_FOUND)

    report, _ = SafetyReport.objects.get_or_create(
        id=request.data.get('id') or uuid.uuid4(),
        defaults={
            'base_station': base_station,
            'work_order_id': request.data.get('work_order') or None,
            'type': report_type,
            'severity': severity,
            'description': description,
            'reported_by': request.user,
        },
    )
    return Response(SafetyReportSerializer(report).data, status=status.HTTP_201_CREATED)


# ── Attachments ───────────────────────────────────────────────────────────────

OWNER_FIELDS = ('asset', 'work_order', 'diesel_delivery', 'safety_report')


@api_view(['POST'])
@parser_classes([MultiPartParser])
def attachments(request):
    upload = request.data.get('file')
    attachment_type = request.data.get('type', '').strip()
    owners = {f'{f}_id': request.data.get(f) for f in OWNER_FIELDS if request.data.get(f)}

    if not upload or not attachment_type:
        return Response({'detail': 'file and type are required.'}, status=status.HTTP_400_BAD_REQUEST)
    if len(owners) != 1:
        return Response(
            {'detail': f'Exactly one of {", ".join(OWNER_FIELDS)} is required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    saved_path = default_storage.save(f'attachments/{upload.name}', upload)
    file_url = request.build_absolute_uri(default_storage.url(saved_path))

    attachment = Attachment.objects.create(file_url=file_url, type=attachment_type, **owners)
    return Response(AttachmentSerializer(attachment).data, status=status.HTTP_201_CREATED)


# ── Asset Categories & Checkpoints (admin reference/editor) ───────────────────
# Temporary admin-facing page: manages the shared checklist template per asset
# category. Any asset of that category, at any station, picks up these
# checkpoints automatically — this does not create physical Asset records.

def _category_checklist(category):
    """The category-level checklist template (asset_category set, pm_category/asset null)."""
    return AssetCheckList.objects.filter(
        asset_category=category, pm_category__isnull=True, asset__isnull=True
    ).prefetch_related('questions').first()


@api_view(['GET', 'POST'])
def asset_categories(request):
    if request.method == 'GET':
        categories = list(AssetCategory.objects.all())
        for category in categories:
            category._checklist = _category_checklist(category)
        return Response(AssetCategorySerializer(categories, many=True).data)

    name = request.data.get('name', '').strip()
    if not name:
        return Response({'detail': 'name is required.'}, status=status.HTTP_400_BAD_REQUEST)
    category = AssetCategory.objects.create(name=name)
    category._checklist = None
    return Response(AssetCategorySerializer(category).data, status=status.HTTP_201_CREATED)


@api_view(['PATCH'])
def asset_category_detail(request, pk):
    try:
        category = AssetCategory.objects.get(pk=pk)
    except AssetCategory.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    if 'name' in request.data:
        name = request.data['name'].strip()
        if not name:
            return Response({'detail': 'name cannot be blank.'}, status=status.HTTP_400_BAD_REQUEST)
        category.name = name
        category.save(update_fields=['name', 'updated'])

    category._checklist = _category_checklist(category)
    return Response(AssetCategorySerializer(category).data)


@api_view(['POST'])
def checklist_questions(request):
    category_id = request.data.get('asset_category')
    question_text = request.data.get('question', '').strip()
    if not category_id or not question_text:
        return Response(
            {'detail': 'asset_category and question are required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        category = AssetCategory.objects.get(pk=category_id)
    except AssetCategory.DoesNotExist:
        return Response({'detail': 'Asset category not found.'}, status=status.HTTP_404_NOT_FOUND)

    checklist, _ = AssetCheckList.objects.get_or_create(
        asset_category=category, pm_category=None, asset=None,
        defaults={'instructions': f'{category.name} routine inspection'},
    )
    question = PMQuestion.objects.create(task_template=checklist, question=question_text)
    return Response(PMQuestionSerializer(question).data, status=status.HTTP_201_CREATED)


@api_view(['PATCH', 'DELETE'])
def checklist_question_detail(request, pk):
    try:
        question = PMQuestion.objects.get(pk=pk)
    except PMQuestion.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'DELETE':
        question.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    question_text = request.data.get('question', '').strip()
    if not question_text:
        return Response({'detail': 'question cannot be blank.'}, status=status.HTTP_400_BAD_REQUEST)
    question.question = question_text
    question.save(update_fields=['question', 'updated'])
    return Response(PMQuestionSerializer(question).data)
