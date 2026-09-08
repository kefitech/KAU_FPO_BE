"""
CBBO / NGO Portal Models — P2-03
"""
from django.contrib.auth.models import User
from django.db import models
from apps.core.models.base import BaseModel


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
    topic = models.CharField(
        max_length=300,
        help_text='MasterLookup category: training_topic'
    )
    date = models.DateField()
    duration_hours = models.DecimalField(max_digits=4, decimal_places=1)
    participants_count = models.IntegerField(default=0)
    venue = models.CharField(
        max_length=300, blank=True,
        help_text='Free text — frontend shows combobox with common venues'
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



