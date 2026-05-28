"""
FPO Submission API
==================
POST /api/fpo/me/submit/

Validates all pre-submission conditions, transitions status DRAFT → SUBMITTED,
generates application_id, and fires notifications to FPO user + admin.

Pre-submission checklist (SRS §3.1.3):
    1. All 4 wizard steps completed
    2. office_email verified
    3. office_phone verified
    4. All 4 required documents uploaded
    5. total_members >= 10
"""

from django.contrib.auth import get_user_model
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.views import APIView

from apps.core.permissions.rbac import IsFPOManager
from apps.core.utils.constants import FPOStatus, UserRole
from apps.core.utils.responses import StandardResponse
from apps.core.services.translation import t
from apps.database.models.fpo import FPO, ApplicationStatusHistory
from apps.notifications.services import send_notification

User = get_user_model()


class FPOSubmitView(APIView):
    permission_classes = [IsFPOManager]

    @extend_schema(
        tags=['FPO - Registration'],
        summary='Submit FPO application',
        description=(
            'Validates all pre-submission conditions and transitions the FPO from '
            '`DRAFT` to `SUBMITTED`.\n\n'
            '**All conditions must be met before submission:**\n'
            '- All 4 wizard steps completed\n'
            '- Office email verified (`POST /api/fpo/email-verify/confirm/`)\n'
            '- Office phone verified (`POST /api/fpo/phone-verify/confirm/`)\n'
            '- All 4 required documents uploaded: `fpo_reg_cert`, `bank_details`, '
            '`signatory_id`, `pan_card`\n'
            '- Minimum 10 members\n\n'
            'On success: generates `application_id` (format: `KAU-FPO-{DISTRICT}-{YEAR}-{SEQ}`), '
            'sends confirmation email + SMS to FPO user, and notifies admin.'
        ),
        request=None,
        responses={200: None, 400: None},
    )
    def post(self, request):
        lang = request.language

        try:
            fpo = FPO.objects.select_related('primary_user').get(primary_user=request.user)
        except FPO.DoesNotExist:
            return StandardResponse.error(
                t('fpo.fpo_not_found', lang),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if fpo.status != FPOStatus.DRAFT:
            return StandardResponse.error(
                t('fpo.already_submitted', lang),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Run all pre-submission checks
        errors = fpo.get_submission_errors()
        if errors:
            return StandardResponse.error(
                errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            application_id = fpo.generate_application_id()
            fpo.application_id = application_id
            fpo.status         = FPOStatus.SUBMITTED
            fpo.save(update_fields=['application_id', 'status', 'updated_at'])

            ApplicationStatusHistory.objects.create(
                fpo         = fpo,
                from_status = FPOStatus.DRAFT,
                to_status   = FPOStatus.SUBMITTED,
                changed_by  = request.user,
            )

        # Notify FPO user — email + SMS
        ctx = {
            'user_name':      request.user.get_full_name() or request.user.username,
            'application_id': application_id,
        }
        send_notification(user=request.user, code='application_submitted', channel='email', context=ctx, lang=lang)
        send_notification(user=request.user, code='application_submitted', channel='sms',   context=ctx, lang=lang)

        # Notify all super_admins
        _notify_admins(fpo, lang)

        return StandardResponse.success(
            message=t('fpo.application_submitted', lang),
            data={'application_id': application_id},
        )


def _notify_admins(fpo, lang):
    """Send new application notification to all super_admin users."""
    admins = User.objects.filter(groups__name=UserRole.SUPER_ADMIN, is_active=True)
    ctx = {
        'fpo_name':       fpo.name,
        'application_id': fpo.application_id,
        'district':       fpo.get_district_display() if hasattr(fpo, 'get_district_display') else fpo.district,
        'button_link':    '',
        'button_text':    'Review Application',
    }
    for admin in admins:
        send_notification(
            user=admin,
            code='admin_new_fpo_application',
            channel='email',
            context=ctx,
            lang='en',
        )
