"""
Admin Ownership Claims API
===========================
GET  /api/admin/ownership-claims/                         — list all claims (filter: status, fpo_id)
GET  /api/admin/ownership-claims/{id}/                    — claim detail
POST /api/admin/ownership-claims/{id}/approve/            — approve → transfer FPO ownership
POST /api/admin/ownership-claims/{id}/reject/             — reject with reason
POST /api/admin/ownership-claims/{id}/request-documents/  — request additional docs from claimant

Approve flow:
- Old FPO: status → CLAIMED (all data + application_id preserved for audit)
- New FPO record created for claimant (status=DRAFT, current_step=0 — forces step 1 on first login only)
- Claimant gets fpo_manager + primary groups + FPOUserMembership on NEW FPO
- Old primary user deactivated (groups removed, account disabled)
- All secondary users of old FPO deactivated
- All other pending claims on same FPO are auto-rejected
"""

from re import search
from django.db.models import Q
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
from apps.database.models.fpo import FPO, FPODocument, FPOOwnershipClaim, FPOUserMembership, ClaimStatus, ApplicationStatusHistory
from apps.notifications.services import send_notification

User = get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
# Serializers
# ─────────────────────────────────────────────────────────────────────────────

class _ClaimListSerializer(serializers.ModelSerializer):
    fpo_name       = serializers.CharField(source='fpo.name', read_only=True)
    fpo_id         = serializers.IntegerField(source='fpo.id', read_only=True)
    claimant_name  = serializers.SerializerMethodField()
    claimant_email = serializers.CharField(source='claimant.email', read_only=True)
    claimant_phone = serializers.SerializerMethodField()
    supporting_docs = serializers.SerializerMethodField()

    class Meta:
        model  = FPOOwnershipClaim
        fields = [
            'id', 'fpo_id', 'fpo_name',
            'claimant_name', 'claimant_email', 'claimant_phone',
            'reason', 'supporting_docs',
            'status', 'reviewed_at', 'review_notes',
            'created_at',
        ]

    def get_claimant_name(self, obj):
        return f"{obj.claimant.first_name} {obj.claimant.last_name}".strip() or obj.claimant.username

    def get_claimant_phone(self, obj):
        profile = getattr(obj.claimant, 'profile', None)
        return profile.phone if profile else None

    def get_supporting_docs(self, obj):
        if not obj.supporting_doc_ids:
            return []
        docs = FPODocument.objects.filter(
            id__in=obj.supporting_doc_ids,
            is_deleted=False,
        ).only('id', 'document_type', 'file', 'created_at')
        request = self.context.get('request')
        result = []
        for doc in docs:
            file_url = doc.file.url if doc.file else None
            if file_url and request:
                file_url = request.build_absolute_uri(file_url)
            result.append({
                'id':            str(doc.id),
                'document_type': doc.document_type,
                'file_url':      file_url,
                'uploaded_at':   doc.created_at,
            })
        return result


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
            OpenApiParameter('search', str, description='Search by FPO name, claimant first name, last name, email, phone number'),
            OpenApiParameter('status',  str, description='Filter: pending / approved / rejected'),
            OpenApiParameter('fpo_id',  int, description='Filter by FPO ID'),
        ],
        responses={200: _ClaimListSerializer(many=True)},
    )
    def get(self, request):
        if not _can_manage(request.user):
            return StandardResponse.error(
                'Permission denied.',
                status_code=status.HTTP_403_FORBIDDEN
            )

        qs = (
            FPOOwnershipClaim.objects.select_related(
        'fpo',
        'claimant',
        'claimant__profile',
        'reviewed_by',
        )
            .order_by('-created_at')
        )

        search = request.query_params.get('search', '').strip()
        print("SEARCH =", repr(search))
        if search:
            qs = qs.filter(
                Q(fpo__name__icontains=search) |
                Q(claimant__first_name__icontains=search) |
                Q(claimant__last_name__icontains=search) |
                Q(claimant__email__icontains=search) |
                Q(claimant__profile__phone__icontains=search)
                )


        status_filter = request.query_params.get('status', '').strip()
        if status_filter:
            qs = qs.filter(status=status_filter)

        fpo_id = request.query_params.get('fpo_id', '').strip()
        if fpo_id:
            qs = qs.filter(fpo_id=fpo_id)


        ORDERING_FIELD_MAP = {
            'created_at':      'created_at',
            '-created_at':     '-created_at',

            'status':          'status',
            '-status':         '-status',

            'fpo_name':        'fpo__name',
            '-fpo_name':       '-fpo__name',

            'claimant_name':   'claimant__first_name',
            '-claimant_name':  '-claimant__first_name',

            'claimant_email':  'claimant__email',
            '-claimant_email': '-claimant__email',
        }

        ordering_param = request.query_params.get('ordering', '-created_at').strip()
        ordering = ORDERING_FIELD_MAP.get(ordering_param, '-created_at')  # translates here

        qs = qs.order_by(ordering)  # always gets the real ORM path, never the raw client string
        


        print("COUNT =", qs.count())
        paginator  = StandardPagination()
        page       = paginator.paginate_queryset(qs, request)
        serializer = _ClaimListSerializer(page, many=True, context={'request': request})
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

        return StandardResponse.success(
            _ClaimListSerializer(claim, context={'request': request}).data,
            'Claim retrieved.',
        )


class OwnershipClaimApproveView(APIView):

    @extend_schema(
        tags=['Admin - Ownership Claims'],
        summary='Approve ownership claim → transfer FPO to claimant',
        description=(
            'Approves the claim and transfers FPO ownership to the claimant:\n\n'
            '1. Sets claim status = approved\n'
            '2. Old FPO status → **CLAIMED** (all data + application_id preserved)\n'
            '3. Creates a **new FPO record** for the claimant (status=DRAFT, step=1)\n'
            '4. Assigns `fpo_manager` + `primary` groups to claimant on new FPO\n'
            '5. **Deactivates old primary user** account + removes their groups\n'
            '6. **Deactivates ALL secondary users** of the old FPO\n'
            '7. Auto-rejects all other pending claims on the same FPO\n'
            '8. Sends `claim_ownership_revoked` email + in-app to old primary and secondaries\n'
            '9. Sends `claim_approved` email + in-app to the claimant\n\n'
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

        if claim.status not in (ClaimStatus.PENDING, ClaimStatus.DOCS_SUBMITTED):
            return StandardResponse.error(
                f'Cannot approve a claim with status: {claim.status}.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        ser = _ReviewSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

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
                    f'Claimant is already the primary owner of another active FPO '
                    f'({existing_fpo.name or existing_fpo.id}). Transfer cannot proceed.',
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

        with transaction.atomic():
            old_primary = fpo.primary_user
            old_fpo_status = fpo.status

            # Collect secondary users before deactivating (for notifications)
            secondary_memberships = list(
                FPOUserMembership.objects.filter(fpo=fpo, is_active=True)
                .exclude(user=old_primary)
                .select_related('user', 'user__profile')
            )

            fpo_manager_group = Group.objects.get(name=UserRole.FPO_MANAGER)
            primary_group     = Group.objects.get(name='primary')

            # ── Mark old FPO as CLAIMED — preserves all data + application_id ──
            fpo.status = FPOStatus.CLAIMED
            fpo.save(update_fields=['status'])

            ApplicationStatusHistory.objects.create(
                fpo         = fpo,
                from_status = old_fpo_status,
                to_status   = FPOStatus.CLAIMED,
                changed_by  = request.user,
                notes       = f'Ownership transferred to claimant (claim #{claim_id})',
            )

            # ── Deactivate old primary ─────────────────────────────────────────
            if old_primary and old_primary != claimant:
                old_primary.is_active = False
                old_primary.save(update_fields=['is_active'])
                old_primary.groups.remove(fpo_manager_group, primary_group)
                FPOUserMembership.objects.filter(fpo=fpo, user=old_primary).update(is_active=False)

                AuditService.log(
                    user=request.user,
                    action=AuditLog.Action.UPDATE,
                    instance=old_primary,
                    request=request,
                    changes={
                        'action':   'account_deactivated',
                        'reason':   'ownership_transfer',
                        'claim_id': claim_id,
                        'fpo_id':   fpo.id,
                        'fpo_name': fpo.name or f'FPO #{fpo.id}',
                    },
                )

            # ── Deactivate ALL secondary users of old FPO ─────────────────────
            for membership in secondary_memberships:
                membership.is_active      = False
                membership.user.is_active = False
                membership.user.save(update_fields=['is_active'])
                AuditService.log(
                    user=request.user,
                    action=AuditLog.Action.UPDATE,
                    instance=membership.user,
                    request=request,
                    changes={
                        'action':   'account_deactivated',
                        'reason':   'ownership_transfer',
                        'claim_id': claim_id,
                        'fpo_id':   fpo.id,
                    },
                )
            if secondary_memberships:
                FPOUserMembership.objects.filter(
                    id__in=[m.id for m in secondary_memberships]
                ).update(is_active=False)

            # ── Create new FPO record for claimant — copy all data from old FPO ─
            # All 4 wizard steps pre-filled so claimant just verifies, not re-enters.
            # email_verified/phone_verified reset — claimant must verify their own contacts.
            new_fpo = FPO.objects.create(
                primary_user             = claimant,
                status                   = FPOStatus.DRAFT,
                current_step             = 0,
                # Step 1
                name                     = fpo.name or '',
                name_ml                  = fpo.name_ml or '',
                legal_structure          = fpo.legal_structure or '',
                legal_structure_detail   = fpo.legal_structure_detail or '',
                registration_number      = fpo.registration_number or '',
                cin_number               = fpo.cin_number or '',
                date_of_registration     = fpo.date_of_registration,
                pan_number               = fpo.pan_number or '',
                gst_number               = fpo.gst_number or '',
                # Step 2
                district                 = fpo.district or '',
                block_taluk              = fpo.block_taluk or '',
                village_town             = fpo.village_town or '',
                address_line1            = fpo.address_line1 or '',
                address_line2            = fpo.address_line2 or '',
                pincode                  = fpo.pincode or '',
                office_phone             = fpo.office_phone or '',
                office_email             = fpo.office_email or '',
                website                  = fpo.website or '',
                email_verified           = False,
                phone_verified           = False,
                latitude                 = fpo.latitude,
                longitude                = fpo.longitude,
                # Step 3
                signatory_name           = fpo.signatory_name or '',
                signatory_designation    = fpo.signatory_designation or '',
                signatory_phone          = fpo.signatory_phone or '',
                signatory_email          = fpo.signatory_email or '',
                signatory_aadhaar_last4  = fpo.signatory_aadhaar_last4 or '',
                total_members            = fpo.total_members,
                male_members             = fpo.male_members,
                female_members           = fpo.female_members,
                sc_st_members            = fpo.sc_st_members,
                promoting_agency         = fpo.promoting_agency or '',
                facilitating_agency_name = fpo.facilitating_agency_name or '',
                ceo_available            = fpo.ceo_available,
                accountant_available     = fpo.accountant_available,
                total_directors          = fpo.total_directors,
                women_directors          = fpo.women_directors,
                directors_under_35       = fpo.directors_under_35,
                # Step 4
                primary_commodities      = fpo.primary_commodities or [],
                secondary_commodities    = fpo.secondary_commodities or [],
                annual_turnover          = fpo.annual_turnover,
                bank_name                = fpo.bank_name or '',
                bank_branch              = fpo.bank_branch or '',
                account_number           = fpo.account_number or '',
                ifsc_code                = fpo.ifsc_code or '',
                description              = fpo.description or '',
            )
            new_fpo.claimed_from_fpo = fpo
            new_fpo.origin_claim_id  = claim.id
            new_fpo.save(update_fields=['claimed_from_fpo', 'origin_claim_id'])

            ApplicationStatusHistory.objects.create(
                fpo         = new_fpo,
                from_status = '',
                to_status   = FPOStatus.DRAFT,
                changed_by  = request.user,
                notes       = f'New FPO created on ownership claim approval (claim #{claim_id}, old FPO #{fpo.id})',
            )

            # ── Assign groups + membership to claimant on new FPO ────────────
            claimant.groups.add(fpo_manager_group, primary_group)
            claimant.is_active = True
            claimant.save(update_fields=['is_active'])

            FPOUserMembership.objects.get_or_create(
                fpo=new_fpo,
                user=claimant,
                defaults={
                    'role':       primary_group,
                    'is_active':  True,
                    'created_by': request.user,
                },
            )

            # ── Approve this claim ────────────────────────────────────────────
            claim.status       = ClaimStatus.APPROVED
            claim.reviewed_by  = request.user
            claim.reviewed_at  = timezone.now()
            claim.review_notes = ser.validated_data['notes']
            claim.save()

            # ── Auto-reject all other pending claims on same FPO ──────────────
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
                    context={
                        'user_name': claimant_name,
                        'fpo_name':  fpo_name,
                        'new_fpo_id': new_fpo.id,
                    },
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
                'old_primary': old_primary.email if old_primary else None,
                'new_primary': claimant.email,
                'old_fpo_id':  fpo.id,
                'old_fpo_status_set_to': 'CLAIMED',
                'new_fpo_id':  new_fpo.id,
                'notes':       ser.validated_data['notes'],
            },
        )

        return StandardResponse.success(
            data={
                'old_fpo_id': fpo.id,
                'new_fpo_id': new_fpo.id,
                'new_primary': claimant.email,
            },
            message=f'Claim approved. New FPO #{new_fpo.id} created for {claimant.get_full_name() or claimant.email}.',
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

        if claim.status not in (ClaimStatus.PENDING, ClaimStatus.DOCS_REQUESTED, ClaimStatus.DOCS_SUBMITTED):
            return StandardResponse.error(
                f'Cannot reject a claim with status: {claim.status}.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        ser = _ReviewSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

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


class OwnershipClaimRequestDocsView(APIView):

    @extend_schema(
        tags=['Admin - Ownership Claims'],
        summary='Request additional documents from claimant',
        description=(
            'Sets claim status to `docs_requested` and sends email + SMS + in-app '
            'notification to the claimant describing what documents are needed. '
            'Can be called on a `pending` or `docs_requested` claim.'
        ),
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

        if claim.status in (ClaimStatus.APPROVED, ClaimStatus.REJECTED):
            return StandardResponse.error(
                f'Cannot request documents on a {claim.status} claim.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        ser = _ReviewSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        claimant = claim.claimant
        fpo      = claim.fpo
        message  = ser.validated_data['notes']

        claim.status       = ClaimStatus.DOCS_REQUESTED
        claim.reviewed_by  = request.user
        claim.reviewed_at  = timezone.now()
        claim.review_notes = message
        claim.save()

        AuditService.log(
            user=request.user,
            action=AuditLog.Action.UPDATE,
            instance=fpo,
            request=request,
            changes={
                'claim_id': claim_id,
                'action':   'docs_requested',
                'message':  message,
            },
        )

        fpo_name      = fpo.name or f'FPO #{fpo.id}'
        claimant_name = claimant.get_full_name() or claimant.username
        for channel in ('email', 'sms', 'in_app'):
            try:
                send_notification(
                    user=claimant,
                    code='claim_docs_requested',
                    channel=channel,
                    context={
                        'user_name':  claimant_name,
                        'fpo_name':   fpo_name,
                        'admin_message': message,
                    },
                )
            except Exception:
                pass

        return StandardResponse.success(
            data=None,
            message='Document request sent to claimant.',
        )
