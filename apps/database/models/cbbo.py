"""
CBBO / NGO Portal Models — P2-03
"""
from django.contrib.auth.models import User
from django.db import models
from apps.core.models.base import BaseModel, TimeStampedModel


from apps.core.models.base import BaseModel
 
 
class CBBOAssignment(BaseModel):
    """
    One row = one CBBO user's access to one district, OR state-wide access.
 
    A rep covering multiple districts gets multiple rows (one per district).
    A rep covering the whole state gets a single row with level='state' and
    district=''  — no need to enumerate every district code.
 
    This is deliberately separate from CapacityBuildingReport/TrainingSession —
    it's an access-control table, not an activity log, so it has its own
    lifecycle (admin creates/revokes it; it's never "submitted" or locked).
    """
    LEVEL_DISTRICT = 'district'
    LEVEL_STATE    = 'state'
    LEVEL_CHOICES  = [
        (LEVEL_DISTRICT, 'District'),
        (LEVEL_STATE,    'State'),
    ]
 
    cbbo = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='cbbo_assignments'
    )
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES)
    district = models.CharField(
        max_length=10, blank=True,
        help_text='District code (matches FPO.district, e.g. TSR, KLM). '
                   'Blank when level=state.'
    )
    is_active = models.BooleanField(default=True)
    assigned_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='cbbo_assignments_made'
    )
 
    class Meta:
        verbose_name = 'CBBO Assignment'
        verbose_name_plural = 'CBBO Assignments'
        constraints = [
            # a user can't have two active rows for the same district
            models.UniqueConstraint(
                fields=['cbbo', 'district'],
                condition=models.Q(is_active=True, level='district'),
                name='unique_active_district_assignment',
            ),
        ]
 
    def __str__(self):
        scope = 'STATE-WIDE' if self.level == self.LEVEL_STATE else self.district
        return f"{self.cbbo} — {scope}"
 




class CapacityBuildingReport(BaseModel):
    fpo = models.ForeignKey(
        'database.FPO', on_delete=models.CASCADE, related_name='cbbo_reports'
    )
    cbbo = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='submitted_reports'
    )
    date = models.DateField()
    activities = models.TextField(help_text='What was done during the visit')
    participants_count = models.IntegerField(default=0)
    outcomes = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=[('draft', 'Draft'), ('submitted', 'Submitted')],
        default='draft'
    )
    # Once submitted → locked, cannot be edited

    class Meta:
        verbose_name = 'Capacity Building Report'
        verbose_name_plural = 'Capacity Building Reports'
        ordering = ['-date']

    def __str__(self):
        return f"{self.fpo} — {self.date} ({self.status})"


class TrainingSession(BaseModel):
    fpo = models.ForeignKey(
        'database.FPO', on_delete=models.CASCADE, related_name='training_sessions'
    )
    cbbo = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='conducted_sessions'
    )
    trainer_name = models.CharField(
        max_length=200, blank=True,
        help_text='Name of the person who actually conducted the session, if different from the logged-in official'
    )
    topic = models.CharField(
        max_length=300,
        help_text='MasterLookup category: training_topic'
    )
    date = models.DateField()
    time = models.CharField(
        max_length=10, blank=True,
        help_text='e.g. 10:00 -- start time of the session'
    )
    duration_hours = models.DecimalField(max_digits=4, decimal_places=1)
    participants_count = models.IntegerField(default=0)
    venue = models.CharField(
        max_length=300, blank=True,
        help_text='Free text — frontend shows combobox with common venues'
    )
    is_active = models.BooleanField(
        default=True,
        help_text='Auto-hidden by Celery task N days after date (training_expiry_days).',
    )
    reminder_sent = models.BooleanField(
        default=False,
        help_text='Celery marks True after the day-before reminder went to the organiser, the FPO and its team.',
    )
    cancellation_reason = models.TextField(
        blank=True,
        help_text='Why the official cancelled it (a cancelled session is a soft-deleted one). Shown to the FPO.',
    )

    class Meta:
        verbose_name = 'Training Session'
        verbose_name_plural = 'Training Sessions'
        ordering = ['-date']

    def __str__(self):
        return f"{self.topic} — {self.fpo} ({self.date})"

class TrainingAttendance(BaseModel):
    session = models.ForeignKey(
        TrainingSession, on_delete=models.CASCADE, related_name='attendance'
    )
    member_name = models.CharField(max_length=200)
    attended = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Training Attendance'
        verbose_name_plural = 'Training Attendance Records'

    def __str__(self):
        return f"{self.member_name} — {self.session}"


class TrainingSessionComment(TimeStampedModel):
    """A KAU super admin / sub-admin remark on a training session.

    Shown to the CBBO officer or government official who recorded the session.
    Author name + designation are snapshotted at comment time, so the comment
    still reads correctly after a district transfer or account deletion.
    """
    session = models.ForeignKey(
        TrainingSession, on_delete=models.CASCADE, related_name='admin_comments'
    )
    author = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name='training_comments'
    )
    author_name = models.CharField(max_length=200)
    author_designation = models.CharField(
        max_length=200, help_text='e.g. "Super Admin" or "Sub-Admin, Thrissur"'
    )
    comment = models.TextField()
    edited_at = models.DateTimeField(
        null=True, blank=True,
        help_text='Set when the author edits the text; shown as "(edited)" and re-flags the comment as unread.',
    )

    class Meta:
        verbose_name = 'Training Session Comment'
        verbose_name_plural = 'Training Session Comments'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.author_name} on {self.session}"


class TrainingSessionCommentRead(TimeStampedModel):
    """When a CBBO officer / government official last read a session's KAU comments.

    Comments newer than `last_read_at` show as unread (blue marker) on that
    user's training table. Per user, since every government official in a
    jurisdiction sees the same sessions.
    """
    session = models.ForeignKey(
        TrainingSession, on_delete=models.CASCADE, related_name='comment_reads'
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='training_comment_reads'
    )
    last_read_at = models.DateTimeField()

    class Meta:
        verbose_name = 'Training Comment Read'
        verbose_name_plural = 'Training Comment Reads'
        constraints = [
            models.UniqueConstraint(fields=['session', 'user'], name='uniq_training_comment_read'),
        ]

    def __str__(self):
        return f"{self.user} read {self.session} at {self.last_read_at}"



