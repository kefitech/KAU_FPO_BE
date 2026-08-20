# P2-01: Row-Level Security

**Status:** ⬜ Not started
**SRS Ref:** §3.3.5
**Must build before:** Government Portal (#2), CBBO Portal (#3)

---

## What This Module Does

Phase 1 uses role-based access control (RBAC) — every sub-admin sees all FPOs.
Phase 2 adds **data-level isolation** on top of RBAC:

- Sub-admins see only FPOs assigned to them (`fpo.assigned_to = request.user`)
- CBBOs see only FPOs assigned to them (`fpo.assigned_cbbo = request.user`)
- Competing CBBOs cannot see each other's FPO data — ever
- Super admin always sees everything

No structural DB change needed for sub-admin side — `FPO.assigned_to` FK is already in the model.
One migration needed — add `assigned_cbbo FK(User)` to FPO model.

---

## Files to Change

| File | Change |
|------|--------|
| `apps/database/models/fpo.py` | Add `assigned_cbbo = FK(User, null=True, related_name='cbbo_fpos')` |
| `apps/fpo/api/registration.py` | Filter queryset by `assigned_to` for sub-admin role |
| `apps/accounts/api/admin/applications.py` | Filter queryset by `assigned_to` for sub-admin role |
| `apps/cbbo/api/` | All querysets filter by `assigned_cbbo=request.user` |
| `apps/accounts/api/admin/applications.py` | Add assign endpoint |

---

## New API Endpoints

| Method | Endpoint | Who | What |
|--------|----------|-----|------|
| POST | `/api/admin/applications/{id}/assign/` | Super Admin | Assign FPO to a sub-admin or CBBO |
| GET | `/api/admin/applications/?assigned_to=me` | Sub Admin | My assigned FPOs only |
| GET | `/api/admin/sub-admins/{id}/assigned-fpos/` | Super Admin | FPOs assigned to a specific sub-admin |

---

## Business Rules

1. Super admin — no filter, sees all FPOs always
2. Sub-admin — `queryset.filter(assigned_to=request.user)` on every FPO endpoint
3. CBBO — `queryset.filter(assigned_cbbo=request.user)` on every FPO endpoint
4. Enforcement is at queryset level (API), not just UI
5. Audit log every time an FPO is assigned or reassigned
6. One FPO can be assigned to only one sub-admin at a time
7. One FPO can be assigned to only one CBBO at a time
8. Unassigned FPOs are visible to super admin only

---

## Testing Guide

### Setup
- Create 2 sub-admin accounts: `subadmin_a`, `subadmin_b`
- Create 2 CBBO accounts: `cbbo_x`, `cbbo_y`
- Create 4 FPOs: `fpo1`, `fpo2`, `fpo3`, `fpo4`
- Assign: `fpo1 → subadmin_a`, `fpo2 → subadmin_b`, `fpo3 → cbbo_x`, `fpo4 → cbbo_y`

### Test Cases

| # | Scenario | Expected Result |
|---|----------|-----------------|
| T01 | `subadmin_a` calls `GET /api/admin/applications/` | Returns only `fpo1` |
| T02 | `subadmin_b` calls `GET /api/admin/applications/` | Returns only `fpo2` |
| T03 | `subadmin_a` calls `GET /api/admin/applications/{fpo2_id}/` | HTTP 404 (not in their scope) |
| T04 | `super_admin` calls `GET /api/admin/applications/` | Returns all 4 FPOs |
| T05 | `cbbo_x` calls `GET /api/cbbo/fpos/` | Returns only `fpo3` |
| T06 | `cbbo_x` calls `GET /api/cbbo/fpos/{fpo4_id}/` | HTTP 404 |
| T07 | Super admin assigns `fpo1` to `subadmin_b` | `fpo1` disappears from `subadmin_a`, appears for `subadmin_b` |
| T08 | `subadmin_a` tries to assign FPO to someone | HTTP 403 |
| T09 | Audit log checked after assignment | Entry exists with old/new assignee |
| T10 | Unassigned FPO — sub-admin calls list | Unassigned FPO not in response |
