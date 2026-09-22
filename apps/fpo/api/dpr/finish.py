"""
DPR Finish endpoint — IN_PROGRESS → SUBMITTED transition.

Fired from the wizard's final section (§2.3.22 Risk Assessment) "Finish"
button. Marks the DPR as ready for the FPO to release a versioned PDF via
Manage DPRs and notifies both the FPO primary user (email + in-app) and
the KAU admin staff (in-app only).

Soft state: any subsequent section save reverts SUBMITTED → IN_PROGRESS
via the existing dpr_section_saved signal, so re-clicking Finish after
edits is expected and creates a fresh audit + notification event.

Author: Athul Gopan (Kefi Tech Solutions)
"""
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.services.audit import AuditService
from apps.core.utils.constants import UserRole
from apps.core.utils.responses import StandardResponse
from apps.core.models.generic import AuditLog
from apps.database.models import DPRProject
from apps.notifications.services import send_notification

from .projects import get_project_or_error


@extend_schema(tags=['FPO - DPR Projects'])
class DPRProjectFinishView(APIView):
    """POST /projects/<uuid>/finish/ — flip IN_PROGRESS → SUBMITTED."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Mark the DPR as submitted (Finish click)",
        description=(
            "Transitions the project from IN_PROGRESS to SUBMITTED, stamps "
            "`submitted_at`, and fires notifications:\n\n"
            "- FPO primary user: `dpr_submitted_fpo` (email + in-app)\n"
            "- Every active super_admin / sub_admin: `dpr_submitted_admin` (in-app only)\n\n"
            "Idempotent for SUBMITTED / GENERATED (no-op returns 200). "
            "Rejects DRAFT (nothing to submit → 400)."
        ),
        request=None,
        responses={200: dict, 400: dict, 404: dict},
    )
    def post(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err

        if project.status == DPRProject.Status.DRAFT:
            return StandardResponse.error(
                'DPR is still in draft — save at least one section before '
                'clicking Finish.',
                status_code=400,
            )

        # Idempotent: already-submitted or generated projects need no work.
        if project.status in (DPRProject.Status.SUBMITTED,
                              DPRProject.Status.GENERATED):
            return StandardResponse.success({
                'uuid': str(project.uuid),
                'status': project.status,
                'submitted_at': project.submitted_at.isoformat() if project.submitted_at else None,
            }, 'DPR is already submitted.')

        # Transition — one row, one save. `submitted_at` is stamped even
        # on re-submits so admin dashboards show the LATEST finish click.
        now = timezone.now()
        with transaction.atomic():
            project.status = DPRProject.Status.SUBMITTED
            project.submitted_at = now
            project.save(update_fields=['status', 'submitted_at', 'updated_at'])

        # ── Audit ────────────────────────────────────────────────────────
        AuditService.log(
            user=request.user,
            action=AuditLog.Action.DPR_SUBMITTED,
            instance=project,
            request=request,
            changes={
                'from_status': DPRProject.Status.IN_PROGRESS,
                'to_status': DPRProject.Status.SUBMITTED,
                'project_uuid': str(project.uuid),
                'project_title': project.title,
            },
        )

        # ── Notify the FPO primary user (email + in-app) ────────────────
        fpo = project.fpo
        primary_user = getattr(fpo, 'primary_user', None)
        context = {
            'user_name':     (primary_user.first_name if primary_user else '')
                             or fpo.name,
            'fpo_name':      fpo.name,
            'project_title': project.title or 'Untitled DPR',
            'submitted_at':  now.strftime('%d %b %Y, %I:%M %p'),
        }
        if primary_user and primary_user.email:
            for channel in ('email', 'in_app'):
                try:
                    send_notification(
                        user=primary_user,
                        code='dpr_submitted_fpo',
                        channel=channel,
                        context=context,
                    )
                except Exception:
                    # Notification failure never blocks the transition —
                    # the state change is the source of truth.
                    pass

        # ── Notify every active super_admin + sub_admin (in-app only) ────
        admin_context = {
            **context,
            'fpo_district': fpo.district or '—',
        }
        admin_users = User.objects.filter(
            is_active=True,
            groups__name__in=[UserRole.SUPER_ADMIN, UserRole.SUB_ADMIN],
        ).distinct()
        for admin in admin_users:
            try:
                send_notification(
                    user=admin,
                    code='dpr_submitted_admin',
                    channel='in_app',
                    context=admin_context,
                )
            except Exception:
                pass

        return StandardResponse.success({
            'uuid': str(project.uuid),
            'status': project.status,
            'submitted_at': now.isoformat(),
        }, 'DPR submitted. You can now generate the PDF from Manage DPRs.')
