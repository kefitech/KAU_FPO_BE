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
from django.db import models

from apps.core.models.base import BaseModel, TimeStampedModel
from apps.core.models.generic import MasterLookup
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

class RegisteredUnder(models.TextChoices):
    COMPANIES_ACT          = 'companies_act',          'Companies Act 2013'
    COOPERATIVE_ACT        = 'cooperative_act',         'Kerala Co-operative Societies Act 1969'
    PRODUCER_COMPANIES_ACT = 'producer_companies_act',  'Producer Companies Act'
    SOCIETIES_ACT          = 'societies_act',           'Societies Registration Act 1860'
    OTHER                  = 'other',                   'Other'


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
    name                 = models.CharField(max_length=255)
    name_ml              = models.CharField(max_length=255, blank=True)
    registration_number  = models.CharField(max_length=100, unique=True)
    cin_number           = models.CharField(max_length=21, blank=True)
    date_of_registration = models.DateField()
    registered_under     = models.CharField(max_length=50, choices=RegisteredUnder.choices)
    pan_number           = models.CharField(max_length=10)
    gst_number           = models.CharField(max_length=15, blank=True)

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
    signatory_designation   = models.CharField(max_length=100, blank=True)
    signatory_phone         = models.CharField(max_length=10, blank=True)
    signatory_email         = models.EmailField(blank=True)
    signatory_aadhaar_last4 = models.CharField(max_length=4, blank=True)
    total_members           = models.PositiveIntegerField(null=True, blank=True)
    male_members            = models.PositiveIntegerField(null=True, blank=True)
    female_members          = models.PositiveIntegerField(null=True, blank=True)
    sc_st_members           = models.PositiveIntegerField(null=True, blank=True)

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
    application_id      = models.CharField(max_length=30, unique=True, blank=True)
    status              = models.CharField(
        max_length=20, choices=FPOStatus.choices, default=FPOStatus.DRAFT
    )
    tier                = models.CharField(
        max_length=1, blank=True,
        help_text='Cached from FPOTierHistory — never set directly (BR-107)'
    )
    max_secondary_users = models.PositiveIntegerField(
        default=15,
        help_text='Max secondary users for this FPO. Configurable by KAU Admin.'
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
            errors.append('All required documents must be uploaded before submission.')
        if not self.total_members or self.total_members < 10:
            errors.append('FPO must have at least 10 members.')
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
        MasterLookup,
        on_delete=models.PROTECT,
        related_name='fpo_memberships',
        null=True, blank=True,
        limit_choices_to={'category': 'fpo_member_role'},
        help_text='FPO-internal role — set from MasterLookup category fpo_member_role'
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


class FPOMemberPermission(BaseModel):
    """
    System-wide permission matrix — role x action ceiling set by KAU Admin.

    Primary user cannot grant their team more than what this matrix allows.
    One row per (role, action) pair. Admin manages via /api/admin/fpo-permissions/.
    """

    role       = models.ForeignKey(
        MasterLookup,
        on_delete=models.CASCADE,
        related_name='fpo_permissions',
        limit_choices_to={'category': 'fpo_member_role'},
    )
    action     = models.ForeignKey(FPOAction, on_delete=models.CASCADE, related_name='role_permissions')
    is_allowed = models.BooleanField(default=False)

    class Meta:
        unique_together = [('role', 'action')]
        ordering        = ['role', 'action']

    def __str__(self):
        return f"{self.role.code} + {self.action.code} -> {'allowed' if self.is_allowed else 'denied'}"


class FPOMemberOverride(BaseModel):
    """
    Per-member permission override set by the FPO primary user.

    Only actions where the role ceiling (FPOMemberPermission.is_allowed=True)
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
