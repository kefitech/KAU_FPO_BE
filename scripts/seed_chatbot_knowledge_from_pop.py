"""
Turn KAU's CropPackageOfPractices rows into ChatKnowledgeEntry rows so the
chatbot can answer crop-related questions from KAU's own PoP data.

Idempotent: uses topic prefix "POP: <crop>" and update_or_create so re-runs
refresh the body without duplicating entries.

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/seed_chatbot_knowledge_from_pop.py').read())
    seed_chatbot_knowledge_from_pop()
    "
"""

from apps.database.models import (
    ChatKnowledgeEntry,
    CropPackageOfPractices,
    CropZoneProfile,
)


def _clean(text):
    """Trim + collapse whitespace so search-vector weights stay meaningful."""
    if not text:
        return ''
    return ' '.join(str(text).split())


def _body_for(pop: CropPackageOfPractices, zone_notes: str) -> str:
    """Build the body_en for one POP row — merges all populated fields into
    a single concise paragraph the QA model can quote spans from."""
    parts = [f'Crop: {pop.crop_name}.']
    if pop.crop_group:
        parts.append(f'Group: {pop.crop_group}.')
    if pop.season:
        parts.append(f'Season: {_clean(pop.season)}.')
    if pop.varieties:
        # varieties is a JSON list of {name, description?} dicts.
        var_names = ', '.join(v.get('name', '').strip() for v in pop.varieties if isinstance(v, dict) and v.get('name'))
        if var_names:
            parts.append(f'Recommended varieties: {var_names}.')
    if pop.spacing:
        parts.append(f'Spacing: {_clean(pop.spacing)}.')
    if pop.manuring_fertilizer:
        parts.append(f'Manuring / fertiliser: {_clean(pop.manuring_fertilizer)}.')
    if pop.plant_protection:
        parts.append(f'Plant protection: {_clean(pop.plant_protection)}.')
    if pop.harvesting:
        parts.append(f'Harvesting: {_clean(pop.harvesting)}.')
    if pop.expected_yield:
        parts.append(f'Expected yield: {_clean(pop.expected_yield)}.')
    if zone_notes:
        parts.append(f'Suitable zones: {zone_notes}.')
    # Book sections that don't map to the fixed fields — append verbatim.
    for section in (pop.sections or []):
        if isinstance(section, dict):
            heading = section.get('heading', '').strip()
            body    = _clean(section.get('body', ''))
            if heading and body:
                parts.append(f'{heading}: {body}.')
    parts.append(f'Source: {pop.source_reference or "KAU Package of Practices"}.')
    return ' '.join(parts)


def _keywords_for(pop: CropPackageOfPractices) -> str:
    """Extra search terms so misspellings / regional names still hit."""
    tokens = [pop.crop_name, pop.crop_group]
    for v in (pop.varieties or []):
        if isinstance(v, dict) and v.get('name'):
            tokens.append(v['name'])
    return ' '.join(t for t in tokens if t)


def _zone_notes_for(crop_name: str) -> str:
    """Comma-list of KAU zones this crop is documented for."""
    zones = list(
        CropZoneProfile.objects
        .filter(crop_name__iexact=crop_name, is_active=True, is_deleted=False)
        .values_list('kau_zone', flat=True).distinct()
    )
    return ', '.join(z for z in zones if z)


def seed_chatbot_knowledge_from_pop(dry_run: bool = False):
    created = updated = skipped = 0
    pops = CropPackageOfPractices.objects.filter(is_active=True, is_deleted=False).order_by('crop_name')
    print(f'Found {pops.count()} active POP rows.')

    for pop in pops:
        topic = f'POP: {pop.crop_name}'
        body  = _body_for(pop, _zone_notes_for(pop.crop_name))
        # Skip rows where every field is empty — the ingest gives nothing useful.
        if len(body) < 80:  # "Crop: X. Source: Y." — too skimpy
            skipped += 1
            continue

        kws = _keywords_for(pop)

        if dry_run:
            print(f'  [dry] {topic:40s}  body={len(body):5d} chars  kws="{kws[:40]}…"')
            continue

        _obj, was_new = ChatKnowledgeEntry.objects.update_or_create(
            topic=topic,
            defaults={
                'body_en':       body,
                'keywords':      kws,
                'audiences':     ['public', 'fpo_manager', 'cbbo', 'government', 'expert'],
                'pages':         [],
                'is_active':     True,
                'display_order': 500,   # sort below platform-help entries
            },
        )
        if was_new: created += 1
        else:       updated += 1
        print(f'  {"✅ NEW" if was_new else "🔄 UPD"}  {topic}')

    print()
    print(f'✅ POP → chatbot KB seed complete.')
    print(f'   Created: {created}  Updated: {updated}  Skipped (empty): {skipped}')
    print(f'   Total chatbot KB entries: {ChatKnowledgeEntry.objects.count()}')
