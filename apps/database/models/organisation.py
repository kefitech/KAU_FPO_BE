"""
CBBO / NGO Organisation Model - P2-03 Section 3.3
"""
from django.db import models
from apps.core.models.base import BaseModel


ORG_TYPE_CHOICES = [
    ('cbbo', 'CBBO'),
    ('ngo', 'NGO'),
]


class Organisation(BaseModel):
    name = models.CharField(max_length=200)
    org_type = models.CharField(max_length=10, choices=ORG_TYPE_CHOICES)
    contact_person = models.CharField(max_length=150)
    contact_designation = models.CharField(max_length=150, blank=True)
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=15)
    districts_covered = models.JSONField(
        default=list, blank=True,
        help_text='List of district codes this organisation operates in'
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Organisation'
        verbose_name_plural = 'Organisations'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.get_org_type_display()})"
