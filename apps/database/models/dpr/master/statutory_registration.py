"""
Statutory Registrations / Approvals / Licences per KAU spec §2.3.19.
Grouped into 7 categories with a default-mandatory flag driving compliance checks.
"""

from django.db import models

from ._base import DPRMasterBase


class DPRStatutoryRegistration(DPRMasterBase):
    class Category(models.TextChoices):
        BUSINESS       = 'business',       'Business Registration'
        PROJECT        = 'project',        'Project Approval'
        ENVIRONMENTAL  = 'environmental',  'Environmental Compliance'
        FOOD_QUALITY   = 'food_quality',   'Food Safety & Quality'
        LABOUR         = 'labour',         'Labour Compliance'
        INSURANCE      = 'insurance',      'Insurance'
        OTHER          = 'other',          'Other'

    category = models.CharField(
        max_length=30, choices=Category.choices, db_index=True,
        help_text='Which of the 7 KAU spec compliance categories this belongs to',
    )
    default_mandatory = models.BooleanField(
        default=False,
        help_text='If True, KAU spec marks this registration as mandatory across all project types',
    )
    issuing_authority_default = models.CharField(
        max_length=200, blank=True,
        help_text='Default issuing authority (FPO can override per registration)',
    )

    class Meta(DPRMasterBase.Meta):
        db_table = 'dpr_statutory_registration'
        verbose_name = 'DPR — Statutory Registration'
        verbose_name_plural = 'DPR — Statutory Registrations'
        ordering = ['category', 'order', 'code']
