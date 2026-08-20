# P2-11: ONDC + Farmer Connect

**Status:** ⬜ Not started
**SRS Ref:** §3.2.3
**Depends on:** Nothing (but ONDC API credentials must be configured in ExternalAPISettings)
**App:** `apps/marketplace/`

---

## What This Module Does

Two integrated components:

1. **ONDC** — registers FPO products on the Open Network for Digital Commerce so buyers on any ONDC-compatible platform can discover them
2. **Farmer Connect** — internal AI-driven buyer-seller matching within the KAU-FPO platform

---

## API Credentials

ONDC API credentials stored in `ExternalAPISettings` (same pattern as SMS/PAN).
Admin configures via `POST /api/admin/external-apis/` with `service_name=ondc`.

---

## New Models

**File:** `apps/database/models/marketplace.py`

```python
class Product(BaseModel):
    fpo                   = FK(FPO)
    name                  = JSONField()          # {"en": "...", "ml": "..."}
    commodity             = FK(MasterLookup)     # links to commodity master data
    quantity              = DecimalField()
    unit                  = CharField()          # kg / quintal / MT
    price_per_unit        = DecimalField()
    quality_certification = CharField(blank=True)
    available_from        = DateField()
    available_until       = DateField(null=True)
    is_ondc_listed        = BooleanField(default=False)
    ondc_product_id       = CharField(null=True, blank=True)
    is_public             = BooleanField(default=False)  # visible on public Market Hub
    status                = CharField(choices=['draft', 'active', 'sold', 'expired'])

class BuyerDirectory(BaseModel):
    name                  = CharField()
    organisation          = CharField()
    contact_email         = CharField()
    contact_phone         = CharField()
    location              = CharField()
    commodities_interested = JSONField()         # list of commodity codes
    min_quantity          = DecimalField()
    max_quantity          = DecimalField()
    is_verified           = BooleanField(default=False)

class BuyerSellerMatch(BaseModel):
    product       = FK(Product)
    buyer         = FK(BuyerDirectory)
    match_score   = DecimalField()               # AI matching confidence 0–1
    status        = CharField(choices=['suggested', 'accepted', 'rejected', 'completed'])
    suggested_at  = DateTimeField(auto_now_add=True)

class MarketPrice(BaseModel):
    commodity    = FK(MasterLookup)
    market_name  = CharField()
    date         = DateField()
    min_price    = DecimalField()
    max_price    = DecimalField()
    modal_price  = DecimalField()
    source       = CharField(default='e-NAM')
```

---

## API Endpoints

### FPO Product Management

| Method | Endpoint | Who | Description |
|--------|----------|-----|-------------|
| GET/POST | `/api/marketplace/products/` | FPO | List / create FPO products |
| GET/PATCH/DELETE | `/api/marketplace/products/{id}/` | FPO | Detail / edit / remove |
| POST | `/api/marketplace/products/{id}/list-ondc/` | FPO | Push product to ONDC network |

### Market Data

| Method | Endpoint | Who | Description |
|--------|----------|-----|-------------|
| GET | `/api/marketplace/prices/` | All | e-NAM price history (filter by commodity, date) |
| GET | `/api/marketplace/opportunities/` | All | Market demand signals by commodity |

### Buyer Directory

| Method | Endpoint | Who | Description |
|--------|----------|-----|-------------|
| GET | `/api/marketplace/buyers/` | FPO | Browse verified buyers |
| POST | `/api/marketplace/buyers/{id}/inquire/` | Buyer | Submit purchase inquiry to FPO |
| GET | `/api/marketplace/inquiries/` | FPO | View received buyer inquiries |

### AI Matching

| Method | Endpoint | Who | Description |
|--------|----------|-----|-------------|
| GET | `/api/marketplace/matches/` | FPO | AI-suggested buyer matches for my products |
| POST | `/api/marketplace/matches/{id}/accept/` | FPO | Accept a match suggestion |
| POST | `/api/marketplace/matches/{id}/reject/` | FPO | Reject a match suggestion |

**Swagger tag:** `tags=["Marketplace"]`

---

## Celery Tasks

| Task | Schedule | What it does |
|------|----------|-------------|
| `refresh_market_prices` | Daily | Fetch latest prices from e-NAM API |
| `run_buyer_seller_matching` | Daily | Score all active products against buyer requirements |
| `expire_products` | Daily | Set status=expired for products past `available_until` |

---

## Business Rules

1. Only APPROVED FPOs can list products
2. ONDC listing requires `quality_certification` to be filled
3. `is_public=True` opt-in required for product to appear on public Market Hub (P2-12)
4. Match acceptance/rejection feeds back to matching algorithm (tracked via `BuyerSellerMatch.status`)
5. e-NAM prices refreshed daily — max 24h stale
6. One buyer can submit only one active inquiry per FPO product
7. ONDC API credentials must be active in `ExternalAPISettings` — if not, listing returns HTTP 503

---

## Testing Guide

### Setup
- Approved FPO account
- ONDC credentials in `ExternalAPISettings` (can use mock for testing)
- e-NAM API credentials in `ExternalAPISettings`
- At least 2 verified buyers in `BuyerDirectory`

### Test Cases

| # | Scenario | Expected Result |
|---|----------|-----------------|
| T01 | FPO creates product listing | Product created with status=draft |
| T02 | FPO activates product | Status=active |
| T03 | FPO clicks "List on ONDC" | `is_ondc_listed=True`, `ondc_product_id` populated |
| T04 | ONDC credentials not configured | HTTP 503 with admin setup message |
| T05 | Celery runs `run_buyer_seller_matching` | `BuyerSellerMatch` rows created |
| T06 | FPO calls `GET /api/marketplace/matches/` | Buyer matches returned with match_score |
| T07 | FPO accepts a match | Status=accepted, buyer notified |
| T08 | Buyer submits inquiry via `POST /api/marketplace/buyers/{id}/inquire/` | Inquiry created, FPO notified |
| T09 | `GET /api/marketplace/prices/?commodity=rice` | Rice price history from e-NAM |
| T10 | Product past `available_until` date | Status auto-set to expired by Celery |
| T11 | DRAFT FPO tries to create product | HTTP 403 |
| T12 | Buyer submits 2nd inquiry for same product | HTTP 400 — already has active inquiry |
