from rest_framework import serializers, status
from rest_framework.views import APIView
 
from apps.core.utils.responses import StandardResponse
from apps.core.utils.pagination import StandardPagination
from apps.core.services.translation import t
from apps.database.models.fpo import FPO
from apps.database.models.cbbo import CBBOAssignment
 
 
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
 
 
class _AssignedFPOSerializer(serializers.ModelSerializer):
    district_display = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
 
    class Meta:
        model = FPO
        fields = [
            'id', 'application_id', 'name', 'name_ml',
            'district', 'district_display',
            'status', 'status_display', 'tier',
            'total_members', 'created_at', 'updated_at',
        ]
 
    def get_district_display(self, obj):
        return _district_display(obj.district, self.context.get('request'))
 
 
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
