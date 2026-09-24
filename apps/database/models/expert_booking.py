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
    is_custom = models.BooleanField(
        default=False,
        help_text='True once the expert has manually set/edited this specific date. '
                   'Custom dates are skipped by the weekly-default cascade.',
    )


    class Meta:
        verbose_name = 'Expert Availability'
        verbose_name_plural = 'Expert Availability Slots'
        unique_together = ('expert', 'date')

    def __str__(self):
        return f"{self.expert} \u2014 {self.date}"


class ExpertTimeSlot(BaseModel):
    availability = models.ForeignKey(
        ExpertAvailability, on_delete=models.CASCADE, related_name='time_slots'
    )
    start_time = models.TimeField()
    end_time = models.TimeField()
    max_bookings = models.PositiveIntegerField(
        default=1, help_text='How many FPOs can book this same slot'
    )

    class Meta:
        verbose_name = 'Expert Time Slot'
        verbose_name_plural = 'Expert Time Slots'
        ordering = ['start_time']
        unique_together = ('availability', 'start_time', 'end_time')

    @property
    def confirmed_count(self):
        return self.bookings.filter(status='confirmed', is_deleted=False).count()

    @property
    def is_full(self):
        return self.confirmed_count >= self.max_bookings

    def __str__(self):
        status = ' (full)' if self.is_full else ''
        return f"{self.availability} {self.start_time}-{self.end_time}{status}"


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
    time_slot = models.ForeignKey(
        ExpertTimeSlot, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='bookings'
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
        return f"{self.fpo} \u2192 {self.expert} on {self.requested_date} ({self.status})"


class ExpertWeeklyDefault(BaseModel):
    expert = models.ForeignKey(
        'database.Expert', on_delete=models.CASCADE, related_name='weekly_defaults'
    )
    weekday = models.PositiveSmallIntegerField(help_text='0=Sunday .. 6=Saturday')
    start_time = models.TimeField()
    end_time = models.TimeField()
    max_bookings = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = 'Expert Weekly Default'
        verbose_name_plural = 'Expert Weekly Defaults'
        ordering = ['weekday', 'start_time']
        unique_together = ('expert', 'weekday', 'start_time', 'end_time')

    def __str__(self):
        return f"{self.expert} - weekday {self.weekday} {self.start_time}-{self.end_time}"
