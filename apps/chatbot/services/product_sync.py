"""
Product (with active public stock) → ChatKnowledgeEntry sync.

One entry per active listable stock batch, so queries like "cheapest
basmati rice" or "who has organic tomato" can find specific product
listings — not just the parent FPO summary.

Entry topic:
    Product: <product name> from <FPO name> — Active Listing

Sync rules:
  - Build entry only when stock.is_public + stock.status == 'active'
    + parent product & FPO not deleted + parent FPO is APPROVED
  - Delete entry when any of those conditions flips off

Signals in apps/chatbot/signals.py call `upsert_product_entry(stock)` on
every ProductStock save/delete. The parent FPO's summary entry is also
kept in sync via fpo_sync.py — the two families are complementary.
"""

import logging

from apps.core.utils.constants import get_district_name, get_district_search_terms

logger = logging.getLogger(__name__)


DEFAULT_AUDIENCES = ['public', 'fpo_manager', 'cbbo', 'government', 'expert']
DEFAULT_DISPLAY_ORDER = 470   # a hair above FPO summaries (480) so product hits surface first


def _stock_is_listable(stock) -> bool:
    """Only public + active + non-deleted stock is a chatbot-worthy listing."""
    if not stock or stock.is_deleted:
        return False
    if not stock.is_public or stock.status != 'active':
        return False
    return True


def _product_name_en(product) -> str:
    if isinstance(product.name, dict):
        return (product.name.get('en') or product.name.get('ml') or '').strip()
    return str(product.name).strip()


def _fpo_qualifies(fpo) -> bool:
    from apps.core.utils.constants import FPOStatus
    return bool(fpo) and not fpo.is_deleted and fpo.status == FPOStatus.APPROVED


def _commodity_label(product) -> str:
    """Human name for the product's canonical commodity."""
    if not product.commodity_id:
        return ''
    try:
        return product.commodity.get_name(language='en') or product.commodity.code
    except Exception:
        return ''


def build_product_entry(stock) -> dict | None:
    """Return {topic, body_en, keywords} for one active stock listing, or None
    when the listing isn't chatbot-eligible."""
    if not _stock_is_listable(stock):
        return None

    product = stock.product
    if not product or product.is_deleted:
        return None

    fpo = product.fpo
    if not _fpo_qualifies(fpo):
        return None

    product_name = _product_name_en(product)
    if not product_name:
        return None

    commodity   = _commodity_label(product)
    district_en = get_district_name(fpo.district, language='en') if fpo.district else 'district not set'
    tier_line   = f'Tier {fpo.tier}' if fpo.tier else 'tier not yet assessed'
    unit        = stock.unit
    avail_from  = stock.available_from.isoformat() if stock.available_from else 'unspecified'
    avail_until = stock.available_until.isoformat() if stock.available_until else 'open-ended'

    parts = [
        f'{fpo.name} ({district_en}, {tier_line}) is currently listing '
        f'{stock.quantity} {unit} of {product_name}'
    ]
    if commodity and commodity.lower() not in product_name.lower():
        parts[-1] += f' ({commodity})'
    parts[-1] += f' at ₹{stock.price_per_unit} per {unit}.'

    if stock.quality_certification:
        parts.append(f'Quality: {stock.quality_certification}.')
    parts.append(f'Available from {avail_from} to {avail_until}.')

    # Malayalam product name in the body so a Malayalam chatbot user can also
    # recognise the listing. Kept short to not bloat the FTS body weight.
    if isinstance(product.name, dict) and product.name.get('ml'):
        parts.append(f'({product.name["ml"]})')

    parts.append('Contact this FPO via the KAU-FPO Market Hub. Source: KAU-FPO Marketplace.')

    # Keywords — every way a searcher might phrase it.
    kw = [
        product_name,
        commodity,
        fpo.name,
    ]
    if isinstance(product.name, dict) and product.name.get('ml'):
        kw.append(product.name['ml'])
    if fpo.name_ml:
        kw.append(fpo.name_ml)
    if fpo.district:
        kw.extend(get_district_search_terms(fpo.district))
    kw.extend([
        stock.quality_certification or '',
        f'₹{stock.price_per_unit}',
        f'{stock.quantity}',
        unit,
        'buy', 'sell', 'sale', 'price', 'available',
        'listing', 'stock', 'active', 'product',
    ])

    return {
        'topic':    f'Product: {product_name} from {fpo.name} — Active Listing',
        'body_en':  ' '.join(parts),
        'keywords': ' '.join(t for t in kw if t),
        # stash for delete-fallback logic
        '_topic':   f'Product: {product_name} from {fpo.name} — Active Listing',
    }


def upsert_product_entry(stock) -> tuple[bool, bool]:
    """Sync one stock's chatbot entry. Returns (created, deleted).

    When the stock no longer qualifies (draft/sold/expired/private/deleted)
    the corresponding entry (identified by product + fpo names) is dropped.
    """
    from apps.database.models import ChatKnowledgeEntry

    entry = build_product_entry(stock)
    if not entry:
        # Nothing to index. Look up the product/fpo names to remove any
        # stale entry we may have written previously.
        product = getattr(stock, 'product', None)
        fpo     = getattr(product, 'fpo', None) if product else None
        if product and fpo:
            name = _product_name_en(product)
            if name:
                deleted = ChatKnowledgeEntry.objects.filter(
                    topic=f'Product: {name} from {fpo.name} — Active Listing',
                ).delete()[0]
                return (False, bool(deleted))
        return (False, False)

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


def delete_entry_for_stock(stock) -> bool:
    """Hard-delete the chatbot entry for this stock's product.
    Used from post_delete signals where the instance's flags don't yet
    reflect that the row is gone."""
    from apps.database.models import ChatKnowledgeEntry
    product = getattr(stock, 'product', None)
    fpo     = getattr(product, 'fpo', None) if product else None
    if not (product and fpo):
        return False
    name = _product_name_en(product)
    if not name:
        return False
    deleted = ChatKnowledgeEntry.objects.filter(
        topic=f'Product: {name} from {fpo.name} — Active Listing',
    ).delete()[0]
    return bool(deleted)


def delete_product_entries_for_fpo(fpo_name: str) -> int:
    """Prune every product entry belonging to an FPO — used when the FPO
    itself is deleted / de-approved."""
    from apps.database.models import ChatKnowledgeEntry
    qs = ChatKnowledgeEntry.objects.filter(
        topic__startswith='Product: ',
        topic__endswith=f' from {fpo_name} — Active Listing',
    )
    count = qs.count()
    qs.delete()
    return count


def sync_all_active_products() -> dict:
    """Full rebuild — used by the seed script."""
    from apps.database.models.marketplace import ProductStock

    stocks = ProductStock.objects.select_related('product__fpo').filter(
        is_deleted=False, is_public=True, status='active',
    )
    created = updated = skipped = 0
    for stock in stocks:
        c, d = upsert_product_entry(stock)
        if c:            created += 1
        elif not d:      updated += 1
        else:            skipped += 1

    return {
        'stocks_processed': stocks.count(),
        'created':          created,
        'updated':          updated,
        'skipped':          skipped,
    }
