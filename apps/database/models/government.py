"""
Government Portal Models — P2-02
"""
from django.contrib.auth.models import User
from django.db import models
from apps.core.models.base import BaseModel


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
        choices=[('district', 'District'), ('state', 'State')]
    )
    assigned_district = models.CharField(
        max_length=10, null=True, blank=True,
        help_text='District code from constants.py — null when jurisdiction_type=state'
    )

    class Meta:
        verbose_name = 'Government Official Profile'
        verbose_name_plural = 'Government Official Profiles'

    def __str__(self):
        return f"{self.user.get_full_name()} — {self.designation}"
