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

import magic

from django.contrib.auth import get_user_model
from django.utils import timezone

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.views import APIView

from apps.core.models.generic import AuditLog
from apps.core.permissions.rbac import IsFPOManager
from apps.core.services.audit import AuditService
from apps.core.utils.constants import DocumentType, UserRole
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
            'status', 'review_notes', 'reviewed_at',
            'created_at',
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
        ser.is_valid(raise_exception=True)

        fpo_id             = ser.validated_data['fpo_id']
        reason             = ser.validated_data['reason']
        supporting_doc_ids = ser.validated_data.get('supporting_doc_ids', [])

        # Validate FPO exists and is claimable
        try:
            fpo = FPO.objects.get(id=fpo_id, is_deleted=False)
        except FPO.DoesNotExist:
            return StandardResponse.error('FPO not found.', status_code=status.HTTP_404_NOT_FOUND)

        if fpo.status == 'claimed':
            return StandardResponse.error(
                'This FPO has already been transferred to its legitimate owner and cannot be claimed.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Block if claimant is already the primary user
        if fpo.primary_user == request.user:
            return StandardResponse.error(
                'You are already the primary user of this FPO.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Block if user already has a pending claim on ANY FPO
        existing_pending = FPOOwnershipClaim.objects.filter(
            claimant=request.user, status=ClaimStatus.PENDING
        ).select_related('fpo').first()
        if existing_pending:
            return StandardResponse.error(
                f'You already have a pending claim on '
                f'"{existing_pending.fpo.name or f"FPO #{existing_pending.fpo.id}"}". '
                f'Please wait for admin review before submitting another claim.',
                status_code=status.HTTP_409_CONFLICT,
            )

        # Max 3 attempts per user per FPO (including rejected claims)
        attempt_count = FPOOwnershipClaim.objects.filter(
            fpo=fpo, claimant=request.user
        ).count()
        if attempt_count >= 3:
            return StandardResponse.error(
                'You have reached the maximum number of claim attempts (3) for this FPO.',
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
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


class FPOClaimRespondView(APIView):
    """
    POST /api/fpo/claim/{claim_id}/respond/

    Claimant uploads supporting documents in response to a docs_requested claim.
    Status transitions: docs_requested → docs_submitted.
    Admin is notified in their inbox.
    """
    permission_classes = [IsFPOManager]

    @extend_schema(
        tags=['FPO - Registration'],
        summary='Respond to a document request on an ownership claim',
        description=(
            'Called after admin sets claim to `docs_requested`. '
            'Claimant submits uploaded document IDs. '
            'Status changes to `docs_submitted` and admin is notified.'
        ),
    )
    def post(self, request, claim_id):
        try:
            claim = FPOOwnershipClaim.objects.select_related('fpo').get(
                id=claim_id,
                claimant=request.user,
                status=ClaimStatus.DOCS_REQUESTED,
            )
        except FPOOwnershipClaim.DoesNotExist:
            return StandardResponse.error(
                'Claim not found or not awaiting documents.',
                status_code=status.HTTP_404_NOT_FOUND,
            )

        supporting_doc_ids = request.data.get('supporting_doc_ids', [])
        if not supporting_doc_ids:
            return StandardResponse.error(
                'Please upload at least one supporting document.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Filter by created_by + claim_support type — works regardless of which FPO the doc is on
        valid_docs = FPODocument.objects.filter(
            document_type=DocumentType.CLAIM_SUPPORT,
            id__in=supporting_doc_ids,
            is_deleted=False,
            created_by=request.user,
        ).values_list('id', flat=True)
        valid_doc_ids = [str(d) for d in valid_docs]

        if not valid_doc_ids:
            return StandardResponse.error(
                'No valid documents found. Please upload your documents first.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        existing = claim.supporting_doc_ids or []
        claim.supporting_doc_ids = list(set(existing + valid_doc_ids))
        claim.status = ClaimStatus.DOCS_SUBMITTED
        claim.save(update_fields=['supporting_doc_ids', 'status'])

        AuditService.log(
            user=request.user,
            action=AuditLog.Action.UPDATE,
            instance=claim,
            request=request,
            changes={'docs_submitted': len(valid_doc_ids), 'status': ClaimStatus.DOCS_SUBMITTED},
        )

        user_name = request.user.get_full_name() or request.user.username
        fpo_name  = claim.fpo.name or f'FPO #{claim.fpo.id}'

        admin_users = User.objects.filter(groups__name=UserRole.SUPER_ADMIN, is_active=True)
        for admin in admin_users:
            try:
                send_notification(
                    user=admin,
                    code='claim_new_admin',
                    channel='in_app',
                    context={'fpo_name': fpo_name, 'claimant_name': user_name},
                )
            except Exception:
                pass

        return StandardResponse.success(
            data=ClaimResponseSerializer(claim).data,
            message='Documents submitted. KAU Admin has been notified and will review your claim shortly.',
        )


class FPOClaimDocumentUploadView(APIView):
    """
    POST /api/fpo/claim/{claim_id}/documents/

    Upload a supporting document for an ownership claim.
    Unlike the main document upload API, this does NOT require FPO to be in DRAFT status.
    Accepts: PDF, JPG, PNG — max 5 MB.
    Stores as document_type='signatory_id' on the claimant's FPO (or creates a standalone record).
    Returns the document ID to use in respond/.
    """
    permission_classes = [IsFPOManager]
    parser_classes     = [MultiPartParser, FormParser]

    @extend_schema(
        tags=['FPO - Registration'],
        summary='Upload a supporting document for an ownership claim',
        description='Upload evidence to support your ownership claim. No FPO status restriction.',
    )
    def post(self, request, claim_id):
        try:
            claim = FPOOwnershipClaim.objects.select_related('fpo').get(
                id=claim_id,
                claimant=request.user,
                status=ClaimStatus.DOCS_REQUESTED,
            )
        except FPOOwnershipClaim.DoesNotExist:
            return StandardResponse.error(
                'Claim not found or not awaiting documents.',
                status_code=status.HTTP_404_NOT_FOUND,
            )

        file = request.FILES.get('file')
        if not file:
            return StandardResponse.error(
                'No file provided.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        max_size = 5 * 1024 * 1024  # 5 MB
        if file.size > max_size:
            return StandardResponse.error(
                'File too large. Maximum allowed size is 5 MB.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        mime_type = magic.from_buffer(file.read(2048), mime=True)
        file.seek(0)
        if mime_type not in {'application/pdf', 'image/jpeg', 'image/png'}:
            return StandardResponse.error(
                'Invalid file format. Only PDF, JPG, and PNG are allowed.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Use the claimant's FPO if they have one; otherwise use the claimed FPO
        user_fpo = getattr(request.user, 'fpo', None) or claim.fpo

        # No soft-delete of previous docs — claims can have multiple supporting files
        doc = FPODocument.objects.create(
            fpo           = user_fpo,
            document_type = DocumentType.CLAIM_SUPPORT,
            file          = file,
            file_size     = file.size,
            mime_type     = mime_type,
            created_by    = request.user,
            updated_by    = request.user,
        )

        AuditService.log(
            user=request.user,
            action=AuditLog.Action.DOCUMENT_UPLOAD,
            instance=doc,
            request=request,
            changes={'claim_id': claim_id, 'file_size': file.size, 'mime_type': mime_type},
        )

        return StandardResponse.success(
            data={'id': str(doc.id), 'file_size': doc.file_size, 'mime_type': mime_type},
            message='Document uploaded successfully.',
            status_code=status.HTTP_201_CREATED,
        )


class FPOClaimDocumentDeleteView(APIView):
    """
    DELETE /api/fpo/claim/{claim_id}/documents/{doc_id}/

    Remove an uploaded supporting document from a docs_requested claim.
    Only works while claim is in docs_requested state.
    """
    permission_classes = [IsFPOManager]

    @extend_schema(
        tags=['FPO - Registration'],
        summary='Delete a supporting document from an ownership claim',
    )
    def delete(self, request, claim_id, doc_id):
        try:
            claim = FPOOwnershipClaim.objects.get(
                id=claim_id,
                claimant=request.user,
                status=ClaimStatus.DOCS_REQUESTED,
            )
        except FPOOwnershipClaim.DoesNotExist:
            return StandardResponse.error(
                'Claim not found or not awaiting documents.',
                status_code=status.HTTP_404_NOT_FOUND,
            )

        user_fpo = getattr(request.user, 'fpo', None) or claim.fpo

        try:
            doc = FPODocument.objects.get(
                id=doc_id,
                fpo=user_fpo,
                document_type=DocumentType.CLAIM_SUPPORT,
                is_deleted=False,
                created_by=request.user,
            )
        except FPODocument.DoesNotExist:
            return StandardResponse.error(
                'Document not found.',
                status_code=status.HTTP_404_NOT_FOUND,
            )

        doc.is_deleted = True
        doc.save(update_fields=['is_deleted'])

        return StandardResponse.success(message='Document removed.')
