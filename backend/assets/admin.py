from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin

from . import parts as parts_rules

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
    Notification,
    Part,
    PartDelivery,
    PartRequest,
    PartRequestLine,
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
    StockMovement,
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
    fields = ('asset', 'part', 'qty_used', 'notes', 'photo')
    autocomplete_fields = ('asset', 'part')
    readonly_fields = ('photo',)


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
            'fields': ('role', 'station', 'cluster_team', 'cluster', 'stations'),
        }),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Role & Assignment', {
            'fields': ('role', 'station', 'cluster_team', 'cluster'),
        }),
    )
    list_display = ('username', 'first_name', 'last_name', 'email', 'role', 'cluster_team', 'cluster', 'is_active')
    list_filter = UserAdmin.list_filter + ('role', 'station')
    search_fields = ('username', 'first_name', 'last_name', 'email')
    autocomplete_fields = ('role', 'station', 'cluster_team', 'cluster')
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
    list_display = ('__str__', 'type', 'status', 'priority', 'assigned_to', 'due_date')
    list_filter = ('type', 'status', 'priority')
    search_fields = ('base_station__name', 'base_station__site_id', 'asset__name', 'asset__tag', 'description')
    autocomplete_fields = ('base_station', 'asset_category', 'asset', 'pm_schedule', 'asset_checklist', 'assigned_to')
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
            'fields': ('assigned_to', 'due_date', 'completed_date'),
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
    list_display = ('name', 'sku', 'kind', 'unit', 'vendor', 'unit_cost', 'created')
    list_filter = ('kind', 'vendor')
    search_fields = ('name', 'sku')
    autocomplete_fields = ('vendor',)
    readonly_fields = ('id', 'created', 'updated')


@admin.register(PartStock)
class PartStockAdmin(admin.ModelAdmin):
    """Read-only quantities: stock changes only through movements, so the log explains every number.
    To change stock, add an Adjustment under Stock movements."""
    list_display = ('part', 'region', 'cluster_team', 'qty', 'reorder_threshold')
    list_filter = ('region', 'cluster_team__cluster')
    search_fields = ('part__name', 'part__sku')
    autocomplete_fields = ('part', 'region', 'cluster_team')
    readonly_fields = ('id', 'qty', 'created', 'updated')


class StockAdjustmentForm(forms.ModelForm):
    class Meta:
        model = StockMovement
        fields = ('part', 'region', 'cluster_team', 'change', 'note')

    def clean(self):
        data = super().clean()
        if bool(data.get('region')) == bool(data.get('cluster_team')):
            raise forms.ValidationError('Choose either a regional store or a cluster team, not both.')
        if not data.get('change'):
            raise forms.ValidationError('The change must be a non-zero number.')
        if not (data.get('note') or '').strip():
            raise forms.ValidationError('An adjustment needs a reason in the note.')
        if data.get('part'):
            holder = {'region': data['region']} if data.get('region') else {'cluster_team': data['cluster_team']}
            on_hand = PartStock.objects.filter(part=data['part'], **holder).values_list('qty', flat=True).first() or 0
            if on_hand + data['change'] < 0:
                raise forms.ValidationError(f'Only {on_hand} in stock there; this would go below zero.')
        return data


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    """The stock log. Adding one here records a manual adjustment (count, write-off, new stock in)."""
    form = StockAdjustmentForm
    list_display = ('created', 'part', 'region', 'cluster_team', 'change', 'reason', 'created_by')
    list_filter = ('reason', 'region')
    search_fields = ('part__name', 'part__sku', 'note')
    autocomplete_fields = ('part', 'region', 'cluster_team')

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        movement = parts_rules.adjust_stock(
            obj.part, obj.change, region=obj.region, team=obj.cluster_team, note=obj.note, by=request.user,
        )
        obj.pk, obj.created, obj._state.adding = movement.pk, movement.created, False
        self.message_user(request, f'Stock is now {movement.stock_row.qty}.', messages.SUCCESS)


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


class PartRequestLineInline(admin.TabularInline):
    model = PartRequestLine
    extra = 0
    fields = ('part', 'quantity', 'required_date', 'is_backdated', 'status', 'decline_reason')
    readonly_fields = ('is_backdated', 'status')
    autocomplete_fields = ('part',)
    show_change_link = True


@admin.register(PartRequest)
class PartRequestAdmin(admin.ModelAdmin):
    list_display = ('base_station', 'requested_by', 'cluster_team', 'requested_at')
    search_fields = ('base_station__name', 'base_station__site_id', 'requested_by__username')
    autocomplete_fields = ('base_station', 'work_order', 'asset', 'requested_by', 'cluster_team', 'team_lead')
    readonly_fields = ('id', 'requested_at', 'created', 'updated')
    inlines = (PartRequestLineInline,)


class PartDeliveryInline(admin.TabularInline):
    model = PartDelivery
    extra = 0
    fields = ('quantity', 'pickup_location', 'marked_delivered_by', 'marked_delivered_at',
              'received_by', 'received_at', 'stock_moved')
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class RecordDeliveryForm(forms.ModelForm):
    class Meta:
        model = PartDelivery
        fields = ('line', 'quantity', 'pickup_location')

    def clean(self):
        data = super().clean()
        if data.get('line') and data.get('quantity'):
            try:
                parts_rules.check_can_record_delivery(data['line'], data['quantity'])
            except parts_rules.PartsError as exc:
                raise forms.ValidationError(str(exc))
        return data


@admin.register(PartRequestLine)
class PartRequestLineAdmin(admin.ModelAdmin):
    """Stands in for the Regional Manager until that phase is built: approve, decline (fill in
    the decline reason first) and close short from the actions menu; record a delivery under
    Part deliveries."""
    list_display = ('part', 'request', 'quantity', 'delivered', 'required_date', 'is_backdated', 'status')
    list_filter = ('status', 'is_backdated')
    search_fields = ('part__name', 'part__sku', 'request__base_station__site_id')
    autocomplete_fields = ('request', 'part')
    readonly_fields = ('id', 'status', 'is_backdated', 'decided_by', 'decided_at', 'closed_short',
                       'closed_short_by', 'closed_short_at', 'created', 'updated')
    inlines = (PartDeliveryInline,)
    actions = ('approve', 'decline', 'close_short')

    @admin.display(description='Delivered')
    def delivered(self, obj):
        return f'{obj.delivered_qty} of {obj.quantity}'

    def _run(self, request, queryset, fn, done):
        ok = 0
        for line in queryset:
            try:
                fn(line)
                ok += 1
            except parts_rules.PartsError as exc:
                self.message_user(request, f'{line}: {exc}', messages.ERROR)
        if ok:
            self.message_user(request, f'{done} {ok} part(s).', messages.SUCCESS)

    @admin.action(description='Approve selected parts')
    def approve(self, request, queryset):
        self._run(request, queryset, lambda l: parts_rules.approve_line(l, by=request.user), 'Approved')

    @admin.action(description='Decline selected parts (uses each line\'s decline reason)')
    def decline(self, request, queryset):
        self._run(request, queryset,
                  lambda l: parts_rules.decline_line(l, by=request.user, reason=l.decline_reason), 'Declined')

    @admin.action(description='Close selected parts short')
    def close_short(self, request, queryset):
        self._run(request, queryset, lambda l: parts_rules.close_short(l, by=request.user), 'Closed')


@admin.register(PartDelivery)
class PartDeliveryAdmin(admin.ModelAdmin):
    """Adding a delivery here records it from the regional store (the approver's side)."""
    form = RecordDeliveryForm
    list_display = ('line', 'quantity', 'marked_delivered_at', 'received_at', 'stock_moved')
    list_filter = ('stock_moved',)
    autocomplete_fields = ('line',)
    actions = ('mark_delivered',)

    def has_change_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        delivery = parts_rules.record_delivery(
            obj.line, by=request.user, quantity=obj.quantity, pickup_location=obj.pickup_location,
        )
        obj.pk, obj._state.adding = delivery.pk, False

    @admin.action(description='Mark selected as delivered (Field Team already confirmed receipt)')
    def mark_delivered(self, request, queryset):
        for delivery in queryset:
            try:
                parts_rules.mark_delivered(delivery, by=request.user)
            except parts_rules.PartsError as exc:
                self.message_user(request, f'{delivery}: {exc}', messages.ERROR)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('created', 'recipient', 'event', 'message', 'read_at')
    list_filter = ('event',)
    search_fields = ('recipient__username', 'message')
    readonly_fields = [f.name for f in Notification._meta.fields]


@admin.register(PartUsage)
class PartUsageAdmin(admin.ModelAdmin):
    list_display = ('part', 'asset', 'qty_used', 'cluster_team', 'work_order', 'recorded_by', 'created')
    search_fields = ('part__name', 'part__sku', 'asset__name', 'asset__tag')
    autocomplete_fields = ('work_order', 'asset', 'part', 'recorded_by', 'cluster_team')
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
