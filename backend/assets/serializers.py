from rest_framework import serializers
from .models import (
    Personnel, BaseStation, WorkOrder, InspectionResponse,
    WorkOrderChecklistResponse, Issue, Condition, Alarm, AlarmNote, Asset,
    Attachment, DieselDelivery, MeterReading, Part, PartRequest, PartUsage,
    SafetyReport, Vendor, AssetCategory, AssetCheckList, PMQuestion,
)


class PersonnelSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    stations = serializers.SerializerMethodField()

    class Meta:
        model = Personnel
        fields = ['id', 'username', 'first_name', 'last_name', 'role', 'stations']

    def get_role(self, obj):
        return obj.role.name if obj.role else None

    def get_stations(self, obj):
        return [str(s.id) for s in obj.stations.all()]


class BaseStationSummarySerializer(serializers.ModelSerializer):
    clients = serializers.SerializerMethodField()
    manager = serializers.SerializerMethodField()

    class Meta:
        model = BaseStation
        fields = ['id', 'site_id', 'name', 'site_classification', 'clients', 'manager']

    def get_clients(self, obj):
        return [c.get_name_display() for c in obj.clients.all()]

    def get_manager(self, obj):
        if obj.manager:
            return {'id': str(obj.manager.id), 'name': obj.manager.name}
        return None


class WorkOrderSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkOrder
        fields = ['id', 'started_at', 'ended_at', 'submitted']


class InspectionResponseSummarySerializer(serializers.ModelSerializer):
    issue_count = serializers.SerializerMethodField()

    class Meta:
        model = InspectionResponse
        fields = ['id', 'done', 'issue_count']

    def get_issue_count(self, obj):
        return obj.issues.count()


class WorkOrderAssetSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    inspection_response = serializers.SerializerMethodField()

    def get_inspection_response(self, obj):
        ir = getattr(obj, '_inspection_response', None)
        if ir is None:
            return None
        return InspectionResponseSummarySerializer(ir).data


class WorkOrderDetailSerializer(serializers.ModelSerializer):
    base_station = BaseStationSummarySerializer()
    assets = serializers.SerializerMethodField()

    class Meta:
        model = WorkOrder
        fields = [
            'id', 'base_station', 'status', 'started_at', 'ended_at',
            'submitted', 'submitted_at', 'geofence_verified', 'updated', 'assets',
        ]

    def get_assets(self, obj):
        if not obj.base_station_id:
            return []
        # All active assets at the base station (via location)
        all_assets = list(
            Asset.objects.filter(
                location__base_station=obj.base_station,
                status=Asset.STATUS_ACTIVE,
            ).order_by('name')
        )
        # Index inspection responses for this WO by asset_id
        irs = {ir.asset_id: ir for ir in obj.inspection_responses.prefetch_related('issues')}
        for asset in all_assets:
            asset._inspection_response = irs.get(asset.id)
        return WorkOrderAssetSerializer(all_assets, many=True).data


class AlarmSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Alarm
        fields = ['id', 'raised_at', 'resolved_at']


class AssetSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Asset
        fields = ['id', 'name']


class AlarmNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlarmNote
        fields = ['id', 'text', 'created']


class AlarmDetailSerializer(serializers.ModelSerializer):
    base_station = serializers.SerializerMethodField()
    resolved_by = serializers.SerializerMethodField()
    notes = AlarmNoteSerializer(many=True)
    assets = serializers.SerializerMethodField()

    class Meta:
        model = Alarm
        fields = [
            'id', 'base_station', 'raised_at', 'resolved_at',
            'resolved_by', 'updated', 'assets', 'notes',
        ]

    def get_base_station(self, obj):
        bs = getattr(obj.asset.location, 'base_station', None) if obj.asset.location else None
        if bs:
            return BaseStationSummarySerializer(bs).data
        return None

    def get_resolved_by(self, obj):
        if obj.resolved_by:
            return {'id': str(obj.resolved_by.id), 'name': obj.resolved_by.name}
        return None

    def get_assets(self, obj):
        return []


class ConditionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Condition
        fields = ['id', 'name']


class ChecklistResponseSerializer(serializers.ModelSerializer):
    question = serializers.SerializerMethodField()

    class Meta:
        model = WorkOrderChecklistResponse
        fields = ['id', 'question', 'checked', 'updated']

    def get_question(self, obj):
        return {'id': str(obj.question.id), 'question': obj.question.question}


class IssueSerializer(serializers.ModelSerializer):
    promoted_work_order = serializers.SerializerMethodField()

    class Meta:
        model = Issue
        fields = ['id', 'description', 'severity', 'promoted_work_order', 'created']

    def get_promoted_work_order(self, obj):
        return str(obj.promoted_work_order_id) if obj.promoted_work_order_id else None


class InspectionResponseDetailSerializer(serializers.ModelSerializer):
    asset = serializers.SerializerMethodField()
    work_order_id = serializers.UUIDField(source='work_order.id')
    conditions = ConditionSerializer(many=True)
    checklist_responses = ChecklistResponseSerializer(many=True)
    issues = IssueSerializer(many=True)

    class Meta:
        model = InspectionResponse
        fields = [
            'id', 'work_order_id', 'asset', 'issues_found', 'done',
            'comments', 'conditions', 'checklist_responses', 'issues',
            'created', 'updated',
        ]

    def get_asset(self, obj):
        return {
            'id': str(obj.asset.id),
            'name': obj.asset.name,
            'asset_category': {
                'id': str(obj.asset.asset_category.id),
                'name': obj.asset.asset_category.name,
            },
        }


# ── Meter Readings ────────────────────────────────────────────────────────────

class MeterReadingSerializer(serializers.ModelSerializer):
    class Meta:
        model = MeterReading
        fields = ['id', 'asset', 'reading_type', 'date', 'value', 'unit', 'work_order', 'created']
        read_only_fields = ['id', 'created']


# ── Vendors & Parts ───────────────────────────────────────────────────────────

class VendorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vendor
        fields = ['id', 'name', 'type']


class PartSerializer(serializers.ModelSerializer):
    class Meta:
        model = Part
        fields = ['id', 'name', 'sku', 'unit_cost']


# ── Attachments ───────────────────────────────────────────────────────────────

class AttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attachment
        fields = [
            'id', 'asset', 'work_order', 'diesel_delivery', 'safety_report',
            'file_url', 'type', 'created',
        ]
        read_only_fields = ['id', 'file_url', 'created']


# ── Diesel Deliveries ─────────────────────────────────────────────────────────

class DieselDeliverySerializer(serializers.ModelSerializer):
    base_station = BaseStationSummarySerializer(read_only=True)
    vendor = VendorSerializer(read_only=True)
    recorded_by = serializers.SerializerMethodField()
    attachments = AttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = DieselDelivery
        fields = [
            'id', 'base_station', 'work_order', 'vendor', 'quantity_litres',
            'tank_level_before', 'tank_level_after', 'delivered_at',
            'recorded_by', 'notes', 'attachments', 'created',
        ]
        read_only_fields = ['id', 'recorded_by', 'attachments', 'created']

    def get_recorded_by(self, obj):
        if obj.recorded_by:
            return {'id': str(obj.recorded_by.id), 'name': obj.recorded_by.name}
        return None


# ── Part Requests ─────────────────────────────────────────────────────────────

class PartRequestSerializer(serializers.ModelSerializer):
    part = PartSerializer(read_only=True)
    base_station = BaseStationSummarySerializer(read_only=True)
    requested_by = serializers.SerializerMethodField()

    class Meta:
        model = PartRequest
        fields = [
            'id', 'part', 'base_station', 'work_order', 'asset', 'quantity',
            'reason', 'status', 'requested_by', 'requested_at', 'received_at',
        ]
        read_only_fields = ['id', 'status', 'requested_by', 'requested_at', 'received_at']

    def get_requested_by(self, obj):
        if obj.requested_by:
            return {'id': str(obj.requested_by.id), 'name': obj.requested_by.name}
        return None


# ── Part Usage ────────────────────────────────────────────────────────────────

class PartUsageSerializer(serializers.ModelSerializer):
    part = PartSerializer(read_only=True)
    asset = AssetSummarySerializer(read_only=True)
    recorded_by = serializers.SerializerMethodField()

    class Meta:
        model = PartUsage
        fields = [
            'id', 'work_order', 'asset', 'part', 'qty_used', 'notes',
            'recorded_by', 'created',
        ]
        read_only_fields = ['id', 'recorded_by', 'created']

    def get_recorded_by(self, obj):
        if obj.recorded_by:
            return {'id': str(obj.recorded_by.id), 'name': obj.recorded_by.name}
        return None


# ── Safety Reports ────────────────────────────────────────────────────────────

class SafetyReportSerializer(serializers.ModelSerializer):
    base_station = BaseStationSummarySerializer(read_only=True)
    reported_by = serializers.SerializerMethodField()
    attachments = AttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = SafetyReport
        fields = [
            'id', 'base_station', 'work_order', 'type', 'severity',
            'description', 'reported_by', 'attachments', 'created',
        ]
        read_only_fields = ['id', 'reported_by', 'attachments', 'created']

    def get_reported_by(self, obj):
        if obj.reported_by:
            return {'id': str(obj.reported_by.id), 'name': obj.reported_by.name}
        return None


# ── Asset Categories & Checkpoints (admin reference/editor) ───────────────────

class PMQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PMQuestion
        fields = ['id', 'question']


class AssetCategorySerializer(serializers.ModelSerializer):
    checklist_id = serializers.SerializerMethodField()
    questions = serializers.SerializerMethodField()

    class Meta:
        model = AssetCategory
        fields = ['id', 'name', 'checklist_id', 'questions']

    def get_checklist_id(self, obj):
        checklist = getattr(obj, '_checklist', None)
        return str(checklist.id) if checklist else None

    def get_questions(self, obj):
        checklist = getattr(obj, '_checklist', None)
        if not checklist:
            return []
        return PMQuestionSerializer(checklist.questions.all(), many=True).data
