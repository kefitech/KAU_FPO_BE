"""
DPR §2.3.19 — Statutory Approvals, Licences and Regulatory Compliance.

Two tables (unified through-table pattern for all 6 compliance categories):
    DPRSectionCompliance   — 1:1 (Cat G pending legal issues)
    DPRComplianceItem      — N per section (Cat A/B/C/D/E/F unified: FK → DPRStatutoryRegistration
                             + tri-state status + optional issuing authority / date / remarks)

Master used:
    DPRStatutoryRegistration — 51 items across 6 categories (business/project/
    environmental/food_quality/labour/insurance)
"""

from django.db import models

from apps.core.models.base import TimeStampedModel, AuditModel


COMPLIANCE_STATUS_CHOICES = [
    ('available',           'Available'),
    ('proposed_to_obtain',  'Proposed to Obtain'),
    ('not_applicable',      'Not Applicable'),
    ('applied',             'Applied'),
    ('under_review',        'Under Review'),
    ('approved',            'Approved'),
    ('rejected',            'Rejected'),
]


class DPRSectionCompliance(TimeStampedModel, AuditModel):
    """§2.3.19 section — one row per project."""

    project = models.OneToOneField(
        'database.DPRProject',
        on_delete=models.CASCADE,
        related_name='section_compliance',
    )

    # ── Cat G: Pending Legal Issues ──
    has_pending_legal_issues = models.BooleanField(default=False)
    nature_of_case = models.TextField(blank=True)
    possible_impact = models.TextField(blank=True)
    present_status = models.CharField(max_length=300, blank=True)
    expected_resolution_timeline = models.CharField(max_length=200, blank=True)

    is_complete = models.BooleanField(default=False)

    class Meta:
        db_table = 'dpr_section_compliance'
        verbose_name = 'DPR — Compliance Section'
        verbose_name_plural = 'DPR — Compliance Sections'

    def __str__(self):
        return f'Compliance section for project {self.project_id}'


class DPRComplianceItem(TimeStampedModel, AuditModel):
    """One compliance/approval/registration/certification item — unified across Cat A-F."""

    section = models.ForeignKey(
        DPRSectionCompliance,
        on_delete=models.CASCADE,
        related_name='items',
    )
    order = models.IntegerField(default=0)

    registration = models.ForeignKey(
        'database.DPRStatutoryRegistration',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='+',
        help_text='FK to master item. Null when custom_name is used (Others Specify case).',
    )
    custom_name = models.CharField(
        max_length=300, blank=True,
        help_text='Used when registration is null — for "Others (Specify)" entries.',
    )
    status = models.CharField(max_length=30, choices=COMPLIANCE_STATUS_CHOICES, blank=True)
    issuing_authority = models.CharField(max_length=300, blank=True)
    expected_date_of_approval = models.DateField(null=True, blank=True)
    remarks = models.TextField(blank=True)

    class Meta:
        db_table = 'dpr_compliance_item'
        verbose_name = 'DPR — Compliance Item'
        verbose_name_plural = 'DPR — Compliance Items'
        ordering = ['order', 'id']

    def __str__(self):
        return self.custom_name or f'Compliance #{self.pk}'
