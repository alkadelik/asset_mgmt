"""Reads values from the Setting store, falling back to defaults when none is saved."""
from .models import Setting

COLOUR_BANDS = 'colour_bands'

DEFAULTS = {
    # Percentages: at or above green_min is green, at or above amber_min is amber, below is red.
    COLOUR_BANDS: {'green_min': 95, 'amber_min': 90},
}


def get_setting(key):
    row = Setting.objects.filter(key=key).first()
    return row.value if row else DEFAULTS[key]


def colour_for_percent(percent):
    bands = get_setting(COLOUR_BANDS)
    if percent >= bands['green_min']:
        return 'green'
    if percent >= bands['amber_min']:
        return 'amber'
    return 'red'
