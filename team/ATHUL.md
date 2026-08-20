# Athul (Lead) — P2-07 AI-Assisted DPR Generation

## What You Are Building

The most complex module in Phase 2.

FPOs fill a 23-section wizard. The system auto-calculates all financials (project cost, P&L, cash flow, balance sheet, IRR, NPV, BCR, DSCR). A readiness score (0–100) is shown before generation. WeasyPrint generates the PDF with placeholder narrative text. Claude API narrative generation is wired later once KAU approves the budget.

---

## Models (You Already Wrote These)

| Model | File |
|---|---|
| `DPRProject` | `apps/database/models/dpr.py` |
| `DPRSection` | `apps/database/models/dpr.py` |
| `DPRCalculation` | `apps/database/models/dpr.py` |
| `DPRAIContent` | `apps/database/models/dpr.py` |
| `DPRDocument` | `apps/database/models/dpr.py` |
| `DPRMasterConfig` | `apps/database/models/dpr.py` |

---

## Step 1 — Run Migrations First

```bash
source venv/bin/activate
python manage.py migrate
```

Confirm clean. Then push migrated state to `develop` so the team can pull.

---

## Step 2 — Folder Structure

```
apps/fpo/api/
├── dpr.py             ← all FPO-facing DPR endpoints (add to existing fpo api folder)

apps/accounts/api/admin/
├── dpr_admin.py       ← admin DPR management endpoints

apps/fpo/services/
├── dpr_calculation.py ← all financial calculation logic (no Django models here — pure Python)
├── dpr_validation.py  ← readiness score + 5 validation types
├── dpr_pdf.py         ← WeasyPrint PDF generation
```

---

## Step 3 — FPO-Facing API Endpoints

```
# Wizard
POST  /api/fpo/dpr/                              — create new DPR project (step 0 — project basics)
GET   /api/fpo/dpr/                              — list my DPR projects
GET   /api/fpo/dpr/{id}/                         — get project + all sections + completion %
PATCH /api/fpo/dpr/{id}/sections/{section_key}/  — save section data (auto-save, partial ok)
GET   /api/fpo/dpr/{id}/sections/{section_key}/  — get one section's data

# Readiness & Validation
GET   /api/fpo/dpr/{id}/readiness/               — readiness score + list of errors/warnings
POST  /api/fpo/dpr/{id}/validate/                — trigger full validation, update score

# Financial Preview
GET   /api/fpo/dpr/{id}/financials/              — preview calculated financials before generating PDF

# Generation
POST  /api/fpo/dpr/{id}/generate/                — trigger PDF generation (status: generating → generated)
GET   /api/fpo/dpr/{id}/documents/               — list all generated PDFs (latest + archived)
GET   /api/fpo/dpr/{id}/documents/latest/        — download latest PDF

# AI Content (for after Claude API is wired)
GET   /api/fpo/dpr/{id}/ai-content/              — view Claude-generated narratives
POST  /api/fpo/dpr/{id}/ai-content/approve/      — FPO marks content as reviewed
```

### Admin Endpoints

```
GET  /api/admin/dpr/                             — list all DPR projects across all FPOs
GET  /api/admin/dpr/{id}/                        — full detail
GET  /api/admin/dpr-config/                      — list DPRMasterConfig values
PATCH /api/admin/dpr-config/{config_key}/        — update a config value (interest rate, etc.)
```

---

## Step 4 — The 23 Wizard Sections

Each section = one `DPRSection` row with `section_key` and `data` (JSON).

| # | section_key | What it collects |
|---|---|---|
| 1 | `project_basics` | Title, type, commodity, components, financial year |
| 2 | `promoter_details` | FPO name, legal structure, date of registration, address |
| 3 | `project_location` | Village, block, district, GPS pin |
| 4 | `nature_of_business` | Processing / storage / marketing etc. |
| 5 | `product_details` | Capacity, product mix, unit, season |
| 6 | `raw_material` | Sources, quantities, costs |
| 7 | `market_linkages` | Buyers, markets, price points |
| 8 | `land_details` | Land area, ownership, lease details |
| 9 | `civil_works` | Building type, area, estimated cost |
| 10 | `machinery` | Equipment list, suppliers, costs, capacity |
| 11 | `utilities` | Power (kW), water requirement, fuel |
| 12 | `manpower` | Skilled/unskilled headcount, wage rates |
| 13 | `working_capital` | Raw material stock days, debtors days, creditors days |
| 14 | `project_cost` | Summary of total capital cost (auto-calculated from sections 8–13) |
| 15 | `means_of_finance` | Equity, term loan, subsidy, grant amounts |
| 16 | `subsidy_details` | Scheme name, agency, sanctioned amount, conditions |
| 17 | `revenue_projections` | Year-wise capacity utilisation %, price per unit |
| 18 | `operating_cost` | Annual raw material, labour, utilities, admin costs |
| 19 | `depreciation` | Auto-calculated from asset costs + DPRMasterConfig rates |
| 20 | `loan_repayment` | Auto-calculated from loan amounts + DPRMasterConfig rates |
| 21 | `profit_loss` | Auto-calculated 5-year P&L |
| 22 | `cash_flow` | Auto-calculated 5-year cash flow |
| 23 | `financial_indicators` | IRR, NPV, BCR, DSCR, payback — auto-calculated |

Sections shown/hidden based on `project_components` selected in section 1.

---

## Step 5 — Financial Calculation Engine

All calculation logic lives in `apps/fpo/services/dpr_calculation.py`. Pure Python — no DB calls inside.

```python
# apps/fpo/services/dpr_calculation.py

from decimal import Decimal

def calculate_depreciation(assets: dict, config: dict) -> dict:
    """
    assets = {
        'civil': 5000000,
        'machinery': 8000000,
        'vehicles': 1200000,
    }
    config = DPRMasterConfig values (depreciation rates)
    """
    return {
        'civil':     Decimal(assets.get('civil', 0)) * Decimal(config['depreciation_rate_civil']) / 100,
        'machinery': Decimal(assets.get('machinery', 0)) * Decimal(config['depreciation_rate_machinery']) / 100,
        'vehicles':  Decimal(assets.get('vehicles', 0)) * Decimal(config['depreciation_rate_vehicles']) / 100,
    }


def calculate_loan_repayment(loan_amount, interest_rate, tenure_years, moratorium_months):
    """EMI calculation after moratorium period."""
    # Standard EMI formula
    monthly_rate = Decimal(interest_rate) / 100 / 12
    moratorium_months = int(moratorium_months)
    effective_months = (tenure_years * 12) - moratorium_months
    emi = loan_amount * monthly_rate / (1 - (1 + monthly_rate) ** -effective_months)
    return {
        'emi': round(emi, 2),
        'total_repayment': round(emi * effective_months, 2),
        'total_interest': round((emi * effective_months) - loan_amount, 2),
    }


def calculate_irr(cash_flows: list) -> float:
    """Newton-Raphson IRR. cash_flows[0] = -initial_investment, rest = annual inflows."""
    import numpy as np
    return float(np.irr(cash_flows)) * 100  # return as %


def calculate_npv(cash_flows: list, discount_rate: float) -> float:
    import numpy as np
    return float(np.npv(discount_rate / 100, cash_flows))
```

Load config from DB once and pass it through:

```python
def get_dpr_config() -> dict:
    from apps.database.models import DPRMasterConfig
    return {obj.config_key: obj.config_value for obj in DPRMasterConfig.objects.all()}
```

---

## Step 6 — Readiness Score

```python
# apps/fpo/services/dpr_validation.py

def calculate_readiness(project) -> dict:
    errors = []      # blocking — PDF not generated until cleared
    warnings = []    # non-blocking
    score = 100

    sections = {s.section_key: s for s in project.sections.all()}

    # Mandatory field check
    required_sections = ['project_basics', 'promoter_details', 'project_location', 'product_details']
    for key in required_sections:
        if key not in sections or not sections[key].is_complete:
            errors.append(f'Section "{key}" is incomplete')
            score -= 10

    # Logical check — equity + loan + subsidy must equal project cost
    calc = getattr(project, 'calculation', None)
    if calc:
        total_means = sum(calc.means_of_finance.values())
        total_cost = sum(calc.project_cost.values())
        if abs(total_means - total_cost) > 1000:
            errors.append('Means of finance does not match total project cost')
            score -= 15

    # Financial check — DSCR must be > 1.25
    if calc and calc.financial_indicators.get('dscr', 0) < 1.25:
        warnings.append('DSCR is below 1.25 — lenders may require equity top-up')
        score -= 5

    return {
        'score': max(score, 0),
        'errors': errors,
        'warnings': warnings,
        'can_generate': len(errors) == 0,
    }
```

---

## Step 7 — PDF Generation

```python
# apps/fpo/services/dpr_pdf.py

from django.template.loader import render_to_string
from weasyprint import HTML

def generate_dpr_pdf(project) -> bytes:
    context = {
        'project': project,
        'calculation': project.calculation,
        'sections': {s.section_key: s.data for s in project.sections.all()},
        # AI content is placeholder text until Claude is wired
        'ai_content': getattr(project, 'ai_content', None),
    }
    html = render_to_string('dpr/report.html', context)
    return HTML(string=html).write_pdf()
```

Create `apps/fpo/templates/dpr/report.html` — full A4 layout with KAU letterhead, all 23 sections, financial tables.

---

## Celery Task for Generation

PDF generation is slow — run it async:

```python
# apps/fpo/tasks.py  (add to existing file)

@shared_task
def generate_dpr_pdf_task(project_id):
    from apps.database.models import DPRProject, DPRDocument
    from apps.fpo.services.dpr_pdf import generate_dpr_pdf
    import boto3, uuid

    project = DPRProject.objects.get(pk=project_id)
    project.status = DPRProject.Status.GENERATING
    project.save(update_fields=['status'])

    try:
        pdf_bytes = generate_dpr_pdf(project)

        # Archive previous documents
        project.documents.filter(is_archived=False).update(is_archived=True)

        # Save to S3 (or local in dev)
        file_url = _save_pdf(pdf_bytes, project_id)

        DPRDocument.objects.create(project=project, file_url=file_url)
        project.status = DPRProject.Status.GENERATED
        project.save(update_fields=['status'])

    except Exception as e:
        project.status = DPRProject.Status.FAILED
        project.save(update_fields=['status'])
        raise
```

---

## DPRMasterConfig — Seed Script

Create `scripts/seed_dpr_config.py`:

```python
DPR_DEFAULTS = [
    ('interest_rate_term_loan',       9.5,  'Default term loan interest rate (%)'),
    ('interest_rate_working_capital', 12.0, 'Working capital loan interest rate (%)'),
    ('depreciation_rate_machinery',   15.0, 'Machinery depreciation SLM (%)'),
    ('depreciation_rate_civil',        5.0, 'Civil works depreciation SLM (%)'),
    ('depreciation_rate_vehicles',    20.0, 'Vehicle depreciation SLM (%)'),
    ('subsidy_rate_default',          35.0, 'Default subsidy % of project cost'),
    ('project_life_years',            10,   'Financial projection period (years)'),
    ('moratorium_period_months',      12,   'Loan holiday period (months)'),
    ('contingency_pct',                5.0, 'Contingency % of civil + machinery cost'),
]

def seed_dpr_config():
    from apps.database.models import DPRMasterConfig
    for key, value, desc in DPR_DEFAULTS:
        DPRMasterConfig.objects.update_or_create(
            config_key=key,
            defaults={'config_value': value, 'description': desc}
        )
    print(f'Seeded {len(DPR_DEFAULTS)} DPR config values')
```

---

## Swagger Tags to Use

```python
@extend_schema(tags=["FPO - DPR"])
@extend_schema(tags=["Admin - DPR"])
```

---

## Translation Keys to Add

```
dpr.project_created
dpr.section_saved
dpr.validation_complete
dpr.generation_started
dpr.generation_complete
dpr.generation_failed
dpr.pdf_ready
dpr.config_updated
```

---

## Git Workflow

```bash
# Your branch names
feature/p2-07-dpr-wizard
feature/p2-07-dpr-financials
feature/p2-07-dpr-validation
feature/p2-07-dpr-pdf
feature/p2-07-dpr-admin

# Raise PR to develop when each piece is done
# You review all other team members' PRs
```

---

## What NOT to Build Yet

- Claude API narrative generation (replace placeholders with Claude API once KAU budget approved)
- All AI content endpoints can return empty strings — `DPRAIContent` rows created with blank fields
