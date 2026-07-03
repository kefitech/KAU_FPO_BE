"""
FPO Ownership Claim API
========================
POST /api/fpo/claim/    — FPO user submits a claim on a duplicate FPO

Flow:
1. Duplicate detected on registration → frontend shows "Claim Your Business" button
2. FPO user submits claim with reason + optional supporting doc IDs
3. KAU Admin reviews → approve (transfers ownership) or reject

Rules:
- Claimant must be an authenticated FPO manager
- Only one pending claim per user per FPO
- Supporting doc IDs must belong to the claimant's own uploaded documents
"""

from django.contrib.auth import get_user_model
from django.utils import timezone

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.views import APIView

from apps.core.models.generic import AuditLog
from apps.core.permissions.rbac import IsFPOManager
from apps.core.services.audit import AuditService
from apps.core.utils.constants import UserRole
from apps.core.utils.responses import StandardResponse
from apps.database.models.fpo import FPO, FPODocument, FPOOwnershipClaim, ClaimStatus
from apps.notifications.services import send_notification

User = get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
# Serializers
# ─────────────────────────────────────────────────────────────────────────────

class ClaimSerializer(serializers.Serializer):
    fpo_id             = serializers.IntegerField(help_text='ID of the FPO being claimed')
    reason             = serializers.CharField(
        min_length=20,
        help_text='Explain why you are the legitimate owner of this FPO (min 20 chars)',
    )
    supporting_doc_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
        help_text='List of your uploaded FPODocument UUIDs as supporting evidence',
    )


class ClaimResponseSerializer(serializers.ModelSerializer):
    fpo_name   = serializers.CharField(source='fpo.name', read_only=True)
    fpo_id     = serializers.IntegerField(source='fpo.id', read_only=True)

    class Meta:
        model  = FPOOwnershipClaim
        fields = [
            'id', 'fpo_id', 'fpo_name',
            'reason', 'supporting_doc_ids',
            'status', 'created_at',
        ]


# ─────────────────────────────────────────────────────────────────────────────
# View
# ─────────────────────────────────────────────────────────────────────────────

class FPOClaimView(APIView):
    permission_classes = [IsFPOManager]

    @extend_schema(
        tags=['FPO - Registration'],
        summary='Submit ownership claim on a duplicate FPO',
        description=(
            'Triggered after duplicate detection on registration.\n\n'
            'If `POST /api/fpo/register/` returns `duplicate_detected: true`, '
            'the frontend shows a "Claim Your Business" button. '
            'The user submits this endpoint with their reason and optional supporting documents.\n\n'
            'KAU Admin then reviews and approves or rejects the claim.\n\n'
            '**Only one pending claim per user per FPO is allowed.**'
        ),
        request=ClaimSerializer,
        responses={201: ClaimResponseSerializer},
    )
    def post(self, request):
        ser = ClaimSerializer(data=request.data)
        if not ser.is_valid():
            return StandardResponse.error(str(ser.errors), status_code=status.HTTP_400_BAD_REQUEST)

        fpo_id             = ser.validated_data['fpo_id']
        reason             = ser.validated_data['reason']
        supporting_doc_ids = ser.validated_data.get('supporting_doc_ids', [])

        # Validate FPO exists
        try:
            fpo = FPO.objects.get(id=fpo_id, is_deleted=False)
        except FPO.DoesNotExist:
            return StandardResponse.error('FPO not found.', status_code=status.HTTP_404_NOT_FOUND)

        # Block if claimant is already the primary user
        if fpo.primary_user == request.user:
            return StandardResponse.error(
                'You are already the primary user of this FPO.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # One pending claim per user per FPO
        if FPOOwnershipClaim.objects.filter(
            fpo=fpo, claimant=request.user, status=ClaimStatus.PENDING
        ).exists():
            return StandardResponse.error(
                'You already have a pending claim on this FPO. Please wait for admin review.',
                status_code=status.HTTP_409_CONFLICT,
            )

        # Validate supporting doc IDs belong to this user
        valid_doc_ids = []
        if supporting_doc_ids:
            user_fpo = getattr(request.user, 'fpo', None)
            if user_fpo:
                valid_docs = FPODocument.objects.filter(
                    fpo=user_fpo,
                    id__in=[str(d) for d in supporting_doc_ids],
                    is_deleted=False,
                ).values_list('id', flat=True)
                valid_doc_ids = [str(d) for d in valid_docs]

        claim = FPOOwnershipClaim.objects.create(
            fpo                = fpo,
            claimant           = request.user,
            reason             = reason,
            supporting_doc_ids = valid_doc_ids,
            status             = ClaimStatus.PENDING,
        )

        AuditService.log(
            user=request.user,
            action=AuditLog.Action.CREATE,
            instance=claim,
            request=request,
            changes={'fpo_id': fpo_id, 'reason': reason[:100]},
        )

        user_name = request.user.get_full_name() or request.user.username
        fpo_name  = fpo.name or f'FPO #{fpo.id}'

        # Notify claimant that claim is received
        for channel in ('email', 'in_app'):
            try:
                send_notification(
                    user=request.user,
                    code='claim_submitted',
                    channel=channel,
                    context={'user_name': user_name, 'fpo_name': fpo_name},
                )
            except Exception:
                pass

        # Notify all super admins in their inbox
        admin_users = User.objects.filter(
            groups__name=UserRole.SUPER_ADMIN,
            is_active=True,
        )
        for admin in admin_users:
            try:
                send_notification(
                    user=admin,
                    code='claim_new_admin',
                    channel='in_app',
                    context={
                        'fpo_name':      fpo_name,
                        'claimant_name': user_name,
                    },
                )
            except Exception:
                pass

        return StandardResponse.created(
            data=ClaimResponseSerializer(claim).data,
            message='Your claim has been submitted. KAU Admin will review it shortly.',
        )

    @extend_schema(
        tags=['FPO - Registration'],
        summary='Get my ownership claims',
        description='Returns all ownership claims submitted by the current user.',
        responses={200: ClaimResponseSerializer(many=True)},
    )
    def get(self, request):
        claims = FPOOwnershipClaim.objects.filter(
            claimant=request.user
        ).select_related('fpo').order_by('-created_at')

        return StandardResponse.success(
            ClaimResponseSerializer(claims, many=True).data,
            'Claims retrieved.',
        )
