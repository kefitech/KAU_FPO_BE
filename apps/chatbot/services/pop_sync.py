"""
POP → ChatKnowledgeEntry sync helpers.

Two callers:
  1. scripts/seed_chatbot_knowledge_from_pop.py — bulk seed
  2. apps/chatbot/signals.py — live sync on POP row save/delete

Both use `build_entries_for_crop()` + `upsert_entries_for_crop()` so
the shape of a chatbot POP entry is defined in exactly one place.
"""

DEFAULT_AUDIENCES = ['public', 'fpo_manager', 'cbbo', 'government', 'expert']
DEFAULT_DISPLAY_ORDER = 500


def _clean(text):
    if not text:
        return ''
    return ' '.join(str(text).split())


def _zone_notes_for(crop_name: str) -> str:
    from apps.database.models import CropZoneProfile
    zones = list(
        CropZoneProfile.objects
        .filter(crop_name__iexact=crop_name, is_active=True, is_deleted=False)
        .values_list('kau_zone', flat=True).distinct()
    )
    return ', '.join(z for z in zones if z)


def _keywords_for(pop, section: str) -> str:
    tokens = [pop.crop_name, pop.crop_group, section]
    for v in (pop.varieties or []):
        if isinstance(v, dict) and v.get('name'):
            tokens.append(v['name'])
    return ' '.join(t for t in tokens if t)


def build_entries_for_crop(pop) -> list[dict]:
    """Return a list of {topic, body_en, keywords} dicts for one crop.

    Skips empty sections. Each entry is a self-contained answer with the
    KAU source line appended.
    """
    entries = []
    src = pop.source_reference or 'KAU Package of Practices'
    zone_notes = _zone_notes_for(pop.crop_name)

    # ── Overview ────────────────────────────────────────────────
    overview_parts = [f'Crop: {pop.crop_name}.']
    if pop.crop_group:
        overview_parts.append(f'Group: {pop.crop_group}.')
    if pop.season:
        overview_parts.append(f'Season: {_clean(pop.season)}.')
    if pop.expected_yield:
        overview_parts.append(f'Expected yield: {_clean(pop.expected_yield)}.')
    if zone_notes:
        overview_parts.append(f'Suitable zones: {zone_notes}.')
    overview_parts.append(f'Source: {src}.')
    if len(overview_parts) >= 3:
        entries.append({
            'topic':    f'POP: {pop.crop_name} — Overview',
            'body_en':  ' '.join(overview_parts),
            'keywords': _keywords_for(pop, 'overview crop general'),
        })

    # ── Varieties ───────────────────────────────────────────────
    var_names = ', '.join(
        v.get('name', '').strip()
        for v in (pop.varieties or [])
        if isinstance(v, dict) and v.get('name')
    )
    if var_names:
        entries.append({
            'topic':    f'POP: {pop.crop_name} — Varieties',
            'body_en':  f'Recommended varieties for {pop.crop_name} (per KAU PoP): {var_names}. Source: {src}.',
            'keywords': _keywords_for(pop, 'variety varieties cultivar seed'),
        })

    # ── Spacing ─────────────────────────────────────────────────
    if pop.spacing:
        entries.append({
            'topic':    f'POP: {pop.crop_name} — Spacing',
            'body_en':  f'Spacing for {pop.crop_name}: {_clean(pop.spacing)}. Source: {src}.',
            'keywords': _keywords_for(pop, 'spacing planting distance layout'),
        })

    # ── Manuring & Fertilizer ───────────────────────────────────
    if pop.manuring_fertilizer:
        entries.append({
            'topic':    f'POP: {pop.crop_name} — Manuring & Fertilizer',
            'body_en':  f'Manuring and fertiliser recommendations for {pop.crop_name}: {_clean(pop.manuring_fertilizer)} Source: {src}.',
            'keywords': _keywords_for(pop, 'manuring fertilizer fertiliser npk urea potash nutrient'),
        })

    # ── Plant Protection ────────────────────────────────────────
    if pop.plant_protection:
        entries.append({
            'topic':    f'POP: {pop.crop_name} — Plant Protection',
            'body_en':  f'Plant protection guidance for {pop.crop_name}: {_clean(pop.plant_protection)} Source: {src}.',
            'keywords': _keywords_for(pop, 'pest disease insect fungus spray pesticide'),
        })

    # ── Harvesting ──────────────────────────────────────────────
    if pop.harvesting:
        entries.append({
            'topic':    f'POP: {pop.crop_name} — Harvesting',
            'body_en':  f'Harvesting guidance for {pop.crop_name}: {_clean(pop.harvesting)} Source: {src}.',
            'keywords': _keywords_for(pop, 'harvest maturity yield timing'),
        })

    # ── Extra free-form sections ────────────────────────────────
    for section in (pop.sections or []):
        if not isinstance(section, dict):
            continue
        heading = section.get('heading', '').strip()
        body    = _clean(section.get('body', ''))
        if not heading or not body:
            continue
        entries.append({
            'topic':    f'POP: {pop.crop_name} — {heading}',
            'body_en':  f'{heading} for {pop.crop_name}: {body} Source: {src}.',
            'keywords': _keywords_for(pop, heading.lower()),
        })

    return entries


def upsert_entries_for_crop(pop, *, is_active: bool = True) -> tuple[int, int, int]:
    """Sync one crop's chatbot entries.

    Returns (created, updated, deleted). Deletes any prior entries for this
    crop that are no longer in the fresh build (e.g. admin removed the
    varieties field → stale "POP: X — Varieties" entry goes away).
    """
    from apps.database.models import ChatKnowledgeEntry

    fresh = build_entries_for_crop(pop) if is_active else []
    fresh_topics = {e['topic'] for e in fresh}

    # Delete stale entries for this crop that aren't in the fresh build.
    stale_qs = ChatKnowledgeEntry.objects.filter(
        topic__startswith=f'POP: {pop.crop_name} — ',
    ).exclude(topic__in=fresh_topics)
    # Also treat the un-sectioned legacy row as stale.
    stale_qs = stale_qs | ChatKnowledgeEntry.objects.filter(topic=f'POP: {pop.crop_name}')
    deleted = stale_qs.count()
    if deleted:
        stale_qs.delete()

    created = updated = 0
    for entry in fresh:
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
        if was_new: created += 1
        else:       updated += 1

    return created, updated, deleted


def delete_entries_for_crop(crop_name: str) -> int:
    """Remove all chatbot entries for a crop. Used when a POP row is deleted."""
    from apps.database.models import ChatKnowledgeEntry
    qs = ChatKnowledgeEntry.objects.filter(
        topic__startswith=f'POP: {crop_name}',
    )
    count = qs.count()
    qs.delete()
    return count
