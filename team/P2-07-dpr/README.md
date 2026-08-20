# P2-07: AI-Assisted DPR Generation Module

**Status:** ⬜ Not started
**SRS Ref:** §3.2.1
**Spec Ref:** `context/phase2/Dpr/Data Collection Module V1.0.pdf` (154 pages, KAU — July 2026)
**Depends on:** Nothing (standalone module — auto-fills from existing FPO profile)
**App:** `apps/dpr/` (new app)

---

## What This Module Does

FPOs need professionally prepared Detailed Project Reports (DPRs) to get bank loans, government subsidies, and scheme benefits. Hiring a DPR consultant is expensive and slow. This module replaces the consultant.

The FPO fills a structured multi-step wizard (23 data elements). The system automatically calculates all financial projections, validates consistency, and uses Claude API to write the consultant-style narrative sections. Output is a bank-ready DPR PDF stored in S3.

**Key design principle (from KAU spec §1.6):** FPO fills only primary inputs. Everything that can be calculated, derived, or AI-written is done automatically. No manual financial statement preparation by the user.

---

## Architecture Overview

```
FPO fills wizard (23 data elements, dynamic form)
    ↓
Layer 1 — Validation Engine
    Mandatory check + Logical check + Technical check + Financial check + Cross-element check
    → Errors BLOCK generation. Warnings DO NOT block.
    ↓
Layer 2 — Auto-Calculation Engine
    Project cost, P&L, Balance Sheet, Cash Flow, IRR, NPV, BCR, DSCR, depreciation, loan schedule
    ↓
Layer 3 — AI Content Engine (Claude API)
    Writes executive summary, market analysis, technical feasibility, risk assessment, SWOT,
    environmental assessment, implementation schedule narrative — all consultant-quality sections
    ↓
Layer 4 — User Review
    FPO reviews AI-generated sections, can edit before final generation
    ↓
Layer 5 — PDF Generation (WeasyPrint → S3)
    Final bank-ready DPR PDF
```

---

## New Models

**File:** `apps/database/models/dpr.py`

```python
class DPRProject(BaseModel):
    fpo                 = FK(FPO)
    project_title       = CharField()
    project_type        = JSONField()           # New/Expansion/Diversification/Modernisation etc.
    primary_commodity   = FK(MasterLookup)
    secondary_commodities = JSONField()         # list of MasterLookup IDs
    project_components  = JSONField()           # selected components — drives dynamic form
    nature_of_business  = JSONField()
    financial_year      = CharField()           # e.g. "2025-26"
    status              = CharField(choices=[
                            'draft',            # wizard in progress
                            'data_complete',    # all sections filled
                            'validated',        # passed validation, ready to generate
                            'generating',       # Celery task running
                            'generated',        # PDF ready
                          ])
    readiness_score     = IntegerField(null=True)   # 0–100, calculated before generation
    risk_rating         = CharField(null=True)       # Low / Moderate / High
    validation_errors   = JSONField(default=list)    # blocking errors list
    validation_warnings = JSONField(default=list)    # non-blocking warnings
    ai_suggestions      = JSONField(default=list)    # AI improvement suggestions

class DPRSection(BaseModel):
    project     = FK(DPRProject, related_name='sections')
    section_key = CharField()       # e.g. 'project_location', 'machinery', 'financial_info'
    data        = JSONField()       # structured answers for this section
    is_complete = BooleanField(default=False)
    completion_pct = IntegerField(default=0)

class DPRCalculation(BaseModel):
    project             = OneToOne(DPRProject)
    project_cost        = JSONField()       # itemised cost breakdown
    means_of_finance    = JSONField()       # equity, loan, subsidy, grant
    working_capital     = JSONField()
    operating_cost      = JSONField()       # annual cost breakdown
    revenue_projections = JSONField()       # year-wise revenue
    profit_loss         = JSONField()       # 5-year projected P&L
    cash_flow           = JSONField()       # 5-year projected cash flow
    balance_sheet       = JSONField()       # 5-year projected balance sheet
    depreciation_schedule = JSONField()
    loan_repayment      = JSONField()
    financial_indicators = JSONField()      # IRR, NPV, BCR, DSCR, payback, ROI, ROE, break-even
    calculated_at       = DateTimeField(auto_now=True)

class DPRAIContent(BaseModel):
    project         = OneToOne(DPRProject)
    executive_summary       = TextField(blank=True)
    project_description     = TextField(blank=True)
    technical_feasibility   = TextField(blank=True)
    market_analysis         = TextField(blank=True)
    financial_analysis      = TextField(blank=True)
    swot_analysis           = JSONField()           # structured {strengths, weaknesses, opportunities, threats}
    risk_assessment         = TextField(blank=True)
    environmental_assessment = TextField(blank=True)
    implementation_narrative = TextField(blank=True)
    is_reviewed             = BooleanField(default=False)
    model_version           = CharField()           # claude-sonnet-4-6

class DPRDocument(BaseModel):
    project         = FK(DPRProject)
    file_url        = CharField()           # S3 pre-signed URL
    generated_at    = DateTimeField(auto_now_add=True)
    is_archived     = BooleanField(default=False)  # old versions when regenerated

class DPRMasterConfig(BaseModel):
    config_key      = CharField(unique=True)    # e.g. 'interest_rate', 'depreciation_building'
    config_value    = JSONField()               # flexible: number, list, dict
    description     = TextField()
    updated_by      = FK(User)
    # Admin-configurable: interest rates, depreciation rates, commodity-specific norms,
    # inflation assumptions, subsidy percentages, engineering assumptions
```

---

## The 23 Data Elements (Wizard Sections)

Each section maps to a `DPRSection` row. The `project_components` selected by the FPO in Section 1 determines which sections are shown (conditional/dynamic form — KAU spec §1.7.2).

| # | Section Key | What FPO Fills | Auto-Fill from Profile |
|---|-------------|----------------|----------------------|
| 1 | `project_identification` | Title, type, commodity, objectives, outcomes | Commodity from FPO profile |
| 2 | `project_components` | Multi-select: Production / Processing / Storage / Marketing / Service / Infrastructure | — |
| 3 | `nature_of_business` | Business model type (production, aggregation, processing, value addition, etc.) | — |
| 4 | `proposed_investment` | Estimated cost (optional — system auto-calculates if blank) | — |
| 5 | `products_services` | Dynamic table: product name, quantity, unit, price | Commodities from FPO profile |
| 6 | `project_location` | State, district, taluk, panchayat, village, PIN, GPS (Google Maps) | District, address from FPO profile |
| 7 | `project_rationale` | Why this project, problem being solved, expected impact | — |
| 8 | `current_status` | Existing capacity, turnover, member count, current activities | Membership, tier from FPO profile |
| 9 | `capacity_production` | Production scale, working days, shifts, capacity utilisation | — |
| 10 | `raw_material_supply` | Sources, suppliers, seasonality, procurement plan | — |
| 11 | `market_assessment` | Buyers, demand, competition, pricing strategy, marketing channels | — |
| 12 | `technology_feasibility` | Technology type, processing method, automation level | — |
| 13 | `land_site` | Land area, ownership type, site status, suitability | GPS from section 6 |
| 14 | `building_civil` | Building type, area, estimated civil cost | — |
| 15 | `machinery_equipment` | Equipment list (dynamic table): name, capacity, cost, supplier | — |
| 16 | `utilities_services` | Power requirement, water, fuel, waste management | Auto-estimated from machinery |
| 17 | `human_resources` | Staff plan (dynamic table): role, count, salary | Auto-estimated from automation level |
| 18 | `financial_information` | Means of finance (equity, loan, subsidy, grant), existing loans | — |
| 19 | `statutory_approvals` | Required licences, current compliance status | Legal structure from FPO profile |
| 20 | `environmental_assessment` | Environmental risks, waste plan, sustainability measures | — |
| 21 | `implementation_plan` | Milestone table: activity, start date, end date, responsible party | — |
| 22 | `risk_assessment` | Risk categories (market, technical, financial, institutional, environmental, regulatory) + mitigation | Cross-compiled from all sections |
| 23 | `declaration_documents` | Document availability checklist + applicant declaration (3 checkboxes) | — |

> **Note:** Sections 2 and 3 (project components + nature of business) are completed first and drive which subsequent sections are displayed. This is the conditional questionnaire logic.

---

## Project Components (drive dynamic form)

**Primary Production:** Crop Production, Horticulture, Plantation Crops, Protected Cultivation, Seed Production, Nursery, Livestock, Fisheries & Aquaculture, Others

**Processing & Value Addition:** Primary Processing, Food Processing, Value Addition, Feed Manufacturing, Organic/Bio-input Production, Others

**Storage & Post-Harvest:** Collection Centre, Pack House, Warehouse, Cold Storage, Ripening Chamber, Dry Storage, Others

**Marketing & Business Development:** Wholesale Marketing, Retail Outlet, E-commerce, Export, Branding & Packaging, Others

**Service-Based Enterprises:** Agri Input Centre, Custom Hiring Centre, Farm Machinery Bank, Soil Testing / Laboratory, Training & Extension Centre, Others

**Supporting Infrastructure:** Administrative Building, Processing Building, Utility Infrastructure, Renewable Energy System, Internal Roads & Site Development, Others

---

## API Endpoints

### FPO — Wizard

| Method | Endpoint | Who | Description |
|--------|----------|-----|-------------|
| POST | `/api/fpo/me/dpr/projects/` | FPO | Create new DPR project (section 1 + 2 initial data) |
| GET | `/api/fpo/me/dpr/projects/` | FPO | List all DPR projects |
| GET | `/api/fpo/me/dpr/projects/{id}/` | FPO | Get project + all section completion status |
| PATCH | `/api/fpo/me/dpr/projects/{id}/sections/{key}/` | FPO | Save/update a section (auto-save) |
| GET | `/api/fpo/me/dpr/projects/{id}/sections/{key}/` | FPO | Get section data + auto-filled defaults |
| GET | `/api/fpo/me/dpr/projects/{id}/calculations/` | FPO | Preview auto-calculated financials |
| POST | `/api/fpo/me/dpr/projects/{id}/validate/` | FPO | Run full validation — returns errors, warnings, suggestions |
| GET | `/api/fpo/me/dpr/projects/{id}/readiness/` | FPO | DPR readiness score + section completion per section |
| GET | `/api/fpo/me/dpr/projects/{id}/ai-content/` | FPO | View AI-generated narrative sections |
| PATCH | `/api/fpo/me/dpr/projects/{id}/ai-content/` | FPO | Edit AI-generated sections before final generation |
| POST | `/api/fpo/me/dpr/projects/{id}/generate/` | FPO | Trigger final PDF generation (async Celery) |
| GET | `/api/fpo/me/dpr/projects/{id}/documents/` | FPO | List generated PDFs with download URLs |

### Admin

| Method | Endpoint | Who | Description |
|--------|----------|-----|-------------|
| GET | `/api/admin/dpr/projects/` | Admin | List all DPR projects across all FPOs |
| GET | `/api/admin/dpr/master-config/` | Super Admin | View all configurable assumptions |
| PATCH | `/api/admin/dpr/master-config/{id}/` | Super Admin | Update interest rate, depreciation rate, commodity norms etc. |

**Swagger tag:** `tags=["FPO - DPR"]`, `tags=["Admin - DPR"]`

---

## Validation Engine (Layer 1)

Runs on `POST /api/fpo/me/dpr/projects/{id}/validate/` and again before PDF generation.

**Errors (BLOCK generation):**
- Mandatory section incomplete
- Total means of finance ≠ total project cost
- Sales quantity > annual production capacity
- Loan amount > total project cost
- Working hours > 24/day, working days > 365/year
- Declaration not accepted
- No product or service defined

**Warnings (DO NOT block — shown to FPO for review):**
- Capacity utilisation > 90%
- High dependence on single buyer or raw material source
- High working capital requirement relative to revenue
- Limited labour availability for proposed automation

**Suggestions (AI-generated — advisory only):**
- Consider additional marketing channels
- Explore applicable government schemes
- Consider renewable energy options
- Strengthen risk mitigation measures

**Readiness Score output:**
```json
{
  "overall_completion": 94,
  "data_quality": "Excellent",
  "project_risk": "Moderate",
  "ai_confidence": "High",
  "dpr_readiness": "Ready for Generation",
  "sections": {
    "project_identification": { "completion": 100, "status": "Complete" },
    "financial_information": { "completion": 90, "status": "Good" }
  }
}
```

---

## Auto-Calculation Engine (Layer 2)

Runs automatically whenever section data is saved. Results stored in `DPRCalculation`.

**Project Cost (auto-built from sections 13–16):**
- Land cost, land development cost, civil works cost, building cost
- Plant and machinery cost, equipment cost
- Utilities cost, furniture and fixtures, preliminary expenses
- Pre-operative expenses, contingencies (%), margin for working capital
- **Total Project Cost** (sum of all above)

**Financial Statements (no manual input from FPO):**
- Projected Profit & Loss Account (5 years)
- Projected Cash Flow Statement (5 years)
- Projected Balance Sheet (5 years)
- Working Capital Statement
- Depreciation Schedule (buildings, machinery, equipment, vehicles, etc.)
- Loan Repayment Schedule (principal, interest, instalment, closing balance)

**Financial Indicators (auto-calculated):**
- Gross Profit, Net Profit, EBITDA
- Break-even Point & Break-even Capacity
- Debt Service Coverage Ratio (DSCR)
- Internal Rate of Return (IRR)
- Net Present Value (NPV)
- Benefit-Cost Ratio (BCR)
- Payback Period
- Return on Investment (ROI), Return on Equity (ROE)

**Configurable assumptions (from `DPRMasterConfig`, admin-managed):**
- Interest rates per loan type
- Depreciation rates per asset category
- Commodity-specific production norms and yield assumptions
- Inflation rate, escalation factors
- Subsidy percentages by scheme

---

## AI Content Engine (Layer 3)

Claude API writes all narrative sections using the validated structured data. All sections remain editable by the FPO before final PDF generation.

| DPR Chapter | What Claude Writes |
|-------------|-------------------|
| Executive Summary | Project overview, key indicators, investment summary |
| Project Description | Detailed project narrative from identification + components + products |
| Technical Feasibility | Technology assessment, production process, machinery justification |
| Market Analysis | Demand analysis, competition, pricing strategy, market access |
| Financial Analysis | Interpretation of auto-calculated financials, viability assessment |
| SWOT Analysis | Strengths, weaknesses, opportunities, threats (structured + narrative) |
| Risk Assessment | Consolidated risk register, mitigation analysis, overall risk profile |
| Environmental Assessment | Environmental impact, sustainability, waste management narrative |
| Implementation Schedule | Narrative description of milestone plan |
| Project Justification | Why this project, social/economic benefits, beneficiary analysis |

**System prompt context passed to Claude:**
- FPO profile (district, tier, commodity, legal structure, members)
- All 23 section responses
- Auto-calculated financial projections
- Kerala agricultural context
- KAU programme context (MIDH-SHM funding)
- Target output: bank-ready consultant-quality narrative

---

## Generation Flow

```
POST /api/fpo/me/dpr/projects/{id}/generate/
    ↓ returns { "task_id": "...", "status": "generating" }
    ↓ (Celery async task)
1. Run full validation — abort if any blocking errors
2. Recalculate all financial projections (DPRCalculation)
3. Fetch DPRAIContent (edited or raw AI content)
4. Render WeasyPrint HTML template with:
   - All FPO profile data
   - All section responses
   - Auto-calculated financial statements (tables)
   - Financial indicators
   - AI-written narrative sections
5. Generate PDF → upload to S3
6. Create DPRDocument row, archive previous versions
7. Send email to FPO: "Your DPR is ready — download link"
    ↓
FPO calls GET /api/fpo/me/dpr/projects/{id}/documents/ → download URL (24h pre-signed)
```

---

## Business Rules

1. FPO must be APPROVED status to create a DPR project
2. Auto-populate FPO profile fields at section creation (district, commodity, address, legal structure) — no re-entry
3. Project components selected in section 2 determine which subsequent sections appear — conditional logic must be enforced server-side, not just frontend
4. Sections auto-save on PATCH — no explicit "Save" required from FPO
5. Validation errors block generation; warnings and suggestions are advisory only
6. All AI-generated narrative content is editable before final generation
7. Financial calculations update automatically whenever any section data changes (re-run on save)
8. No document upload required for DPR — section 23 only records availability status (Available / Not Available / Will Obtain Later)
9. One DPR project per financial year per project title — FPO can have multiple projects
10. Regenerating a DPR archives the previous version (`is_archived=True`) — old PDFs still accessible
11. `DPRMasterConfig` values (interest rates, depreciation, commodity norms) are admin-managed — changes apply to future calculations only
12. Claude API key from `ExternalAPISettings` — same pattern as chatbot and marketing strategies

---

## Testing Guide

### Setup
- Approved FPO with complete profile (district, commodities, GPS coordinates)
- Claude API key configured in ExternalAPISettings
- `DPRMasterConfig` seeded with base assumptions (interest rate 12%, depreciation rates)
- Celery worker running

### Test Cases

| # | Scenario | Expected Result |
|---|----------|-----------------|
| T01 | FPO creates DPR project with project title + components | `DPRProject` created with status=draft |
| T02 | FPO opens section 6 (location) | District and address auto-filled from FPO profile |
| T03 | FPO selects only "Cold Storage" component | Only storage-relevant sections appear in wizard |
| T04 | FPO saves machinery section with 3 machines | `DPRCalculation` machinery cost auto-updated |
| T05 | FPO saves financial section | Means of finance total auto-checked against project cost |
| T06 | Means of finance ≠ project cost | Validation returns blocking error, generation blocked |
| T07 | FPO calls readiness endpoint before completing all sections | Shows per-section % + overall score |
| T08 | FPO calls validate — all sections complete | Returns `{ errors: [], warnings: [...], suggestions: [...] }` |
| T09 | FPO triggers generation | Returns task_id, 202 Accepted |
| T10 | Celery task completes | `DPRDocument` created, email sent, status=generated |
| T11 | FPO downloads PDF | PDF contains all sections including financial statements and AI narratives |
| T12 | FPO edits executive summary AI content then regenerates | PDF uses edited content, not regenerated AI content |
| T13 | FPO regenerates DPR | Previous DPRDocument marked is_archived=True, new one created |
| T14 | DRAFT FPO tries to create DPR project | HTTP 403 |
| T15 | Admin updates interest rate in DPRMasterConfig | Next project's financial calculations use new rate |
| T16 | Claude API not configured | Generation fails with HTTP 503 + admin setup message |
| T17 | S3 URL accessed after 24h | URL expired — FPO must call documents endpoint again for fresh URL |
| T18 | Check financial indicators in generated PDF | IRR, NPV, DSCR, payback period all present with calculated values |
| T19 | FPO fills Section 22 (risk) with market + environmental risks | AI generates consolidated risk register + mitigation matrix in PDF |
| T20 | Section 23 declaration not accepted | Generation blocked with error |
