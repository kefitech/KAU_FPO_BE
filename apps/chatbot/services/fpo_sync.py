"""
FPO → ChatKnowledgeEntry sync.

One entry per APPROVED FPO, summarising:
  - FPO name (EN + ML if set), application ID
  - District, tier, primary commodities
  - Active product listings (public + within stock validity)

Used by both:
  1. scripts/seed_chatbot_knowledge_from_fpos.py — bulk seed
  2. apps/chatbot/signals.py — live sync on FPO/Product save/delete

Kept privacy-safe: no personal emails/phones. Buyers/users can find the
FPO via the KAU-FPO market hub and inquire through the platform's own form.
"""

import logging

from apps.core.utils.constants import get_district_name, get_district_search_terms


logger = logging.getLogger(__name__)


DEFAULT_AUDIENCES = ['public', 'fpo_manager', 'cbbo', 'government', 'expert']
DEFAULT_DISPLAY_ORDER = 480    # a hair above the 500 POP entries so FPO summaries surface first
MAX_PRODUCTS_IN_BODY = 8       # cap to keep body compact for Gemini


def _product_lines(product) -> list[str]:
    """
    Return one line per listable active stock batch for this product (a
    product can now have multiple batches live at the same time).
    Returns [] if the product has nothing public + active to list.
    """
    name = ''
    if isinstance(product.name, dict):
        name = product.name.get('en') or product.name.get('ml') or ''
    if not name:
        return []

    # Walk prefetched stocks when available to avoid N+1 inside sync loops.
    cache = getattr(product, '_prefetched_objects_cache', None)
    if cache and 'stocks' in cache:
        stocks = list(cache['stocks'])
    else:
        stocks = list(product.stocks.filter(is_deleted=False))

    lines = []
    for stock in stocks:
        if getattr(stock, 'is_deleted', False):
            continue
        if not stock.is_public or stock.status != 'active':
            continue
        parts = [name,
                 f'{stock.quantity} {stock.unit}',
                 f'₹{stock.price_per_unit}/{stock.unit}']
        if stock.quality_certification:
            parts.append(stock.quality_certification)
        lines.append(' — '.join(parts))
    return lines


def _commodity_labels_for(fpo) -> list[str]:
    """Extract primary commodity labels from the FPO's own crops list.

    FPO.primary_commodities is a JSON list of MasterLookup codes; display
    names live in the Translation table via MasterLookup.get_name().
    """
    codes = getattr(fpo, 'primary_commodities', None) or []
    if not isinstance(codes, list) or not codes:
        return []

    from apps.core.models.generic import MasterLookup
    lookups = MasterLookup.objects.filter(
        category='commodity', code__in=codes, is_active=True,
    )
    labels = [lk.get_name(language='en') for lk in lookups]
    return [lbl for lbl in labels if lbl]


def build_fpo_entry(fpo) -> dict | None:
    """Return {topic, body_en, keywords} for one APPROVED FPO, or None if we
    shouldn't index it (not approved, no name, etc.)."""
    from apps.core.utils.constants import FPOStatus

    if fpo.is_deleted or fpo.status != FPOStatus.APPROVED:
        return None
    if not fpo.name:
        return None

    tier_line   = f'Tier {fpo.tier}' if fpo.tier else 'Tier not yet assessed'
    district_en = get_district_name(fpo.district, language='en') if fpo.district else 'district not set'
    application = fpo.application_id or 'application ID pending'

    # Product summary — one line per public ACTIVE stock batch. We cap the
    # total number of lines in the body (not products) at
    # MAX_PRODUCTS_IN_BODY so a single product with many batches doesn't
    # starve the summary.
    products    = fpo.products.prefetch_related('stocks').filter(is_deleted=False)
    prod_lines = []
    for p in products:
        for line in _product_lines(p):
            prod_lines.append(line)
            if len(prod_lines) >= MAX_PRODUCTS_IN_BODY:
                break
        if len(prod_lines) >= MAX_PRODUCTS_IN_BODY:
            break
    total_prods = fpo.products.filter(is_deleted=False).count()

    body_parts = [
        f'{fpo.name} (application ID {application}) is an APPROVED FPO '
        f'based in {district_en} district, currently rated {tier_line}.'
    ]

    commodities = _commodity_labels_for(fpo)
    if commodities:
        body_parts.append(f'Primary commodities: {", ".join(commodities)}.')

    if prod_lines:
        prod_list = '; '.join(prod_lines)
        suffix = f' (+{total_prods - len(prod_lines)} more)' if total_prods > len(prod_lines) else ''
        body_parts.append(f'Active product listings: {prod_list}{suffix}.')
    elif total_prods > 0:
        body_parts.append(f'The FPO has {total_prods} product record(s) but no publicly-listed active stock at the moment.')

    body_parts.append(
        'For contact details, reach the FPO directly via the KAU-FPO market hub. '
        'Source: KAU-FPO Registry.'
    )

    # Build the searchable keyword string
    kw_parts = [fpo.name]
    if fpo.name_ml:
        kw_parts.append(fpo.name_ml)
    if application != 'application ID pending':
        kw_parts.append(application)
    kw_parts.extend(get_district_search_terms(fpo.district) if fpo.district else [])
    kw_parts.extend(commodities)
    for line in prod_lines:
        # first token of the product line = name — helpful for "who sells X"
        kw_parts.append(line.split(' — ')[0])
    kw_parts.extend(['FPO', 'producer organisation', 'sells', 'products', 'listings'])

    return {
        'topic':    f'FPO: {fpo.name} — Details & Products',
        'body_en':  ' '.join(body_parts),
        'keywords': ' '.join(t for t in kw_parts if t),
    }


def upsert_fpo_entry(fpo) -> tuple[bool, bool]:
    """Sync one FPO's chatbot entry. Returns (created, deleted).
    Deletes the entry when the FPO no longer qualifies (not APPROVED / soft-deleted)."""
    from apps.database.models import ChatKnowledgeEntry

    entry = build_fpo_entry(fpo)
    topic_prefix = f'FPO: {fpo.name} — '

    if not entry:
        deleted = ChatKnowledgeEntry.objects.filter(
            topic__startswith=topic_prefix,
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


def delete_fpo_entries(fpo_name: str) -> int:
    """Remove chatbot entries for a hard-deleted / renamed FPO."""
    from apps.database.models import ChatKnowledgeEntry
    qs = ChatKnowledgeEntry.objects.filter(
        topic__startswith=f'FPO: {fpo_name} — ',
    )
    count = qs.count()
    qs.delete()
    return count


def sync_all_approved_fpos() -> dict:
    """Full rebuild — used by the seed script."""
    from apps.core.utils.constants import FPOStatus
    from apps.database.models.fpo import FPO
    created = updated = skipped = 0
    fpos = FPO.objects.filter(status=FPOStatus.APPROVED, is_deleted=False).prefetch_related('products__stocks')
    for fpo in fpos:
        c, d = upsert_fpo_entry(fpo)
        if c: created += 1
        elif not d: updated += 1
        else: skipped += 1
    return {
        'created':  created,
        'updated':  updated,
        'skipped':  skipped,
        'total_fpos_processed': fpos.count(),
    }
