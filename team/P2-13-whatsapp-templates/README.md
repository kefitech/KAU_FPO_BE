# P2-13: WhatsApp Extended Templates

**Status:** ⬜ Not started
**SRS Ref:** §3.1.3, §3.1.4
**Depends on:** Each template added when its feature ships (not all at once)
**File:** `scripts/seed_notification_templates.py`

---

## What This Module Does

As each Phase 2 feature ships, new WhatsApp notification templates are added for it. All WhatsApp templates require **Meta approval** before going live in production. The backend WhatsApp channel is already built — this is just template data.

---

## Template List

Add each template when the corresponding feature is built and ready for production.

| Template Code | Feature | Trigger | Meta Approval Needed |
|---|---|---|---|
| `crop_recommendation_ready` | P2-06 Recommendations | New AI recommendation generated for FPO | Yes |
| `scheme_alert` | Existing schemes module | New relevant scheme published (admin triggers) | Yes |
| `tier_updated` | Tier assessment | FPO tier changed for new financial year | Yes |
| `expert_booking_requested` | P2-08 Expert Booking | New booking request (sent to expert) | Yes |
| `expert_booking_confirmed` | P2-08 Expert Booking | Booking confirmed (sent to FPO) | Yes |
| `dpr_ready` | P2-07 DPR | DPR PDF generated and download link ready | Yes |
| `market_match` | P2-11 Marketplace | AI found a buyer match for FPO product | Yes |
| `price_alert` | P2-11 Marketplace | Commodity price crossed threshold set by FPO | Yes |

---

## How to Add a New Template

1. Add template code to `NotificationTemplateCode` via `POST /api/notifications/template-codes/`
2. Add EN + ML template body via `POST /api/notifications/templates/`
3. Add WhatsApp `template_name` (Meta-approved name) and `template_language` fields
4. Submit template to Meta for approval
5. Once approved — activate via `POST /api/notifications/templates/{id}/activate/`
6. Add to `scripts/seed_notification_templates.py` for idempotent re-seeding

---

## WhatsApp Credential Config

WhatsApp credentials already configured in `NotificationChannelSettings`.
No code change needed — just template data.

---

## Testing Guide

### For each new template:

| # | Scenario | Expected Result |
|---|----------|-----------------|
| T01 | Template code created | `NotificationTemplateCode` row exists and is active |
| T02 | EN + ML bodies created | Both `NotificationTemplate` rows exist |
| T03 | Test render via `POST /api/notifications/templates/{id}/test_render/` | Rendered body with variables substituted |
| T04 | Trigger the feature that sends this notification | WhatsApp message delivered (requires active Meta-approved template) |
| T05 | Template not yet Meta-approved | Falls back to SMS or email (channel fallback) |
