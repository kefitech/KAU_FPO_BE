# P2-14: AI Product Marketing Strategies

**Status:** ⬜ Not started
**SRS Ref:** §3.2.7
**Depends on:** P2-06 (Recommendations), P2-11 (Marketplace — for market + buyer data)
**Files:** `apps/fpo/api/marketing.py`, `apps/database/models/marketing.py`

---

## What This Module Does

AI-generated product marketing strategy templates tailored to the FPO's commodity profile, geographic region, and target market segment. FPO users can download and share the generated strategy document.

Uses Claude API to generate the content (same API used for DPR and chatbot — credentials already in ExternalAPISettings).

---

## New Models

**File:** `apps/database/models/marketing.py`

```python
class MarketingStrategy(BaseModel):
    fpo              = FK(FPO)
    commodity        = FK(MasterLookup)         # which commodity this strategy is for
    target_segment   = CharField()              # e.g. "retail", "wholesale", "export"
    region           = CharField()              # district or state
    financial_year   = CharField()
    content          = JSONField()              # AI-generated sections
    file_url         = CharField(null=True)     # S3 URL of exported PDF/DOCX
    generated_at     = DateTimeField(auto_now_add=True)
    ai_model_version = CharField()             # which Claude model was used
```

---

## API Endpoints

| Method | Endpoint | Who | Description |
|--------|----------|-----|-------------|
| GET | `/api/fpo/me/marketing-strategies/` | FPO | List generated strategies |
| POST | `/api/fpo/me/marketing-strategies/generate/` | FPO | Generate new strategy for a commodity |
| GET | `/api/fpo/me/marketing-strategies/{id}/` | FPO | View strategy detail |
| GET | `/api/fpo/me/marketing-strategies/{id}/download/` | FPO | Download as PDF |

**Swagger tag:** `tags=["FPO - Marketing"]`

---

## Strategy Content Sections (AI-generated)

| Section | What it covers |
|---------|---------------|
| `market_overview` | Current demand + price trends for the commodity in the region |
| `target_buyers` | Who to sell to — wholesalers, retailers, exporters, processors |
| `pricing_strategy` | Recommended price range based on e-NAM + market data |
| `distribution_channels` | How to reach buyers — ONDC, local markets, direct B2B |
| `value_addition` | Processing/packaging suggestions to increase margin |
| `promotion_ideas` | Low-cost promotion for the FPO's scale |
| `seasonal_calendar` | Best time to sell for maximum price |

---

## Generation Flow

```
FPO selects commodity + target segment
    ↓
POST /api/fpo/me/marketing-strategies/generate/
    ↓ (Celery async)
1. Fetch FPO profile: commodity, district, tier, turnover
2. Fetch market price data (e-NAM) for the commodity
3. Fetch buyer demand signals from marketplace
4. Fetch crop recommendation context (P2-06)
5. Claude API: generate each section with Kerala agricultural context
6. Store in MarketingStrategy.content (JSON)
7. WeasyPrint → PDF → S3 upload
8. Notify FPO: "Your marketing strategy is ready"
    ↓
FPO downloads PDF
```

---

## Business Rules

1. FPO must be APPROVED to generate a strategy
2. One strategy per commodity per financial year (can regenerate — old one archived)
3. Claude API credentials read from `ExternalAPISettings` (same as chatbot + DPR)
4. Generation is async — Celery task, returns `task_id` immediately
5. PDF stored in S3 — pre-signed URL (24h expiry), same as DPR
6. Strategy content is in the FPO's preferred language (EN or ML)

---

## Testing Guide

### Setup
- Approved FPO with commodity profile set
- Claude API credentials in ExternalAPISettings
- e-NAM price data available (from P2-11)
- Celery worker running

### Test Cases

| # | Scenario | Expected Result |
|---|----------|-----------------|
| T01 | FPO generates strategy for rice commodity | Returns task_id, 202 Accepted |
| T02 | Celery task completes | MarketingStrategy record created, PDF in S3 |
| T03 | FPO gets email notification | "Your marketing strategy is ready" email received |
| T04 | FPO calls download endpoint | PDF downloads with all 7 sections |
| T05 | DRAFT FPO tries to generate | HTTP 403 |
| T06 | Generate for same commodity twice in same year | Old strategy archived, new one generated |
| T07 | Check content — `pricing_strategy` section | References actual e-NAM price data |
| T08 | Check content — `target_buyers` section | Relevant to FPO's district and commodity |
| T09 | S3 URL accessed after 24h | URL expired — FPO must call download endpoint again |
| T10 | Claude API not configured | HTTP 503 with admin setup message |
