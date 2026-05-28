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
    status           → /fpo/status
    dashboard        → /fpo/dashboard
    None             → no redirect (admin/other roles use menu)
"""

from apps.core.utils.constants import FPOStatus, UserRole


def get_fpo_redirect(user):
    """
    Return redirect stage dict for fpo_manager users.
    Returns None for all other roles.
    """
    if not user.groups.filter(name=UserRole.FPO_MANAGER).exists():
        return None

    from apps.database.models.fpo import FPO

    fpo = FPO.objects.filter(primary_user=user).first()

    if not fpo:
        return {'stage': 'wizard_step', 'step': 1}

    if fpo.status in (FPOStatus.SUBMITTED, FPOStatus.UNDER_REVIEW, FPOStatus.SUSPENDED):
        return {'stage': 'status', 'step': None}

    if fpo.status == FPOStatus.APPROVED:
        return {'stage': 'dashboard', 'step': None}

    # DRAFT, INFO_REQUIRED, REJECTED — determine wizard stage
    if fpo.current_step < 4:
        return {'stage': 'wizard_step', 'step': fpo.current_step + 1}

    if not fpo.email_verified:
        return {'stage': 'verify_email', 'step': None}

    if not fpo.phone_verified:
        return {'stage': 'verify_phone', 'step': None}

    if not fpo.required_documents_uploaded:
        return {'stage': 'upload_documents', 'step': None}

    return {'stage': 'submit', 'step': None}
