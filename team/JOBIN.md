# Jobin — P2-01 Row-Level Security + P2-02 Government Portal + P2-03 CBBO Portal + P2-08 Expert Booking

## What You Are Building

Four modules — all build now, no external API dependencies:

1. **P2-01 Row-Level Security** — enforce that sub-admins only see FPOs assigned to them, and CBBO users only see FPOs assigned to them.
2. **P2-02 Government Portal** — read-only portal for government officials. District-level sees their district. State-level sees all.
3. **P2-03 CBBO Portal** — CBBO workers file capacity building reports and track training sessions for their assigned FPOs.
4. **P2-08 Expert Booking** — experts publish availability slots, FPOs book them, Celery sends 24h reminders.

---

## Models (Already Written — Do Not Change)

| Model | File |
|---|---|
| `GovernmentOfficialProfile` | `apps/database/models/government.py` |
| `CapacityBuildingReport` | `apps/database/models/cbbo.py` |
| `TrainingSession` | `apps/database/models/cbbo.py` |
| `TrainingAttendance` | `apps/database/models/cbbo.py` |
| `ExpertAvailability` | `apps/database/models/expert_booking.py` |
| `ExpertBooking` | `apps/database/models/expert_booking.py` |

Also — `FPO.assigned_cbbo` field is already in the FPO model (FK to User). You will use it but not add it.

---

## Step 1 — Run Migrations

```bash
source venv/bin/activate
python manage.py migrate
```

Confirm clean before starting.

---

## Step 2 — Folder Structure to Create

```
apps/government/api/
├── officials.py      ← admin creates government accounts
├── fpo_view.py       ← government reads FPO data (read-only)
└── urls.py

apps/cbbo/api/
├── assignments.py    ← CBBO sees their assigned FPOs
├── reports.py        ← capacity building reports
├── training.py       ← training sessions + attendance
└── urls.py

apps/experts/api/
├── availability.py   ← expert manages calendar
├── bookings.py       ← FPO books expert, expert confirms
└── urls.py           (this app already exists — add new files inside it)
```

---

## P2-01 — Row-Level Security

This is not a separate endpoint. It is a queryset filter that you add to every admin and CBBO viewset.

### For Sub-Admin (already partially in place)

In any admin ViewSet that lists FPOs, add:

```python
def get_queryset(self):
    user = self.request.user
    qs = FPO.objects.all()
    # Sub-admins only see their assigned FPOs
    if user.groups.filter(name='sub_admin').exists():
        qs = qs.filter(assigned_to=user)
    return qs
```

### For CBBO

In every CBBO ViewSet that touches FPOs:

```python
def get_queryset(self):
    return FPO.objects.filter(assigned_cbbo=self.request.user)
```

---

## P2-02 — Government Portal Endpoints

```
# Admin creates government official accounts
POST  /api/admin/government-officials/           — create official (sends temp password)
GET   /api/admin/government-officials/           — list all officials
PATCH /api/admin/government-officials/{id}/      — update designation/district
POST  /api/admin/government-officials/{id}/activate/
POST  /api/admin/government-officials/{id}/deactivate/

# Government official reads FPO data (read-only, jurisdiction-scoped)
GET   /api/government/fpos/                      — list FPOs in their jurisdiction
GET   /api/government/fpos/{id}/                 — single FPO detail
GET   /api/government/dashboard/                 — stats for their district or state
```

### Jurisdiction filtering — the core logic

```python
# apps/government/api/fpo_view.py

class GovernmentFPOViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, TranslatedViewSet):
    permission_classes = [IsAuthenticated, IsGovernmentOfficial]
    serializer_class = GovernmentFPOSerializer

    def get_queryset(self):
        profile = self.request.user.govt_profile
        qs = FPO.objects.filter(status='approved')

        if profile.jurisdiction_type == 'district':
            qs = qs.filter(district=profile.assigned_district)
        # state jurisdiction → sees all, no filter needed

        return qs
```

### Read-only rule

Government officials must NEVER have write access. Use:

```python
permission_classes = [IsAuthenticated, IsGovernmentOfficial]
http_method_names = ['get', 'head', 'options']   # blocks POST, PUT, PATCH, DELETE
```

---

## P2-03 — CBBO Portal Endpoints

```
# CBBO sees their assigned FPOs
GET  /api/cbbo/my-fpos/                             — FPOs where FPO.assigned_cbbo = me

# Capacity Building Reports
GET  /api/cbbo/reports/                             — my reports (all FPOs)
POST /api/cbbo/reports/                             — create report (status=draft)
GET  /api/cbbo/reports/{id}/
PATCH /api/cbbo/reports/{id}/                       — edit (draft only)
POST /api/cbbo/reports/{id}/submit/                 — draft → submitted (locked after this)

# Training Sessions
GET  /api/cbbo/training/                            — list sessions
POST /api/cbbo/training/                            — create session
GET  /api/cbbo/training/{id}/
PATCH /api/cbbo/training/{id}/
POST /api/cbbo/training/{id}/attendance/            — save attendance list
GET  /api/cbbo/training/{id}/attendance/
```

### Submit = Lock

```python
@action(detail=True, methods=['post'])
def submit(self, request, pk=None):
    report = self.get_object()
    if report.status == 'submitted':
        return StandardResponse.error('Report already submitted', 400)
    report.status = 'submitted'
    report.save()
    return StandardResponse.success(message=t('cbbo.report_submitted', self.get_language()))
```

---

## P2-08 — Expert Booking Endpoints

```
# Expert manages their own availability
GET  /api/experts/me/availability/                  — list my slots
POST /api/experts/me/availability/                  — add slots for a date
PATCH /api/experts/me/availability/{id}/            — edit slot times
DELETE /api/experts/me/availability/{id}/           — remove a date's slots

# Expert manages bookings
GET  /api/experts/me/bookings/                      — incoming booking requests
POST /api/experts/me/bookings/{id}/confirm/         — pending → confirmed
POST /api/experts/me/bookings/{id}/reject/          — pending → rejected
POST /api/experts/me/bookings/{id}/complete/        — confirmed → completed

# FPO books an expert
GET  /api/fpo/experts/{expert_id}/availability/     — see expert's available slots
POST /api/fpo/bookings/                             — request a booking
GET  /api/fpo/bookings/                             — my bookings
POST /api/fpo/bookings/{id}/cancel/                 — cancel a booking
```

### Celery reminder task

Create `apps/experts/tasks.py`:

```python
from celery import shared_task

@shared_task
def send_booking_reminders():
    """Runs daily — sends reminder 24h before confirmed booking."""
    from datetime import date, timedelta
    from apps.database.models import ExpertBooking
    from apps.notifications.services import send_notification

    tomorrow = date.today() + timedelta(days=1)
    bookings = ExpertBooking.objects.filter(
        status='confirmed',
        requested_date=tomorrow,
        reminder_sent=False
    )
    for booking in bookings:
        send_notification(
            user=booking.fpo.primary_user,
            code='expert_booking_reminder',
            channel='email',
            context={
                'expert_name': booking.expert.name,
                'date': str(booking.requested_date),
                'time': booking.requested_time,
            }
        )
        booking.reminder_sent = True
        booking.save(update_fields=['reminder_sent'])
```

Register this task in `config/celery.py` beat schedule (run daily at 8 AM IST).

---

## Permissions to Use

```python
from apps.core.permissions.rbac import (
    IsAdmin,             # super_admin or sub_admin
    IsFPOManager,        # fpo_manager group
    IsGovernmentOfficial,# government group
    IsCBBO,              # cbbo group
    IsExpert,            # expert group
)
```

If `IsGovernmentOfficial` or `IsCBBO` don't exist yet, add them to `apps/core/permissions/rbac.py` following the same pattern as the others:

```python
class IsGovernmentOfficial(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and \
               request.user.groups.filter(name='government').exists()

class IsCBBO(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and \
               request.user.groups.filter(name='cbbo').exists()
```

---

## How to Write a ViewSet — Copy This Pattern

```python
from rest_framework import mixins
from rest_framework.decorators import action
from drf_spectacular.utils import extend_schema
from apps.core.views import TranslatedViewSet
from apps.core.utils.responses import StandardResponse
from apps.core.utils.pagination import StandardPagination
from apps.core.permissions.rbac import IsCBBO
from apps.core.services.translation import t
from apps.database.models import CapacityBuildingReport


class CapacityBuildingReportViewSet(TranslatedViewSet):
    serializer_class = CapacityBuildingReportSerializer
    permission_classes = [IsAuthenticated, IsCBBO]
    pagination_class = StandardPagination

    list_message    = 'cbbo.reports_retrieved'
    create_message  = 'cbbo.report_created'
    update_message  = 'cbbo.report_updated'
    destroy_message = 'cbbo.report_deleted'

    def get_queryset(self):
        # CBBO only sees reports they submitted
        return CapacityBuildingReport.objects.filter(cbbo=self.request.user)

    def perform_create(self, serializer):
        serializer.save(cbbo=self.request.user)
```

---

## Swagger Tags to Use

```python
@extend_schema(tags=["Admin - Government Officials"])
@extend_schema(tags=["Government Portal"])
@extend_schema(tags=["CBBO Portal"])
@extend_schema(tags=["Expert - Availability"])
@extend_schema(tags=["Expert - Bookings"])
```

---

## Translation Keys to Add

```
govt.officials_retrieved
govt.official_created
govt.fpos_retrieved
cbbo.fpos_retrieved
cbbo.reports_retrieved
cbbo.report_created
cbbo.report_submitted
cbbo.report_locked
cbbo.training_created
cbbo.attendance_saved
expert.availability_updated
expert.booking_confirmed
expert.booking_rejected
expert.booking_completed
expert.booking_reminder_sent
```

---

## Git Workflow

```bash
# Your branch names
feature/p2-01-row-level-security
feature/p2-02-government-portal
feature/p2-03-cbbo-portal
feature/p2-08-expert-booking

# Raise PR to develop when each is done
```
