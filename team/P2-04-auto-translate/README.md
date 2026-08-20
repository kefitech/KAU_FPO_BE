# P2-04: Auto-Translate (Claude API)

**Status:** ⬜ Not started
**SRS Ref:** ⚠️ NOT explicitly in SRS — this is a Kefitech-proposed enhancement to improve admin efficiency. The SRS requires multilingual support (§2.2) but does not specify auto-translation tooling. Confirm with KAU before building.
**Depends on:** Nothing (self-contained admin utility)
**File:** `apps/accounts/api/admin/translations.py` (extends existing)

---

## What This Module Does

Currently adding a new language (e.g. Hindi, Tamil) requires manually uploading hundreds of translation strings via Excel. This feature lets the super admin click "Auto-translate" and the Claude API translates all English strings in batches — saving them as unverified so the admin can review before activating.

---

## New API Endpoint

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/admin/translations/auto-translate/` | Trigger auto-translation for a language |

**Request body:**
```json
{
  "language_code": "hi",
  "category_code": "ui"   // optional — omit to translate all categories
}
```

**Response:**
```json
{
  "created": 120,
  "skipped": 45,
  "failed": 2,
  "failed_keys": ["auth.some_key"]
}
```

**Swagger tag:** `tags=["Admin - Translations"]`
**Permission:** `IsSuperAdmin` only

---

## How It Works

1. Fetch all English strings for the category (or all categories if not specified)
2. Skip keys that already have a translation in the target language
3. Send to Claude API in batches of 50 keys
4. System prompt: "Agricultural domain, Kerala government context, formal register"
5. Batch JSON format sent: `{ "auth.login_success": "Login successful", ... }`
6. Claude returns same JSON shape with translated values
7. Save each result as `Translation` row with `is_verified=False`
8. Return summary: `{ created, skipped, failed }`

**Library to add:** `anthropic` (add to `requirements/base.txt`)

---

## Business Rules

1. Only `super_admin` can trigger auto-translate
2. Keys that already have a translation in the target language are skipped (not overwritten)
3. All auto-translated strings saved with `is_verified=False`
4. Admin must review and verify strings before they appear to users
5. Failed keys (Claude API timeout etc.) are returned in `failed_keys` list — admin retries manually
6. Language must exist and be active in the `Language` table before translating

---

## Testing Guide

### Setup
- Add Hindi language via `POST /api/admin/languages/` with `code=hi`
- Ensure English translations exist for `auth` category

### Test Cases

| # | Scenario | Expected Result |
|---|----------|-----------------|
| T01 | Super admin calls auto-translate for `hi`, category `auth` | Returns `{ created: N, skipped: 0, failed: 0 }` |
| T02 | Check DB — Hindi translations exist with `is_verified=False` | Correct |
| T03 | Call auto-translate again for same language + category | Returns `{ created: 0, skipped: N, failed: 0 }` — no duplicates |
| T04 | Sub-admin tries to call auto-translate | HTTP 403 |
| T05 | Auto-translate with non-existent language code `xx` | HTTP 400 with clear error |
| T06 | Auto-translate without `category_code` | All categories translated |
| T07 | Public endpoint `GET /api/translations/public/?lang=hi` after auto-translate | Hindi strings returned |
| T08 | Verify a translated string via `POST /api/admin/translations/{id}/verify/` | `is_verified` becomes True |
