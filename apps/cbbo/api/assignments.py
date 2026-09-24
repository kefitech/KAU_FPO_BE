from rest_framework import serializers, status
from rest_framework.views import APIView
 
from apps.core.utils.responses import StandardResponse
from apps.core.utils.pagination import StandardPagination
from apps.core.services.translation import t
from apps.database.models.fpo import FPO, FPODocument
from apps.database.models.cbbo import CBBOAssignment
from apps.core.services.lookup import LookupService
 
 
# ──────────────────────────────────────────────────────────────────────────────
# Scoping — import these from reports.py / training.py
# ──────────────────────────────────────────────────────────────────────────────
def get_assignment_scope(user):
    """
    Returns one of:
      - 'ALL'      → active state-level assignment
      - [<codes>]  → one or more active district assignments
      - []         → authenticated CBBO user, zero active jurisdiction
    """
    assignments = CBBOAssignment.objects.filter(cbbo=user, is_active=True)
    if assignments.filter(level=CBBOAssignment.LEVEL_STATE).exists():
        return 'ALL'
    return list(
        assignments.filter(level=CBBOAssignment.LEVEL_DISTRICT)
                   .values_list('district', flat=True)
    )
 
 
def is_cbbo_user(user):
    """True if the user has ANY CBBOAssignment row, active or not."""
    if not user or not user.is_authenticated:
        return False
    return CBBOAssignment.objects.filter(cbbo=user).exists()
 
 
def scope_fpo_qs(qs, user):
    scope = get_assignment_scope(user)
    if scope == 'ALL':
        return qs
    return qs.filter(district__in=scope)
 
 
def is_fpo_assigned(fpo, user):
    scope = get_assignment_scope(user)
    if scope == 'ALL':
        return True
    return fpo.district in scope
 
 
def get_fpo_scoped(fpo_id, user):
    scope = get_assignment_scope(user)
    qs = FPO.objects.filter(id=fpo_id)
    # If your FPO model has soft-delete, uncomment the next line:
    # qs = qs.filter(is_deleted=False)
    if scope != 'ALL':
        qs = qs.filter(district__in=scope)
    return qs.select_related('primary_user').first()
 
 
# ──────────────────────────────────────────────────────────────────────────────
# Serializers
# ──────────────────────────────────────────────────────────────────────────────
def _district_display(district_code, request):
    """Best-effort district name lookup — never crashes the response if the
    helper/import doesn't exist in your project; falls back to the raw code."""
    if not district_code:
        return None
    try:
        from apps.core.utils.constants import get_district_name
        lang = getattr(request, 'language', 'en')
        return get_district_name(district_code, language=lang)
    except ImportError:
        return district_code

def _lookup_display(category, code, request):
    if not code:
        return code
    lang = getattr(request, 'language', 'en')
    name = LookupService.get_name(category, code, lang)
    return name or code
 
 
class _CBBODocumentSerializer(serializers.ModelSerializer):
    verified_by_name = serializers.SerializerMethodField()
    file_url          = serializers.SerializerMethodField()

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


class _AssignedFPOSerializer(serializers.ModelSerializer):
    district_display = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    documents = serializers.SerializerMethodField()
    legal_structure_display = serializers.SerializerMethodField()
    promoting_agency_display = serializers.SerializerMethodField()
    signatory_designation_display = serializers.SerializerMethodField()
    bank_name_display = serializers.SerializerMethodField()
    primary_commodities_display = serializers.SerializerMethodField()
    secondary_commodities_display = serializers.SerializerMethodField()

    class Meta:
        model = FPO
        fields = [
            'id', 'application_id', 'name', 'name_ml',
            'district', 'district_display',
            'status', 'status_display', 'tier',
            'registration_number', 'date_of_registration',
            'legal_structure', 'legal_structure_display', 'legal_structure_detail',
            'promoting_agency', 'promoting_agency_display', 'facilitating_agency_name',
            'block_taluk', 'village_town',
            'address_line1', 'address_line2', 'pincode',
            'office_phone', 'office_email', 'website',
            'total_members', 'male_members', 'female_members', 'sc_st_members',
            'ceo_available', 'accountant_available',
            'total_directors', 'women_directors', 'directors_under_35',
            'primary_commodities', 'primary_commodities_display',
            'secondary_commodities', 'secondary_commodities_display',
            'annual_turnover',
            'signatory_name', 'signatory_designation', 'signatory_designation_display',
            'signatory_phone', 'signatory_email', 'signatory_aadhaar_last4',
            'bank_name', 'bank_name_display', 'bank_branch', 'account_number', 'ifsc_code',
            'created_at', 'updated_at',
            'documents',
        ]

    def get_district_display(self, obj):
        return _district_display(obj.district, self.context.get('request'))

    def get_documents(self, obj):
        docs = obj.documents.filter(is_deleted=False).order_by('-created_at')
        return _CBBODocumentSerializer(docs, many=True, context=self.context).data

    def get_legal_structure_display(self, obj):
        return _lookup_display('legal_structure', obj.legal_structure, self.context.get('request'))

    def get_promoting_agency_display(self, obj):
        return _lookup_display('promoting_agency', obj.promoting_agency, self.context.get('request'))

    def get_signatory_designation_display(self, obj):
        return _lookup_display('signatory_designation', obj.signatory_designation, self.context.get('request'))

    def get_bank_name_display(self, obj):
        return _lookup_display('bank_name', obj.bank_name, self.context.get('request'))

    def get_primary_commodities_display(self, obj):
        request = self.context.get('request')
        return [_lookup_display('commodity', c, request) for c in (obj.primary_commodities or [])]

    def get_secondary_commodities_display(self, obj):
        request = self.context.get('request')
        return [_lookup_display('commodity', c, request) for c in (obj.secondary_commodities or [])]
        return _CBBODocumentSerializer(docs, many=True, context=self.context).data
 
 
# ──────────────────────────────────────────────────────────────────────────────
# Views   

# ──────────────────────────────────────────────────────────────────────────────
class AssignedFPOListView(APIView):
    """GET /api/cbbo/fpos/"""
    # created by jobin.j
    # cbbo
 
    # ── LIST FPOs IN MY JURISDICTION ────────────────────────────────────────
    # Any authenticated CBBO (is_cbbo_user) can call this. The queryset is
    # scoped up front via scope_fpo_qs(), so a district CBBO physically
    # cannot page/search into another district's FPOs — jurisdiction is
    # enforced at the query level, not filtered out after the fact.
    #
    # Query params (all optional):
    #   status = <FPO.status value>   -> exact match
    #   search = <text>               -> matches name OR application_id

    def get(self, request):
        if not is_cbbo_user(request.user):
            return StandardResponse.error(
                t('common.permission_denied', request.language),
                status_code=status.HTTP_403_FORBIDDEN,
            )
 
        qs = FPO.objects.select_related('primary_user')
        # If your FPO model has soft-delete, uncomment:
        # qs = qs.filter(is_deleted=False)
        qs = scope_fpo_qs(qs, request.user)
 
        s = request.query_params.get('status')
        search = request.query_params.get('search', '').strip()
        if s:
            qs = qs.filter(status=s)
        if search:
            qs = qs.filter(name__icontains=search) | qs.filter(application_id__icontains=search)
 
        qs = qs.order_by('-updated_at')
 
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        data = _AssignedFPOSerializer(page, many=True, context={'request': request}).data
        return paginator.get_paginated_response(data)
 
 
class AssignedFPODetailView(APIView):

 # ── GET ONE FPO (JURISDICTION-CHECKED) ──────────────────────────────────
    # Returns 404 rather than 403 when the FPO exists but belongs to a
    # district outside this CBBO's assignment — this is intentional: a 403
    # would confirm to the caller that the FPO id is valid, which leaks
    # information about FPOs outside their jurisdiction. get_fpo_scoped()
    # returns None for both "doesn't exist" and "not mine", so both cases
    # look identical from the outside.


    """GET /api/cbbo/fpos/{id}/ — 404 if outside jurisdiction, not 403."""
 
    def get(self, request, fpo_id):
        if not is_cbbo_user(request.user):
            return StandardResponse.error(
                t('common.permission_denied', request.language),
                status_code=status.HTTP_403_FORBIDDEN,
            )
 
        fpo = get_fpo_scoped(fpo_id, request.user)
        if not fpo:
            return StandardResponse.error(
                t('fpo.fpo_not_found', request.language),
                status_code=status.HTTP_404_NOT_FOUND,
            )
 
        return StandardResponse.success(
            data=_AssignedFPOSerializer(fpo, context={'request': request}).data,
        )


class AssignedFPOVerifyDocumentView(APIView):
    """POST /api/cbbo/fpos/{fpo_id}/verify-document/{doc_id}/

    Jurisdiction-checked exactly like AssignedFPODetailView: a CBBO officer
    can only verify documents for FPOs within their own assigned district(s)
    or a state-wide assignment. get_fpo_scoped() returns None for both
    "doesn't exist" and "not mine", so both cases look identical (404).
    """

    def post(self, request, fpo_id, doc_id):
        if not is_cbbo_user(request.user):
            return StandardResponse.error(
                t('common.permission_denied', request.language),
                status_code=status.HTTP_403_FORBIDDEN,
            )

        fpo = get_fpo_scoped(fpo_id, request.user)
        if not fpo:
            return StandardResponse.error(
                t('fpo.fpo_not_found', request.language),
                status_code=status.HTTP_404_NOT_FOUND,
            )

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

        from django.utils import timezone
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
