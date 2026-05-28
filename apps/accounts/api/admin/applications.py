"""
Admin FPO Applications Workflow
=================================
KAU admin staff review, approve, reject, and manage FPO applications.

Endpoints:
    GET    /api/admin/applications/                                 — list with filters
    GET    /api/admin/applications/{id}/                            — full detail
    POST   /api/admin/applications/{id}/mark-under-review/
    POST   /api/admin/applications/{id}/approve/
    POST   /api/admin/applications/{id}/reject/                     — reason ≥ 20 chars (BR-103)
    POST   /api/admin/applications/{id}/request-info/
    POST   /api/admin/applications/{id}/verify-document/{doc_id}/
    PATCH  /api/admin/applications/{id}/set-user-limit/

Permissions:
    list / detail / verify-document  → super_admin OR sub_admin with can_view_all_fpos
    mark-under-review / approve / reject / request-info
                                     → super_admin OR sub_admin with can_approve_fpo
    set-user-limit                   → super_admin only
"""

from django.contrib.auth import get_user_model
from django.utils import timezone

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from rest_framework import serializers, status
from rest_framework.views import APIView

from apps.core.utils.constants import FPOStatus, UserRole
from apps.core.utils.pagination import StandardPagination
from apps.core.utils.responses import StandardResponse
from apps.core.services.translation import t
from apps.database.models.fpo import FPO, FPODocument, ApplicationStatusHistory

User = get_user_model()


# ──────────────────────────────────────────────────────────────────────────────
# Serializers
# ──────────────────────────────────────────────────────────────────────────────

class _DocumentSerializer(serializers.ModelSerializer):
    verified_by_name = serializers.SerializerMethodField()
    file_url         = serializers.SerializerMethodField()

    class Meta:
        model  = FPODocument
        fields = [
            'id', 'document_type', 'file_url', 'file_size', 'mime_type',
            'is_verified', 'verified_by_name', 'verified_at', 'created_at',
        ]

    def get_verified_by_name(self, obj):
        if obj.verified_by:
            return f"{obj.verified_by.first_name} {obj.verified_by.last_name}".strip() or obj.verified_by.username
        return None

    def get_file_url(self, obj):
        request = self.context.get('request')
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        return str(obj.file) if obj.file else None


class _StatusHistorySerializer(serializers.ModelSerializer):
    changed_by_name = serializers.SerializerMethodField()

    class Meta:
        model  = ApplicationStatusHistory
        fields = ['from_status', 'to_status', 'changed_by_name', 'notes', 'created_at']

    def get_changed_by_name(self, obj):
        if obj.changed_by:
            return f"{obj.changed_by.first_name} {obj.changed_by.last_name}".strip() or obj.changed_by.username
        return None


class _ApplicationListSerializer(serializers.ModelSerializer):
    primary_user_name  = serializers.SerializerMethodField()
    primary_user_email = serializers.SerializerMethodField()
    primary_user_phone = serializers.SerializerMethodField()

    class Meta:
        model  = FPO
        fields = [
            'id', 'application_id', 'name', 'name_ml', 'district',
            'status', 'tier', 'current_step',
            'email_verified', 'phone_verified',
            'primary_user_name', 'primary_user_email', 'primary_user_phone',
            'created_at', 'updated_at',
        ]

    def get_primary_user_name(self, obj):
        if obj.primary_user:
            return f"{obj.primary_user.first_name} {obj.primary_user.last_name}".strip()
        return None

    def get_primary_user_email(self, obj):
        return obj.primary_user.email if obj.primary_user else None

    def get_primary_user_phone(self, obj):
        profile = getattr(obj.primary_user, 'profile', None) if obj.primary_user else None
        return profile.phone if profile else None


class _ApplicationDetailSerializer(serializers.ModelSerializer):
    documents      = serializers.SerializerMethodField()
    status_history = serializers.SerializerMethodField()
    primary_user   = serializers.SerializerMethodField()

    class Meta:
        model  = FPO
        fields = [
            'id', 'application_id', 'status', 'tier', 'current_step',
            'name', 'name_ml', 'registration_number', 'cin_number',
            'date_of_registration', 'registered_under', 'pan_number', 'gst_number',
            'district', 'block_taluk', 'village_town',
            'address_line1', 'address_line2', 'pincode',
            'office_phone', 'office_email', 'website',
            'email_verified', 'phone_verified',
            'latitude', 'longitude',
            'signatory_name', 'signatory_designation',
            'signatory_phone', 'signatory_email', 'signatory_aadhaar_last4',
            'total_members', 'male_members', 'female_members', 'sc_st_members',
            'primary_commodities', 'secondary_commodities',
            'annual_turnover', 'bank_name', 'bank_branch',
            'account_number', 'ifsc_code', 'description',
            'primary_user', 'max_secondary_users',
            'documents', 'status_history',
            'created_at', 'updated_at',
        ]

    def get_primary_user(self, obj):
        if not obj.primary_user:
            return None
        profile = getattr(obj.primary_user, 'profile', None)
        return {
            'id':    obj.primary_user.id,
            'name':  f"{obj.primary_user.first_name} {obj.primary_user.last_name}".strip(),
            'email': obj.primary_user.email,
            'phone': profile.phone if profile else '',
        }

    def get_documents(self, obj):
        docs = obj.documents.filter(is_deleted=False).order_by('document_type')
        return _DocumentSerializer(docs, many=True, context=self.context).data

    def get_status_history(self, obj):
        history = obj.status_history.select_related('changed_by').order_by('created_at')
        return _StatusHistorySerializer(history, many=True).data


class _RejectSerializer(serializers.Serializer):
    reason = serializers.CharField(
        min_length=20,
        help_text='Rejection reason — minimum 20 characters (BR-103)',
    )


class _RequestInfoSerializer(serializers.Serializer):
    notes = serializers.CharField(
        min_length=10,
        help_text='Describe what additional information is required from the FPO',
    )


class _SetUserLimitSerializer(serializers.Serializer):
    max_secondary_users = serializers.IntegerField(
        min_value=1,
        max_value=100,
        help_text='New secondary user limit for this FPO (1–100)',
    )


# ──────────────────────────────────────────────────────────────────────────────
# Permission helpers
# ──────────────────────────────────────────────────────────────────────────────

def _can_view(user):
    if user.groups.filter(name=UserRole.SUPER_ADMIN).exists():
        return True
    return (
        user.groups.filter(name=UserRole.SUB_ADMIN).exists()
        and user.has_perm('apps_database.can_view_all_fpos')
    )


def _can_act(user):
    if user.groups.filter(name=UserRole.SUPER_ADMIN).exists():
        return True
    return (
        user.groups.filter(name=UserRole.SUB_ADMIN).exists()
        and user.has_perm('apps_database.can_approve_fpo')
    )


def _can_verify_docs(user):
    if user.groups.filter(name=UserRole.SUPER_ADMIN).exists():
        return True
    return (
        user.groups.filter(name=UserRole.SUB_ADMIN).exists()
        and user.has_perm('apps_database.can_verify_documents')
    )


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────

def _get_fpo(fpo_id):
    try:
        return FPO.objects.select_related(
            'primary_user', 'primary_user__profile',
        ).get(id=fpo_id, is_deleted=False)
    except FPO.DoesNotExist:
        return None


def _transition(fpo, to_status, changed_by, notes=''):
    from apps.notifications.services import send_notification

    from_status = fpo.status
    fpo.status  = to_status
    fpo.save(update_fields=['status', 'updated_at'])

    ApplicationStatusHistory.objects.create(
        fpo        =fpo,
        from_status=from_status,
        to_status  =to_status,
        changed_by =changed_by,
        notes      =notes,
    )

    notification_map = {
        FPOStatus.APPROVED:      'fpo_approved',
        FPOStatus.REJECTED:      'fpo_rejected',
        FPOStatus.INFO_REQUIRED: 'fpo_info_required',
    }

    code = notification_map.get(to_status)
    if code and fpo.primary_user:
        try:
            send_notification(
                user   =fpo.primary_user,
                code   =code,
                channel='email',
                context={
                    'user_name':      fpo.primary_user.first_name or fpo.primary_user.username,
                    'fpo_name':       fpo.name,
                    'application_id': fpo.application_id,
                    'notes':          notes,
                },
            )
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────────────────
# Views
# ──────────────────────────────────────────────────────────────────────────────

class ApplicationListView(APIView):

    @extend_schema(
        tags=['Admin - FPO Applications'],
        summary='List FPO applications',
        description='Paginated list of all FPO applications. Filter by status, district, tier, or search by name/application_id.',
        parameters=[
            OpenApiParameter('status',   description='Filter by FPO status (draft/submitted/under_review/approved/rejected/info_required/suspended)', required=False),
            OpenApiParameter('district', description='Filter by district code (e.g. TSR, KLM)', required=False),
            OpenApiParameter('tier',     description='Filter by tier (A/B/C/D)', required=False),
            OpenApiParameter('search',   description='Search by FPO name or application_id', required=False),
        ],
    )
    def get(self, request):
        if not _can_view(request.user):
            return StandardResponse.error(
                t('common.permission_denied', request.language),
                status_code=status.HTTP_403_FORBIDDEN,
            )

        qs = FPO.objects.filter(is_deleted=False).select_related(
            'primary_user', 'primary_user__profile',
        ).order_by('-created_at')

        s      = request.query_params.get('status')
        d      = request.query_params.get('district')
        tier   = request.query_params.get('tier')
        search = request.query_params.get('search', '').strip()

        if s:
            qs = qs.filter(status=s)
        if d:
            qs = qs.filter(district=d)
        if tier:
            qs = qs.filter(tier=tier)
        if search:
            qs = qs.filter(name__icontains=search) | qs.filter(application_id__icontains=search)

        paginator = StandardPagination()
        page      = paginator.paginate_queryset(qs, request)
        data      = _ApplicationListSerializer(page, many=True).data
        return paginator.get_paginated_response(data)


class ApplicationDetailView(APIView):

    @extend_schema(
        tags=['Admin - FPO Applications'],
        summary='Get full FPO application detail',
        description='Returns all wizard data, documents with verification status, and full status timeline.',
    )
    def get(self, request, fpo_id):
        if not _can_view(request.user):
            return StandardResponse.error(
                t('common.permission_denied', request.language),
                status_code=status.HTTP_403_FORBIDDEN,
            )

        fpo = FPO.objects.select_related(
            'primary_user', 'primary_user__profile',
        ).prefetch_related(
            'documents', 'status_history__changed_by',
        ).filter(id=fpo_id, is_deleted=False).first()

        if not fpo:
            return StandardResponse.error(
                t('fpo.fpo_not_found', request.language),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        return StandardResponse.success(
            data=_ApplicationDetailSerializer(fpo, context={'request': request}).data,
        )


class ApplicationMarkUnderReviewView(APIView):

    @extend_schema(
        tags=['Admin - FPO Applications'],
        summary='Mark application as Under Review',
        description='Transitions SUBMITTED → UNDER_REVIEW. Call this when an admin starts reviewing the application.',
        request=None,
    )
    def post(self, request, fpo_id):
        if not _can_act(request.user):
            return StandardResponse.error(
                t('common.permission_denied', request.language),
                status_code=status.HTTP_403_FORBIDDEN,
            )

        fpo = _get_fpo(fpo_id)
        if not fpo:
            return StandardResponse.error(t('fpo.fpo_not_found', request.language), status_code=status.HTTP_404_NOT_FOUND)

        if fpo.status != FPOStatus.SUBMITTED:
            return StandardResponse.error(
                f'Cannot move to UNDER_REVIEW from "{fpo.status}". Application must be SUBMITTED.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        _transition(fpo, FPOStatus.UNDER_REVIEW, request.user)
        return StandardResponse.success(
            data={'status': fpo.status},
            message=t('admin.fpo_under_review', request.language),
        )


class ApplicationApproveView(APIView):

    @extend_schema(
        tags=['Admin - FPO Applications'],
        summary='Approve FPO application',
        description='Transitions UNDER_REVIEW → APPROVED. FPO user receives email notification.',
        request=None,
    )
    def post(self, request, fpo_id):
        if not _can_act(request.user):
            return StandardResponse.error(
                t('common.permission_denied', request.language),
                status_code=status.HTTP_403_FORBIDDEN,
            )

        fpo = _get_fpo(fpo_id)
        if not fpo:
            return StandardResponse.error(t('fpo.fpo_not_found', request.language), status_code=status.HTTP_404_NOT_FOUND)

        if fpo.status != FPOStatus.UNDER_REVIEW:
            return StandardResponse.error(
                f'Cannot approve from "{fpo.status}". Application must be UNDER_REVIEW.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        _transition(fpo, FPOStatus.APPROVED, request.user)
        return StandardResponse.success(
            data={'status': fpo.status},
            message=t('admin.fpo_approved', request.language),
        )


class ApplicationRejectView(APIView):

    @extend_schema(
        tags=['Admin - FPO Applications'],
        summary='Reject FPO application',
        description='Transitions to REJECTED. Reason must be at least 20 characters (BR-103). FPO user receives email with reason.',
        request=_RejectSerializer,
        examples=[
            OpenApiExample('Reject', value={'reason': 'Submitted documents are incomplete and do not meet requirements.'}, request_only=True),
        ],
    )
    def post(self, request, fpo_id):
        if not _can_act(request.user):
            return StandardResponse.error(
                t('common.permission_denied', request.language),
                status_code=status.HTTP_403_FORBIDDEN,
            )

        serializer = _RejectSerializer(data=request.data)
        if not serializer.is_valid():
            return StandardResponse.error(serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)

        fpo = _get_fpo(fpo_id)
        if not fpo:
            return StandardResponse.error(t('fpo.fpo_not_found', request.language), status_code=status.HTTP_404_NOT_FOUND)

        if fpo.status not in {FPOStatus.SUBMITTED, FPOStatus.UNDER_REVIEW}:
            return StandardResponse.error(
                f'Cannot reject from "{fpo.status}". Must be SUBMITTED or UNDER_REVIEW.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        _transition(fpo, FPOStatus.REJECTED, request.user, notes=serializer.validated_data['reason'])
        return StandardResponse.success(
            data={'status': fpo.status},
            message=t('admin.fpo_rejected', request.language),
        )


class ApplicationRequestInfoView(APIView):

    @extend_schema(
        tags=['Admin - FPO Applications'],
        summary='Request additional information from FPO',
        description='Transitions UNDER_REVIEW → INFO_REQUIRED. FPO user receives email with the notes.',
        request=_RequestInfoSerializer,
        examples=[
            OpenApiExample('Request info', value={'notes': 'Please upload a clearer copy of the bank statement.'}, request_only=True),
        ],
    )
    def post(self, request, fpo_id):
        if not _can_act(request.user):
            return StandardResponse.error(
                t('common.permission_denied', request.language),
                status_code=status.HTTP_403_FORBIDDEN,
            )

        serializer = _RequestInfoSerializer(data=request.data)
        if not serializer.is_valid():
            return StandardResponse.error(serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)

        fpo = _get_fpo(fpo_id)
        if not fpo:
            return StandardResponse.error(t('fpo.fpo_not_found', request.language), status_code=status.HTTP_404_NOT_FOUND)

        if fpo.status != FPOStatus.UNDER_REVIEW:
            return StandardResponse.error(
                f'Cannot request info from "{fpo.status}". Application must be UNDER_REVIEW.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        _transition(fpo, FPOStatus.INFO_REQUIRED, request.user, notes=serializer.validated_data['notes'])
        return StandardResponse.success(
            data={'status': fpo.status},
            message=t('admin.fpo_info_requested', request.language),
        )


class ApplicationVerifyDocumentView(APIView):

    @extend_schema(
        tags=['Admin - FPO Applications'],
        summary='Mark a document as verified',
        description='Sets is_verified=True on the document and records who verified it and when.',
        request=None,
    )
    def post(self, request, fpo_id, doc_id):
        if not _can_verify_docs(request.user):
            return StandardResponse.error(
                t('common.permission_denied', request.language),
                status_code=status.HTTP_403_FORBIDDEN,
            )

        fpo = _get_fpo(fpo_id)
        if not fpo:
            return StandardResponse.error(t('fpo.fpo_not_found', request.language), status_code=status.HTTP_404_NOT_FOUND)

        doc = fpo.documents.filter(id=doc_id, is_deleted=False).first()
        if not doc:
            return StandardResponse.error(
                t('fpo.document_not_found', request.language),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if doc.is_verified:
            return StandardResponse.error(
                'Document is already verified.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        doc.is_verified = True
        doc.verified_by = request.user
        doc.verified_at = timezone.now()
        doc.save(update_fields=['is_verified', 'verified_by', 'verified_at', 'updated_at'])

        return StandardResponse.success(
            data={
                'doc_id':        str(doc.id),
                'document_type': doc.document_type,
                'is_verified':   doc.is_verified,
                'verified_at':   doc.verified_at,
            },
            message=t('admin.document_verified', request.language),
        )


class ApplicationSetUserLimitView(APIView):

    @extend_schema(
        tags=['Admin - FPO Applications'],
        summary='Set secondary user limit for an FPO',
        description='Overrides the default limit of 15 secondary users for this FPO. Super admin only.',
        request=_SetUserLimitSerializer,
        examples=[
            OpenApiExample('Set limit', value={'max_secondary_users': 25}, request_only=True),
        ],
    )
    def patch(self, request, fpo_id):
        if not request.user.groups.filter(name=UserRole.SUPER_ADMIN).exists():
            return StandardResponse.error(
                t('common.permission_denied', request.language),
                status_code=status.HTTP_403_FORBIDDEN,
            )

        serializer = _SetUserLimitSerializer(data=request.data)
        if not serializer.is_valid():
            return StandardResponse.error(serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)

        fpo = _get_fpo(fpo_id)
        if not fpo:
            return StandardResponse.error(t('fpo.fpo_not_found', request.language), status_code=status.HTTP_404_NOT_FOUND)

        fpo.max_secondary_users = serializer.validated_data['max_secondary_users']
        fpo.save(update_fields=['max_secondary_users', 'updated_at'])

        return StandardResponse.success(
            data={'max_secondary_users': fpo.max_secondary_users},
            message=t('admin.user_limit_updated', request.language),
        )
