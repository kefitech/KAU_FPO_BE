"""
CropZoneProfile → ChatKnowledgeEntry sync.

Builds two entry families so the chatbot can answer district- and
zone-level "what can I grow here?" questions:

  Zone: <KAU zone> — Suitable Crops
    e.g. "Zone: Coastal Plain — Suitable Crops"

  District: <District Name> — Suitable Crops
    e.g. "District: Thiruvananthapuram — Suitable Crops"

The KAU zone → district crosswalk is defined locally in this module.
Each Kerala district maps to one or more KAU zones (a coastal district
covers both Coastal Plain and Midland Laterites, for example). Crops
from the "General (all zones)" bucket are always included.

Both callers reuse the same helpers:
  1. scripts/seed_chatbot_knowledge_from_zones.py — bulk seed
  2. apps/chatbot/signals.py — live sync on CropZoneProfile save/delete
"""

from apps.core.utils.constants import District, get_district_name, get_district_search_terms


DEFAULT_AUDIENCES = ['public', 'fpo_manager', 'cbbo', 'government', 'expert']
DEFAULT_DISPLAY_ORDER = 490    # a touch above the per-crop 500s so overview questions surface these first


# Which KAU zones (from CropZoneProfile.kau_zone) each of Kerala's 14
# districts is covered by. "General (all zones)" is added implicitly
# during the build.
DISTRICT_TO_KAU_ZONES = {
    'TVM': ['Coastal Plain', 'Midland Laterites', 'Foothills'],
    'KLM': ['Coastal Plain', 'Midland Laterites', 'Foothills'],
    'PTA': ['Midland Laterites', 'Foothills', 'High Hills'],
    'ALP': ['Coastal Plain', 'Midland Laterites'],
    'KTM': ['Midland Laterites', 'Foothills', 'High Hills'],
    'IDK': ['High Hills', 'Foothills'],
    'EKM': ['Coastal Plain', 'Midland Laterites', 'Foothills'],
    'TSR': ['Coastal Plain', 'Midland Laterites', 'Foothills'],
    'PKD': ['Palakkad Plain', 'Midland Laterites', 'Foothills'],
    'MLP': ['Coastal Plain', 'Midland Laterites', 'Foothills'],
    'KZD': ['Coastal Plain', 'Midland Laterites'],
    'WYD': ['High Hills', 'Foothills'],
    'KNR': ['Coastal Plain', 'Midland Laterites'],
    'KSD': ['Coastal Plain', 'Midland Laterites'],
}

# All six KAU zones we index — matches CropZoneProfile.KauZone.
ALL_KAU_ZONES = [
    'Coastal Plain', 'Midland Laterites', 'Foothills',
    'High Hills', 'Palakkad Plain', 'General (all zones)',
]

# Cap on the crop list length inside an entry — Gemini needs concise context.
_MAX_CROPS_PER_ENTRY = 40


def _crops_for_zone(zone_name: str) -> list[str]:
    """Sorted unique crop_names active in this KAU zone."""
    from apps.database.models import CropZoneProfile
    return sorted(
        set(
            CropZoneProfile.objects
            .filter(kau_zone=zone_name, is_active=True, is_deleted=False)
            .values_list('crop_name', flat=True)
        )
    )


def _crops_for_district(district_code: str) -> list[str]:
    """Aggregate crops from every KAU zone that covers this district.
    Always folds in the 'General (all zones)' bucket."""
    zones = DISTRICT_TO_KAU_ZONES.get(district_code, []) + ['General (all zones)']
    crops = set()
    for z in zones:
        crops.update(_crops_for_zone(z))
    return sorted(crops)


def _format_crop_list(crops: list[str]) -> str:
    """Comma-list, trimmed to _MAX_CROPS_PER_ENTRY, with an "and more" hint."""
    if len(crops) <= _MAX_CROPS_PER_ENTRY:
        return ', '.join(crops)
    shown = crops[:_MAX_CROPS_PER_ENTRY]
    return ', '.join(shown) + f' — and {len(crops) - _MAX_CROPS_PER_ENTRY} more'


def build_zone_entry(zone_name: str) -> dict | None:
    """Return {topic, body_en, keywords} for one KAU zone, or None if empty."""
    crops = _crops_for_zone(zone_name)
    if not crops:
        return None
    body = (
        f'Crops that KAU recommends for the {zone_name} agro-climatic zone of '
        f'Kerala include: {_format_crop_list(crops)}. '
        f'Total: {len(crops)} crops documented for this zone. '
        f'Source: KAU Package of Practices — CropZoneProfile.'
    )
    return {
        'topic':    f'Zone: {zone_name} — Suitable Crops',
        'body_en':  body,
        'keywords': f'{zone_name} zone agro-climatic crops suitable which what grow cultivate',
    }


def build_district_entry(district_code: str) -> dict | None:
    """Return {topic, body_en, keywords} for one district, or None if empty."""
    crops = _crops_for_district(district_code)
    if not crops:
        return None
    district_name = get_district_name(district_code)
    zones = DISTRICT_TO_KAU_ZONES.get(district_code, [])
    zones_display = ', '.join(zones) if zones else 'all Kerala zones'

    body = (
        f'In {district_name} district, KAU-documented suitable crops (across '
        f'the {zones_display} zones plus crops that grow across all Kerala) '
        f'include: {_format_crop_list(crops)}. '
        f'Total: {len(crops)} crops recommended for {district_name}. '
        f'Source: KAU Package of Practices — CropZoneProfile.'
    )
    # Every alias, malayalam name, and code — so "Trivandrum", "TVM",
    # "തിരുവനന്തപുരം" all hit the "Thiruvananthapuram" entry.
    aliases = " ".join(get_district_search_terms(district_code))
    return {
        'topic':    f'District: {district_name} — Suitable Crops',
        'body_en':  body,
        'keywords': (
            f'{aliases} district location where '
            f'{" ".join(zones)} zone crops suitable which what grow cultivate plant'
        ),
    }


def upsert_zone_entry(zone_name: str) -> tuple[bool, bool]:
    """Sync one zone's chatbot entry. Returns (created, deleted)."""
    from apps.database.models import ChatKnowledgeEntry
    entry = build_zone_entry(zone_name)
    if not entry:
        deleted = ChatKnowledgeEntry.objects.filter(
            topic=f'Zone: {zone_name} — Suitable Crops',
        ).delete()[0]
        return (False, bool(deleted))
    _obj, was_new = ChatKnowledgeEntry.objects.update_or_create(
        topic=entry['topic'],
        defaults={
            'body_en':       entry['body_en'],
            'keywords':      entry['keywords'],
            'audiences':     DEFAULT_AUDIENCES,
            'pages':         [],
            'is_active':     True,
            'display_order': DEFAULT_DISPLAY_ORDER,
        },
    )
    return (was_new, False)


def upsert_district_entry(district_code: str) -> tuple[bool, bool]:
    """Sync one district's chatbot entry. Returns (created, deleted)."""
    from apps.database.models import ChatKnowledgeEntry
    entry = build_district_entry(district_code)
    if not entry:
        deleted = ChatKnowledgeEntry.objects.filter(
            topic__startswith=f'District: ',
            topic__endswith=' — Suitable Crops',
            keywords__icontains=district_code,
        ).delete()[0]
        return (False, bool(deleted))
    _obj, was_new = ChatKnowledgeEntry.objects.update_or_create(
        topic=entry['topic'],
        defaults={
            'body_en':       entry['body_en'],
            'keywords':      entry['keywords'],
            'audiences':     DEFAULT_AUDIENCES,
            'pages':         [],
            'is_active':     True,
            'display_order': DEFAULT_DISPLAY_ORDER,
        },
    )
    return (was_new, False)


def sync_all_zones_and_districts() -> dict:
    """Full rebuild. Used by the seed script and can be called from a shell."""
    zone_created = zone_deleted = 0
    for zone in ALL_KAU_ZONES:
        c, d = upsert_zone_entry(zone)
        zone_created += int(c)
        zone_deleted += int(d)

    dist_created = dist_deleted = 0
    for code, _ in District.choices:
        c, d = upsert_district_entry(code)
        dist_created += int(c)
        dist_deleted += int(d)

    return {
        'zones_created':       zone_created,
        'zones_deleted_empty': zone_deleted,
        'districts_created':   dist_created,
        'districts_deleted_empty': dist_deleted,
    }
