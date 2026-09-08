"""
CBBO Officer Profile - P2-03 Section 3.7
Mirrors GovernmentOfficialProfile's self-registration/approval pattern.
"""
from django.contrib.auth.models import User
from django.db import models
from apps.core.models.base import BaseModel
from apps.database.models.organisation import Organisation


REGISTRATION_STATUS_CHOICES = [
    ('approved', 'Approved'),
    ('pending', 'Pending Approval'),
    ('rejected', 'Rejected'),
]


class CBBOOfficerProfile(BaseModel):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='cbbo_profile'
    )
    organisation = models.ForeignKey(
        Organisation, on_delete=models.PROTECT, related_name='officers'
    )
    designation = models.CharField(max_length=200, blank=True)
    registration_status = models.CharField(
        max_length=20, choices=REGISTRATION_STATUS_CHOICES, default='approved',
        help_text='Self-registered accounts start pending; admin-created accounts are auto-approved'
    )
    approved_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='approved_cbbo_officers'
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'CBBO Officer Profile'
        verbose_name_plural = 'CBBO Officer Profiles'

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.organisation.name}"
