"""The nine asset types from Form 1a, with their checklist points and defects.

Defects come from the Defects Rating Criteria: each is Poor or Fair. Used by migration 0034
(for existing databases) and by seed.py, so both load identical reference data.
"""

CONTROL_PANEL_POOR = ['Exposed terminals', 'Faulty panel door', 'Damaged components', 'Bypassed control panel']
CONTROL_PANEL_FAIR = ['Poor cable management', 'Panel cleanliness', 'Aged components', 'Panel labelling']

ASSET_TYPES = [
    {
        'name': 'Janitorial Services',
        'group': '1. Janitorial Services',
        'points': [
            'Cleanliness of concrete and gravel floors', 'Additional gravel required',
            'Oil and diesel spillage', 'Rodent or insect infestations',
            'Site access control (locks etc.)', 'Warning signs and safety labels',
        ],
        'poor': [
            'Rodents', 'Perimeter fence', 'Major granite stain',
            'Damaged shelter floor / leaking roof (indoor sites)', 'Palisade fence earthing',
        ],
        'fair': [
            'Internal cleanliness', 'External cleanliness', 'Minor granite stain',
            'Shelter cleanliness (indoor sites)',
        ],
    },
    {
        'name': 'Diesel Generator',
        'group': '2. Generator Power Supply',
        'points': [
            'Generator cleanliness', 'Housing rust, leakages, bolts and nuts',
            'Oil, diesel and coolant leakages', 'Wiring and control system', 'Pipes and hoses',
            'Exhaust secure and free of obstruction', 'Exhaust carbon build-up', 'Incorrect load sizing',
            'Proper cabling', 'Engine condition', 'Electrical condition', 'Engine vibration',
        ],
        'poor': [
            'Engine oil, diesel or radiator coolant leakages', 'Engine problems', 'Exhaust conditions',
            'Generator vibration', 'Safety devices bypassed', 'Generator earthing',
        ],
        'fair': [
            'Generator housing', 'Generator cleanliness', 'Minor wiring (battery terminals etc.)',
            'Generator not installed on plinth',
        ],
    },
    {
        'name': 'Diesel Tank',
        'group': '2. Generator Power Supply',
        'points': [
            'Tank cleanliness', 'Tank rust and leakages', 'Water separator condition',
            'Diesel leakages', 'Diesel pipes and hoses',
        ],
        'poor': [
            'Leakages from diesel tank', 'Water ingress', 'Severe rust', 'Water separator',
            'Galvanized diesel line', 'Tank tilting', 'Tank not installed on plinth', 'Tank earthing',
        ],
        'fair': ['Minor rust', 'Tank dented', 'Tank calibration'],
    },
    {
        'name': 'Solar Panels and Structure',
        'group': '3. Solar Power Supply',
        'points': ['Solar panel condition', 'Panel structure condition', 'Solar control condition'],
        'poor': ['Structural stability', 'Solar structure earthing', 'Solar cables termination'],
        'fair': ['Solar panels condition', 'Tree shading solar panel'],
    },
    {
        'name': 'Battery Packs',
        'group': '3. Solar Power Supply',
        'points': ['Battery pack condition'],
        'poor': [],  # none yet: always Good until defects are added
        'fair': [],
    },
    {
        'name': 'Transformer',
        'group': '4. Grid Power Supply',
        'points': ['Transformer condition', 'Grid cables'],
        'poor': [
            'Transformer inside the site and not fenced', 'Grid functionality',
            'Grid cable unsafe termination/connection/condition',
        ],
        'fair': ['Transformer condition'],
    },
    {
        'name': 'AC Control Panel',
        'group': '5. Control Panels',
        'points': ['AC control panel condition'],
        'poor': CONTROL_PANEL_POOR,
        'fair': CONTROL_PANEL_FAIR,
    },
    {
        'name': 'DC Control Panel',
        'group': '5. Control Panels',
        'points': ['DC control panel condition'],
        'poor': CONTROL_PANEL_POOR,
        'fair': CONTROL_PANEL_FAIR,
    },
    {
        'name': 'Tower Structure',
        'group': '6. Telecoms Tower',
        'points': [
            'Painting, rust, bolts etc.', 'Security and aviation light',
            'Cables, cable trays and arrangement', 'Earthing system',
        ],
        'poor': ['Earthing', 'Foundation structure', 'Tower deflection', 'Unsafe tower ladder'],
        'fair': ['Painting wear', 'Aviation light', 'Security light', 'Cables arrangement'],
    },
]

TYPE_NAMES = [t['name'] for t in ASSET_TYPES]

# Old category name -> new type, for assets that already exist. Types not listed (Air
# Conditioning, Rectifier, anything else) are removed along with their assets.
OLD_TO_NEW = {
    'Generator': 'Diesel Generator',
    'Solar': 'Solar Panels and Structure',
    'Battery Bank': 'Battery Packs',
    'DC Electricals': 'DC Control Panel',
    'AC Electricals': 'AC Control Panel',
    'Janitorial': 'Janitorial Services',
}


def load_asset_types(AssetCategory, Condition, AssetCheckList, PMQuestion):
    """Create or update the nine types with their checklist points and defects.
    Safe to run more than once. Takes the model classes so a migration can pass historical ones."""
    categories = {}
    for spec in ASSET_TYPES:
        category, _ = AssetCategory.objects.get_or_create(
            name=spec['name'], defaults={'group': spec['group']}
        )
        if category.group != spec['group']:
            category.group = spec['group']
            category.save(update_fields=['group'])
        categories[spec['name']] = category

        checklist = AssetCheckList.objects.filter(
            asset_category=category, pm_category__isnull=True, asset__isnull=True
        ).first()
        if checklist is None:
            checklist = AssetCheckList.objects.create(
                asset_category=category, instructions=f"{spec['name']} routine maintenance",
            )
        for point in spec['points']:
            if not PMQuestion.objects.filter(task_template=checklist, question=point).exists():
                PMQuestion.objects.create(task_template=checklist, question=point)

        for severity, names in (('poor', spec['poor']), ('fair', spec['fair'])):
            for name in names:
                Condition.objects.get_or_create(
                    name=name, asset_category=category, defaults={'severity': severity},
                )
    return categories
