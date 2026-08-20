# P2-02: Government Portal

**Status:** ⬜ Not started
**SRS Ref:** §3.2.2, §3.3.4
**Depends on:** P2-01 (Row-Level Security)
**App:** `apps/government/`

---

## What This Module Does

A read-only portal for government officials (district collectors, agriculture officers, etc.) to monitor FPOs in their assigned jurisdiction. They cannot create, edit, or delete any data.

---

## User Role

`government` — already exists in `UserRole` enum and Django Groups.

Jurisdiction types:
- **District level** — sees only FPOs in their assigned district
- **State level** — sees all Kerala FPOs

---

## New Model

**File:** `apps/database/models/government.py`

```python
class GovernmentOfficialProfile(BaseModel):
    user = OneToOneField(User)
    designation = CharField()                           # e.g. "District Collector"
    jurisdiction_type = CharField(choices=['district', 'state'])
    assigned_district = CharField(null=True, blank=True)  # District code — null if state-level
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/government/dashboard/` | District/state stats overview |
| GET | `/api/government/fpos/` | List FPOs in jurisdiction (read-only) |
| GET | `/api/government/fpos/{id}/` | FPO detail (read-only) |
| GET | `/api/government/schemes/utilisation/` | Scheme participation rates in jurisdiction |
| GET | `/api/government/reports/district/` | Download district summary PDF or Excel |

**Swagger tag:** `tags=["Government Portal"]`

---

## Admin Endpoints (super admin manages government accounts)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET/POST | `/api/admin/government-officials/` | List / create government official accounts |
| PATCH | `/api/admin/government-officials/{id}/` | Update designation or jurisdiction |
| POST | `/api/admin/government-officials/{id}/activate/` | Activate account |
| POST | `/api/admin/government-officials/{id}/deactivate/` | Deactivate account |

---

## Business Rules

1. District official: all queries filtered by `fpo.district = official.assigned_district`
2. State official: sees all approved FPOs, no district filter
3. HTTP 403 if attempting to access FPO outside jurisdiction
4. All endpoints are GET only — zero write operations permitted
5. Dashboard stats scoped to jurisdiction (not platform-wide)
6. Reports filtered to jurisdiction automatically

---

## Testing Guide

### Setup
- Create government official `gov_district_trs` with `jurisdiction_type=district`, `assigned_district=TRS`
- Create government official `gov_state` with `jurisdiction_type=state`
- Have at least 2 FPOs in Thrissur district, 1 FPO in another district

### Test Cases

| # | Scenario | Expected Result |
|---|----------|-----------------|
| T01 | `gov_district_trs` calls `GET /api/government/fpos/` | Only Thrissur FPOs returned |
| T02 | `gov_district_trs` calls `GET /api/government/fpos/{ernakulam_fpo_id}/` | HTTP 403 or 404 |
| T03 | `gov_state` calls `GET /api/government/fpos/` | All Kerala FPOs returned |
| T04 | `gov_district_trs` calls `GET /api/government/dashboard/` | Stats show Thrissur district only |
| T05 | Government official tries `POST /api/fpo/register/` | HTTP 403 |
| T06 | Government official tries to PATCH an FPO | HTTP 403 |
| T07 | `GET /api/government/reports/district/?file_format=pdf` | PDF downloaded, Thrissur data only |
| T08 | `GET /api/government/reports/district/?file_format=excel` | Excel downloaded |
| T09 | `gov_state` calls `GET /api/government/schemes/utilisation/` | All Kerala scheme data |
| T10 | Super admin creates government official via admin API | Account created, welcome email sent |
