# P2-10: AI Chatbot

**Status:** ⬜ Not started
**SRS Ref:** §3.2.9
**Depends on:** Nothing
**App:** `apps/chat/` (new app — add to INSTALLED_APPS)

---

## What This Module Does

An AI chatbot assistant for FPO users — helps with crop guidance, scheme eligibility questions, platform navigation, and registration help. Responds in the user's preferred language (English or Malayalam).

**SRS §3.2.9 access:** Both Primary and Secondary FPO Users only. No public/anonymous access is in the SRS.

---

## API Key Storage

Claude API credentials are stored in `ExternalAPISettings` (same pattern as SMS, PAN, GSTIN).
Admin configures via `POST /api/admin/external-apis/` with `service_name=claude`.
No env var needed — fetched from DB at runtime (cached in Redis).

---

## New Models

**File:** `apps/database/models/chat.py`

```python
class ChatConversation(BaseModel):
    user        = FK(User)
    language    = CharField(default='en')
    started_at  = DateTimeField(auto_now_add=True)

class ChatMessage(TimeStampedModel):
    conversation  = FK(ChatConversation)
    role          = CharField(choices=['user', 'assistant'])
    content       = TextField()
    model_version = CharField()             # e.g. "claude-sonnet-4-6"
    tokens_used   = IntegerField(default=0)
```

---

## API Endpoints

| Method | Endpoint | Who | Description |
|--------|----------|-----|-------------|
| POST | `/api/chat/message/` | FPO (Primary + Secondary) | Send message, get AI response |
| GET | `/api/chat/history/` | FPO (Primary + Secondary) | Get conversation history |
| DELETE | `/api/chat/history/` | FPO (Primary + Secondary) | Clear all conversation history |
| GET | `/api/admin/chat/metrics/` | Super Admin | Usage stats, token costs, volume |

**Swagger tag:** `tags=["Chat"]`

---


## Context Enrichment

When a logged-in FPO user sends a message, their profile context is injected:

```
"You are an agricultural assistant for Kerala FPOs.
 Language: {language}.
 FPO context: district={district}, commodities=[{list}], tier={tier}, status={status}.
 Relevant schemes: [{active_schemes}].
 Kerala agricultural context: [domain knowledge]."
```

---

## Business Rules

1. Claude API key stored in `ExternalAPISettings` table (admin-configurable, encrypted) — not in env
2. Access restricted to Primary and Secondary FPO users (SRS §3.2.9) — no public/anonymous access
3. Conversation history stored per user (indefinitely, clearable by user)
4. `model_version` logged per message for cost audit
5. Admin can see token usage per day/week/month
6. No PII in system prompt — only FPO's public profile fields
7. If Claude API is unavailable → HTTP 503 with graceful message

---

## Testing Guide

### Setup
- Admin configures Claude API key via `POST /api/admin/external-apis/` with `service_name=claude`
- Approved FPO user account (primary or secondary role)

### Test Cases

| # | Scenario | Expected Result |
|---|----------|-----------------|
| T01 | FPO primary user sends message | Response received, history saved |
| T02 | FPO secondary user sends message | Response received, history saved |
| T03 | Unauthenticated request to `POST /api/chat/message/` | HTTP 401 |
| T04 | FPO sends message with `X-Language: ml` | Response in Malayalam |
| T05 | FPO asks about schemes | Response mentions relevant Kerala agricultural schemes |
| T06 | `GET /api/chat/history/` | Returns FPO's past messages in order |
| T07 | `DELETE /api/chat/history/` | History cleared |
| T08 | Admin calls `GET /api/admin/chat/metrics/` | Token usage, message count per day |
| T09 | Claude API credentials not configured | HTTP 503 with admin setup message |
| T10 | FPO context injected — ask "what should I grow?" | Response references FPO's actual district/commodities |
| T11 | Government official calls `POST /api/chat/message/` | HTTP 403 — FPO role only |
