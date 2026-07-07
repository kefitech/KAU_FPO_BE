"""
Admin FPO Applications Workflow
=================================
KAU admin staff review and manage FPO applications.

NOTE (KAU RCD June 2026): Approval is fully automated.
FPOs go DRAFT → SUBMITTED → APPROVED in one transaction on submit.
Admin can only reject or request info AFTER the FPO is already APPROVED.

Endpoints:
    GET    /api/admin/applications/                                 — list with filters
    GET    /api/admin/applications/{id}/                            — full detail
    POST   /api/admin/applications/{id}/reject/                     — reason ≥ 20 chars (BR-103)
    POST   /api/admin/applications/{id}/request-info/               — APPROVED → INFO_REQUIRED
    POST   /api/admin/applications/{id}/verify-document/{doc_id}/
    PATCH  /api/admin/applications/{id}/set-user-limit/             — deprecated (410)

Permissions:
    list / detail / verify-document  → super_admin OR sub_admin with can_view_all_fpos
    reject / request-info            → super_admin OR sub_admin with can_approve_fpo
    set-user-limit                   → super_admin only
"""

from django.contrib.auth import get_user_model
from django.utils import timezone

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from rest_framework import serializers, status
from rest_framework.views import APIView
from rest_framework.filters import OrderingFilter

from apps.core.utils.constants import FPOStatus, UserRole
from apps.core.utils.pagination import StandardPagination
from apps.core.utils.responses import StandardResponse
from apps.core.services.translation import t
from apps.database.models.fpo import FPO, FPODocument, ApplicationStatusHistory, FPOTierHistory
from apps.core.models.generic import AuditLog
from apps.core.services.audit import AuditService

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
    primary_user_id    = serializers.IntegerField(source='primary_user.id', default=None)
    primary_user_name  = serializers.SerializerMethodField()
    primary_user_email = serializers.SerializerMethodField()
    primary_user_phone = serializers.SerializerMethodField()
    current_tier       = serializers.CharField(source='tier', default=None)
    status_display     = serializers.CharField(source='get_status_display', read_only=True)
    district_display   = serializers.SerializerMethodField()

    class Meta:
        model  = FPO
        fields = [
            'id', 'application_id', 'name', 'name_ml',
            'district', 'district_display',
            'status', 'status_display',
            'tier', 'current_tier', 'current_step',
            'total_members',
            'office_email', 'office_phone',
            'email_verified', 'phone_verified',
            'primary_user_id', 'primary_user_name', 'primary_user_email', 'primary_user_phone',
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

    def get_district_display(self, obj):
        from apps.core.utils.constants import get_district_name
        return get_district_name(obj.district) if obj.district else None


class _ApplicationDetailSerializer(serializers.ModelSerializer):
    documents      = serializers.SerializerMethodField()
    status_history = serializers.SerializerMethodField()
    primary_user   = serializers.SerializerMethodField()
    claim_origin   = serializers.SerializerMethodField()

    class Meta:
        model  = FPO
        fields = [
            'id', 'application_id', 'status', 'tier', 'current_step',
            'name', 'name_ml', 'legal_structure', 'legal_structure_detail',
            'registration_number', 'cin_number',
            'date_of_registration', 'pan_number', 'gst_number',
            'district', 'block_taluk', 'village_town',
            'address_line1', 'address_line2', 'pincode',
            'office_phone', 'office_email', 'website',
            'email_verified', 'phone_verified',
            'latitude', 'longitude',
            'signatory_name', 'signatory_designation',
            'signatory_phone', 'signatory_email', 'signatory_aadhaar_last4',
            'total_members', 'male_members', 'female_members', 'sc_st_members',
            'promoting_agency', 'facilitating_agency_name',
            'ceo_available', 'accountant_available',
            'total_directors', 'women_directors', 'directors_under_35',
            'primary_commodities', 'secondary_commodities',
            'annual_turnover', 'bank_name', 'bank_branch',
            'account_number', 'ifsc_code', 'description',
            'primary_user',
            'documents', 'status_history',
            'claim_origin',
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

    def get_claim_origin(self, obj):
        if not obj.claimed_from_fpo_id:
            return None
        return {
            'original_fpo_id':   obj.claimed_from_fpo_id,
            'original_fpo_name': obj.claimed_from_fpo.name if obj.claimed_from_fpo else None,
            'claim_id':          obj.origin_claim_id,
        }


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


class _ActivateDeactivateSerializer(serializers.Serializer):
    notes = serializers.CharField(
        required=False, allow_blank=True,
        help_text='Optional notes for this status change',
    )


class _AdminEditFPOSerializer(serializers.Serializer):
    name                   = serializers.CharField(max_length=200, required=False)
    name_ml                = serializers.CharField(max_length=200, required=False, allow_blank=True)
    district               = serializers.CharField(max_length=10, required=False)
    pan_number             = serializers.CharField(max_length=10, required=False, allow_blank=True)
    gst_number             = serializers.CharField(max_length=15, required=False, allow_blank=True)
    cin_number             = serializers.CharField(max_length=21, required=False, allow_blank=True)
    registration_number    = serializers.CharField(max_length=50, required=False, allow_blank=True)
    office_email           = serializers.EmailField(required=False, allow_blank=True)
    office_phone           = serializers.CharField(max_length=15, required=False, allow_blank=True)
    total_members          = serializers.IntegerField(required=False, min_value=0)
    male_members           = serializers.IntegerField(required=False, min_value=0)
    female_members         = serializers.IntegerField(required=False, min_value=0)
    legal_structure        = serializers.CharField(max_length=50, required=False, allow_blank=True)
    legal_structure_detail = serializers.CharField(max_length=100, required=False, allow_blank=True)


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
    ordering_fields = [
        'application_id', 'name', 'district', 'status',
        'total_members', 'updated_at', 'created_at',
    ]
    ordering = ['-updated_at']  # default ordering if no `ordering` param sent

    @extend_schema(
        tags=['Admin - FPO Applications'],
        summary='List FPO applications',
        description='Paginated list of all FPO applications. Filter by status, district, tier, or search by name/application_id.',
        parameters=[
            OpenApiParameter('status',   description='Filter by FPO status (draft/submitted/under_review/approved/rejected/info_required/suspended)', required=False),
            OpenApiParameter('district', description='Filter by district code (e.g. TSR, KLM)', required=False),
            OpenApiParameter('tier',     description='Filter by tier (A/B/C/D)', required=False),
            OpenApiParameter('search',   description='Search by FPO name or application_id', required=False),
            OpenApiParameter('ordering', description='Order by field (prefix with "-" for descending), e.g. application_id or -updated_at', required=False),
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
        )

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

        qs = OrderingFilter().filter_queryset(request, qs, self)

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
            'primary_user', 'primary_user__profile', 'claimed_from_fpo',
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

    @extend_schema(
        tags=['Admin - FPO Applications'],
        summary='Edit FPO details (admin)',
        description=(
            'Allows admin to edit key FPO fields on any status.\n\n'
            'Unique fields (`pan_number`, `gst_number`, `cin_number`, `registration_number`, '
            '`office_email`, `office_phone`) are checked for duplicates across other FPOs '
            '(excluding CLAIMED FPOs). Returns 400 with field-level error if a duplicate is found.\n\n'
            'All fields are optional — only include what needs to change.'
        ),
        request=_AdminEditFPOSerializer,
        responses={200: None},
    )
    def patch(self, request, fpo_id):
        if not _can_act(request.user):
            return StandardResponse.error(
                t('common.permission_denied', request.language),
                status_code=status.HTTP_403_FORBIDDEN,
            )

        fpo = _get_fpo(fpo_id)
        if not fpo:
            return StandardResponse.error(
                t('fpo.fpo_not_found', request.language),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        ser = _AdminEditFPOSerializer(data=request.data)
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=status.HTTP_400_BAD_REQUEST)

        data = ser.validated_data
        if not data:
            return StandardResponse.error(
                'No fields provided to update.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Duplicate check for unique fields
        UNIQUE_FIELDS = [
            'pan_number', 'gst_number', 'cin_number',
            'registration_number', 'office_email', 'office_phone',
        ]
        for field in UNIQUE_FIELDS:
            if field not in data:
                continue
            new_val = data[field]
            if not new_val:
                continue
            conflict = FPO.objects.filter(
                **{field: new_val},
                is_deleted=False,
            ).exclude(id=fpo.id).exclude(status=FPOStatus.CLAIMED).first()
            if conflict:
                return StandardResponse.error(
                    {field: f"'{new_val}' is already registered to another FPO (#{conflict.id} — {conflict.name})."},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

        # Build changes dict (old → new) for audit log
        changes = {}
        update_fields = []
        for field, new_val in data.items():
            old_val = getattr(fpo, field, None)
            if old_val != new_val:
                changes[field] = {'old': old_val, 'new': new_val}
                setattr(fpo, field, new_val)
                update_fields.append(field)

        if not update_fields:
            return StandardResponse.success(
                data={'fpo_id': fpo.id},
                message='No changes detected.',
            )

        update_fields.append('updated_at')
        fpo.save(update_fields=update_fields)

        AuditService.log(
            user=request.user,
            action=AuditLog.Action.UPDATE,
            instance=fpo,
            request=request,
            changes=changes,
        )

        return StandardResponse.success(
            data={'fpo_id': fpo.id, 'updated_fields': list(changes.keys())},
            message='FPO details updated.',
        )


class ApplicationRejectView(APIView):

    @extend_schema(
        tags=['Admin - FPO Applications'],
        summary='Reject FPO application',
        description=(
            'Transitions APPROVED → REJECTED. Reason must be at least 20 characters (BR-103). '
            'FPO user receives email with reason.\n\n'
            '**Note:** Since approval is automated, admin can only reject an already-APPROVED FPO.'
        ),
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

        if fpo.status != FPOStatus.APPROVED:
            return StandardResponse.error(
                f'Cannot reject from "{fpo.status}". FPO must be APPROVED.',
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
        description=(
            'Transitions APPROVED → INFO_REQUIRED. FPO user receives email with the notes '
            'and can re-submit once they have addressed the request.\n\n'
            '**Note:** Since approval is automated, admin raises info requests on an already-APPROVED FPO.'
        ),
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

        if fpo.status != FPOStatus.APPROVED:
            return StandardResponse.error(
                f'Cannot request info from "{fpo.status}". FPO must be APPROVED.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        _transition(fpo, FPOStatus.INFO_REQUIRED, request.user, notes=serializer.validated_data['notes'])
        return StandardResponse.success(
            data={'status': fpo.status},
            message=t('admin.fpo_info_requested', request.language),
        )


class ApplicationActivateView(APIView):

    @extend_schema(
        tags=['Admin - FPO Applications'],
        summary='Activate a suspended or rejected FPO',
        description=(
            'Transitions SUSPENDED or REJECTED → APPROVED.\n\n'
            'Before activating, checks for duplicate `pan_number`, `gst_number`, `cin_number`, '
            '`registration_number` against other APPROVED FPOs. If a conflict is found, returns 400.\n\n'
            'Optional `notes` field is recorded in the status history.'
        ),
        request=_ActivateDeactivateSerializer,
        responses={200: None},
    )
    def post(self, request, fpo_id):
        if not _can_act(request.user):
            return StandardResponse.error(
                t('common.permission_denied', request.language),
                status_code=status.HTTP_403_FORBIDDEN,
            )

        ser = _ActivateDeactivateSerializer(data=request.data)
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=status.HTTP_400_BAD_REQUEST)

        fpo = _get_fpo(fpo_id)
        if not fpo:
            return StandardResponse.error(
                t('fpo.fpo_not_found', request.language),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        ALLOWED_FROM = [FPOStatus.SUSPENDED, FPOStatus.REJECTED]
        if fpo.status not in ALLOWED_FROM:
            return StandardResponse.error(
                f'Cannot activate from "{fpo.status}". FPO must be SUSPENDED or REJECTED.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Duplicate check against other ACTIVE (approved) FPOs, excluding claimed FPOs
        UNIQUE_FIELDS = [
            ('pan_number', fpo.pan_number),
            ('gst_number', fpo.gst_number),
            ('cin_number', fpo.cin_number),
            ('registration_number', fpo.registration_number),
        ]
        for field, value in UNIQUE_FIELDS:
            if not value:
                continue
            conflict = FPO.objects.filter(
                **{field: value},
                status=FPOStatus.APPROVED,
                is_deleted=False,
            ).exclude(id=fpo.id).exclude(status=FPOStatus.CLAIMED).first()
            if conflict:
                return StandardResponse.error(
                    f'Cannot activate: {field} \'{value}\' is already registered to another active FPO '
                    f'(#{conflict.id} — {conflict.name}).',
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

        notes = ser.validated_data.get('notes', '')
        _transition(fpo, FPOStatus.APPROVED, request.user, notes=notes)

        AuditService.log(
            user=request.user,
            action=AuditLog.Action.FPO_STATUS_CHANGE,
            instance=fpo,
            request=request,
            changes={'action': 'fpo_activated', 'new_status': FPOStatus.APPROVED, 'notes': notes},
        )

        return StandardResponse.success(
            data={'status': fpo.status, 'fpo_id': fpo.id},
            message='FPO activated successfully.',
        )


class ApplicationDeactivateView(APIView):

    @extend_schema(
        tags=['Admin - FPO Applications'],
        summary='Deactivate (suspend) an approved FPO',
        description=(
            'Transitions APPROVED → SUSPENDED.\n\n'
            'Optional `notes` field is recorded in the status history.'
        ),
        request=_ActivateDeactivateSerializer,
        responses={200: None},
    )
    def post(self, request, fpo_id):
        if not _can_act(request.user):
            return StandardResponse.error(
                t('common.permission_denied', request.language),
                status_code=status.HTTP_403_FORBIDDEN,
            )

        ser = _ActivateDeactivateSerializer(data=request.data)
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=status.HTTP_400_BAD_REQUEST)

        fpo = _get_fpo(fpo_id)
        if not fpo:
            return StandardResponse.error(
                t('fpo.fpo_not_found', request.language),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if fpo.status != FPOStatus.APPROVED:
            return StandardResponse.error(
                f'Cannot deactivate from "{fpo.status}". FPO must be APPROVED.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        notes = ser.validated_data.get('notes', '')
        _transition(fpo, FPOStatus.SUSPENDED, request.user, notes=notes)

        AuditService.log(
            user=request.user,
            action=AuditLog.Action.FPO_STATUS_CHANGE,
            instance=fpo,
            request=request,
            changes={'action': 'fpo_deactivated', 'new_status': FPOStatus.SUSPENDED, 'notes': notes},
        )

        return StandardResponse.success(
            data={'status': fpo.status, 'fpo_id': fpo.id},
            message='FPO deactivated (suspended) successfully.',
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
    """KAU confirmed: no secondary user limit. This endpoint is retained for future use."""

    @extend_schema(
        tags=['Admin - FPO Applications'],
        summary='Secondary user limit (disabled)',
        description='KAU confirmed no secondary user limit is required. This endpoint is a no-op placeholder.',
        deprecated=True,
    )
    def patch(self, request, fpo_id):
        return StandardResponse.error(
            'Secondary user limit has been removed by KAU. No limit applies.',
            status_code=status.HTTP_410_GONE,
        )


class _AssignTierSerializer(serializers.Serializer):
    tier           = serializers.ChoiceField(choices=['A', 'B', 'C', 'D'])
    financial_year = serializers.RegexField(
        r'^\d{4}-\d{2}$',
        help_text='e.g. 2026-27',
    )
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True)


class ApplicationAssignTierView(APIView):

    @extend_schema(
        tags=['Admin - Tier Management'],
        summary='Manually assign tier to an FPO',
        description=(
            'Admin override — manually assign a tier (A/B/C/D) to an FPO for a specific financial year.\n\n'
            'Creates a new `FPOTierHistory` record and syncs `FPO.tier` immediately.\n\n'
            'Use this when the auto-scored tier needs correction.\n\n'
            '**Request body:**\n'
            '```json\n'
            '{ "tier": "A", "financial_year": "2026-27", "notes": "Manually verified — exceptional performance" }\n'
            '```'
        ),
        request=_AssignTierSerializer,
        responses={200: None},
    )
    def post(self, request, fpo_id):
        if not request.user.groups.filter(name=UserRole.SUPER_ADMIN).exists():
            return StandardResponse.error(
                'Only super admin can manually assign a tier.',
                status_code=status.HTTP_403_FORBIDDEN,
            )

        try:
            fpo = FPO.objects.get(id=fpo_id)
        except FPO.DoesNotExist:
            return StandardResponse.error('FPO not found.', status_code=status.HTTP_404_NOT_FOUND)

        ser = _AssignTierSerializer(data=request.data)
        if not ser.is_valid():
            return StandardResponse.error(str(ser.errors), status_code=status.HTTP_400_BAD_REQUEST)

        tier           = ser.validated_data['tier']
        financial_year = ser.validated_data['financial_year']
        notes          = ser.validated_data.get('notes', '')

        from django.db import transaction
        with transaction.atomic():
            FPOTierHistory.objects.create(
                fpo            = fpo,
                tier           = tier,
                financial_year = financial_year,
                assigned_by    = request.user,
                notes          = notes or f'Manually assigned by admin ({request.user.get_full_name() or request.user.username})',
            )

        AuditService.log(
            user=request.user,
            action=AuditLog.Action.TIER_RECALCULATION,
            instance=fpo,
            request=request,
            changes={
                'tier':           tier,
                'financial_year': financial_year,
                'manual_override': True,
                'notes':          notes,
            },
        )

        fpo.refresh_from_db()
        return StandardResponse.success(
            data={'tier': fpo.tier, 'financial_year': financial_year},
            message=f'Tier {tier} manually assigned to {fpo.name} for {financial_year}.',
        )


class ApplicationTierHistoryView(APIView):

    @extend_schema(
        tags=['Admin - Tier Management'],
        summary='Tier history for an FPO',
        description='Returns the full tier assignment history for an FPO — one row per financial year, oldest first.',
        responses={200: None},
    )
    def get(self, request, fpo_id):
        if not request.user.groups.filter(
            name__in=[UserRole.SUPER_ADMIN, UserRole.SUB_ADMIN]
        ).exists():
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        try:
            fpo = FPO.objects.get(id=fpo_id)
        except FPO.DoesNotExist:
            return StandardResponse.error('FPO not found.', status_code=status.HTTP_404_NOT_FOUND)

        history = fpo.tier_history.select_related('assigned_by').order_by('created_at')

        data = [
            {
                'id':             row.id,
                'tier':           row.tier,
                'financial_year': row.financial_year,
                'assigned_by':    (
                    f"{row.assigned_by.first_name} {row.assigned_by.last_name}".strip()
                    or row.assigned_by.username
                ) if row.assigned_by else 'System',
                'notes':          row.notes,
                'assigned_at':    row.created_at,
            }
            for row in history
        ]

        return StandardResponse.success(
            data={'fpo_id': fpo.id, 'current_tier': fpo.tier, 'history': data},
            message='Tier history retrieved.',
        )
