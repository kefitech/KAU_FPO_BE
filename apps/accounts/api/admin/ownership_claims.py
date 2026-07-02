"""
Admin Ownership Claims API
===========================
GET  /api/admin/ownership-claims/           — list all claims (filter: status, fpo_id)
GET  /api/admin/ownership-claims/{id}/      — claim detail
POST /api/admin/ownership-claims/{id}/approve/  — approve → transfer FPO ownership
POST /api/admin/ownership-claims/{id}/reject/   — reject with reason

Approve flow:
- Sets claim status = approved
- Transfers FPO.primary_user to claimant
- Old primary user's FPOUserMembership (if any) is deactivated
- New primary user gets fpo_manager + primary groups
- All other pending claims on same FPO are auto-rejected
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from django.utils import timezone

from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import serializers, status
from rest_framework.views import APIView

from apps.core.models.generic import AuditLog
from apps.core.services.audit import AuditService
from apps.core.utils.constants import UserRole, FPOStatus
from apps.core.utils.pagination import StandardPagination
from apps.core.utils.responses import StandardResponse
from apps.database.models.fpo import FPO, FPOOwnershipClaim, FPOUserMembership, ClaimStatus
from apps.notifications.services import send_notification

User = get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
# Serializers
# ─────────────────────────────────────────────────────────────────────────────

class _ClaimListSerializer(serializers.ModelSerializer):
    fpo_name      = serializers.CharField(source='fpo.name', read_only=True)
    fpo_id        = serializers.IntegerField(source='fpo.id', read_only=True)
    claimant_name = serializers.SerializerMethodField()
    claimant_email = serializers.CharField(source='claimant.email', read_only=True)
    claimant_phone = serializers.SerializerMethodField()

    class Meta:
        model  = FPOOwnershipClaim
        fields = [
            'id', 'fpo_id', 'fpo_name',
            'claimant_name', 'claimant_email', 'claimant_phone',
            'reason', 'supporting_doc_ids',
            'status', 'reviewed_at', 'review_notes',
            'created_at',
        ]

    def get_claimant_name(self, obj):
        return f"{obj.claimant.first_name} {obj.claimant.last_name}".strip() or obj.claimant.username

    def get_claimant_phone(self, obj):
        profile = getattr(obj.claimant, 'profile', None)
        return profile.phone if profile else None


class _ReviewSerializer(serializers.Serializer):
    notes = serializers.CharField(
        min_length=10,
        help_text='Reason for approval or rejection (min 10 chars)',
    )


# ─────────────────────────────────────────────────────────────────────────────
# Permission helper
# ─────────────────────────────────────────────────────────────────────────────

def _can_manage(user):
    return user.groups.filter(name__in=[UserRole.SUPER_ADMIN, UserRole.SUB_ADMIN]).exists()


# ─────────────────────────────────────────────────────────────────────────────
# Views
# ─────────────────────────────────────────────────────────────────────────────

class OwnershipClaimListView(APIView):

    @extend_schema(
        tags=['Admin - Ownership Claims'],
        summary='List all ownership claims',
        parameters=[
            OpenApiParameter('status',  str, description='Filter: pending / approved / rejected'),
            OpenApiParameter('fpo_id',  int, description='Filter by FPO ID'),
        ],
        responses={200: _ClaimListSerializer(many=True)},
    )
    def get(self, request):
        if not _can_manage(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        qs = FPOOwnershipClaim.objects.select_related(
            'fpo', 'claimant', 'claimant__profile', 'reviewed_by'
        ).order_by('-created_at')

        status_filter = request.query_params.get('status', '').strip()
        if status_filter:
            qs = qs.filter(status=status_filter)

        fpo_id = request.query_params.get('fpo_id', '').strip()
        if fpo_id:
            qs = qs.filter(fpo_id=fpo_id)

        paginator  = StandardPagination()
        page       = paginator.paginate_queryset(qs, request)
        serializer = _ClaimListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class OwnershipClaimDetailView(APIView):

    @extend_schema(
        tags=['Admin - Ownership Claims'],
        summary='Get ownership claim detail',
        responses={200: _ClaimListSerializer},
    )
    def get(self, request, claim_id):
        if not _can_manage(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        try:
            claim = FPOOwnershipClaim.objects.select_related(
                'fpo', 'claimant', 'claimant__profile', 'reviewed_by'
            ).get(id=claim_id)
        except FPOOwnershipClaim.DoesNotExist:
            return StandardResponse.error('Claim not found.', status_code=status.HTTP_404_NOT_FOUND)

        return StandardResponse.success(_ClaimListSerializer(claim).data, 'Claim retrieved.')


class OwnershipClaimApproveView(APIView):

    @extend_schema(
        tags=['Admin - Ownership Claims'],
        summary='Approve ownership claim → transfer FPO to claimant',
        description=(
            'Approves the claim and transfers FPO ownership to the claimant:\n\n'
            '1. Sets claim status = approved\n'
            '2. Transfers `FPO.primary_user` to claimant\n'
            '3. Assigns `fpo_manager` + `primary` groups to claimant\n'
            '4. **Deactivates old primary user** account + removes their groups\n'
            '5. **Deactivates ALL secondary users** of the FPO\n'
            '6. Auto-rejects all other pending claims on the same FPO\n'
            '7. Sends `claim_ownership_revoked` email + in-app to old primary and all secondaries\n'
            '8. Sends `claim_approved` email + in-app to the claimant\n\n'
            '**Only super admin can approve.**'
        ),
        request=_ReviewSerializer,
        responses={200: None},
    )
    def post(self, request, claim_id):
        if not request.user.groups.filter(name=UserRole.SUPER_ADMIN).exists():
            return StandardResponse.error(
                'Only super admin can approve ownership claims.',
                status_code=status.HTTP_403_FORBIDDEN,
            )

        try:
            claim = FPOOwnershipClaim.objects.select_related('fpo', 'claimant').get(id=claim_id)
        except FPOOwnershipClaim.DoesNotExist:
            return StandardResponse.error('Claim not found.', status_code=status.HTTP_404_NOT_FOUND)

        if claim.status != ClaimStatus.PENDING:
            return StandardResponse.error(
                f'Claim is already {claim.status}.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        ser = _ReviewSerializer(data=request.data)
        if not ser.is_valid():
            return StandardResponse.error(str(ser.errors), status_code=status.HTTP_400_BAD_REQUEST)

        fpo       = claim.fpo
        claimant  = claim.claimant

        # Guard: claimant must not already be primary_user of a different FPO
        existing_fpo = FPO.objects.filter(primary_user=claimant).exclude(id=fpo.id).first()
        if existing_fpo:
            if existing_fpo.status == FPOStatus.DRAFT:
                # Draft is incomplete — delete it so transfer can proceed
                existing_fpo.delete()
                try:
                    send_notification(
                        user=claimant,
                        code='claim_draft_removed',
                        channel='email',
                        context={
                            'user_name': claimant.get_full_name() or claimant.username,
                            'fpo_name':  fpo.name or f'FPO #{fpo.id}',
                        },
                    )
                    send_notification(
                        user=claimant,
                        code='claim_draft_removed',
                        channel='in_app',
                        context={
                            'user_name': claimant.get_full_name() or claimant.username,
                            'fpo_name':  fpo.name or f'FPO #{fpo.id}',
                        },
                    )
                except Exception:
                    pass
            else:
                return StandardResponse.error(
                    f'Claimant is already the primary owner of another active FPO ({existing_fpo.name or existing_fpo.id}). '
                    f'Transfer cannot proceed.',
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

        with transaction.atomic():
            # Collect secondary users before deactivating (for notifications)
            secondary_memberships = list(
                FPOUserMembership.objects.filter(fpo=fpo, is_active=True)
                .exclude(user=fpo.primary_user)
                .select_related('user', 'user__profile')
            )

            # Transfer FPO ownership
            old_primary = fpo.primary_user
            fpo.primary_user = claimant
            fpo.save(update_fields=['primary_user'])

            # Assign correct groups to new primary user
            fpo_manager_group = Group.objects.get(name=UserRole.FPO_MANAGER)
            primary_group     = Group.objects.get(name='primary')
            claimant.groups.add(fpo_manager_group, primary_group)

            # Deactivate old primary — revoke account + remove fpo_manager group
            if old_primary and old_primary != claimant:
                old_primary.is_active = False
                old_primary.save(update_fields=['is_active'])
                old_primary.groups.remove(fpo_manager_group, primary_group)
                FPOUserMembership.objects.filter(fpo=fpo, user=old_primary).update(is_active=False)

            # Deactivate ALL secondary users
            for membership in secondary_memberships:
                membership.is_active = False
                membership.user.is_active = False
                membership.user.save(update_fields=['is_active'])
            if secondary_memberships:
                FPOUserMembership.objects.filter(
                    id__in=[m.id for m in secondary_memberships]
                ).update(is_active=False)

            # Create membership record for new primary
            FPOUserMembership.objects.get_or_create(
                fpo=fpo,
                user=claimant,
                defaults={
                    'role': primary_group,
                    'is_active': True,
                    'created_by': request.user,
                },
            )

            # Approve this claim
            claim.status       = ClaimStatus.APPROVED
            claim.reviewed_by  = request.user
            claim.reviewed_at  = timezone.now()
            claim.review_notes = ser.validated_data['notes']
            claim.save()

            # Auto-reject all other pending claims on same FPO
            FPOOwnershipClaim.objects.filter(
                fpo=fpo,
                status=ClaimStatus.PENDING,
            ).exclude(id=claim_id).update(
                status       = ClaimStatus.REJECTED,
                reviewed_by  = request.user,
                reviewed_at  = timezone.now(),
                review_notes = 'Auto-rejected: another claim was approved for this FPO.',
            )

        # Send notifications (outside transaction — failures must not roll back ownership transfer)
        fpo_name = fpo.name or f'FPO #{fpo.id}'

        # Notify old primary
        if old_primary and old_primary != claimant:
            old_name = old_primary.get_full_name() or old_primary.username
            for channel in ('email', 'in_app'):
                try:
                    send_notification(
                        user=old_primary,
                        code='claim_ownership_revoked',
                        channel=channel,
                        context={'user_name': old_name, 'fpo_name': fpo_name},
                    )
                except Exception:
                    pass

        # Notify secondary users
        for membership in secondary_memberships:
            sec_user = membership.user
            sec_name = sec_user.get_full_name() or sec_user.username
            for channel in ('email', 'in_app'):
                try:
                    send_notification(
                        user=sec_user,
                        code='claim_ownership_revoked',
                        channel=channel,
                        context={'user_name': sec_name, 'fpo_name': fpo_name},
                    )
                except Exception:
                    pass

        # Notify claimant (new primary)
        claimant_name = claimant.get_full_name() or claimant.username
        for channel in ('email', 'in_app'):
            try:
                send_notification(
                    user=claimant,
                    code='claim_approved',
                    channel=channel,
                    context={'user_name': claimant_name, 'fpo_name': fpo_name},
                )
            except Exception:
                pass

        AuditService.log(
            user=request.user,
            action=AuditLog.Action.UPDATE,
            instance=fpo,
            request=request,
            changes={
                'claim_id':    claim_id,
                'action':      'ownership_transferred',
                'new_primary': claimant.email,
                'notes':       ser.validated_data['notes'],
            },
        )

        return StandardResponse.success(
            data={'fpo_id': fpo.id, 'new_primary': claimant.email},
            message=f'Claim approved. FPO ownership transferred to {claimant.get_full_name() or claimant.email}.',
        )


class OwnershipClaimRejectView(APIView):

    @extend_schema(
        tags=['Admin - Ownership Claims'],
        summary='Reject ownership claim',
        request=_ReviewSerializer,
        responses={200: None},
    )
    def post(self, request, claim_id):
        if not _can_manage(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        try:
            claim = FPOOwnershipClaim.objects.select_related('fpo', 'claimant').get(id=claim_id)
        except FPOOwnershipClaim.DoesNotExist:
            return StandardResponse.error('Claim not found.', status_code=status.HTTP_404_NOT_FOUND)

        if claim.status != ClaimStatus.PENDING:
            return StandardResponse.error(
                f'Claim is already {claim.status}.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        ser = _ReviewSerializer(data=request.data)
        if not ser.is_valid():
            return StandardResponse.error(str(ser.errors), status_code=status.HTTP_400_BAD_REQUEST)

        claimant = claim.claimant
        fpo      = claim.fpo
        notes    = ser.validated_data['notes']

        claim.status       = ClaimStatus.REJECTED
        claim.reviewed_by  = request.user
        claim.reviewed_at  = timezone.now()
        claim.review_notes = notes
        claim.save()

        AuditService.log(
            user=request.user,
            action=AuditLog.Action.UPDATE,
            instance=fpo,
            request=request,
            changes={
                'claim_id': claim_id,
                'action':   'claim_rejected',
                'notes':    notes,
            },
        )

        fpo_name      = fpo.name or f'FPO #{fpo.id}'
        claimant_name = claimant.get_full_name() or claimant.username
        for channel in ('email', 'in_app'):
            try:
                send_notification(
                    user=claimant,
                    code='claim_rejected',
                    channel=channel,
                    context={
                        'user_name':        claimant_name,
                        'fpo_name':         fpo_name,
                        'rejection_reason': notes,
                    },
                )
            except Exception:
                pass

        return StandardResponse.success(
            data=None,
            message='Claim rejected.',
        )
