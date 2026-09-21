"""
FPO Redirect Service
====================
Determines where an fpo_manager user should land after login.

Returns a stage dict that the frontend maps to its own routes.
Backend never hardcodes frontend URLs — frontend owns route mapping.

Stages:
    wizard_step      → /fpo/register  (step 1-4)
    verify_email     → /fpo/register  (step 5 — email OTP)
    verify_phone     → /fpo/register  (step 5 — phone OTP)
    upload_documents → /fpo/register  (step 6)
    submit           → /fpo/register  (step 7)
    status           → /fpo/status  (submitted, under_review, suspended, info_required)
    claim_status     → /fpo/claim/status  (pending or docs_requested claim)
    dashboard        → /fpo/dashboard
    None             → no redirect (admin/other roles use menu)

Primary vs. secondary users:
    Only the FPO's primary_user ever goes through the registration wizard
    (verify_email/verify_phone/upload_documents/submit are all steps of
    *their* onboarding). A secondary/team-member user (linked via
    FPOUserMembership, not FPO.primary_user) never created the FPO and
    must never be sent through that wizard — they only ever land on
    'dashboard' (FPO approved) or 'status' (FPO not ready yet).
"""

from apps.core.utils.constants import FPOStatus, UserRole
from apps.database.models.fpo import FPO, FPOOwnershipClaim, ClaimStatus, FPOUserMembership


def get_fpo_redirect(user):
    """
    Return redirect stage dict for fpo_manager users.
    Returns None for all other roles.
    """
    if not user.groups.filter(name=UserRole.FPO_MANAGER).exists():
        return None

    # If user has any active claim (pending review or docs requested), send to claim status page
    if FPOOwnershipClaim.objects.filter(
        claimant=user,
        status__in=[ClaimStatus.PENDING, ClaimStatus.DOCS_REQUESTED]
    ).exists():
        return {'stage': 'claim_status', 'step': None}

    fpo = FPO.objects.filter(primary_user=user).first()

    if fpo:
        return _primary_redirect(fpo)

    # Not a primary user — check whether they're an invited secondary/team member
    membership = (
        FPOUserMembership.objects
        .filter(user=user, is_active=True)
        .select_related('fpo')
        .first()
    )
    if membership:
        return _secondary_redirect(membership.fpo)

    # Neither a primary user nor an active team member — start registration
    return {'stage': 'wizard_step', 'step': 1}


def _primary_redirect(fpo):
    """Redirect logic for the FPO's own primary/registering user."""
    if fpo.status in (FPOStatus.SUBMITTED, FPOStatus.UNDER_REVIEW, FPOStatus.SUSPENDED, FPOStatus.INFO_REQUIRED):
        return {'stage': 'status', 'step': None}

    if fpo.status == FPOStatus.APPROVED:
        return {'stage': 'dashboard', 'step': None}

    # DRAFT, REJECTED — determine wizard stage
    if fpo.current_step < 4:
        return {'stage': 'wizard_step', 'step': fpo.current_step + 1}

    if not fpo.email_verified:
        return {'stage': 'verify_email', 'step': None}

    if not fpo.phone_verified:
        return {'stage': 'verify_phone', 'step': None}

    if not fpo.required_documents_uploaded:
        return {'stage': 'upload_documents', 'step': None}

    return {'stage': 'submit', 'step': None}


def _secondary_redirect(fpo):
    """
    Redirect logic for an invited secondary/team-member user.

    They never go through the registration wizard — that belongs to the
    primary user alone. They only ever land on the dashboard once the
    FPO is approved, or on the status page while it's still being
    reviewed/set up.
    """
    if fpo.status == FPOStatus.APPROVED:
        return {'stage': 'dashboard', 'step': None}
    return {'stage': 'status', 'step': None}