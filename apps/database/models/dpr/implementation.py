"""
DPR §2.3.21 — Project Implementation Plan.

Three tables:
    DPRSectionImplementation     — 1:1 (Cat B procurement + Cat C responsibility + Cat E monitoring)
    DPRImplementationActivity    — N per section (Cat A — activities with start/completion dates, Gantt chart data)
    DPRImplementationMilestone   — N per section (Cat D — milestones with expected dates)
"""

from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.core.models.base import TimeStampedModel, AuditModel


PROCUREMENT_METHOD_CHOICES = [
    ('direct_purchase',   'Direct Purchase'),
    ('tender',            'Tender'),
    ('quotation',         'Quotation-based'),
    ('rate_contract',     'Rate Contract'),
    ('empanelled',        'Empanelled Supplier'),
    ('other',             'Others (Specify)'),
]

RESPONSIBILITY_AGENCY_CHOICES = [
    ('fpo_board',            'FPO Board'),
    ('ceo',                  'CEO'),
    ('project_manager',      'Project Manager'),
    ('consultant',           'Consultant'),
    ('contractor',           'Contractor'),
    ('machinery_supplier',   'Machinery Supplier'),
    ('government_dept',      'Government Department'),
    ('bank',                 'Bank'),
    ('other',                'Other Agencies (Specify)'),
]

MILESTONE_TYPE_CHOICES = [
    ('financial_closure',    'Financial Closure'),
    ('civil_completion',     'Civil Work Completion'),
    ('machinery_install',    'Machinery Installation'),
    ('trial_production',     'Trial Production'),
    ('commercial_production', 'Commercial Production'),
    ('first_sale',           'First Sale'),
    ('break_even',           'Break-even Achievement'),
    ('other',                'Others (Specify)'),
]

MONITORING_FREQUENCY_CHOICES = [
    ('weekly',      'Weekly'),
    ('fortnightly', 'Fortnightly'),
    ('monthly',     'Monthly'),
    ('quarterly',   'Quarterly'),
]


class DPRSectionImplementation(TimeStampedModel, AuditModel):
    """§2.3.21 section — one row per project."""

    project = models.OneToOneField(
        'database.DPRProject',
        on_delete=models.CASCADE,
        related_name='section_implementation',
    )

    # ── Cat B: Procurement Plan ──
    procurement_method = models.CharField(max_length=30, choices=PROCUREMENT_METHOD_CHOICES, blank=True)
    procurement_method_other = models.CharField(max_length=200, blank=True)
    tender_required = models.BooleanField(null=True, blank=True)
    num_quotations_proposed = models.IntegerField(null=True, blank=True)
    supplier_finalisation_method = models.CharField(max_length=300, blank=True)
    expected_procurement_period = models.CharField(max_length=100, blank=True, help_text='e.g. "3 months"')

    # ── Cat C: Implementation Responsibility ──
    responsibility_agencies = ArrayField(
        models.CharField(max_length=30, choices=RESPONSIBILITY_AGENCY_CHOICES),
        default=list, blank=True,
    )
    responsibility_agency_other = models.CharField(max_length=200, blank=True)
    responsibility_remarks = models.TextField(blank=True)

    # ── Cat E: Project Monitoring ──
    monitoring_frequency = models.CharField(max_length=20, choices=MONITORING_FREQUENCY_CHOICES, blank=True)
    monitoring_authority = models.CharField(max_length=300, blank=True)
    reporting_mechanism = models.TextField(blank=True)
    corrective_action_process = models.TextField(blank=True)

    is_complete = models.BooleanField(default=False)

    class Meta:
        db_table = 'dpr_section_implementation'
        verbose_name = 'DPR — Implementation Section'
        verbose_name_plural = 'DPR — Implementation Sections'

    def __str__(self):
        return f'Implementation section for project {self.project_id}'


class DPRImplementationActivity(TimeStampedModel, AuditModel):
    """§2.3.21 Cat A — one activity per row (feeds Gantt chart)."""

    section = models.ForeignKey(
        DPRSectionImplementation,
        on_delete=models.CASCADE,
        related_name='activities',
    )
    order = models.IntegerField(default=0)

    activity_name = models.CharField(max_length=300)
    proposed_start_date = models.DateField(null=True, blank=True)
    proposed_completion_date = models.DateField(null=True, blank=True)
    estimated_duration = models.CharField(max_length=100, blank=True, help_text='e.g. "45 days", "2 months"')
    responsible_person_or_agency = models.CharField(max_length=300, blank=True)

    class Meta:
        db_table = 'dpr_implementation_activity'
        verbose_name = 'DPR — Implementation Activity'
        verbose_name_plural = 'DPR — Implementation Activities'
        ordering = ['order', 'id']

    def __str__(self):
        return self.activity_name or f'Activity #{self.pk}'


class DPRImplementationMilestone(TimeStampedModel, AuditModel):
    """§2.3.21 Cat D — one milestone per row."""

    section = models.ForeignKey(
        DPRSectionImplementation,
        on_delete=models.CASCADE,
        related_name='milestones',
    )
    order = models.IntegerField(default=0)

    milestone_type = models.CharField(max_length=30, choices=MILESTONE_TYPE_CHOICES)
    milestone_type_other = models.CharField(max_length=200, blank=True)
    expected_date = models.DateField(null=True, blank=True)
    remarks = models.TextField(blank=True)

    class Meta:
        db_table = 'dpr_implementation_milestone'
        verbose_name = 'DPR — Implementation Milestone'
        verbose_name_plural = 'DPR — Implementation Milestones'
        ordering = ['order', 'id']

    def __str__(self):
        return f'{self.get_milestone_type_display()} — section {self.section_id}'
