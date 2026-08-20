"""
Advanced Expert Booking Models — P2-08

Expert model exists in Phase 1 (schemes.py).
These models add booking and availability on top of it.
"""
from django.db import models
from apps.core.models.base import BaseModel


class ExpertAvailability(BaseModel):
    expert = models.ForeignKey(
        'database.Expert', on_delete=models.CASCADE, related_name='availability_slots'
    )
    date = models.DateField()
    time_slots = models.JSONField(
        default=list,
        help_text='[{"start":"09:00","end":"10:00","is_booked":false}]'
    )

    class Meta:
        verbose_name = 'Expert Availability'
        verbose_name_plural = 'Expert Availability Slots'
        unique_together = ('expert', 'date')

    def __str__(self):
        return f"{self.expert} — {self.date}"


class ExpertBooking(BaseModel):

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        CONFIRMED = 'confirmed', 'Confirmed'
        REJECTED = 'rejected', 'Rejected'
        CANCELLED = 'cancelled', 'Cancelled'
        COMPLETED = 'completed', 'Completed'

    expert = models.ForeignKey(
        'database.Expert', on_delete=models.CASCADE, related_name='bookings'
    )
    fpo = models.ForeignKey(
        'database.FPO', on_delete=models.CASCADE, related_name='expert_bookings'
    )
    requested_date = models.DateField()
    requested_time = models.CharField(max_length=10, help_text='e.g. 09:00')
    topic = models.CharField(
        max_length=500, blank=True,
        help_text='MasterLookup category: expert_booking_topic'
    )
    notes = models.TextField(blank=True, help_text="FPO's query or reason for booking")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    cancellation_reason = models.TextField(blank=True)
    reminder_sent = models.BooleanField(
        default=False,
        help_text='Celery marks True after sending 24h reminder'
    )

    class Meta:
        verbose_name = 'Expert Booking'
        verbose_name_plural = 'Expert Bookings'
        ordering = ['-requested_date']

    def __str__(self):
        return f"{self.fpo} → {self.expert} on {self.requested_date} ({self.status})"
