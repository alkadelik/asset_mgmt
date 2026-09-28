from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    Alarm,
    AlarmNote,
    Asset,
    AssetCategory,
    AssetChecklistCondition,
    AssetCheckList,
    Attachment,
    BaseStation,
    Client,
    Cluster,
    ClusterGroup,
    ClusterTeam,
    Condition,
    DieselDelivery,
    InspectionResponse,
    Issue,
    Location,
    MeterReading,
    Part,
    PartRequest,
    PartStock,
    PartUsage,
    Personnel,
    PMCategory,
    PMQuestion,
    PMSchedule,
    Region,
    Role,
    SafetyReport,
    Station,
    Vendor,
    WorkOrder,
    WorkOrderChecklistResponse,
)


# ── Inlines ──────────────────────────────────────────────────────────────────

class AssetChecklistConditionInline(admin.TabularInline):
    model = AssetChecklistCondition
    extra = 1
    fields = ('condition', 'grade', 'comment')


class PMQuestionInline(admin.TabularInline):
    model = PMQuestion
    extra = 1
    fields = ('question',)


class PartUsageInline(admin.TabularInline):
    model = PartUsage
    extra = 0
    fields = ('asset', 'part', 'qty_used', 'notes')
    autocomplete_fields = ('asset', 'part')


class MeterReadingInline(admin.TabularInline):
    model = MeterReading
    extra = 0
    fields = ('date', 'value', 'unit')


class MaintenanceListInline(admin.StackedInline):
    model = AssetCheckList
    fk_name = 'asset'
    extra = 0
    fields = ('instructions', 'estimated_duration', 'required_parts', 'condition', 'comments')
    filter_horizontal = ('required_parts',)
    verbose_name = 'Maintenance Item'
    verbose_name_plural = 'Maintenance List'


class AttachmentAssetInline(admin.TabularInline):
    model = Attachment
    extra = 0
    fields = ('file_url', 'type')
    verbose_name = 'Attachment'
    verbose_name_plural = 'Attachments'
    fk_name = 'asset'


class AttachmentWorkOrderInline(admin.TabularInline):
    model = Attachment
    extra = 0
    fields = ('file_url', 'type')
    verbose_name = 'Attachment'
    verbose_name_plural = 'Attachments'
    fk_name = 'work_order'


# ── Geography ─────────────────────────────────────────────────────────────────

@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ('name', 'created')
    search_fields = ('name',)
    readonly_fields = ('id', 'created', 'updated')


@admin.register(ClusterGroup)
class ClusterGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'region', 'created')
    list_filter = ('region',)
    search_fields = ('name',)
    autocomplete_fields = ('region',)
    readonly_fields = ('id', 'created', 'updated')


@admin.register(Cluster)
class ClusterAdmin(admin.ModelAdmin):
    list_display = ('name', 'cluster_group', 'created')
    list_filter = ('cluster_group__region', 'cluster_group')
    search_fields = ('name',)
    autocomplete_fields = ('cluster_group',)
    readonly_fields = ('id', 'created', 'updated')


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('get_name_display', 'created')
    search_fields = ('name',)
    readonly_fields = ('id', 'created', 'updated')


@admin.register(BaseStation)
class BaseStationAdmin(admin.ModelAdmin):
    list_display = ('name', 'site_id', 'site_classification', 'cluster', 'state', 'manager', 'created')
    list_filter = ('clients', 'site_classification', 'cluster__cluster_group__region', 'cluster__cluster_group', 'cluster', 'state')
    search_fields = ('name', 'site_id')
    autocomplete_fields = ('cluster', 'manager')
    filter_horizontal = ('clients',)
    readonly_fields = ('id', 'created', 'updated')


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ('name', 'base_station', 'parent_location')
    list_filter = ('base_station__cluster',)
    search_fields = ('name',)
    autocomplete_fields = ('base_station', 'parent_location')
    readonly_fields = ('id', 'created', 'updated')


@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'type', 'region', 'cluster_group', 'cluster', 'created')
    list_filter = ('type',)
    search_fields = ('address',)
    autocomplete_fields = ('region', 'cluster_group', 'cluster')
    readonly_fields = ('id', 'created', 'updated')


@admin.register(ClusterTeam)
class ClusterTeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'cluster', 'created')
    list_filter = ('cluster__cluster_group',)
    search_fields = ('name',)
    autocomplete_fields = ('cluster',)
    readonly_fields = ('id', 'created', 'updated')


# ── Personnel ─────────────────────────────────────────────────────────────────

@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('get_name_display', 'created')
    search_fields = ('name',)
    readonly_fields = ('id', 'created', 'updated')


@admin.register(Personnel)
class PersonnelAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Role & Assignment', {
            'fields': ('role', 'station', 'cluster_team', 'stations'),
        }),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Role & Assignment', {
            'fields': ('role', 'station', 'cluster_team'),
        }),
    )
    list_display = ('username', 'first_name', 'last_name', 'email', 'role', 'station', 'is_active')
    list_filter = UserAdmin.list_filter + ('role', 'station')
    search_fields = ('username', 'first_name', 'last_name', 'email')
    autocomplete_fields = ('role', 'station', 'cluster_team')
    filter_horizontal = ('stations',)
    readonly_fields = ('id', 'date_joined', 'last_login', 'updated')


# ── Assets ────────────────────────────────────────────────────────────────────

@admin.register(AssetCategory)
class AssetCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'maintenance_required', 'depreciation_method', 'created')
    list_filter = ('maintenance_required',)
    search_fields = ('name',)
    readonly_fields = ('id', 'created', 'updated')


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ('name', 'model', 'tag', 'status', 'asset_category', 'location', 'purchase_date')
    list_filter = ('status', 'asset_category')
    search_fields = ('name', 'tag', 'serial_number', 'model')
    autocomplete_fields = ('asset_category', 'location', 'parent_asset')
    readonly_fields = ('id', 'created', 'updated')
    inlines = (MaintenanceListInline, AssetChecklistConditionInline, AttachmentAssetInline,)
    fieldsets = (
        (None, {
            'fields': ('id', 'asset_category', 'location', 'parent_asset'),
        }),
        ('Identity', {
            'fields': ('name', 'model', 'tag', 'serial_number', 'status'),
        }),
        ('Financials', {
            'fields': ('purchase_date', 'purchase_cost', 'warranty_expiry', 'current_value'),
        }),
        ('Timestamps', {
            'fields': ('created', 'updated'),
            'classes': ('collapse',),
        }),
    )


# ── Preventive Maintenance ────────────────────────────────────────────────────

@admin.register(PMCategory)
class PMCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'created')
    search_fields = ('name',)
    readonly_fields = ('id', 'created', 'updated')


@admin.register(PMQuestion)
class PMQuestionAdmin(admin.ModelAdmin):
    list_display = ('question', 'task_template', 'created')
    search_fields = ('question',)
    autocomplete_fields = ('task_template',)
    readonly_fields = ('id', 'created', 'updated')


@admin.register(AssetCheckList)
class AssetCheckListAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'pm_category', 'asset_category', 'asset', 'condition', 'estimated_duration', 'created')
    list_filter = ('pm_category', 'asset_category', 'condition')
    search_fields = ('instructions',)
    autocomplete_fields = ('pm_category', 'asset_category', 'asset', 'required_parts')
    readonly_fields = ('id', 'created', 'updated')
    inlines = (PMQuestionInline,)
    filter_horizontal = ('required_parts',)


@admin.register(AssetChecklistCondition)
class AssetChecklistConditionAdmin(admin.ModelAdmin):
    list_display = ('asset', 'condition', 'grade', 'comment', 'created')
    list_filter = ('grade',)
    search_fields = ('comment', 'asset__name')
    autocomplete_fields = ('asset',)
    readonly_fields = ('id', 'created', 'updated')


@admin.register(PMSchedule)
class PMScheduleAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'asset_checklist', 'owner', 'trigger_type', 'interval', 'interval_unit', 'next_due_date')
    list_filter = ('trigger_type', 'interval_unit')
    search_fields = ('asset__name', 'category__name', 'asset_checklist__instructions')
    autocomplete_fields = ('asset', 'category', 'asset_checklist', 'owner')
    readonly_fields = ('id', 'created', 'updated')


# ── Work Orders ───────────────────────────────────────────────────────────────

class WorkOrderChecklistResponseInline(admin.TabularInline):
    model = WorkOrderChecklistResponse
    extra = 0
    fields = ('question', 'checked')
    autocomplete_fields = ('question',)
    readonly_fields = ('created',)


class IssueInline(admin.TabularInline):
    model = Issue
    extra = 0
    fields = ('description', 'severity', 'promoted_work_order')
    autocomplete_fields = ('promoted_work_order',)
    readonly_fields = ('created',)


class AlarmNoteInline(admin.TabularInline):
    model = AlarmNote
    extra = 1
    fields = ('text',)
    readonly_fields = ('created',)


@admin.register(WorkOrder)
class WorkOrderAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'type', 'status', 'priority', 'assigned_technician', 'due_date')
    list_filter = ('type', 'status', 'priority')
    search_fields = ('base_station__name', 'base_station__site_id', 'asset__name', 'asset__tag', 'description')
    autocomplete_fields = ('base_station', 'asset_category', 'asset', 'pm_schedule', 'asset_checklist', 'assigned_technician')
    readonly_fields = ('id', 'created', 'updated')
    inlines = (PartUsageInline, MeterReadingInline, AttachmentWorkOrderInline)
    fieldsets = (
        ('Target', {
            'fields': ('id', 'base_station', 'asset_category', 'asset'),
            'description': 'Set exactly one of: base station, asset category, or asset.',
        }),
        ('Work Order', {
            'fields': ('type', 'status', 'priority'),
        }),
        ('PM Link', {
            'fields': ('pm_schedule', 'asset_checklist', 'instructions_snapshot'),
            'classes': ('collapse',),
        }),
        ('Assignment & Schedule', {
            'fields': ('assigned_technician', 'due_date', 'completed_date'),
        }),
        ('Details', {
            'fields': ('description', 'cost_labour', 'cost_parts'),
        }),
        ('Timestamps', {
            'fields': ('created', 'updated'),
            'classes': ('collapse',),
        }),
    )


# ── Parts & Stock ─────────────────────────────────────────────────────────────

@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'email', 'phone_number', 'created')
    list_filter = ('type',)
    search_fields = ('name', 'email')
    readonly_fields = ('id', 'created', 'updated')


@admin.register(Part)
class PartAdmin(admin.ModelAdmin):
    list_display = ('name', 'sku', 'vendor', 'unit_cost', 'created')
    list_filter = ('vendor',)
    search_fields = ('name', 'sku')
    autocomplete_fields = ('vendor',)
    readonly_fields = ('id', 'created', 'updated')


@admin.register(PartStock)
class PartStockAdmin(admin.ModelAdmin):
    list_display = ('part', 'cluster_group', 'qty', 'reorder_threshold')
    list_filter = ('cluster_group',)
    search_fields = ('part__name', 'part__sku')
    autocomplete_fields = ('part', 'cluster_group')
    readonly_fields = ('id', 'created', 'updated')


# ── Supporting models ─────────────────────────────────────────────────────────

@admin.register(MeterReading)
class MeterReadingAdmin(admin.ModelAdmin):
    list_display = ('asset', 'reading_type', 'date', 'value', 'unit', 'work_order')
    list_filter = ('reading_type', 'unit')
    search_fields = ('asset__name', 'asset__tag')
    autocomplete_fields = ('asset', 'work_order', 'recorded_by')
    readonly_fields = ('id', 'created', 'updated')


@admin.register(DieselDelivery)
class DieselDeliveryAdmin(admin.ModelAdmin):
    list_display = ('base_station', 'quantity_litres', 'vendor', 'delivered_at', 'recorded_by')
    list_filter = ('vendor',)
    search_fields = ('base_station__name', 'base_station__site_id')
    autocomplete_fields = ('base_station', 'work_order', 'vendor', 'recorded_by')
    readonly_fields = ('id', 'created', 'updated')


@admin.register(PartRequest)
class PartRequestAdmin(admin.ModelAdmin):
    list_display = ('part', 'base_station', 'quantity', 'status', 'requested_by', 'requested_at')
    list_filter = ('status',)
    search_fields = ('part__name', 'part__sku', 'base_station__name', 'base_station__site_id')
    autocomplete_fields = ('part', 'base_station', 'work_order', 'asset', 'requested_by')
    readonly_fields = ('id', 'requested_at', 'created', 'updated')


@admin.register(PartUsage)
class PartUsageAdmin(admin.ModelAdmin):
    list_display = ('part', 'asset', 'qty_used', 'work_order', 'recorded_by', 'created')
    search_fields = ('part__name', 'part__sku', 'asset__name', 'asset__tag')
    autocomplete_fields = ('work_order', 'asset', 'part', 'recorded_by')
    readonly_fields = ('id', 'created', 'updated')


@admin.register(SafetyReport)
class SafetyReportAdmin(admin.ModelAdmin):
    list_display = ('base_station', 'type', 'severity', 'reported_by', 'created')
    list_filter = ('type', 'severity')
    search_fields = ('base_station__name', 'base_station__site_id', 'description')
    autocomplete_fields = ('base_station', 'work_order', 'reported_by')
    readonly_fields = ('id', 'created', 'updated')


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ('type', 'asset', 'work_order', 'diesel_delivery', 'safety_report', 'file_url', 'created')
    list_filter = ('type',)
    search_fields = ('asset__name', 'work_order__id')
    autocomplete_fields = ('asset', 'work_order', 'diesel_delivery', 'safety_report')
    readonly_fields = ('id', 'created', 'updated')


@admin.register(Condition)
class ConditionAdmin(admin.ModelAdmin):
    list_display = ('name', 'asset_category', 'created')
    list_filter = ('asset_category',)
    search_fields = ('name',)
    autocomplete_fields = ('asset_category',)
    readonly_fields = ('id', 'created', 'updated')


@admin.register(InspectionResponse)
class InspectionResponseAdmin(admin.ModelAdmin):
    list_display = ('asset', 'work_order', 'issues_found', 'done', 'created')
    list_filter = ('issues_found', 'done')
    search_fields = ('asset__name', 'asset__tag', 'work_order__id')
    autocomplete_fields = ('work_order', 'asset')
    filter_horizontal = ('conditions',)
    readonly_fields = ('id', 'created', 'updated')
    inlines = (WorkOrderChecklistResponseInline, IssueInline)


@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    list_display = ('inspection_response', 'severity', 'description', 'promoted_work_order', 'created')
    list_filter = ('severity',)
    search_fields = ('description',)
    autocomplete_fields = ('inspection_response', 'promoted_work_order')
    readonly_fields = ('id', 'created', 'updated')


@admin.register(Alarm)
class AlarmAdmin(admin.ModelAdmin):
    list_display = ('asset', 'raised_at', 'resolved_at', 'resolved_by', 'work_order')
    list_filter = ('resolved_at',)
    search_fields = ('asset__name', 'asset__tag')
    autocomplete_fields = ('asset', 'work_order', 'resolved_by')
    readonly_fields = ('id', 'created', 'updated')
    inlines = (AlarmNoteInline,)


@admin.register(WorkOrderChecklistResponse)
class WorkOrderChecklistResponseAdmin(admin.ModelAdmin):
    list_display = ('inspection_response', 'question', 'checked', 'created')
    list_filter = ('checked',)
    search_fields = ('inspection_response__asset__name', 'question__question')
    autocomplete_fields = ('inspection_response', 'question')
    readonly_fields = ('id', 'created', 'updated')


@admin.register(AlarmNote)
class AlarmNoteAdmin(admin.ModelAdmin):
    list_display = ('alarm', 'text', 'created')
    search_fields = ('text',)
    autocomplete_fields = ('alarm',)
    readonly_fields = ('id', 'created')
