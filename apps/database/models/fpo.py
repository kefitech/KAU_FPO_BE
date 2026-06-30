"""
FPO Models — KAU-FPO Platform
==============================

All FPO-related models: registration wizard, documents,
user membership, tier system, and ownership claims.

Key rules:
- FPO.tier is NEVER set directly — always via FPOTierHistory (BR-107)
- FPO is editable only in DRAFT or INFO_REQUIRED status (BR-007)
- application_id is auto-generated on submit: KAU-FPO-{DISTRICT}-{YEAR}-{SEQ}
- FPO.assigned_to is Phase 2 row-level security anchor — enforced in Phase 2
"""

import uuid
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import models

from apps.core.models.base import BaseModel, TimeStampedModel
from apps.core.utils.constants import (
    District,
    DocumentType,
    FPOStatus,
    REQUIRED_DOCUMENTS,
)

User = get_user_model()


# =============================================================================
# CHOICES
# =============================================================================

# Legal structure values that require CIN format (21-char MCA21).
# All others use Registration Number (alphanumeric).
# Stored here as a set for serializer validation — legal_structure field itself
# is a plain CharField; options come from MasterLookup category='legal_structure'.
LEGAL_STRUCTURES_REQUIRING_CIN = {'companies_act', 'producer_companies'}


class TierChoice(models.TextChoices):
    A = 'A', 'Tier A'
    B = 'B', 'Tier B'
    C = 'C', 'Tier C'
    D = 'D', 'Tier D'


class ClaimStatus(models.TextChoices):
    PENDING  = 'pending',  'Pending'
    APPROVED = 'approved', 'Approved'
    REJECTED = 'rejected', 'Rejected'


# =============================================================================
# FPO — MAIN MODEL
# =============================================================================

class FPO(BaseModel):
    """
    Main FPO profile — 4-step registration wizard.

    BaseModel gives: uuid, created_at, updated_at, created_by (who registered),
    updated_by (who last updated), is_deleted, deleted_at, deleted_by.

    current_step tracks wizard progress so frontend can resume
    where the user left off after logging back in.

    latitude/longitude enable Phase 1 map display. Phase 2 adds
    PostGIS PointField alongside these — zero conflict.
    """

    # ── Step 1: Basic Info ────────────────────────────────────────────────────
    name                   = models.CharField(max_length=255)
    name_ml                = models.CharField(max_length=255, blank=True)
    legal_structure        = models.CharField(max_length=50, blank=True,
                                              help_text="MasterLookup category='legal_structure'")
    legal_structure_detail = models.CharField(max_length=100, blank=True,
                                              help_text="State CSA act name when legal_structure='state_specific_csa'")
    registration_number    = models.CharField(max_length=100, blank=True,
                                              help_text="For non-Companies Act FPOs. Unique when non-empty.")
    cin_number             = models.CharField(max_length=21, blank=True,
                                              help_text="Companies Act / Producer Companies only. MCA21 21-char format.")
    date_of_registration   = models.DateField(null=True, blank=True)
    pan_number             = models.CharField(max_length=10)
    gst_number             = models.CharField(max_length=15, blank=True)

    # ── Step 2: Contact & Location ────────────────────────────────────────────
    district       = models.CharField(max_length=3, choices=District.choices, blank=True)
    block_taluk    = models.CharField(max_length=100, blank=True)
    village_town   = models.CharField(max_length=100, blank=True)
    address_line1  = models.CharField(max_length=255, blank=True)
    address_line2  = models.CharField(max_length=255, blank=True)
    pincode        = models.CharField(max_length=6, blank=True)
    office_phone    = models.CharField(max_length=10, blank=True)
    office_email    = models.EmailField(blank=True)
    website         = models.URLField(blank=True)
    email_verified  = models.BooleanField(default=False)
    phone_verified  = models.BooleanField(default=False)

    # Map coordinates — frontend plots pin on Google Maps / Leaflet
    # Phase 2 adds PostGIS PointField alongside these
    latitude  = models.DecimalField(
        max_digits=9, decimal_places=6,
        null=True, blank=True,
        help_text='GPS latitude — sent by frontend from browser location or geocoded from address'
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6,
        null=True, blank=True,
        help_text='GPS longitude — sent by frontend from browser location or geocoded from address'
    )

    # ── Step 3: Signatory & Members ───────────────────────────────────────────
    signatory_name          = models.CharField(max_length=255, blank=True)
    signatory_designation   = models.CharField(max_length=100, blank=True,
                                               help_text="MasterLookup category='signatory_designation'")
    signatory_phone         = models.CharField(max_length=10, blank=True)
    signatory_email         = models.EmailField(blank=True)
    signatory_aadhaar_last4 = models.CharField(max_length=4, blank=True)
    total_members           = models.PositiveIntegerField(null=True, blank=True)
    male_members            = models.PositiveIntegerField(null=True, blank=True)
    female_members          = models.PositiveIntegerField(null=True, blank=True)
    sc_st_members           = models.PositiveIntegerField(null=True, blank=True)

    # New Step 3 fields (KAU RCD Reply, June 2026)
    promoting_agency        = models.CharField(max_length=50, blank=True,
                                               help_text="MasterLookup category='promoting_agency'")
    facilitating_agency_name = models.CharField(max_length=255, blank=True)
    ceo_available           = models.BooleanField(null=True, blank=True)
    accountant_available    = models.BooleanField(null=True, blank=True)
    total_directors         = models.PositiveIntegerField(null=True, blank=True)
    women_directors         = models.PositiveIntegerField(null=True, blank=True)
    directors_under_35      = models.PositiveIntegerField(null=True, blank=True)

    # ── Step 4: Business Details ──────────────────────────────────────────────
    primary_commodities   = models.JSONField(default=list, blank=True)
    secondary_commodities = models.JSONField(default=list, blank=True)
    annual_turnover       = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True
    )
    bank_name      = models.CharField(max_length=100, blank=True)
    bank_branch    = models.CharField(max_length=100, blank=True)
    account_number = models.CharField(max_length=18, blank=True)
    ifsc_code      = models.CharField(max_length=11, blank=True)
    description    = models.TextField(blank=True)

    # ── Wizard Progress ───────────────────────────────────────────────────────
    current_step = models.PositiveSmallIntegerField(
        default=1,
        help_text='Last completed wizard step (1-4). Frontend uses this to resume registration.'
    )

    # ── Meta / System Fields ──────────────────────────────────────────────────
    application_id = models.CharField(max_length=30, unique=True, blank=True, null=True, default=None)
    status         = models.CharField(
        max_length=20, choices=FPOStatus.choices, default=FPOStatus.DRAFT
    )
    tier           = models.CharField(
        max_length=1, blank=True,
        help_text='Cached from FPOTierHistory — never set directly (BR-107)'
    )
    primary_user = models.OneToOneField(
        User, on_delete=models.PROTECT,
        related_name='fpo', null=True, blank=True,
    )
    assigned_to  = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        related_name='assigned_fpos', null=True, blank=True,
        help_text='Phase 2: sub-admin row-level security anchor'
    )

    class Meta:
        verbose_name        = 'FPO'
        verbose_name_plural = 'FPOs'
        ordering            = ['-created_at']
        indexes             = [
            models.Index(fields=['status']),
            models.Index(fields=['district']),
            models.Index(fields=['tier']),
            models.Index(fields=['pan_number']),
        ]

    def __str__(self):
        return f"{self.name} ({self.application_id or 'DRAFT'})"

    def generate_application_id(self):
        """Format: KAU-FPO-{DISTRICT}-{YEAR}-{4-digit sequence}"""
        year     = date.today().year
        district = self.district
        count    = FPO.objects.filter(
            district=district,
            application_id__startswith=f'KAU-FPO-{district}-{year}-',
        ).count()
        return f'KAU-FPO-{district}-{year}-{str(count + 1).zfill(4)}'

    @property
    def current_tier(self):
        """Read current tier from history — never from FPO.tier directly."""
        latest = self.tier_history.order_by('-created_at').first()
        return latest.tier if latest else None

    @property
    def required_documents_uploaded(self):
        uploaded = set(self.documents.values_list('document_type', flat=True))
        return all(doc in uploaded for doc in REQUIRED_DOCUMENTS)

    @property
    def required_documents_verified(self):
        for doc_type in REQUIRED_DOCUMENTS:
            doc = self.documents.filter(document_type=doc_type).first()
            if not doc or not doc.is_verified:
                return False
        return True

    def get_submission_errors(self):
        """Returns list of blocking errors before submission (SRS §3.1.3)."""
        errors = []
        if self.current_step < 4:
            errors.append(f'Registration wizard incomplete. Complete all 4 steps (currently on step {self.current_step}).')
        if not self.email_verified:
            errors.append('Office email must be verified before submission.')
        if not self.phone_verified:
            errors.append('Office phone number must be verified before submission.')
        if not self.required_documents_uploaded:
            errors.append('All 3 required documents must be uploaded before submission.')
        if not self.total_members or self.total_members < 10:
            errors.append('FPO must have at least 10 members.')
        if not self.latitude or not self.longitude:
            errors.append('GPS coordinates are required. Please allow location access or enter coordinates manually.')
        return errors


# =============================================================================
# APPLICATION STATUS HISTORY
# =============================================================================

class ApplicationStatusHistory(TimeStampedModel):
    """
    Append-only audit trail — every FPO status change is permanently recorded.

    TimeStampedModel only — status history is never deleted or modified.
    Gives full timeline: who changed what, when, and why.

    Example timeline:
        DRAFT → SUBMITTED        (by FPO user, no notes)
        SUBMITTED → UNDER_REVIEW (by admin)
        UNDER_REVIEW → INFO_REQUIRED (by admin, notes: "Bank proof unclear")
        INFO_REQUIRED → SUBMITTED  (by FPO user after fixing)
        SUBMITTED → APPROVED     (by admin, notes: "All documents verified")
    """

    fpo         = models.ForeignKey(FPO, on_delete=models.CASCADE, related_name='status_history')
    from_status = models.CharField(max_length=20, blank=True)
    to_status   = models.CharField(max_length=20)
    changed_by  = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    notes       = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = 'Application Status Histories'
        ordering            = ['-created_at']

    def __str__(self):
        return f"{self.fpo} | {self.from_status} → {self.to_status}"


# =============================================================================
# FPO DOCUMENT
# =============================================================================

def fpo_document_upload_path(instance, filename):
    ext = filename.rsplit('.', 1)[-1].lower()
    return f'fpo/{instance.fpo_id}/documents/{instance.document_type}/{uuid.uuid4().hex}.{ext}'


class FPODocument(BaseModel):
    """
    Uploaded documents stored on S3 via django-storages.

    BaseModel gives: uuid, timestamps, created_by (who uploaded),
    updated_by, is_deleted (soft delete — deleted docs still traceable
    for audit — admin can see a document was uploaded then deleted).

    Required types (BR-005): fpo_reg_cert, bank_details,
    signatory_id, pan_card — all 4 must be uploaded before submission.
    """

    MAX_SIZE_STANDARD = 5  * 1024 * 1024   # 5 MB
    MAX_SIZE_LARGE    = 10 * 1024 * 1024   # 10 MB — member_list, annual_report
    LARGE_TYPES       = {DocumentType.MEMBER_LIST, DocumentType.ANNUAL_REPORT}

    fpo           = models.ForeignKey(FPO, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=30, choices=DocumentType.choices)
    file          = models.FileField(upload_to=fpo_document_upload_path)
    file_size     = models.PositiveIntegerField(help_text='Size in bytes')
    mime_type     = models.CharField(max_length=100)
    is_verified   = models.BooleanField(default=False)
    verified_by   = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='verified_documents',
    )
    verified_at   = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes  = [models.Index(fields=['fpo', 'document_type'])]

    def __str__(self):
        return f"{self.fpo} — {self.get_document_type_display()}"

    @property
    def max_allowed_size(self):
        return self.MAX_SIZE_LARGE if self.document_type in self.LARGE_TYPES else self.MAX_SIZE_STANDARD

    @property
    def is_required(self):
        return self.document_type in REQUIRED_DOCUMENTS


# =============================================================================
# FPO USER MEMBERSHIP
# =============================================================================

class FPOUserMembership(BaseModel):
    """
    User hierarchy within an FPO.

    BaseModel gives: uuid, timestamps, created_by (who added this member),
    updated_by (who last changed their status), is_deleted (soft delete —
    deactivated members are soft deleted, membership history preserved).

    Primary user: full control (one per FPO).
    Secondary users: data entry + view only, require primary approval.
    Max secondary users controlled by FPO.max_secondary_users (default 15).
    """

    fpo       = models.ForeignKey(FPO, on_delete=models.CASCADE, related_name='memberships')
    user      = models.OneToOneField(User, on_delete=models.CASCADE, related_name='fpo_membership')
    role      = models.ForeignKey(
        Group,
        on_delete=models.PROTECT,
        related_name='fpo_memberships',
        null=True, blank=True,
        help_text='FPO-internal role — Django Group (primary, secondary, etc.)',
    )
    is_active = models.BooleanField(default=False)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('fpo', 'user')]
        ordering        = ['joined_at']

    def __str__(self):
        return f"{self.user} — {self.role} @ {self.fpo}"


# =============================================================================
# TIER CRITERIA
# =============================================================================

class TierCriteria(BaseModel):
    """
    Configurable scoring criteria managed by KAU Admin.

    BaseModel gives: uuid, timestamps, created_by (who created this criterion),
    updated_by (who last changed weights/thresholds), is_deleted (soft delete —
    removed criteria are soft deleted so historical tier calculations still make sense).

    is_visible_to_fpo controls whether FPOs can see this criterion on dashboard.
    """

    criteria_name     = models.CharField(max_length=200)
    weight            = models.DecimalField(
        max_digits=5, decimal_places=2,
        help_text='Scoring weight, e.g. 20.00 = 20%'
    )
    threshold_a       = models.DecimalField(
        max_digits=5, decimal_places=2,
        help_text='Minimum score for Tier A'
    )
    threshold_b       = models.DecimalField(
        max_digits=5, decimal_places=2,
        help_text='Minimum score for Tier B'
    )
    threshold_c       = models.DecimalField(
        max_digits=5, decimal_places=2,
        help_text='Minimum score for Tier C'
    )
    threshold_d       = models.DecimalField(
        max_digits=5, decimal_places=2,
        help_text='Minimum score for Tier D'
    )
    is_visible_to_fpo = models.BooleanField(
        default=False,
        help_text='Whether FPOs can see this criterion on their dashboard'
    )
    is_active         = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = 'Tier Criteria'
        ordering            = ['-weight']

    def __str__(self):
        return f"{self.criteria_name} (weight: {self.weight})"


# =============================================================================
# FPO TIER HISTORY
# =============================================================================

class FPOTierHistory(TimeStampedModel):
    """
    Append-only tier assignment log — one row per tier change per financial year.

    TimeStampedModel only — tier history is never deleted or modified.
    Current tier = latest row for that FPO.
    On save, FPO.tier is synced for efficient DB filtering.

    Full promotion/demotion history:
        2024-25 → Tier D  (starting tier)
        2025-26 → Tier C  (promoted)
        2026-27 → Tier B  (promoted)
        2027-28 → Tier C  (demoted)
    """

    fpo            = models.ForeignKey(FPO, on_delete=models.CASCADE, related_name='tier_history')
    tier           = models.CharField(max_length=1, choices=TierChoice.choices)
    financial_year = models.CharField(max_length=7, help_text="e.g. 2025-26")
    assigned_by    = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    notes          = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = 'FPO Tier Histories'
        ordering            = ['-created_at']

    def __str__(self):
        return f"{self.fpo} — Tier {self.tier} ({self.financial_year})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Sync FPO.tier so admin can filter efficiently without a subquery
        FPO.objects.filter(pk=self.fpo_id).update(tier=self.tier)


# =============================================================================
# TIER ASSESSMENT — FRAMEWORK MODELS
# =============================================================================

class TierDomain(models.Model):
    """6 domains from KAU Tier Framework v1.0."""
    code       = models.CharField(max_length=5, unique=True)   # I, II, III, IV, V, VI
    name       = models.CharField(max_length=100)
    max_marks  = models.PositiveSmallIntegerField()
    order      = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"Domain {self.code} — {self.name} ({self.max_marks} marks)"


class TierCriterion(models.Model):
    """16 criteria across 6 domains."""

    class ScoringType(models.TextChoices):
        COMPUTED        = 'computed',        'Computed automatically'
        SINGLE_SELECT   = 'single_select',   'Single select'
        BOOLEAN         = 'boolean',         'Yes / No'
        NUMERIC_RANGE   = 'numeric_range',   'Numeric range'
        ADDITIVE_BOOL   = 'additive_bool',   'Additive Yes/No'
        PERCENTAGE      = 'percentage',      'System calculated percentage'
        MULTI_SELECT    = 'multi_select',    'Multi select'
        CONDITIONAL     = 'conditional',     'Conditional logic'

    domain       = models.ForeignKey(TierDomain, on_delete=models.CASCADE, related_name='criteria')
    code         = models.CharField(max_length=50, unique=True)
    name         = models.CharField(max_length=200)
    max_marks    = models.PositiveSmallIntegerField()
    scoring_type = models.CharField(max_length=20, choices=ScoringType.choices)
    order        = models.PositiveSmallIntegerField(default=0)
    is_active    = models.BooleanField(default=True)

    class Meta:
        ordering = ['domain__order', 'order']

    def __str__(self):
        return f"{self.code} — {self.name}"


class TierQuestion(models.Model):
    """28 questions linked to criteria. answer_config stores options+scores as JSON."""

    class InputType(models.TextChoices):
        NUMBER        = 'number',        'Numeric input'
        BOOLEAN       = 'boolean',       'Yes / No'
        SINGLE_SELECT = 'single_select', 'Single select dropdown'
        MULTI_SELECT  = 'multi_select',  'Multi select checkboxes'
        COMPUTED      = 'computed',      'Auto-computed — no user input'

    criterion    = models.ForeignKey(TierCriterion, on_delete=models.CASCADE, related_name='questions')
    question_no  = models.PositiveSmallIntegerField(unique=True)   # Q1–Q29
    text         = models.TextField()
    input_type   = models.CharField(max_length=20, choices=InputType.choices)
    answer_config = models.JSONField(
        default=dict,
        help_text=(
            'For single_select/boolean: {"options": [{"value": "yes", "label": "Yes", "score": 5}]}\n'
            'For number/multi_select: {"score_ranges": [...]} or {"options": [...]}\n'
            'For computed: {"source": "date_of_registration"}'
        )
    )
    is_conditional   = models.BooleanField(default=False)
    condition_on     = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='dependent_questions',
        help_text='Show this question only when condition_on question has condition_value'
    )
    condition_value  = models.CharField(max_length=50, blank=True)
    is_required      = models.BooleanField(default=True)
    has_upload       = models.BooleanField(default=False, help_text='Q6, Q17, Q27 require document upload')
    upload_label     = models.CharField(max_length=200, blank=True)
    order            = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['question_no']

    def __str__(self):
        return f"Q{self.question_no}: {self.text[:60]}"


# =============================================================================
# TIER ASSESSMENT — FPO RESPONSE MODELS
# =============================================================================

class FPOAssessment(BaseModel):
    """One assessment per FPO per financial year. Editable until locked."""

    class Status(models.TextChoices):
        DRAFT     = 'draft',     'Draft'
        SUBMITTED = 'submitted', 'Submitted'

    fpo            = models.ForeignKey(FPO, on_delete=models.CASCADE, related_name='assessments')
    financial_year = models.CharField(max_length=7, help_text='e.g. 2025-26')
    status         = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    total_score    = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    tier_assigned  = models.CharField(max_length=1, blank=True)
    domain_scores  = models.JSONField(default=dict, blank=True, help_text='{"I": 17.0, "II": 13.0, ...} — stored on submit')
    submitted_at   = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [('fpo', 'financial_year')]
        ordering        = ['-financial_year']

    def __str__(self):
        return f"{self.fpo} — {self.financial_year} ({self.status})"


class AssessmentAnswer(models.Model):
    """One answer per question per assessment. answer stored as JSON for flexibility."""

    assessment = models.ForeignKey(FPOAssessment, on_delete=models.CASCADE, related_name='answers')
    question   = models.ForeignKey(TierQuestion, on_delete=models.CASCADE, related_name='answers')
    answer     = models.JSONField(
        help_text='Stored as JSON: "yes", 5000, ["local_market","trader"], etc.'
    )
    score      = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        unique_together = [('assessment', 'question')]
        ordering        = ['question__question_no']

    def __str__(self):
        return f"Assessment {self.assessment_id} — Q{self.question.question_no}"


class AssessmentUpload(models.Model):
    """Supporting document uploaded alongside a tier assessment question (Q6, Q17, Q27)."""

    def _upload_path(self, filename):
        ext = filename.rsplit('.', 1)[-1].lower()
        return f'fpo/{self.assessment.fpo_id}/tier-assessment/{self.assessment_id}/q{self.question_no}/{uuid.uuid4()}.{ext}'

    assessment        = models.ForeignKey(FPOAssessment, on_delete=models.CASCADE, related_name='uploads')
    question_no       = models.PositiveSmallIntegerField()
    file              = models.FileField(upload_to=_upload_path)
    original_filename = models.CharField(max_length=255)
    uploaded_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['question_no', 'uploaded_at']

    def __str__(self):
        return f"Assessment {self.assessment_id} — Q{self.question_no} — {self.original_filename}"


# =============================================================================
# FPO OWNERSHIP CLAIM
# =============================================================================

class FPOOwnershipClaim(TimeStampedModel):
    """
    Append-only claim record — triggered when duplicate detection fires (BR-109).

    TimeStampedModel only — claims are never deleted.
    Legitimate owner submits claim with reason + supporting documents.
    KAU Admin manually verifies and transfers FPO ownership if valid.
    """

    fpo                = models.ForeignKey(FPO, on_delete=models.CASCADE, related_name='ownership_claims')
    claimant           = models.ForeignKey(User, on_delete=models.CASCADE, related_name='fpo_claims')
    reason             = models.TextField()
    supporting_doc_ids = models.JSONField(
        default=list,
        help_text='List of FPODocument IDs submitted as supporting evidence'
    )
    status      = models.CharField(
        max_length=10, choices=ClaimStatus.choices, default=ClaimStatus.PENDING
    )
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='reviewed_claims',
    )
    reviewed_at  = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Claim by {self.claimant} on {self.fpo} [{self.status}]"


# =============================================================================
# FPO PERMISSION MATRIX
# =============================================================================

class FPOAction(BaseModel):
    """
    Registry of all actions that can be performed within an FPO.

    Seeded by developers when new features are built.
    Admin can toggle is_active and edit labels — code is immutable once set
    (used in has_fpo_permission() checks throughout the codebase).
    """

    code        = models.CharField(max_length=50, unique=True, help_text="Immutable action code used in permission checks")
    description = models.CharField(max_length=255, blank=True)
    is_active   = models.BooleanField(default=True)
    menu_item   = models.ForeignKey(
        'database.MenuItem',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='actions',
        help_text='Page this action belongs to — used to group actions in the permission matrix',
    )

    class Meta:
        ordering = ['code']

    def __str__(self):
        return self.code

    def get_label(self, language: str = 'en') -> str:
        from apps.core.services.translation import t
        key = f'fpo_action.{self.code}'
        result = t(key, language=language)
        if result != key:
            return result
        return self.code


class RoleActionPermission(BaseModel):
    """
    System-wide permission matrix — role x action ceiling set by KAU Admin.

    Covers all roles in the system (super_admin, sub_admin, fpo_manager,
    government, cbbo, expert, viewer, primary, secondary, and any future roles).
    One row per (role, action) pair. Admin manages via /api/admin/fpo-permissions/.
    """

    role       = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name='role_action_permissions',
    )
    action     = models.ForeignKey(FPOAction, on_delete=models.CASCADE, related_name='role_permissions')
    is_allowed = models.BooleanField(default=False)

    class Meta:
        unique_together = [('role', 'action')]
        ordering        = ['role', 'action']

    def __str__(self):
        return f"{self.role.name} + {self.action.code} -> {'allowed' if self.is_allowed else 'denied'}"


class FPOMemberOverride(BaseModel):
    """
    Per-member permission override set by the FPO primary user.

    Only actions where the role ceiling (RoleActionPermission.is_allowed=True)
    can be overridden — primary cannot grant above the ceiling.
    """

    membership = models.ForeignKey(
        FPOUserMembership,
        on_delete=models.CASCADE,
        related_name='permission_overrides',
    )
    action     = models.ForeignKey(FPOAction, on_delete=models.CASCADE, related_name='member_overrides')
    is_allowed = models.BooleanField(default=False)

    class Meta:
        unique_together = [('membership', 'action')]
        ordering        = ['membership', 'action']

    def __str__(self):
        return f"{self.membership.user} + {self.action.code} -> {'allowed' if self.is_allowed else 'denied'} (override)"


class RolePageAccess(BaseModel):
    """
    Which pages each role can access — Step 2 of the permission matrix flow.

    Role → Pages mapping. Admin sets this via the unified permission matrix UI:
    Step 1: Select role → Step 2: Pages shown as rows, toggle access → Step 3: Save.
    """

    role      = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name='page_access',
    )
    menu_item = models.ForeignKey(
        'database.MenuItem',
        on_delete=models.CASCADE,
        related_name='role_access',
    )
    is_allowed = models.BooleanField(default=False)

    class Meta:
        unique_together = [('role', 'menu_item')]
        ordering        = ['role', 'menu_item']

    def __str__(self):
        status = 'allowed' if self.is_allowed else 'denied'
        return f"{self.role.name} → {self.menu_item.path} ({status})"
