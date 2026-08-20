# Arunima — P2-11 Marketplace + P2-12 Market Hub + P2-14 Marketing Strategies

## What You Are Building

Three connected modules:
1. **Marketplace (P2-11)** — FPOs list their products for sale. Admin manages a buyer directory. System matches buyers to products.
2. **Market Hub (P2-12)** — Public-facing page showing active products and live commodity prices (no login required).
3. **Marketing Strategies (P2-14)** — AI-generated marketing plans per FPO per commodity. Build the data layer and endpoints; Claude API content generation comes later.

---

## Models (Already Written — Do Not Change)

All models are in `apps/database/models/`. Your models are:

| Model | File |
|---|---|
| `Product` | `apps/database/models/marketplace.py` |
| `BuyerDirectory` | `apps/database/models/marketplace.py` |
| `BuyerSellerMatch` | `apps/database/models/marketplace.py` |
| `MarketPrice` | `apps/database/models/marketplace.py` |
| `MarketingStrategy` | `apps/database/models/marketing.py` |

**Do not move models.** API logic goes in `apps/marketplace/` and the marketing strategy endpoints can live in the same app or `apps/marketplace/api/marketing.py`.

---

## Step 1 — Run Migrations

```bash
source venv/bin/activate
python manage.py migrate
```

Confirm clean before starting APIs.

---

## Step 2 — Folder Structure to Create

```
apps/marketplace/api/
├── products.py         ← FPO product CRUD
├── buyers.py           ← Admin buyer directory
├── matches.py          ← Buyer-seller match endpoints
├── market_prices.py    ← Market price list (admin seed + FPO view)
├── market_hub.py       ← Public endpoints (no auth)
├── marketing.py        ← Marketing strategy endpoints
└── urls.py
```

---

## Step 3 — Endpoints to Build

### Products (FPO — must be APPROVED to list products)

```
GET    /api/marketplace/products/                  — list my FPO's products
POST   /api/marketplace/products/                  — create product listing
GET    /api/marketplace/products/{id}/             — detail
PATCH  /api/marketplace/products/{id}/             — edit (only if status=draft or active)
DELETE /api/marketplace/products/{id}/             — soft delete (draft only)
POST   /api/marketplace/products/{id}/publish/     — draft → active
POST   /api/marketplace/products/{id}/mark-sold/   — active → sold
```

### Buyer Directory (Admin only)

```
GET    /api/admin/buyers/                  — list all buyers
POST   /api/admin/buyers/                  — add new buyer
PATCH  /api/admin/buyers/{id}/             — edit buyer
DELETE /api/admin/buyers/{id}/             — remove buyer
POST   /api/admin/buyers/{id}/verify/      — mark buyer as verified
```

### Buyer-Seller Matches (Admin + FPO)

```
GET  /api/marketplace/matches/             — FPO sees suggested matches for their products
POST /api/marketplace/matches/{id}/accept/ — FPO accepts a match
POST /api/marketplace/matches/{id}/reject/ — FPO rejects a match
GET  /api/admin/matches/                   — admin sees all matches
```

### Market Prices

```
GET  /api/marketplace/prices/             — list prices (filter by commodity, date)
GET  /api/admin/prices/                   — admin list
POST /api/admin/prices/                   — admin manually seeds price data
```

### Public Market Hub (no auth — use `AllowAny`)

```
GET  /api/public/market/products/          — active public products (is_public=True)
GET  /api/public/market/prices/            — today's commodity prices
GET  /api/public/market/prices/{commodity}/ — price history for one commodity
```

### Marketing Strategies

```
GET  /api/marketplace/marketing/           — my FPO's strategies
POST /api/marketplace/marketing/           — generate strategy (returns placeholder until Claude wired)
GET  /api/marketplace/marketing/{id}/      — detail
GET  /api/marketplace/marketing/{id}/pdf/  — download PDF
```

---

## How to Write a ViewSet — Copy This Pattern

```python
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from drf_spectacular.utils import extend_schema
from apps.core.views import TranslatedViewSet
from apps.core.utils.responses import StandardResponse
from apps.core.utils.pagination import StandardPagination
from apps.core.permissions.rbac import IsFPOManager
from apps.core.services.translation import t
from apps.database.models import Product


class ProductViewSet(TranslatedViewSet):
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated, IsFPOManager]
    pagination_class = StandardPagination

    list_message    = 'marketplace.products_retrieved'
    create_message  = 'marketplace.product_created'
    update_message  = 'marketplace.product_updated'
    destroy_message = 'marketplace.product_deleted'

    def get_queryset(self):
        # FPO only sees their own products
        fpo = self.request.user.fpo
        return Product.objects.filter(fpo=fpo).order_by('-created_at')

    @extend_schema(tags=["Marketplace - Products"])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(tags=["Marketplace - Products"])
    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        product = self.get_object()
        if product.status != Product.Status.DRAFT:
            return StandardResponse.error('Only draft products can be published', 400)
        product.status = Product.Status.ACTIVE
        product.save()
        lang = self.get_language()
        return StandardResponse.success(
            data=ProductSerializer(product).data,
            message=t('marketplace.product_published', lang)
        )
```

---

## Buyer-Seller Matching Logic

Build rule-based matching first. No AI needed for Phase 2 launch.

```python
# apps/marketplace/services.py

def run_matching(product):
    """Find buyers interested in this product's commodity and quantity range."""
    from apps.database.models import BuyerDirectory, BuyerSellerMatch

    buyers = BuyerDirectory.objects.filter(
        is_verified=True,
        commodities_interested__contains=product.commodity.code,
    )

    for buyer in buyers:
        # Skip if already matched
        if BuyerSellerMatch.objects.filter(product=product, buyer=buyer).exists():
            continue

        # Simple score — 1.0 if quantity fits, 0.7 otherwise
        score = 1.0
        if buyer.min_quantity and product.quantity < buyer.min_quantity:
            score = 0.5
        if buyer.max_quantity and product.quantity > buyer.max_quantity:
            score = 0.5

        BuyerSellerMatch.objects.create(
            product=product,
            buyer=buyer,
            match_score=score,
        )
```

Call this service in the `publish` action — run matching when product goes active.

---

## Marketing Strategy — Placeholder Response

Until Claude API is wired, return a placeholder:

```python
@action(detail=False, methods=['post'])
def generate(self, request):
    # Save the strategy record
    strategy = MarketingStrategy.objects.create(
        fpo=request.user.fpo,
        commodity_id=request.data['commodity_id'],
        target_segment=request.data['target_segment'],
        region=request.data['region'],
        financial_year=request.data.get('financial_year', '2025-26'),
        content={
            "market_overview": "AI generation pending — Claude API not yet configured.",
            "target_buyers": "",
            "pricing_strategy": "",
            "distribution_channels": "",
            "value_addition": "",
            "promotion_ideas": "",
            "seasonal_calendar": "",
        }
    )
    return StandardResponse.success(data=MarketingStrategySerializer(strategy).data)
```

---

## Celery Tasks to Create

Create `apps/marketplace/tasks.py`:

```python
from celery import shared_task

@shared_task
def expire_products():
    """Daily — mark products past available_until as expired."""
    from django.utils import timezone
    from apps.database.models import Product
    Product.objects.filter(
        status=Product.Status.ACTIVE,
        available_until__lt=timezone.now().date()
    ).update(status=Product.Status.EXPIRED)

@shared_task
def run_buyer_seller_matching():
    """Daily — run matching for all newly active products."""
    from apps.database.models import Product
    from apps.marketplace.services import run_matching
    for product in Product.objects.filter(status=Product.Status.ACTIVE):
        run_matching(product)

# Wire later — waiting for AGMARKNET API access
# @shared_task
# def refresh_market_prices():
#     pass
```

Register both tasks in `config/celery.py` beat schedule.

---

## Swagger Tags to Use

```python
@extend_schema(tags=["Marketplace - Products"])
@extend_schema(tags=["Marketplace - Buyers"])
@extend_schema(tags=["Marketplace - Matches"])
@extend_schema(tags=["Marketplace - Prices"])
@extend_schema(tags=["Marketplace - Market Hub"])     # public endpoints
@extend_schema(tags=["Marketplace - Marketing"])
```

---

## Translation Keys to Add

```
marketplace.products_retrieved
marketplace.product_created
marketplace.product_updated
marketplace.product_deleted
marketplace.product_published
marketplace.product_sold
marketplace.match_accepted
marketplace.match_rejected
marketplace.strategy_generated
marketplace.prices_retrieved
```

---

## Git Workflow

```bash
# Your branch names
feature/p2-11-product-listing
feature/p2-11-buyer-directory
feature/p2-11-buyer-matching
feature/p2-12-market-hub-public
feature/p2-14-marketing-strategy

# Raise PR to develop when each is done
```

---

## What NOT to Build Yet

- ONDC API integration (`Product.is_ondc_listed` flag stays False for now)
- Live AGMARKNET price pull Celery task (waiting for API access)
- Claude API for marketing strategy content (waiting for budget approval)
