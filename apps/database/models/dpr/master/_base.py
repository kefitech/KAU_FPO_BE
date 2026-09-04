"""
Abstract base for all DPR dropdown master data models.

Reuses TimeStampedModel + AuditModel from the platform base classes.
Skips SoftDeleteModel (use is_active flag instead) and UUID (internal FK use).
"""

from django.db import models

from apps.core.models.base import TimeStampedModel, AuditModel


class DPRMasterBase(TimeStampedModel, AuditModel):
    code = models.CharField(
        max_length=100, unique=True,
        help_text='Stable machine-readable identifier used in FK references and API payloads',
    )
    label_en = models.CharField(
        max_length=200,
        help_text='English display label',
    )
    label_ml = models.CharField(
        max_length=200, blank=True,
        help_text='Malayalam display label (optional)',
    )
    order = models.IntegerField(
        default=0,
        help_text='Display order in dropdowns (ascending)',
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text='Uncheck to hide from FPO-facing dropdowns without deleting',
    )

    class Meta:
        abstract = True
        ordering = ['order', 'code']

    def __str__(self):
        return self.label_en

    def label(self, language='en'):
        """Return label in requested language, falling back to English."""
        if language == 'ml' and self.label_ml:
            return self.label_ml
        return self.label_en
