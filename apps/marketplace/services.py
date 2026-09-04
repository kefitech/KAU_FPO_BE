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


def run_matching(product):
    """Find verified buyers interested in this product's commodity and quantity range."""
    from apps.database.models import BuyerDirectory, BuyerSellerMatch

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
        if buyer.min_quantity and product.quantity < buyer.min_quantity:
            score = Decimal('0.500')
        if buyer.max_quantity and product.quantity > buyer.max_quantity:
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