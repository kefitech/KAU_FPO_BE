from rest_framework import serializers, status
from rest_framework.views import APIView

from apps.core.utils.responses import StandardResponse
from apps.core.utils.pagination import StandardPagination
from apps.core.services.translation import t
from apps.core.services.lookup import LookupService
from apps.database.models.fpo import FPO

from apps.government.api.scoping import is_government_user, scope_fpo_qs, get_fpo_scoped


def _district_display(district_code, request):
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


class _GovtFPOSerializer(serializers.ModelSerializer):
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


def _lookup_display(category, code, request):
    if not code:
        return code
    lang = getattr(request, 'language', 'en')
    name = LookupService.get_name(category, code, lang)
    return name or code


class _GovtFPODetailSerializer(serializers.ModelSerializer):
    district_display = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
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
        ]

    def get_district_display(self, obj):
        return _district_display(obj.district, self.context.get('request'))

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


class GovernmentFPOListView(APIView):
    def get(self, request):
        if not is_government_user(request.user):
            return StandardResponse.error(
                t('common.permission_denied', request.language),
                status_code=status.HTTP_403_FORBIDDEN,
            )

        qs = FPO.objects.select_related('primary_user')
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
        data = _GovtFPOSerializer(page, many=True, context={'request': request}).data
        return paginator.get_paginated_response(data)


class GovernmentFPODetailView(APIView):
    def get(self, request, fpo_id):
        if not is_government_user(request.user):
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
            data=_GovtFPODetailSerializer(fpo, context={'request': request}).data,
        )
