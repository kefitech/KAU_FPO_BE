"""
Arunima S

Buyer-seller matching — rule-based for Phase 2 launch (ARUNIMA.md: "No AI
needed for Phase 2 launch").

Note on units: Product.unit is a choice field (kg/quintal/mt/litre/piece).
BuyerDirectory.unit is free text and often blank. This version matches on
commodity + quantity range only and does NOT attempt unit conversion —
if a buyer wants "quintal" and the product lists "kg", quantity comparison
will be wrong. Flag for the team: either normalize units at write-time
(convert BuyerDirectory.unit to the same choice set) or add a conversion
step here before this goes live with real data.
"""

from decimal import Decimal


def run_matching(stock):
    """
    Find verified buyers interested in this stock batch's product commodity
    and quantity range.

    Takes a ProductStock (the batch that just went ACTIVE), not a Product —
    different batches of the same product can have different quantities and
    therefore different match scores. BuyerSellerMatch is still keyed on
    (product, buyer) so matching the same product twice from two batches
    only ever creates one row.
    """
    from apps.database.models import BuyerDirectory, BuyerSellerMatch

    product = stock.product
    buyers = BuyerDirectory.objects.filter(
        is_verified=True,
        commodities_interested__contains=[product.commodity.code],
    )

    created = []
    for buyer in buyers:
        # Skip if already matched
        if BuyerSellerMatch.objects.filter(product=product, buyer=buyer).exists():
            continue

        # Simple score — 1.0 if quantity fits buyer's stated range, 0.5 otherwise.
        # match_score is DecimalField(max_digits=4, decimal_places=3) -> use Decimal.
        score = Decimal('1.000')
        if buyer.min_quantity and stock.quantity < buyer.min_quantity:
            score = Decimal('0.500')
        if buyer.max_quantity and stock.quantity > buyer.max_quantity:
            score = Decimal('0.500')

        match = BuyerSellerMatch.objects.create(
            product=product,
            buyer=buyer,
            match_score=score,
        )
        created.append(match)

    return created


def compute_opportunities():
    """
    Market demand signals by commodity — for GET /api/marketplace/opportunities/.

    Not in ARUNIMA.md's original endpoint list (this is from the other P2-11
    spec doc), and there's no dedicated "demand" model in the real schema.
    Built from what actually exists: BuyerDirectory.commodities_interested
    (verified buyers only) counted per commodity, joined with each
    commodity's most recent MarketPrice entry if one exists.

    Returns a list of dicts, sorted by buyer demand (highest first):
        [{
            "commodity_code": "RICE",
            "interested_buyer_count": 5,
            "latest_price": {
                "date": date(...),
                "modal_price": Decimal("..."),
                "market_name": "...",
                "source": "AGMARKNET",
            } or None,
        }, ...]
    """
    from collections import Counter

    from apps.database.models import BuyerDirectory, MarketPrice

    # Count how many verified buyers want each commodity code.
    # commodities_interested is a JSONField list, so this has to be done in
    # Python rather than a single ORM aggregate — fine at this data scale.
    counter = Counter()
    for codes in BuyerDirectory.objects.filter(is_verified=True).values_list(
        'commodities_interested', flat=True
    ):
        for code in codes or []:
            counter[code] += 1

    opportunities = []
    for code, buyer_count in counter.items():
        latest_price = (
            MarketPrice.objects.filter(commodity__code=code, is_deleted=False)
            .order_by('-date')
            .first()
        )
        opportunities.append({
            'commodity_code': code,
            'interested_buyer_count': buyer_count,
            'latest_price': {
                'date': latest_price.date,
                'modal_price': latest_price.modal_price,
                'market_name': latest_price.market_name,
                'source': latest_price.source,
            } if latest_price else None,
        })

    return sorted(opportunities, key=lambda o: o['interested_buyer_count'], reverse=True)

def _get_buyer_row(user):
    """Resolve the BuyerDirectory row for this user, whichever way they're linked."""
    buyer = getattr(user, 'buyer_profile', None)
    if buyer is not None:
        return buyer

    fpo = getattr(user, 'fpo', None)
    if fpo is not None:
        buyer = fpo.buyer_registration.first()
        if buyer is not None:
            return buyer

    return None


def buyer_catalogue_queryset(buyer):
    """
    Stock batches this buyer can see in the catalogue — the same rules as
    BuyerProductListView: public, not deleted, ACTIVE or EXPIRED but still
    inside the PRODUCT_GRACE_DAYS window, and never the buyer's own FPO's
    listings. Used for the buyer dashboard counts so they match the catalogue.
    """
    from datetime import timedelta

    from django.db.models import Q
    from django.utils import timezone

    from apps.database.models import ProductStock
    from apps.marketplace.tasks import PRODUCT_GRACE_DAYS

    grace_cutoff = timezone.now().date() - timedelta(days=PRODUCT_GRACE_DAYS)
    qs = ProductStock.objects.filter(
        is_public=True, is_deleted=False, product__is_deleted=False,
    ).filter(
        Q(status=ProductStock.Status.ACTIVE)
        | Q(status=ProductStock.Status.EXPIRED, available_until__gte=grace_cutoff)
    )
    if buyer.fpo_id:
        qs = qs.exclude(product__fpo_id=buyer.fpo_id)
    return qs


def get_buyer_redirect(user):
    """
    Return redirect status dict for buyer users (external or FPO-as-buyer).
    Returns None if the user has no BuyerDirectory row at all.
    """
    buyer = _get_buyer_row(user)
    if buyer is None:
        return None
    return {'status': buyer.status}
