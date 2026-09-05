"""
Government Portal Models - P2-02
"""
from django.contrib.auth.models import User
from django.db import models
from apps.core.models.base import BaseModel


USER_CATEGORY_CHOICES = [
    ('agri_officer', 'Agri Officer'),
    ('university_official', 'University Official'),
    ('sfac_official', 'SFAC Official'),
    ('cbbo_personnel', 'CBBO Personnel'),
    ('nabard_official', 'NABARD Official'),
    ('atma_specialist', 'ATMA Specialist'),
]

REGISTRATION_STATUS_CHOICES = [
    ('approved', 'Approved'),
    ('pending', 'Pending Approval'),
    ('rejected', 'Rejected'),
]


class GovernmentOfficialProfile(BaseModel):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='govt_profile'
    )
    designation = models.CharField(
        max_length=200,
        help_text='MasterLookup category: govt_designation'
    )
    department = models.CharField(
        max_length=200,
        help_text='MasterLookup category: govt_department'
    )
    jurisdiction_type = models.CharField(
        max_length=20,
        choices=[('district', 'District'), ('block', 'Block'), ('state', 'State')]
    )
    assigned_district = models.CharField(
        max_length=10, null=True, blank=True,
        help_text='District code from constants.py - set when jurisdiction_type=district or block'
    )
    assigned_block = models.CharField(
        max_length=100, null=True, blank=True,
        help_text='Block/taluk code, MasterLookup category: block - set when jurisdiction_type=block'
    )
    user_category = models.CharField(
        max_length=30, choices=USER_CATEGORY_CHOICES, null=True, blank=True,
        help_text='Determines ID number format validation'
    )
    id_number = models.CharField(
        max_length=30, null=True, blank=True,
        help_text='PEN / PAN / CIN / Employee ID, format depends on user_category'
    )
    registration_status = models.CharField(
        max_length=20, choices=REGISTRATION_STATUS_CHOICES, default='approved',
        help_text='Self-registered accounts start pending; admin-created accounts are auto-approved'
    )
    approved_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='approved_govt_officials'
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Government Official Profile'
        verbose_name_plural = 'Government Official Profiles'

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.designation}"
