import uuid

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class Region(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class ClusterGroup(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    region = models.ForeignKey(Region, on_delete=models.PROTECT, related_name='cluster_groups')
    name = models.CharField(max_length=255)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Cluster(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cluster_group = models.ForeignKey(ClusterGroup, on_delete=models.PROTECT, related_name='clusters')
    name = models.CharField(max_length=255)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Client(models.Model):
    NAME_MTN = 'mtn'
    NAME_AIRTEL = 'airtel'
    NAME_HUAWEI = 'huawei'
    NAME_CHOICES = [
        (NAME_MTN, 'MTN'),
        (NAME_AIRTEL, 'Airtel'),
        (NAME_HUAWEI, 'Huawei'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=20, choices=NAME_CHOICES, unique=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.get_name_display()


class BaseStation(models.Model):
    CLASS_PLATINUM = 'platinum'
    CLASS_CHOICES = [
        (CLASS_PLATINUM, 'Platinum'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cluster = models.ForeignKey(Cluster, on_delete=models.PROTECT, related_name='base_stations')
    name = models.CharField(max_length=255)
    address = models.TextField()
    state = models.CharField(max_length=32, null=True, blank=True)
    site_id = models.CharField(max_length=16)
    clients = models.ManyToManyField(Client, blank=True, related_name='base_stations')
    site_classification = models.CharField(max_length=20, choices=CLASS_CHOICES)
    manager = models.ForeignKey(
        'Personnel', on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_stations'
    )
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def clean(self):
        super().clean()
        if self.manager_id and self.manager.role_id and self.manager.role.name != Role.REGIONAL_MANAGER:
            raise ValidationError({'manager': 'Manager must be a Regional Manager.'})

    def __str__(self):
        return self.name


class Location(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    base_station = models.ForeignKey(BaseStation, on_delete=models.PROTECT, related_name='locations')
    name = models.CharField(max_length=255)
    parent_location = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True, related_name='child_locations'
    )
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class AssetCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    # description = models.TextField(blank=True)
    maintenance_required = models.BooleanField(default=True)
    depreciation_method = models.CharField(max_length=100, blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'asset categories'

    def __str__(self):
        return self.name


class Condition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    asset_category = models.ForeignKey(
        AssetCategory, on_delete=models.CASCADE, null=True, blank=True, related_name='conditions'
    )
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Asset(models.Model):
    STATUS_ACTIVE = 'active'
    STATUS_PASSIVE = 'passive'
    STATUS_IN_REPAIR = 'in_repair'
    STATUS_RETIRED = 'retired'
    STATUS_DISPOSED = 'disposed'
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_PASSIVE, 'Passive'),
        (STATUS_IN_REPAIR, 'In Repair'),
        (STATUS_RETIRED, 'Retired'),
        (STATUS_DISPOSED, 'Disposed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset_category = models.ForeignKey(AssetCategory, on_delete=models.PROTECT, related_name='assets')
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name='assets', null=True, blank=True)
    name = models.CharField(max_length=255)
    model = models.CharField(max_length=255, blank=True)
    tag = models.CharField(max_length=100, blank=True) # add unique=True when tags are available
    serial_number = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    purchase_date = models.DateField(null=True, blank=True)
    purchase_cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    warranty_expiry = models.DateField(null=True, blank=True)
    current_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    parent_asset = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True, related_name='sub_assets'
    )
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.tag})" if self.tag else self.name


class Role(models.Model):
    FIELD_TEAM = 'field_team'
    TEAM_LEAD = 'team_lead'
    REGIONAL_MANAGER = 'regional_manager'
    CLUSTER_GROUP_MANAGER = 'cluster_group_manager'
    CLUSTER_MANAGER = 'cluster_manager'
    NAME_CHOICES = [
        (FIELD_TEAM, 'Field Team'),
        (TEAM_LEAD, 'Team Lead'),
        (REGIONAL_MANAGER, 'Regional Manager'),
        (CLUSTER_GROUP_MANAGER, 'Cluster Group Manager'),
        (CLUSTER_MANAGER, 'Cluster Manager'),
    ]
    # Roles that do base-station maintenance and see the Field Team screens.
    FIELD_ROLES = (FIELD_TEAM, TEAM_LEAD)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, choices=NAME_CHOICES, unique=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.get_name_display()


class Station(models.Model):
    TYPE_HEAD_OFFICE = 'head_office'
    TYPE_REGION = 'region'
    TYPE_CLUSTER_GROUP = 'cluster_group'
    TYPE_CLUSTER = 'cluster'
    TYPE_CHOICES = [
        (TYPE_HEAD_OFFICE, 'Head Office'),
        (TYPE_REGION, 'Region'),
        (TYPE_CLUSTER_GROUP, 'Cluster Group'),
        (TYPE_CLUSTER, 'Cluster'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    region = models.ForeignKey(
        Region, on_delete=models.PROTECT, null=True, blank=True, related_name='stations'
    )
    cluster_group = models.ForeignKey(
        ClusterGroup, on_delete=models.PROTECT, null=True, blank=True, related_name='stations'
    )
    cluster = models.ForeignKey(
        Cluster, on_delete=models.PROTECT, null=True, blank=True, related_name='stations'
    )
    address = models.TextField()
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(type='head_office', region_id__isnull=True, cluster_group_id__isnull=True, cluster_id__isnull=True) |
                    Q(type='region', region_id__isnull=False, cluster_group_id__isnull=True, cluster_id__isnull=True) |
                    Q(type='cluster_group', cluster_group_id__isnull=False, region_id__isnull=True, cluster_id__isnull=True) |
                    Q(type='cluster', cluster_id__isnull=False, region_id__isnull=True, cluster_group_id__isnull=True)
                ),
                name='station_type_fk_consistency',
            )
        ]

    def __str__(self):
        return f"{self.get_type_display()} Station"


class ClusterTeam(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    cluster = models.ForeignKey(Cluster, on_delete=models.PROTECT, related_name='teams')
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    @property
    def team_lead(self):
        """The team's Team Lead (one per team), or None."""
        return self.members.filter(role__name=Role.TEAM_LEAD).first()

    def __str__(self):
        return self.name


class Personnel(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.ForeignKey(Role, on_delete=models.PROTECT, null=True, blank=True, related_name='personnel')
    station = models.ForeignKey(Station, on_delete=models.PROTECT, null=True, blank=True, related_name='personnel')
    cluster_team = models.ForeignKey(
        ClusterTeam, on_delete=models.SET_NULL, null=True, blank=True, related_name='members'
    )
    # The one cluster a Cluster Manager is assigned to.
    cluster = models.ForeignKey(
        Cluster, on_delete=models.SET_NULL, null=True, blank=True, related_name='managers',
        help_text='Cluster Managers only: the cluster they manage.',
    )
    stations = models.ManyToManyField('BaseStation', blank=True, related_name='assigned_field_team')
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'personnel'

    def clean(self):
        super().clean()
        if self.role_id and self.role.name == Role.TEAM_LEAD and self.cluster_team_id:
            other_lead = Personnel.objects.filter(
                cluster_team_id=self.cluster_team_id, role__name=Role.TEAM_LEAD,
            ).exclude(pk=self.pk).first()
            if other_lead:
                raise ValidationError({'role': f'{self.cluster_team} already has a Team Lead ({other_lead}).'})

    def accessible_stations(self):
        """Stations this person may work at. Cluster Managers get every station in their cluster
        (no per-station assignment); everyone else gets the stations assigned to them."""
        if self.role_id and self.role.name == Role.CLUSTER_MANAGER:
            return BaseStation.objects.filter(cluster_id=self.cluster_id) if self.cluster_id \
                else BaseStation.objects.none()
        return self.stations.all()

    @property
    def name(self):
        return self.get_full_name() or self.username

    def __str__(self):
        return self.name


class PMCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'PM Category'
        verbose_name_plural = 'PM Categories'

    def __str__(self):
        return self.name


class Vendor(models.Model):
    TYPE_CONTRACTOR = 'contractor'
    TYPE_SUPPLIER = 'supplier'
    TYPE_CHOICES = [
        (TYPE_CONTRACTOR, 'Contractor'),
        (TYPE_SUPPLIER, 'Supplier'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Part(models.Model):
    KIND_CONSUMABLE = 'consumable'
    KIND_SPARE_PART = 'spare_part'
    KIND_CHOICES = [
        (KIND_CONSUMABLE, 'Consumable'),
        (KIND_SPARE_PART, 'Spare part'),
    ]
    UNIT_EACH = 'each'
    UNIT_LITRE = 'litre'
    UNIT_KG = 'kg'
    UNIT_CHOICES = [
        (UNIT_EACH, 'Each'),
        (UNIT_LITRE, 'Litre'),
        (UNIT_KG, 'Kg'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name='parts')
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=100, unique=True)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=KIND_SPARE_PART)
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES, default=UNIT_EACH)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.sku})"


class AssetCheckList(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pm_category = models.ForeignKey(
        PMCategory, on_delete=models.PROTECT, null=True, blank=True, related_name='task_templates'
    )
    asset_category = models.ForeignKey(
        AssetCategory, on_delete=models.PROTECT, null=True, blank=True, related_name='checklists'
    )
    asset = models.ForeignKey(
        Asset, on_delete=models.CASCADE, null=True, blank=True, related_name='maintenance_list'
    )
    CONDITION_GOOD = 'good'
    CONDITION_FAIR = 'fair'
    CONDITION_POOR = 'poor'
    CONDITION_CHOICES = [
        (CONDITION_GOOD, 'Good'),
        (CONDITION_FAIR, 'Fair'),
        (CONDITION_POOR, 'Poor'),
    ]

    instructions = models.TextField()
    estimated_duration = models.PositiveIntegerField(help_text='Minutes', null=True, blank=True)
    required_parts = models.ManyToManyField(Part, blank=True, related_name='task_templates')
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, null=True, blank=True)
    comments = models.TextField(blank=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Asset checklist'
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(pm_category_id__isnull=False, asset_category_id__isnull=True, asset_id__isnull=True) |
                    Q(pm_category_id__isnull=True, asset_category_id__isnull=False, asset_id__isnull=True) |
                    Q(pm_category_id__isnull=True, asset_category_id__isnull=True, asset_id__isnull=False)
                ),
                name='assetchecklist_exactly_one_owner',
            )
        ]

    def __str__(self):
        return f"{self.instructions}"


class AssetChecklistCondition(models.Model):
    GRADE_POOR = 'poor'
    GRADE_FAIR = 'fair'
    GRADE_GOOD = 'good'
    GRADE_CHOICES = [
        (GRADE_POOR, 'Poor'),
        (GRADE_FAIR, 'Fair'),
        (GRADE_GOOD, 'Good'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='conditions')
    condition = models.CharField(max_length=255)
    comment = models.TextField(blank=True)
    grade = models.CharField(max_length=10, choices=GRADE_CHOICES, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.asset} — {self.get_grade_display()}"


class PMQuestion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task_template = models.ForeignKey(AssetCheckList, on_delete=models.CASCADE, related_name='questions')
    question = models.TextField()
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.question[:80]


class PMSchedule(models.Model):
    TRIGGER_TIME_BASED = 'time_based'
    TRIGGER_USAGE_BASED = 'usage_based'
    TRIGGER_CHOICES = [
        (TRIGGER_TIME_BASED, 'Time Based'),
        (TRIGGER_USAGE_BASED, 'Usage Based'),
    ]

    UNIT_HOURS = 'hours'
    UNIT_DAYS = 'days'
    UNIT_WEEKS = 'weeks'
    INTERVAL_UNIT_CHOICES = [
        (UNIT_HOURS, 'Hours'),
        (UNIT_DAYS, 'Days'),
        (UNIT_WEEKS, 'Weeks'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset = models.ForeignKey(
        Asset, on_delete=models.CASCADE, null=True, blank=True, related_name='pm_schedules'
    )
    category = models.ForeignKey(
        AssetCategory, on_delete=models.CASCADE, null=True, blank=True, related_name='pm_schedules'
    )
    asset_checklist = models.ForeignKey(AssetCheckList, on_delete=models.PROTECT, related_name='schedules')
    owner = models.ForeignKey(Personnel, on_delete=models.PROTECT, related_name='owned_schedules')
    trigger_type = models.CharField(max_length=20, choices=TRIGGER_CHOICES)
    interval = models.PositiveIntegerField()
    interval_unit = models.CharField(max_length=10, choices=INTERVAL_UNIT_CHOICES)
    last_completed = models.DateTimeField(null=True, blank=True)
    next_due_date = models.DateField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(asset_id__isnull=False, category_id__isnull=True) |
                    Q(asset_id__isnull=True, category_id__isnull=False)
                ),
                name='pm_schedule_asset_xor_category',
            )
        ]

    def clean(self):
        super().clean()
        if self.owner_id and self.owner.role_id and self.owner.role.name != Role.REGIONAL_MANAGER:
            raise ValidationError({'owner': 'Owner must be a Regional Manager.'})

    def __str__(self):
        target = self.asset or self.category
        return f"PM Schedule — {target}"


class WorkOrder(models.Model):
    TYPE_PREVENTIVE = 'preventive'
    TYPE_CORRECTIVE = 'corrective'
    TYPE_INSPECTION = 'inspection'
    TYPE_OVERHAUL = 'overhaul'
    TYPE_CHOICES = [
        (TYPE_PREVENTIVE, 'Preventive'),
        (TYPE_CORRECTIVE, 'Corrective'),
        (TYPE_INSPECTION, 'Inspection'),
        (TYPE_OVERHAUL, 'Overhaul'),
    ]

    STATUS_OPEN = 'open'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_COMPLETE = 'complete'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_OPEN, 'Open'),
        (STATUS_IN_PROGRESS, 'In Progress'),
        (STATUS_COMPLETE, 'Complete'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    PRIORITY_LOW = 'low'
    PRIORITY_MEDIUM = 'medium'
    PRIORITY_HIGH = 'high'
    PRIORITY_CRITICAL = 'critical'
    PRIORITY_CHOICES = [
        (PRIORITY_LOW, 'Low'),
        (PRIORITY_MEDIUM, 'Medium'),
        (PRIORITY_HIGH, 'High'),
        (PRIORITY_CRITICAL, 'Critical'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    base_station = models.ForeignKey(
        BaseStation, on_delete=models.PROTECT, null=True, blank=True, related_name='work_orders'
    )
    asset_category = models.ForeignKey(
        AssetCategory, on_delete=models.PROTECT, null=True, blank=True, related_name='work_orders'
    )
    asset = models.ForeignKey(
        Asset, on_delete=models.PROTECT, null=True, blank=True, related_name='work_orders'
    )
    pm_schedule = models.ForeignKey(
        PMSchedule, on_delete=models.SET_NULL, null=True, blank=True, related_name='work_orders'
    )
    asset_checklist = models.ForeignKey(
        AssetCheckList, on_delete=models.SET_NULL, null=True, blank=True, related_name='work_orders'
    )
    instructions_snapshot = models.TextField(blank=True)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default=PRIORITY_MEDIUM)
    due_date = models.DateField(null=True, blank=True)
    completed_date = models.DateField(null=True, blank=True)
    assigned_to = models.ForeignKey(
        Personnel, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_work_orders'
    )
    description = models.TextField(blank=True)
    cost_labour = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    cost_parts = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    submitted = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(null=True, blank=True)
    geofence_verified = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(base_station_id__isnull=False, asset_category_id__isnull=True, asset_id__isnull=True) |
                    Q(base_station_id__isnull=True, asset_category_id__isnull=False, asset_id__isnull=True) |
                    Q(base_station_id__isnull=True, asset_category_id__isnull=True, asset_id__isnull=False)
                ),
                name='work_order_exactly_one_target',
            )
        ]

    def clean(self):
        super().clean()
        if (
            self.assigned_to_id and self.assigned_to.role_id
            and self.assigned_to.role.name not in Role.FIELD_ROLES
        ):
            raise ValidationError({'assigned_to': 'Assigned person must be Field Team or a Team Lead.'})

    @property
    def target(self):
        return self.base_station or self.asset_category or self.asset

    def __str__(self):
        return f"WO {str(self.id)[:8]} — {self.target} ({self.get_type_display()})"


class PartUsage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    work_order = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name='part_usages')
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name='part_usages')
    part = models.ForeignKey(Part, on_delete=models.PROTECT, related_name='usages')
    qty_used = models.PositiveIntegerField()
    notes = models.TextField(blank=True)
    # Required for new logs (enforced by the API); blank only on logs made before photos existed.
    photo = models.ImageField(upload_to='part_usages/%Y/%m/', blank=True)
    photo_taken_at = models.DateTimeField(null=True, blank=True)
    # Identifier of the physical part used (e.g. a serial number). Left blank for now.
    part_identifier = models.CharField('Part ID', max_length=100, blank=True)
    # The team whose stock this usage drew from (the logging person's team at the time).
    cluster_team = models.ForeignKey(
        ClusterTeam, on_delete=models.SET_NULL, null=True, blank=True, related_name='part_usages',
    )
    recorded_by = models.ForeignKey(
        'Personnel', on_delete=models.SET_NULL, null=True, blank=True, related_name='part_usages'
    )
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created']
        verbose_name_plural = 'part usages'

    @property
    def base_station(self):
        return self.work_order.base_station

    def __str__(self):
        return f"{self.qty_used}x {self.part} on {self.asset}"


class Attachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset = models.ForeignKey(
        Asset, on_delete=models.CASCADE, null=True, blank=True, related_name='attachments'
    )
    work_order = models.ForeignKey(
        WorkOrder, on_delete=models.CASCADE, null=True, blank=True, related_name='attachments'
    )
    diesel_delivery = models.ForeignKey(
        'DieselDelivery', on_delete=models.CASCADE, null=True, blank=True, related_name='attachments'
    )
    safety_report = models.ForeignKey(
        'SafetyReport', on_delete=models.CASCADE, null=True, blank=True, related_name='attachments'
    )
    file_url = models.URLField()
    type = models.CharField(max_length=100)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(asset_id__isnull=False, work_order_id__isnull=True, diesel_delivery_id__isnull=True, safety_report_id__isnull=True) |
                    Q(asset_id__isnull=True, work_order_id__isnull=False, diesel_delivery_id__isnull=True, safety_report_id__isnull=True) |
                    Q(asset_id__isnull=True, work_order_id__isnull=True, diesel_delivery_id__isnull=False, safety_report_id__isnull=True) |
                    Q(asset_id__isnull=True, work_order_id__isnull=True, diesel_delivery_id__isnull=True, safety_report_id__isnull=False)
                ),
                name='attachment_exactly_one_owner',
            )
        ]

    def __str__(self):
        return f"Attachment ({self.type})"


class MeterReading(models.Model):
    TYPE_RUN_HOURS = 'run_hours'
    TYPE_DIESEL_LEVEL = 'diesel_level'
    TYPE_CHOICES = [
        (TYPE_RUN_HOURS, 'Run Hours'),
        (TYPE_DIESEL_LEVEL, 'Diesel Level'),
    ]

    UNIT_HOURS = 'hours'
    UNIT_DAYS = 'days'
    UNIT_LITRES = 'litres'
    UNIT_MM = 'mm'
    UNIT_CHOICES = [
        (UNIT_HOURS, 'Hours'),
        (UNIT_DAYS, 'Days'),
        (UNIT_LITRES, 'Litres'),
        (UNIT_MM, 'Millimetres'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name='meter_readings')
    reading_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_RUN_HOURS)
    date = models.DateField()
    value = models.PositiveIntegerField()
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES)
    work_order = models.ForeignKey(
        WorkOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name='meter_readings'
    )
    recorded_by = models.ForeignKey(
        'Personnel', on_delete=models.SET_NULL, null=True, blank=True, related_name='meter_readings'
    )
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created']

    def __str__(self):
        return f"{self.asset} — {self.value} {self.unit} on {self.date}"


class PartStock(models.Model):
    """Stock of one part in one place: a regional store, or a cluster team (held by its Team Lead).

    `qty` is only ever changed through assets.stock, which writes a StockMovement in the same
    transaction, so the movement log always explains the number.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    part = models.ForeignKey(Part, on_delete=models.PROTECT, related_name='stock')
    region = models.ForeignKey(
        Region, on_delete=models.PROTECT, null=True, blank=True, related_name='part_stocks',
    )
    cluster_team = models.ForeignKey(
        ClusterTeam, on_delete=models.PROTECT, null=True, blank=True, related_name='part_stocks',
    )
    qty = models.PositiveIntegerField(default=0)
    reorder_threshold = models.PositiveIntegerField(default=0)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'part stocks'
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(region_id__isnull=False, cluster_team_id__isnull=True) |
                    Q(region_id__isnull=True, cluster_team_id__isnull=False)
                ),
                name='partstock_exactly_one_holder',
            ),
            models.UniqueConstraint(
                fields=['part', 'region'], condition=Q(region__isnull=False),
                name='partstock_one_row_per_part_per_region',
            ),
            models.UniqueConstraint(
                fields=['part', 'cluster_team'], condition=Q(cluster_team__isnull=False),
                name='partstock_one_row_per_part_per_team',
            ),
        ]

    @property
    def holder(self):
        return self.region or self.cluster_team

    def __str__(self):
        where = f"{self.region} regional store" if self.region_id else f"team {self.cluster_team}"
        return f"{self.part} at {where}"


class StockMovement(models.Model):
    """One change to one stock record. A delivery writes two: regional store down, team up."""
    REASON_DELIVERY = 'delivery'
    REASON_USAGE = 'usage'
    REASON_ADDED_AT_SITE = 'added_at_site'
    REASON_ADJUSTMENT = 'adjustment'
    REASON_CHOICES = [
        (REASON_DELIVERY, 'Delivery'),
        (REASON_USAGE, 'Usage'),
        (REASON_ADDED_AT_SITE, 'Added at site'),
        (REASON_ADJUSTMENT, 'Adjustment'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    part = models.ForeignKey(Part, on_delete=models.PROTECT, related_name='stock_movements')
    region = models.ForeignKey(
        Region, on_delete=models.PROTECT, null=True, blank=True, related_name='stock_movements',
    )
    cluster_team = models.ForeignKey(
        ClusterTeam, on_delete=models.PROTECT, null=True, blank=True, related_name='stock_movements',
    )
    change = models.IntegerField(help_text='Positive adds stock, negative removes it.')
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    delivery = models.ForeignKey(
        'PartDelivery', on_delete=models.PROTECT, null=True, blank=True, related_name='stock_movements',
    )
    usage = models.ForeignKey(
        'PartUsage', on_delete=models.PROTECT, null=True, blank=True, related_name='stock_movements',
    )
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(
        'Personnel', on_delete=models.SET_NULL, null=True, blank=True, related_name='stock_movements',
    )
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created']
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(region_id__isnull=False, cluster_team_id__isnull=True) |
                    Q(region_id__isnull=True, cluster_team_id__isnull=False)
                ),
                name='stockmovement_exactly_one_holder',
            ),
            models.CheckConstraint(condition=~Q(change=0), name='stockmovement_change_not_zero'),
        ]

    def __str__(self):
        where = self.region or self.cluster_team
        return f"{self.change:+d} {self.part} at {where} ({self.get_reason_display()})"


class Alarm(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name='alarms')
    work_order = models.ForeignKey(
        WorkOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name='alarms'
    )
    raised_at = models.DateTimeField()
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        Personnel, on_delete=models.SET_NULL, null=True, blank=True, related_name='resolved_alarms'
    )
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Alarm — {self.asset} at {self.raised_at:%Y-%m-%d %H:%M}"


class AlarmNote(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    alarm = models.ForeignKey(Alarm, on_delete=models.CASCADE, related_name='notes')
    text = models.TextField()
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created']

    def __str__(self):
        return f"Note on {self.alarm} at {self.created:%Y-%m-%d %H:%M}"


class InspectionResponse(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    work_order = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name='inspection_responses')
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name='inspection_responses')
    issues_found = models.BooleanField(null=True, blank=True)
    conditions = models.ManyToManyField(Condition, blank=True, related_name='inspection_responses')
    comments = models.TextField(blank=True)
    done = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('work_order', 'asset')]

    def __str__(self):
        return f"{self.asset} — WO {str(self.work_order_id)[:8]}"


class WorkOrderChecklistResponse(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    inspection_response = models.ForeignKey(
        InspectionResponse, on_delete=models.CASCADE, related_name='checklist_responses'
    )
    question = models.ForeignKey(PMQuestion, on_delete=models.PROTECT, related_name='responses')
    checked = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('inspection_response', 'question')]
        # Without an explicit ordering, an UPDATE (toggling `checked`) can move a row's
        # physical tuple, making a plain scan return items in a different order on
        # the next fetch — items appeared to "jump" in the checklist after a tap.
        ordering = ['created']

    def __str__(self):
        return f"{'✓' if self.checked else '✗'} {self.question}"


class Issue(models.Model):
    SEVERITY_LOW = 'low'
    SEVERITY_MEDIUM = 'medium'
    SEVERITY_HIGH = 'high'
    SEVERITY_CRITICAL = 'critical'
    SEVERITY_CHOICES = [
        (SEVERITY_LOW, 'Low'),
        (SEVERITY_MEDIUM, 'Medium'),
        (SEVERITY_HIGH, 'High'),
        (SEVERITY_CRITICAL, 'Critical'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    inspection_response = models.ForeignKey(InspectionResponse, on_delete=models.CASCADE, related_name='issues')
    description = models.TextField()
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES)
    promoted_work_order = models.ForeignKey(
        WorkOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name='source_issues'
    )
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.get_severity_display()} issue — {self.description[:60]}"


class DieselDelivery(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    base_station = models.ForeignKey(BaseStation, on_delete=models.PROTECT, related_name='diesel_deliveries')
    work_order = models.ForeignKey(
        WorkOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name='diesel_deliveries'
    )
    vendor = models.ForeignKey(
        Vendor, on_delete=models.SET_NULL, null=True, blank=True, related_name='diesel_deliveries'
    )
    quantity_litres = models.PositiveIntegerField()
    tank_level_before = models.PositiveIntegerField(null=True, blank=True, help_text='Millimetres (dipstick reading)')
    tank_level_after = models.PositiveIntegerField(null=True, blank=True, help_text='Millimetres (dipstick reading)')
    delivered_at = models.DateTimeField()
    recorded_by = models.ForeignKey(
        Personnel, on_delete=models.SET_NULL, null=True, blank=True, related_name='diesel_deliveries'
    )
    notes = models.TextField(blank=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-delivered_at']
        verbose_name_plural = 'diesel deliveries'

    def __str__(self):
        return f"{self.quantity_litres}L delivered to {self.base_station} on {self.delivered_at:%Y-%m-%d}"


class PartRequest(models.Model):
    """A Field Team request for parts for one base station. The parts are its lines."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    base_station = models.ForeignKey(BaseStation, on_delete=models.PROTECT, related_name='part_requests')
    work_order = models.ForeignKey(
        WorkOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name='part_requests'
    )
    asset = models.ForeignKey(
        Asset, on_delete=models.SET_NULL, null=True, blank=True, related_name='part_requests'
    )
    notes = models.TextField(blank=True)
    requested_by = models.ForeignKey(
        Personnel, on_delete=models.SET_NULL, null=True, blank=True, related_name='part_requests'
    )
    # Snapshots taken when the request is made, so later team changes don't rewrite history.
    cluster_team = models.ForeignKey(
        ClusterTeam, on_delete=models.SET_NULL, null=True, blank=True, related_name='part_requests',
    )
    team_lead = models.ForeignKey(
        Personnel, on_delete=models.SET_NULL, null=True, blank=True, related_name='led_part_requests',
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-requested_at']

    def __str__(self):
        return f"Request for {self.base_station} on {self.requested_at:%Y-%m-%d}"


class PartRequestLine(models.Model):
    """One part on a request, with its own quantity, required date and status."""
    STATUS_REQUESTED = 'requested'
    STATUS_APPROVED = 'approved'
    STATUS_DECLINED = 'declined'
    STATUS_CANCELLED = 'cancelled'
    STATUS_PENDING = 'pending'
    STATUS_DELIVERED = 'delivered'
    STATUS_CHOICES = [
        (STATUS_REQUESTED, 'Requested'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_DECLINED, 'Declined'),
        (STATUS_CANCELLED, 'Cancelled'),
        (STATUS_PENDING, 'Pending'),
        (STATUS_DELIVERED, 'Delivered'),
    ]
    FINAL_STATUSES = (STATUS_DECLINED, STATUS_CANCELLED, STATUS_DELIVERED)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(PartRequest, on_delete=models.CASCADE, related_name='lines')
    part = models.ForeignKey(Part, on_delete=models.PROTECT, related_name='request_lines')
    quantity = models.PositiveIntegerField()
    required_date = models.DateField()
    # True when the required date was already past on the day the request was made.
    is_backdated = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_REQUESTED)
    decline_reason = models.TextField(blank=True)
    decided_by = models.ForeignKey(
        Personnel, on_delete=models.SET_NULL, null=True, blank=True, related_name='decided_request_lines',
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    closed_short = models.BooleanField(default=False)
    closed_short_by = models.ForeignKey(
        Personnel, on_delete=models.SET_NULL, null=True, blank=True, related_name='closed_request_lines',
    )
    closed_short_at = models.DateTimeField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-request__requested_at', 'created']
        constraints = [
            models.UniqueConstraint(fields=['request', 'part'], name='partrequestline_one_line_per_part'),
        ]

    @property
    def delivered_qty(self):
        """Total of deliveries both sides have confirmed."""
        return sum(d.quantity for d in self.deliveries.all() if d.is_complete)

    @property
    def shortfall(self):
        return max(self.quantity - self.delivered_qty, 0) if self.closed_short else 0

    def __str__(self):
        return f"{self.quantity}x {self.part} for {self.request.base_station} ({self.get_status_display()})"


class PartDelivery(models.Model):
    """One delivery against a request line. Complete once both sides have confirmed it:
    the approver records it (marked delivered) and the Field Team confirms they received it."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    line = models.ForeignKey(PartRequestLine, on_delete=models.CASCADE, related_name='deliveries')
    quantity = models.PositiveIntegerField()
    # Usually the regional office's address; left blank until locations are decided.
    pickup_location = models.CharField(max_length=255, blank=True)
    marked_delivered_by = models.ForeignKey(
        Personnel, on_delete=models.SET_NULL, null=True, blank=True, related_name='marked_deliveries',
    )
    marked_delivered_at = models.DateTimeField(null=True, blank=True)
    received_by = models.ForeignKey(
        Personnel, on_delete=models.SET_NULL, null=True, blank=True, related_name='received_deliveries',
    )
    # When the Field Team confirmed receipt = the pick-up date.
    received_at = models.DateTimeField(null=True, blank=True)
    # Set once the stock has moved from the regional store to the team, so it moves only once.
    stock_moved = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created']
        verbose_name_plural = 'part deliveries'

    @property
    def is_complete(self):
        return bool(self.marked_delivered_at and self.received_at)

    @property
    def is_pending(self):
        return bool(self.marked_delivered_at) != bool(self.received_at)

    def __str__(self):
        return f"{self.quantity}x {self.line.part} delivery"


class Notification(models.Model):
    """An in-app alert for one person."""
    EVENT_NEW_REQUEST = 'new_request'
    EVENT_REQUEST_CANCELLED = 'request_cancelled'
    EVENT_LINE_APPROVED = 'line_approved'
    EVENT_LINE_DECLINED = 'line_declined'
    EVENT_DELIVERY_RECORDED = 'delivery_recorded'
    EVENT_DELIVERY_RECEIVED = 'delivery_received'
    EVENT_ADDED_AT_SITE = 'added_at_site'
    EVENT_LOW_STOCK = 'low_stock'
    EVENT_CHOICES = [
        (EVENT_NEW_REQUEST, 'New request'),
        (EVENT_REQUEST_CANCELLED, 'Request cancelled'),
        (EVENT_LINE_APPROVED, 'Part approved'),
        (EVENT_LINE_DECLINED, 'Part declined'),
        (EVENT_DELIVERY_RECORDED, 'Delivery recorded'),
        (EVENT_DELIVERY_RECEIVED, 'Delivery received'),
        (EVENT_ADDED_AT_SITE, 'Stock added at site'),
        (EVENT_LOW_STOCK, 'Stock below reorder level'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(Personnel, on_delete=models.CASCADE, related_name='notifications')
    event = models.CharField(max_length=30, choices=EVENT_CHOICES)
    message = models.TextField()
    part_request = models.ForeignKey(
        PartRequest, on_delete=models.CASCADE, null=True, blank=True, related_name='notifications',
    )
    part_request_line = models.ForeignKey(
        PartRequestLine, on_delete=models.CASCADE, null=True, blank=True, related_name='notifications',
    )
    part_delivery = models.ForeignKey(
        PartDelivery, on_delete=models.CASCADE, null=True, blank=True, related_name='notifications',
    )
    part_usage = models.ForeignKey(
        PartUsage, on_delete=models.CASCADE, null=True, blank=True, related_name='notifications',
    )
    read_at = models.DateTimeField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created']

    def __str__(self):
        return f"{self.get_event_display()} for {self.recipient}"


class SafetyReport(models.Model):
    TYPE_INCIDENT = 'incident'
    TYPE_NEAR_MISS = 'near_miss'
    TYPE_HAZARD = 'hazard'
    TYPE_CHOICES = [
        (TYPE_INCIDENT, 'Incident'),
        (TYPE_NEAR_MISS, 'Near Miss'),
        (TYPE_HAZARD, 'Hazard'),
    ]

    SEVERITY_LOW = 'low'
    SEVERITY_MEDIUM = 'medium'
    SEVERITY_HIGH = 'high'
    SEVERITY_CRITICAL = 'critical'
    SEVERITY_CHOICES = [
        (SEVERITY_LOW, 'Low'),
        (SEVERITY_MEDIUM, 'Medium'),
        (SEVERITY_HIGH, 'High'),
        (SEVERITY_CRITICAL, 'Critical'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    base_station = models.ForeignKey(BaseStation, on_delete=models.PROTECT, related_name='safety_reports')
    work_order = models.ForeignKey(
        WorkOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name='safety_reports'
    )
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES)
    description = models.TextField()
    reported_by = models.ForeignKey(
        Personnel, on_delete=models.SET_NULL, null=True, blank=True, related_name='safety_reports'
    )
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created']

    def __str__(self):
        return f"{self.get_type_display()} at {self.base_station} — {self.description[:60]}"
