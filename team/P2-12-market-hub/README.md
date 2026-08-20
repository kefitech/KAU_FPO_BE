# P2-12: Public Market Linkage Hub

**Status:** ⬜ Not started
**SRS Ref:** §3.2.5
**Depends on:** P2-11 (ONDC + Farmer Connect — product data source)
**App:** `apps/marketplace/api/public.py` (extends marketplace app)

---

## What This Module Does

The public-facing discovery layer on top of the Marketplace. Public buyers (no login needed) can browse FPO products, see e-NAM commodity price trends, and submit purchase inquiries. FPOs must explicitly opt-in (`product.is_public=True`) for products to appear here.

---

## API Endpoints (all public, no auth)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/public/market/commodities/` | Commodity list with current price range (from e-NAM) |
| GET | `/api/public/market/opportunities/` | Demand signals + buyer requirements by commodity |
| GET | `/api/public/market/products/` | Publicly opted-in FPO product listings |
| GET | `/api/public/market/products/{id}/` | Single product detail |
| POST | `/api/public/market/products/{id}/inquire/` | Public buyer submits purchase inquiry |

**Swagger tag:** `tags=["Public Market Hub"]`

---

## Business Rules

1. Product appears on public hub only if `product.is_public=True` (FPO opt-in)
2. FPO contact details not exposed in public listing — inquiry goes through platform
3. Public buyer inquiry: stored as `BuyerSellerMatch` with status=suggested, FPO notified
4. Price data is from e-NAM (daily refresh from P2-11 Celery task)
5. Public endpoints cached in Redis (1h TTL) — same cache invalidation pattern as CMS

---

## Testing Guide

### Setup
- FPO has active product with `is_public=True`
- FPO has active product with `is_public=False`
- e-NAM price data exists

### Test Cases

| # | Scenario | Expected Result |
|---|----------|-----------------|
| T01 | `GET /api/public/market/products/` (no auth) | Only `is_public=True` products returned |
| T02 | Private product (`is_public=False`) — check list | Not in response |
| T03 | `GET /api/public/market/commodities/` | Commodity list with price ranges |
| T04 | `POST /api/public/market/products/{id}/inquire/` | Inquiry created, FPO notified |
| T05 | FPO contact details in public product response | Not exposed — only product info |
| T06 | Response time for commodity list | Fast (Redis cached) |
| T07 | FPO unpublishes product (`is_public=False`) | Disappears from public hub |
