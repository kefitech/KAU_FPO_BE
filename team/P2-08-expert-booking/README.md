# P2-08: Advanced Expert Booking

**Status:** ⬜ Not started
**SRS Ref:** §3.2.4
**Depends on:** Nothing (extends Phase 1 expert directory)
**App:** `apps/experts/` (Phase 1 has basic directory — this extends it)

---

## What This Module Does

Phase 1 has: Expert directory listing + contact enquiry form.
Phase 2 adds: Calendar-based appointment booking, scheduling, and expert self-service availability calendar management.

> **Note:** Video call integration is NOT in the SRS. Not in scope for Phase 2.

---

## New Models

**File:** `apps/database/models/expert_booking.py`

```python
class ExpertAvailability(BaseModel):
    expert      = FK(Expert)
    date        = DateField()
    time_slots  = JSONField()
    # time_slots format: [{"start": "09:00", "end": "10:00", "is_booked": false}, ...]

class ExpertBooking(BaseModel):
    expert              = FK(Expert)
    fpo                 = FK(FPO)
    requested_date      = DateField()
    requested_time      = CharField()        # e.g. "09:00"
    status              = CharField(choices=['pending', 'confirmed', 'rejected', 'cancelled', 'completed'])
    notes               = TextField(blank=True)
    cancellation_reason = TextField(blank=True)
    reminder_sent       = BooleanField(default=False)
```

---

## API Endpoints

### Expert Self-Service

| Method | Endpoint | Who | Description |
|--------|----------|-----|-------------|
| GET | `/api/experts/me/availability/` | Expert | View my availability calendar |
| POST | `/api/experts/me/availability/` | Expert | Set available dates and time slots (bulk) |
| PATCH | `/api/experts/me/availability/{id}/` | Expert | Update or remove a slot |
| GET | `/api/experts/me/bookings/` | Expert | List all booking requests |
| POST | `/api/experts/me/bookings/{id}/confirm/` | Expert | Confirm booking → generate Jitsi URL |
| POST | `/api/experts/me/bookings/{id}/reject/` | Expert | Reject booking with reason |

### FPO-Facing

| Method | Endpoint | Who | Description |
|--------|----------|-----|-------------|
| GET | `/api/experts/{id}/availability/` | FPO | View expert's available (non-booked) slots |
| POST | `/api/experts/{id}/book/` | FPO | Request a booking slot |
| GET | `/api/fpo/me/bookings/` | FPO | My booking history |
| POST | `/api/fpo/me/bookings/{id}/cancel/` | FPO | Cancel a pending booking |

**Swagger tag:** `tags=["Expert - Booking"]`

---

## Notification Triggers

| Event | Recipient | Channel |
|-------|-----------|---------|
| New booking request | Expert | Email + in-app |
| Booking confirmed | FPO | Email + in-app |
| Booking rejected | FPO | Email + in-app |
| Booking cancelled by FPO | Expert | Email + in-app |
| Reminder 1 day before appointment | Both | Email + in-app |

---

## Business Rules

1. FPO can only book a slot that `is_booked=False`
2. On booking confirmation → slot marked `is_booked=True`
3. On cancellation → slot freed back (`is_booked=False`)
4. Expert can set bulk availability (e.g. every Monday 9–5 for next 4 weeks)
5. Expert cannot delete a slot that has a `confirmed` booking
6. Reminder sent 1h before call (Celery beat task scans upcoming bookings every 15 min)
7. APPROVED FPOs only can book experts
8. One booking per expert per time slot

---

## Testing Guide

### Setup
- Expert account created with `expert` role
- Approved FPO account
- Expert sets availability for tomorrow, 09:00–10:00 slot

### Test Cases

| # | Scenario | Expected Result |
|---|----------|-----------------|
| T01 | Expert sets availability for a date/time | `ExpertAvailability` created |
| T02 | FPO views `GET /api/experts/{id}/availability/` | Sees available slots only |
| T03 | FPO requests booking for 09:00 slot | Booking created with status=pending |
| T04 | Expert confirms booking | Status=confirmed, Jitsi URL generated |
| T05 | FPO receives confirmation notification | Email + in-app notification received |
| T06 | Booked slot checked | `is_booked=True` |
| T07 | Another FPO tries to book same slot | HTTP 400 — slot already booked |
| T08 | FPO cancels confirmed booking | Status=cancelled, slot freed, expert notified |
| T09 | Expert rejects a booking with reason | Status=rejected, FPO notified with reason |
| T10 | 1h before call — check notifications | Reminder sent to both FPO and Expert |
| T11 | DRAFT FPO tries to book expert | HTTP 403 — must be APPROVED |
| T12 | Expert deletes slot with confirmed booking | HTTP 400 — cannot delete confirmed slot |
