"""
AI-Assisted DPR Generation Models — P2-07

Most complex model set in Phase 2.
- DPRProject     : main wizard record
- DPRSection     : one row per wizard section (23 sections)
- DPRCalculation : all financial tables as JSONFields (auto-computed)
- DPRAIContent   : Claude-generated narrative text
- DPRDocument    : generated PDFs (older versions archived)
- DPRMasterConfig: admin-configurable financial defaults
"""
from django.contrib.auth.models import User
from django.db import models
from apps.core.models.base import BaseModel


class DPRProject(BaseModel):

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        DATA_COMPLETE = 'data_complete', 'Data Complete'
        VALIDATED = 'validated', 'Validated'
        GENERATING = 'generating', 'Generating'
        GENERATED = 'generated', 'Generated'
        FAILED = 'failed', 'Failed'

    fpo = models.ForeignKey(
        'database.FPO', on_delete=models.CASCADE, related_name='dpr_projects'
    )
    project_title = models.CharField(max_length=500)
    project_type = models.CharField(
        max_length=100,
        help_text='MasterLookup category: dpr_project_type (new, expansion, diversification, modernisation)'
    )
    primary_commodity = models.ForeignKey(
        'database.MasterLookup', on_delete=models.PROTECT,
        related_name='dpr_projects'
    )
    secondary_commodities = models.JSONField(
        default=list,
        help_text='List of MasterLookup IDs'
    )
    project_components = models.JSONField(
        default=list,
        help_text='MasterLookup codes from dpr_project_component — drives which sections appear'
    )
    nature_of_business = models.CharField(
        max_length=100, blank=True,
        help_text='MasterLookup category: nature_of_business'
    )
    financial_year = models.CharField(max_length=10, help_text='e.g. 2025-26')
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    readiness_score = models.IntegerField(
        null=True, blank=True,
        help_text='0–100 — shown to FPO before generation starts'
    )
    risk_rating = models.CharField(
        max_length=20, null=True, blank=True,
        choices=[('low', 'Low'), ('moderate', 'Moderate'), ('high', 'High')]
    )
    validation_errors = models.JSONField(
        default=list,
        help_text='Blocking issues — PDF not generated until cleared'
    )
    validation_warnings = models.JSONField(
        default=list,
        help_text='Non-blocking — shown as cautions'
    )
    ai_suggestions = models.JSONField(
        default=list,
        help_text='Improvement tips shown to FPO before generation'
    )

    class Meta:
        verbose_name = 'DPR Project'
        verbose_name_plural = 'DPR Projects'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.project_title} — {self.fpo} ({self.financial_year})"


class DPRSection(BaseModel):
    project = models.ForeignKey(
        DPRProject, on_delete=models.CASCADE, related_name='sections'
    )
    section_key = models.CharField(
        max_length=100,
        help_text='e.g. project_location, machinery, financial_info'
    )
    data = models.JSONField(default=dict, help_text='Structured answers for this section')
    is_complete = models.BooleanField(default=False)
    completion_pct = models.IntegerField(default=0)

    class Meta:
        verbose_name = 'DPR Section'
        verbose_name_plural = 'DPR Sections'
        unique_together = ('project', 'section_key')

    def __str__(self):
        return f"{self.project} — {self.section_key}"


class DPRCalculation(BaseModel):
    project = models.OneToOneField(
        DPRProject, on_delete=models.CASCADE, related_name='calculation'
    )
    project_cost = models.JSONField(
        default=dict,
        help_text='land, civil, machinery, equipment, vehicles, pre-op, contingency, working_capital'
    )
    means_of_finance = models.JSONField(
        default=dict,
        help_text='equity, term_loan, working_capital_loan, subsidy, grant'
    )
    working_capital = models.JSONField(default=dict)
    operating_cost = models.JSONField(
        default=dict,
        help_text='Annual: raw_material, labour, utilities, admin'
    )
    revenue_projections = models.JSONField(default=dict, help_text='Year-wise revenue')
    profit_loss = models.JSONField(default=dict, help_text='5-year projected P&L')
    cash_flow = models.JSONField(default=dict, help_text='5-year projected cash flow')
    balance_sheet = models.JSONField(default=dict, help_text='5-year projected balance sheet')
    depreciation_schedule = models.JSONField(default=dict)
    loan_repayment = models.JSONField(default=dict)
    financial_indicators = models.JSONField(
        default=dict,
        help_text='irr, npv, bcr, dscr, payback_period, roi, roe, break_even_year, break_even_capacity, debt_equity_ratio, current_ratio, gross_margin'
    )
    calculated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'DPR Calculation'
        verbose_name_plural = 'DPR Calculations'

    def __str__(self):
        return f"Calculation — {self.project}"


class DPRAIContent(BaseModel):
    project = models.OneToOneField(
        DPRProject, on_delete=models.CASCADE, related_name='ai_content'
    )
    executive_summary = models.TextField(blank=True)
    project_description = models.TextField(blank=True)
    technical_feasibility = models.TextField(blank=True)
    market_analysis = models.TextField(blank=True)
    financial_analysis = models.TextField(blank=True)
    swot_analysis = models.JSONField(
        default=dict,
        help_text='{strengths, weaknesses, opportunities, threats}'
    )
    risk_assessment = models.TextField(blank=True)
    environmental_assessment = models.TextField(blank=True)
    implementation_narrative = models.TextField(blank=True)
    conclusion = models.TextField(blank=True)
    is_reviewed = models.BooleanField(
        default=False,
        help_text='FPO has reviewed and approved the AI-generated content'
    )
    claude_model_version = models.CharField(
        max_length=100, blank=True,
        help_text='e.g. claude-sonnet-4-6'
    )

    class Meta:
        verbose_name = 'DPR AI Content'
        verbose_name_plural = 'DPR AI Content'

    def __str__(self):
        return f"AI Content — {self.project}"


class DPRDocument(BaseModel):
    project = models.ForeignKey(
        DPRProject, on_delete=models.CASCADE, related_name='documents'
    )
    file_url = models.CharField(
        max_length=1000,
        help_text='S3 pre-signed URL of generated PDF'
    )
    generated_at = models.DateTimeField(auto_now_add=True)
    is_archived = models.BooleanField(
        default=False,
        help_text='True when a newer version replaces this — kept for audit'
    )

    class Meta:
        verbose_name = 'DPR Document'
        verbose_name_plural = 'DPR Documents'
        ordering = ['-generated_at']

    def __str__(self):
        return f"DPR PDF — {self.project} ({'archived' if self.is_archived else 'latest'})"


class DPRMasterConfig(BaseModel):
    config_key = models.CharField(
        max_length=100, unique=True,
        help_text='e.g. interest_rate_term_loan, depreciation_rate_machinery'
    )
    config_value = models.JSONField(
        help_text='Number, list, or dict depending on the config'
    )
    description = models.TextField()
    updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        help_text='KAU Admin who last updated this value'
    )

    class Meta:
        verbose_name = 'DPR Master Config'
        verbose_name_plural = 'DPR Master Configs'

    def __str__(self):
        return f"{self.config_key} = {self.config_value}"
