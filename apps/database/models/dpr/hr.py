"""
DPR §2.3.17 — Human Resources and Organisational Structure.

Four tables:
    DPRSectionHR              — 1:1 (Cat A + D + F + G + H + I section-level)
    DPREmployeeCategory       — N per section (Cat B — designation/nature/count/type)
    DPRDepartmentStaffing     — N per section (Cat C — department + count)
    DPRTrainingRequirement    — N per section (Cat E — FK to DPRTrainingArea)

Master used:
    DPRTrainingArea — 9 items (Cat E)
"""

from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.core.models.base import TimeStampedModel, AuditModel


MANAGEMENT_MODEL_CHOICES = [
    ('by_fpo',            'Managed by FPO'),
    ('professional_ceo',  'Managed by Professional CEO'),
    ('hired_manager',     'Managed by Hired Manager'),
    ('outsourced',        'Outsourced Management'),
    ('joint',             'Joint Management'),
    ('other',             'Others (Specify)'),
]

EMPLOYMENT_TYPE_CHOICES = [
    ('permanent',   'Permanent'),
    ('contract',    'Contract'),
    ('daily_wage',  'Daily Wage'),
    ('seasonal',    'Seasonal'),
    ('part_time',   'Part-time'),
    ('outsourced',  'Outsourced'),
]

DEPARTMENT_CHOICES = [
    ('administration',    'Administration'),
    ('technical',         'Technical'),
    ('production',        'Production'),
    ('quality_control',   'Quality Control'),
    ('warehouse',         'Warehouse'),
    ('sales_marketing',   'Sales & Marketing'),
    ('accounts_finance',  'Accounts & Finance'),
    ('other',             'Others (Specify)'),
]

LABOUR_AVAILABILITY_CHOICES = [
    ('easily',          'Easily Available'),
    ('moderately',      'Moderately Available'),
    ('seasonal',        'Seasonal'),
    ('difficult',       'Difficult to Obtain'),
]

PRIMARY_LABOUR_SOURCE_CHOICES = [
    ('local',            'Local'),
    ('nearby_villages',  'Nearby Villages'),
    ('other_districts',  'Other Districts'),
    ('other_states',     'Other States'),
    ('contract_labour',  'Contract Labour'),
]

WELFARE_ITEM_CHOICES = [
    ('staff_room',        'Staff Room'),
    ('toilets',           'Toilets'),
    ('drinking_water',    'Drinking Water'),
    ('safety_equipment',  'Safety Equipment'),
    ('rest_area',         'Rest Area'),
    ('dining_area',       'Dining Area'),
    ('uniforms',          'Uniforms'),
    ('health_insurance',  'Health Insurance'),
    ('provident_fund',    'Provident Fund'),
    ('esi',               'ESI'),
    ('transportation',    'Transportation'),
    ('accommodation',     'Accommodation'),
    ('other',             'Others (Specify)'),
]

STATUTORY_COMPLIANCE_CHOICES = [
    ('epf',                    'EPF'),
    ('esi',                    'ESI'),
    ('labour_registration',    'Labour Registration'),
    ('minimum_wages',          'Minimum Wages Compliance'),
    ('contract_labour_lic',    'Contract Labour Licence'),
    ('bonus_act',              'Bonus Act'),
    ('gratuity',               'Gratuity'),
    ('shops_establishments',   'Shops & Establishments Registration'),
    ('other',                  'Others (Specify)'),
]


class DPRSectionHR(TimeStampedModel, AuditModel):
    """§2.3.17 section — one row per project."""

    project = models.OneToOneField(
        'database.DPRProject',
        on_delete=models.CASCADE,
        related_name='section_hr',
    )

    # ── Cat A: Project Management Structure ──
    project_head = models.CharField(max_length=200, blank=True)
    operational_management_model = models.CharField(max_length=30, choices=MANAGEMENT_MODEL_CHOICES, blank=True)
    operational_management_other = models.CharField(max_length=200, blank=True)
    reporting_authority = models.CharField(max_length=300, blank=True)
    org_structure_description = models.TextField(blank=True)
    decision_making_authority = models.CharField(max_length=300, blank=True)

    # ── Cat D: Existing Human Resources ──
    has_existing_employees = models.BooleanField(default=False)
    existing_employees_total = models.IntegerField(null=True, blank=True)
    existing_technical_staff = models.IntegerField(null=True, blank=True)
    existing_administrative_staff = models.IntegerField(null=True, blank=True)
    existing_marketing_staff = models.IntegerField(null=True, blank=True)
    existing_skilled_operators = models.IntegerField(null=True, blank=True)
    existing_qualification_notes = models.TextField(blank=True)
    existing_experience_notes = models.TextField(blank=True)

    # ── Cat F: Labour Availability ──
    labour_availability = models.CharField(max_length=20, choices=LABOUR_AVAILABILITY_CHOICES, blank=True)
    primary_labour_source = models.CharField(max_length=30, choices=PRIMARY_LABOUR_SOURCE_CHOICES, blank=True)
    labour_remarks = models.TextField(blank=True)

    # ── Cat G: Employee Welfare ──
    welfare_items = ArrayField(
        models.CharField(max_length=30, choices=WELFARE_ITEM_CHOICES),
        default=list, blank=True,
    )
    welfare_other = models.CharField(max_length=200, blank=True)

    # ── Cat H: Statutory Compliance ──
    statutory_compliance = ArrayField(
        models.CharField(max_length=30, choices=STATUTORY_COMPLIANCE_CHOICES),
        default=list, blank=True,
    )
    statutory_compliance_other = models.CharField(max_length=200, blank=True)

    # ── Cat I: Future Manpower Expansion ──
    has_future_manpower_expansion = models.BooleanField(default=False)
    expansion_year = models.IntegerField(null=True, blank=True)
    additional_employees_planned = models.IntegerField(null=True, blank=True)
    additional_technical_staff = models.IntegerField(null=True, blank=True)
    additional_administrative_staff = models.IntegerField(null=True, blank=True)
    additional_salary_requirement = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    is_complete = models.BooleanField(default=False)

    class Meta:
        db_table = 'dpr_section_hr'
        verbose_name = 'DPR — HR Section'
        verbose_name_plural = 'DPR — HR Sections'

    def __str__(self):
        return f'HR section for project {self.project_id}'


class DPREmployeeCategory(TimeStampedModel, AuditModel):
    """§2.3.17 Cat B — employee category (designation, count, type, salary)."""

    section = models.ForeignKey(
        DPRSectionHR,
        on_delete=models.CASCADE,
        related_name='employee_categories',
    )
    order = models.IntegerField(default=0)

    designation = models.CharField(max_length=200)
    nature_of_work = models.CharField(max_length=500, blank=True)
    number_required = models.IntegerField(null=True, blank=True)
    employment_type = models.CharField(max_length=20, choices=EMPLOYMENT_TYPE_CHOICES, blank=True)
    qualification = models.CharField(max_length=200, blank=True)
    experience_required = models.CharField(max_length=200, blank=True)
    monthly_salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    annual_salary = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    recruitment_stage = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = 'dpr_employee_category'
        verbose_name = 'DPR — Employee Category'
        verbose_name_plural = 'DPR — Employee Categories'
        ordering = ['order', 'id']

    def __str__(self):
        return self.designation or f'Employee category #{self.pk}'


class DPRDepartmentStaffing(TimeStampedModel, AuditModel):
    """§2.3.17 Cat C — one department per row with staff count."""

    section = models.ForeignKey(
        DPRSectionHR,
        on_delete=models.CASCADE,
        related_name='departments',
    )
    department = models.CharField(max_length=20, choices=DEPARTMENT_CHOICES)
    department_other = models.CharField(max_length=200, blank=True)
    num_persons = models.IntegerField(null=True, blank=True)
    annual_salary = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    remarks = models.TextField(blank=True)

    class Meta:
        db_table = 'dpr_department_staffing'
        verbose_name = 'DPR — Department Staffing'
        verbose_name_plural = 'DPR — Department Staffings'
        unique_together = [('section', 'department')]
        ordering = ['id']

    def __str__(self):
        return f'{self.get_department_display()} — section {self.section_id}'


class DPRTrainingRequirement(TimeStampedModel, AuditModel):
    """§2.3.17 Cat E — one training area per row."""

    section = models.ForeignKey(
        DPRSectionHR,
        on_delete=models.CASCADE,
        related_name='training_requirements',
    )
    training_area = models.ForeignKey(
        'database.DPRTrainingArea',
        on_delete=models.PROTECT,
        related_name='+',
    )
    training_area_other = models.CharField(max_length=200, blank=True)
    duration = models.CharField(max_length=100, blank=True)
    training_provider = models.CharField(max_length=200, blank=True)
    estimated_cost = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = 'dpr_training_requirement'
        verbose_name = 'DPR — Training Requirement'
        verbose_name_plural = 'DPR — Training Requirements'
        unique_together = [('section', 'training_area')]
        ordering = ['id']

    def __str__(self):
        return f'{self.training_area_id} — section {self.section_id}'
