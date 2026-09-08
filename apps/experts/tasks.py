"""
Expert Booking - Scheduled Tasks
==================================
- send_booking_reminders: runs hourly, emails/notifies FPO + expert 24h before
  a confirmed appointment.
- mark_completed_bookings: runs hourly, flips confirmed bookings whose date/time
  has passed to 'completed'.
"""
import logging
from datetime import datetime, timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name='apps.experts.tasks.send_booking_reminders')
def send_booking_reminders():
    from apps.database.models.expert_booking import ExpertBooking
    from apps.notifications.services import send_notification

    now = timezone.localtime()
    window_start = now + timedelta(hours=23)
    window_end = now + timedelta(hours=25)

    candidates = ExpertBooking.objects.filter(
        status=ExpertBooking.Status.CONFIRMED,
        reminder_sent=False,
        is_deleted=False,
    ).select_related('expert', 'fpo', 'fpo__primary_user')

    count = 0
    for booking in candidates:
        try:
            hour, minute = map(int, booking.requested_time.split(':')[:2])
        except (ValueError, AttributeError):
            continue

        appointment_dt = timezone.make_aware(
            datetime.combine(booking.requested_date, datetime.min.time().replace(hour=hour, minute=minute))
        )

        if not (window_start <= appointment_dt <= window_end):
            continue

        fpo_email = booking.fpo.primary_user.email if booking.fpo.primary_user else None
        if fpo_email:
            try:
                send_notification(
                    user=booking.fpo.primary_user,
                    code='expert_booking_reminder',
                    channel='email',
                    context={
                        'expert_name': booking.expert.name_en,
                        'fpo_name': booking.fpo.name,
                        'date': str(booking.requested_date),
                        'time': booking.requested_time,
                    },
                )
            except Exception:
                logger.exception(f"Failed to send FPO reminder for booking {booking.id}")

        if booking.expert.email:
            try:
                send_notification(
                    user=booking.fpo.primary_user,
                    code='expert_booking_reminder',
                    channel='email',
                    context={
                        'expert_name': booking.expert.name_en,
                        'fpo_name': booking.fpo.name,
                        'date': str(booking.requested_date),
                        'time': booking.requested_time,
                    },
                    override_recipient=booking.expert.email,
                )
            except Exception:
                logger.exception(f"Failed to send expert reminder for booking {booking.id}")

        booking.reminder_sent = True
        booking.save(update_fields=['reminder_sent'])
        count += 1

    logger.info(f"Sent {count} booking reminders")
    return count


@shared_task(name='apps.experts.tasks.mark_completed_bookings')
def mark_completed_bookings():
    from apps.database.models.expert_booking import ExpertBooking

    now = timezone.localtime()
    candidates = ExpertBooking.objects.filter(
        status=ExpertBooking.Status.CONFIRMED,
        is_deleted=False,
        requested_date__lte=now.date(),
    )

    count = 0
    for booking in candidates:
        try:
            hour, minute = map(int, booking.requested_time.split(':')[:2])
        except (ValueError, AttributeError):
            continue

        appointment_dt = timezone.make_aware(
            datetime.combine(booking.requested_date, datetime.min.time().replace(hour=hour, minute=minute))
        )

        if appointment_dt < now:
            booking.status = ExpertBooking.Status.COMPLETED
            booking.save(update_fields=['status'])
            count += 1

    logger.info(f"Marked {count} bookings as completed")
    return count
