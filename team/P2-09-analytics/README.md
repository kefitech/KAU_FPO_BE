# P2-09: Analytics Dashboards

**Status:** ⬜ Not started
**SRS Ref:** §3.2.3
**Depends on:** P2-02 (Government Portal), P2-03 (CBBO Portal)
**App:** `apps/analytics/`

---

## What This Module Does

District and state-level analytics dashboards with FPO performance metrics, commodity trends, scheme utilisation rates, and market activity data. Exportable as PDF and Excel. SRS requires data to not be more than 24 hours stale.

---

## Who Uses It

| Role | Access Level |
|------|-------------|
| Super Admin | All Kerala data, all districts |
| Sub-Admin | Their assigned FPOs only |
| Government official (district) | Their district only |
| Government official (state) | All Kerala |

---

## New Model

**File:** `apps/database/models/analytics.py`

```python
class AnalyticsSnapshot(BaseModel):
    snapshot_date      = DateField()
    district           = CharField(null=True)    # null = state-level snapshot
    fpo_count          = IntegerField()
    approved_count     = IntegerField()
    draft_count        = IntegerField()
    rejected_count     = IntegerField()
    tier_distribution  = JSONField()    # {"A": 12, "B": 34, "C": 56, "D": 8, "not_assessed": 20}
    commodity_breakdown = JSONField()   # {"rice": 45, "banana": 30, ...}
    scheme_utilisation = JSONField()    # {"scheme_id": {"applied": 10, "approved": 7}, ...}
    avg_member_count   = DecimalField()
    total_members      = IntegerField()
    women_members      = IntegerField()
```

**Celery Beat task:** `refresh_analytics_snapshots` — runs daily at 2:00 AM IST, writes one state-level + one per-district `AnalyticsSnapshot` row.

---

## API Endpoints

| Method | Endpoint | Who | Description |
|--------|----------|-----|-------------|
| GET | `/api/analytics/district/{code}/` | Admin / Govt | District dashboard data |
| GET | `/api/analytics/state/` | Admin / State Govt | State-level aggregates |
| GET | `/api/analytics/commodities/` | Admin / Govt | Commodity-wise production trends |
| GET | `/api/analytics/schemes/` | Admin / Govt | Scheme utilisation rates |
| GET | `/api/analytics/export/` | Admin / Govt | PDF or Excel export |

**Query params for all endpoints:**
- `?date_range=last_30_days` | `last_quarter` | `ytd` | `custom`
- `?from_date=2025-01-01&to_date=2025-03-31` (for custom range)
- `?commodity=rice` (commodity filter)

**Swagger tag:** `tags=["Analytics"]`

---

## Export Formats

- `?file_format=pdf` — WeasyPrint PDF with KAU branding (header/footer)
- `?file_format=excel` — openpyxl Excel with formatted tables

---

## Business Rules

1. Data refreshed daily at 2am — max 24h stale (SRS requirement)
2. Dashboard shows `last_updated` timestamp so users know data freshness
3. Government district official: queryset scoped to `assigned_district`
4. Government state official: state-level snapshot only
5. Sub-admin: filtered to their assigned FPOs (aggregates over subset)
6. Drill-down: state → district → block level (block-level in future iteration)
7. All exports scoped to the caller's jurisdiction automatically

---

## Testing Guide

### Setup
- Multiple approved FPOs across 2+ districts
- Run `refresh_analytics_snapshots` manually to populate snapshot data
- Government official with district jurisdiction created

### Test Cases

| # | Scenario | Expected Result |
|---|----------|-----------------|
| T01 | `GET /api/analytics/state/` as super admin | State-level aggregates returned |
| T02 | `GET /api/analytics/district/TRS/` | Thrissur district data |
| T03 | Government district official calls `GET /api/analytics/district/EKM/` | HTTP 403 (not their jurisdiction) |
| T04 | Government district official calls `GET /api/analytics/district/TRS/` | Data returned (their jurisdiction) |
| T05 | `GET /api/analytics/export/?file_format=pdf` | PDF downloaded with KAU header |
| T06 | `GET /api/analytics/export/?file_format=excel` | Excel downloaded |
| T07 | Response includes `last_updated` field | Shows snapshot date (within last 24h) |
| T08 | Filter by commodity: `?commodity=rice` | Only rice-related FPOs in stats |
| T09 | Filter by date range `?date_range=last_30_days` | Data scoped correctly |
| T10 | Check `tier_distribution` in response | A/B/C/D/not_assessed counts present |
