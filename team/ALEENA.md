# Aleena — P2-09 Analytics + P2-10 Chatbot + P2-04 Auto-Translate + P2-13 WhatsApp Templates

## What You Are Building

Four modules:

1. **P2-09 Analytics** — nightly snapshots of platform stats. Dashboards read from this pre-computed table, never from live queries.
2. **P2-10 AI Chatbot** — conversation history stored in DB. Claude API responses come later; build the data layer and return a placeholder response for now.
3. **P2-04 Auto-Translate** — admin endpoint that triggers bulk translation using Claude API. Build the skeleton; Claude API wired later.
4. **P2-13 WhatsApp Templates** — seed new notification template codes for Phase 2 events. No new models needed — uses existing `NotificationTemplate` system.

---

## Models (Already Written — Do Not Change)

| Model | File |
|---|---|
| `AnalyticsSnapshot` | `apps/database/models/analytics.py` |
| `ChatConversation` | `apps/database/models/chat.py` |
| `ChatMessage` | `apps/database/models/chat.py` |

For P2-04 and P2-13 — no new models. Uses existing `Translation` and `NotificationTemplate`.

---

## Step 1 — Run Migrations

```bash
source venv/bin/activate
python manage.py migrate
```

---

## Step 2 — Folder Structure to Create

```
apps/analytics/api/
├── snapshots.py       ← dashboard stats endpoints
├── exports.py         ← PDF + Excel export
└── urls.py

apps/chat/api/
├── conversations.py   ← create conversation, send message, get history
└── urls.py
```

P2-04 auto-translate adds one endpoint to the existing admin translations API:
```
apps/accounts/api/admin/translations.py   ← add auto_translate action here
```

P2-13 WhatsApp templates go in a seed script — no new API file needed.

---

## P2-09 — Analytics Endpoints

```
GET  /api/analytics/dashboard/                     — stats cards (admin + govt + cbbo scoped)
GET  /api/analytics/dashboard/?district=TRS        — filter by district
GET  /api/analytics/dashboard/?date=2026-08-01     — specific snapshot date
GET  /api/analytics/trends/                        — monthly trend data (last 12 snapshots)
GET  /api/analytics/export/?file_format=pdf        — download PDF report
GET  /api/analytics/export/?file_format=excel      — download Excel report
```

### The Celery task (most important part)

Create `apps/analytics/tasks.py`:

```python
from celery import shared_task

@shared_task
def refresh_analytics_snapshots():
    """Runs daily at 2:00 AM IST. Creates one state-level row + one row per district."""
    from datetime import date
    from django.db.models import Avg, Count, Q
    from apps.database.models import FPO, AnalyticsSnapshot
    from apps.core.utils.constants import District

    today = date.today()
    districts = [d.value for d in District]   # all 14 Kerala district codes

    # State-level snapshot (district=None)
    _take_snapshot(today, district=None)

    # Per-district snapshots
    for district_code in districts:
        _take_snapshot(today, district=district_code)


def _take_snapshot(snapshot_date, district=None):
    from apps.database.models import FPO, AnalyticsSnapshot

    qs = FPO.objects.all()
    if district:
        qs = qs.filter(district=district)

    tier_dist = {}
    for tier in ['A', 'B', 'C', 'D']:
        tier_dist[tier] = qs.filter(tier=tier).count()
    tier_dist['not_assessed'] = qs.filter(tier__isnull=True).count()

    AnalyticsSnapshot.objects.update_or_create(
        snapshot_date=snapshot_date,
        district=district,
        defaults={
            'fpo_count':       qs.count(),
            'approved_count':  qs.filter(status='approved').count(),
            'draft_count':     qs.filter(status='draft').count(),
            'rejected_count':  qs.filter(status='rejected').count(),
            'suspended_count': qs.filter(status='suspended').count(),
            'tier_distribution': tier_dist,
        }
    )
```

Register in `config/celery.py`:

```python
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    # existing tasks...
    'refresh-analytics-snapshots': {
        'task': 'apps.analytics.tasks.refresh_analytics_snapshots',
        'schedule': crontab(hour=2, minute=0),   # 2:00 AM daily (IST offset handled by server TZ)
    },
}
```

### Role-scoped dashboard

Different roles see different scopes:

```python
def get_queryset(self):
    user = self.request.user
    qs = AnalyticsSnapshot.objects.all()

    if user.groups.filter(name='government').exists():
        profile = user.govt_profile
        if profile.jurisdiction_type == 'district':
            qs = qs.filter(district=profile.assigned_district)
    elif user.groups.filter(name='cbbo').exists():
        # CBBO sees their district (derive from assigned FPOs)
        districts = FPO.objects.filter(assigned_cbbo=user).values_list('district', flat=True).distinct()
        qs = qs.filter(district__in=districts)
    # super_admin / sub_admin → sees all (no filter)

    return qs.order_by('-snapshot_date')
```

---

## P2-10 — Chatbot Endpoints

```
POST /api/chat/conversations/                    — start new conversation
GET  /api/chat/conversations/                    — list my conversations
GET  /api/chat/conversations/{id}/               — get conversation with messages
POST /api/chat/conversations/{id}/messages/      — send a message
DELETE /api/chat/conversations/{id}/             — delete conversation
```

FPO Primary and Secondary users only — use `IsFPOManager` permission.

### Send message — placeholder response

```python
@action(detail=True, methods=['post'], url_path='messages')
def send_message(self, request, pk=None):
    conversation = self.get_object()
    content = request.data.get('content', '').strip()
    if not content:
        return StandardResponse.error('Message cannot be empty', 400)

    # Save user message
    ChatMessage.objects.create(
        conversation=conversation,
        role='user',
        content=content,
    )

    # TODO: Replace with Claude API call when budget approved
    # For now return placeholder
    reply = ChatMessage.objects.create(
        conversation=conversation,
        role='assistant',
        content='AI service not yet configured. Please contact your KAU advisor for assistance.',
        tokens_used=0,
    )

    return StandardResponse.success(data=ChatMessageSerializer(reply).data)
```

When Claude API is activated, replace the placeholder block with:

```python
# Wire this later — do not build yet
# response = anthropic_client.messages.create(
#     model="claude-sonnet-4-6",
#     messages=[{"role": m.role, "content": m.content} for m in conversation.messages.all()],
# )
```

---

## P2-04 — Auto-Translate Endpoint

Add this action to the existing `TranslationViewSet` in `apps/accounts/api/admin/translations.py`:

```python
@extend_schema(tags=["Admin - Translations"])
@action(detail=False, methods=['post'], url_path='auto-translate')
def auto_translate(self, request):
    """
    Trigger auto-translation of all unverified keys for a language.
    Claude API call happens in a Celery task.
    Returns immediately with a job ID.
    """
    language_code = request.data.get('language_code')
    if not language_code:
        return StandardResponse.error('language_code is required', 400)

    # TODO: Wire Claude API task here — for now return acknowledgement
    return StandardResponse.success(
        data={'status': 'queued', 'language_code': language_code},
        message='Auto-translation job queued. Results will appear within a few minutes.'
    )
```

---

## P2-13 — WhatsApp Templates (Seed Script)

No new API. Add new template codes to `scripts/seed_notification_templates.py`.

New template codes to add for Phase 2 events:

```python
PHASE2_TEMPLATE_CODES = [
    # DPR
    {'code': 'dpr_generated',           'channel': 'whatsapp', 'description': 'DPR PDF generated successfully'},
    {'code': 'dpr_generation_failed',   'channel': 'whatsapp', 'description': 'DPR generation failed'},
    # Expert Booking
    {'code': 'expert_booking_confirmed','channel': 'whatsapp', 'description': 'Expert booking confirmed'},
    {'code': 'expert_booking_rejected', 'channel': 'whatsapp', 'description': 'Expert booking rejected'},
    {'code': 'expert_booking_reminder', 'channel': 'whatsapp', 'description': '24h reminder before booking'},
    # Marketplace
    {'code': 'buyer_match_found',       'channel': 'whatsapp', 'description': 'New buyer match for your product'},
    # Chatbot
    {'code': 'chat_session_started',    'channel': 'in_app',   'description': 'Chat session initiated'},
]
```

Add corresponding WhatsApp template bodies in English and Malayalam too.

---

## How to Write a ViewSet — Copy This Pattern

```python
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from drf_spectacular.utils import extend_schema
from apps.core.views import TranslatedViewSet
from apps.core.utils.responses import StandardResponse
from apps.core.utils.pagination import StandardPagination
from apps.core.permissions.rbac import IsAdmin
from apps.core.services.translation import t
from apps.database.models import AnalyticsSnapshot


class AnalyticsDashboardViewSet(mixins.ListModelMixin, TranslatedViewSet):
    serializer_class = AnalyticsSnapshotSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    pagination_class = StandardPagination

    list_message = 'analytics.data_retrieved'

    def get_queryset(self):
        qs = AnalyticsSnapshot.objects.all()
        district = self.request.query_params.get('district')
        if district:
            qs = qs.filter(district=district)
        return qs.order_by('-snapshot_date')

    @extend_schema(tags=["Analytics"])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
```

---

## Export (PDF + Excel)

For PDF use WeasyPrint — already installed. For Excel use openpyxl.

```python
# apps/analytics/api/exports.py

from django.http import HttpResponse
from weasyprint import HTML

@action(detail=False, methods=['get'])
def export(self, request):
    file_format = request.query_params.get('file_format', 'pdf')
    snapshot = AnalyticsSnapshot.objects.filter(district=None).order_by('-snapshot_date').first()

    if file_format == 'excel':
        # Use openpyxl — same pattern as reports.py in Phase 1
        pass

    # PDF
    html_string = render_to_string('analytics/report.html', {'snapshot': snapshot})
    pdf = HTML(string=html_string).write_pdf()
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="analytics_report.pdf"'
    return response
```

---

## Swagger Tags to Use

```python
@extend_schema(tags=["Analytics"])
@extend_schema(tags=["Analytics - Export"])
@extend_schema(tags=["Chat"])
@extend_schema(tags=["Admin - Translations"])   # for auto-translate action
```

---

## Translation Keys to Add

```
analytics.data_retrieved
analytics.export_generated
chat.conversation_started
chat.message_sent
chat.service_unavailable
```

---

## Git Workflow

```bash
# Your branch names
feature/p2-09-analytics-snapshots
feature/p2-09-analytics-export
feature/p2-10-chatbot-api
feature/p2-04-auto-translate-endpoint
feature/p2-13-whatsapp-template-codes

# Raise PR to develop when each is done
```

---

## What NOT to Build Yet

- Claude API calls in chatbot (return placeholder)
- Claude API calls in auto-translate (return `status: queued` only)
- WhatsApp template submission to Meta (waiting for template content approval)
