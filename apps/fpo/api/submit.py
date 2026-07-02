"""
FPO Submission API
==================
POST /api/fpo/me/submit/

Validates all pre-submission conditions, then auto-approves the registration
(KAU confirmed June 2026: approval is automated, no manual review needed).

Flow: DRAFT → SUBMITTED → APPROVED (in one atomic transaction, two history rows)

Pre-submission checklist (SRS §3.1.3):
    1. All 4 wizard steps completed
    2. office_email verified
    3. office_phone verified
    4. All 3 required documents uploaded (reg_cert, bank_details, pan_card)
    5. total_members >= 10
    6. GPS coordinates present
"""

from django.contrib.auth import get_user_model
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.views import APIView

from apps.core.permissions.rbac import IsFPOManager
from apps.core.utils.constants import FPOStatus
from apps.core.utils.responses import StandardResponse
from apps.core.services.translation import t
from apps.core.services.audit import AuditService
from apps.core.models.generic import AuditLog
from apps.database.models.fpo import FPO, ApplicationStatusHistory
from apps.notifications.services import send_notification

User = get_user_model()


class FPOSubmitView(APIView):
    permission_classes = [IsFPOManager]

    @extend_schema(
        tags=['FPO - Registration'],
        summary='Submit FPO application',
        description=(
            'Validates all pre-submission conditions and auto-approves the FPO registration.\n\n'
            '**Flow:** `DRAFT` → `SUBMITTED` → `APPROVED` (single transaction)\n\n'
            '**All conditions must be met before submission:**\n'
            '- All 4 wizard steps completed\n'
            '- Office email verified (`POST /api/fpo/email-verify/confirm/`)\n'
            '- Office phone verified (`POST /api/fpo/phone-verify/confirm/`)\n'
            '- All 3 required documents uploaded: `fpo_reg_cert`, `bank_details`, `pan_card`\n'
            '- Minimum 10 members\n'
            '- GPS coordinates (latitude + longitude)\n\n'
            'On success: generates `application_id` (format: `KAU-FPO-{DISTRICT}-{YEAR}-{SEQ}`), '
            'auto-approves the FPO, and sends confirmation email + SMS to the FPO user.'
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

        if fpo.status not in (FPOStatus.DRAFT, FPOStatus.INFO_REQUIRED):
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
            from_status    = fpo.status
            application_id = fpo.application_id or fpo.generate_application_id()
            fpo.application_id = application_id
            fpo.status         = FPOStatus.APPROVED
            fpo.save(update_fields=['application_id', 'status', 'updated_at'])

            # Two history entries: DRAFT → SUBMITTED → APPROVED
            ApplicationStatusHistory.objects.create(
                fpo         = fpo,
                from_status = from_status,
                to_status   = FPOStatus.SUBMITTED,
                changed_by  = request.user,
            )
            ApplicationStatusHistory.objects.create(
                fpo         = fpo,
                from_status = FPOStatus.SUBMITTED,
                to_status   = FPOStatus.APPROVED,
                changed_by  = None,
                notes       = 'Auto-approved on submission.',
            )

        AuditService.log(
            user=request.user,
            action=AuditLog.Action.FPO_SUBMIT,
            instance=fpo,
            request=request,
            changes={'application_id': application_id, 'status': FPOStatus.APPROVED},
        )

        # Notify FPO user — email + SMS (approved, not just submitted)
        ctx = {
            'user_name':      request.user.get_full_name() or request.user.username,
            'fpo_name':       fpo.name or f'FPO #{fpo.id}',
            'application_id': application_id,
        }
        send_notification(user=request.user, code='application_approved', channel='email',  context=ctx, lang=lang)
        send_notification(user=request.user, code='application_approved', channel='sms',   context=ctx, lang=lang)
        send_notification(user=request.user, code='application_approved', channel='in_app', context=ctx, lang=lang)

        return StandardResponse.success(
            message=t('fpo.application_approved', lang),
            data={'application_id': application_id, 'status': FPOStatus.APPROVED},
        )


