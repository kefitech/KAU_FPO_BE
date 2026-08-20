# P2-03: CBBO / NGO Portal

**Status:** ⬜ Not started
**SRS Ref:** §3.2.2, §3.3.5
**Depends on:** P2-01 (Row-Level Security)
**App:** `apps/cbbo/`

---

## What This Module Does

Portal for Capacity Building and Business Operation (CBBO) organisations and NGOs that are assigned to support specific FPOs. A CBBO can only see FPOs assigned to them — competing CBBOs are completely isolated from each other's data.

---

## User Role

`cbbo` — already exists in `UserRole` enum and Django Groups.

---

## New Models

**File:** `apps/database/models/cbbo.py`

```python
class CapacityBuildingReport(BaseModel):
    fpo = FK(FPO)
    cbbo = FK(User)
    date = DateField()
    activities = TextField()            # what was done during the visit
    participants_count = IntegerField()
    outcomes = TextField()
    status = CharField(choices=['draft', 'submitted'])  # submitted = locked

class TrainingSession(BaseModel):
    fpo = FK(FPO)
    cbbo = FK(User)
    topic = CharField()
    date = DateField()
    duration_hours = DecimalField()
    participants_count = IntegerField()
    venue = CharField()

class TrainingAttendance(BaseModel):
    session = FK(TrainingSession)
    member_name = CharField()
    attended = BooleanField(default=False)
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/cbbo/fpos/` | List my assigned FPOs only |
| GET | `/api/cbbo/fpos/{id}/` | FPO detail (assigned only) |
| GET | `/api/cbbo/reports/` | List capacity building reports |
| POST | `/api/cbbo/reports/` | Submit new report |
| PATCH | `/api/cbbo/reports/{id}/` | Update draft report only |
| GET | `/api/cbbo/training/` | List training sessions |
| POST | `/api/cbbo/training/` | Log new training session |
| POST | `/api/cbbo/training/{id}/attendance/` | Mark member attendance |
| GET | `/api/cbbo/dashboard/` | Summary: assigned FPOs, pending reports, recent training |

**Swagger tag:** `tags=["CBBO Portal"]`

---

## Business Rules

1. All CBBO querysets: `queryset.filter(assigned_cbbo=request.user)` — no exceptions
2. Submitted reports are locked — cannot be edited or deleted (admin can archive)
3. Training attendance is per-member (name-based, not user account)
4. CBBO cannot approve/reject FPOs or modify FPO profile
5. CBBO cannot see reports submitted by another CBBO, even for the same FPO

---

## Testing Guide

### Setup
- Create 2 CBBO accounts: `cbbo_org_a`, `cbbo_org_b`
- Assign `fpo1`, `fpo2` to `cbbo_org_a`; assign `fpo3` to `cbbo_org_b`

### Test Cases

| # | Scenario | Expected Result |
|---|----------|-----------------|
| T01 | `cbbo_org_a` calls `GET /api/cbbo/fpos/` | Returns `fpo1`, `fpo2` only |
| T02 | `cbbo_org_a` calls `GET /api/cbbo/fpos/{fpo3_id}/` | HTTP 404 |
| T03 | `cbbo_org_b` calls `GET /api/cbbo/fpos/` | Returns `fpo3` only |
| T04 | `cbbo_org_a` submits capacity building report for `fpo1` | Report created, status=draft |
| T05 | `cbbo_org_a` submits (changes status to submitted) the report | Status=submitted, no further edits |
| T06 | `cbbo_org_a` tries to PATCH submitted report | HTTP 400 — report is locked |
| T07 | `cbbo_org_a` logs training session for `fpo2` | Session created |
| T08 | `cbbo_org_a` marks attendance for training session | Attendance records created |
| T09 | `cbbo_org_b` tries to read `cbbo_org_a`'s reports | HTTP 404 — isolated |
| T10 | FPO primary user tries to access `/api/cbbo/` | HTTP 403 |
