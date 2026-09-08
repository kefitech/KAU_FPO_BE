"""
DPR Admin — Project detail endpoint (read-only oversight).

GET /api/admin/dpr/projects/<uuid>/ — returns the project meta, FPO summary,
and every section's data + readiness result in one payload.

Reuses the FPO-side serializers + validators. Nothing is mutated.

Author: Athul Gopan (Kefi Tech Solutions)
"""
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions.rbac import IsSubAdminOrSuperAdmin
from apps.core.utils.responses import StandardResponse
from apps.database.models import (
    DPRProject,
    DPRSectionBaseline,
    DPRSectionCapacity,
    DPRSectionCivil,
    DPRSectionCompliance,
    DPRSectionComponents,
    DPRSectionESS,
    DPRSectionFinance,
    DPRSectionHR,
    DPRSectionImplementation,
    DPRSectionInvestment,
    DPRSectionLocation,
    DPRSectionMachinery,
    DPRSectionMarket,
    DPRSectionNatureOfBusiness,
    DPRSectionProducts,
    DPRSectionRationale,
    DPRSectionRawMaterial,
    DPRSectionRisk,
    DPRSectionSite,
    DPRSectionTechnology,
    DPRSectionUtilities,
)
from apps.fpo.api.dpr.serializers import (
    DPRSectionBaselineSerializer,
    DPRSectionCapacitySerializer,
    DPRSectionCivilSerializer,
    DPRSectionComplianceSerializer,
    DPRSectionComponentsSerializer,
    DPRSectionESSSerializer,
    DPRSectionFinanceSerializer,
    DPRSectionHRSerializer,
    DPRSectionImplementationSerializer,
    DPRSectionInvestmentSerializer,
    DPRSectionLocationSerializer,
    DPRSectionMachinerySerializer,
    DPRSectionMarketSerializer,
    DPRSectionNatureOfBusinessSerializer,
    DPRSectionProductsSerializer,
    DPRSectionRationaleSerializer,
    DPRSectionRawMaterialSerializer,
    DPRSectionRiskSerializer,
    DPRSectionSiteSerializer,
    DPRSectionTechnologySerializer,
    DPRSectionUtilitiesSerializer,
)
from apps.fpo.services.dpr import (
    baseline_validators, capacity_validators, civil_validators,
    compliance_validators, components_validators, ess_validators,
    finance_validators, hr_validators, identification_validators,
    implementation_validators,
    investment_validators, location_validators, machinery_validators,
    market_validators, nature_of_business_validators, products_validators,
    rationale_validators, raw_material_validators, risk_validators,
    site_validators, technology_validators, utilities_validators,
)

from .enrichers import enrich_section_data


# section_key → (Model, Serializer, validator_module)
SECTION_REGISTRY = {
    'nature-of-business': (DPRSectionNatureOfBusiness, DPRSectionNatureOfBusinessSerializer, nature_of_business_validators),
    'components':         (DPRSectionComponents,       DPRSectionComponentsSerializer,       components_validators),
    'investment':         (DPRSectionInvestment,       DPRSectionInvestmentSerializer,       investment_validators),
    'products':           (DPRSectionProducts,         DPRSectionProductsSerializer,         products_validators),
    'location':           (DPRSectionLocation,         DPRSectionLocationSerializer,         location_validators),
    'rationale':          (DPRSectionRationale,        DPRSectionRationaleSerializer,        rationale_validators),
    'baseline':           (DPRSectionBaseline,         DPRSectionBaselineSerializer,         baseline_validators),
    'capacity':           (DPRSectionCapacity,         DPRSectionCapacitySerializer,         capacity_validators),
    'raw-material':       (DPRSectionRawMaterial,      DPRSectionRawMaterialSerializer,      raw_material_validators),
    'market':             (DPRSectionMarket,           DPRSectionMarketSerializer,           market_validators),
    'technology':         (DPRSectionTechnology,       DPRSectionTechnologySerializer,       technology_validators),
    'site':               (DPRSectionSite,             DPRSectionSiteSerializer,             site_validators),
    'civil':              (DPRSectionCivil,            DPRSectionCivilSerializer,            civil_validators),
    'machinery':          (DPRSectionMachinery,        DPRSectionMachinerySerializer,        machinery_validators),
    'utilities':          (DPRSectionUtilities,        DPRSectionUtilitiesSerializer,        utilities_validators),
    'hr':                 (DPRSectionHR,               DPRSectionHRSerializer,               hr_validators),
    'finance':            (DPRSectionFinance,          DPRSectionFinanceSerializer,          finance_validators),
    'compliance':         (DPRSectionCompliance,       DPRSectionComplianceSerializer,       compliance_validators),
    'ess':                (DPRSectionESS,              DPRSectionESSSerializer,              ess_validators),
    'implementation':     (DPRSectionImplementation,   DPRSectionImplementationSerializer,   implementation_validators),
    'risk':               (DPRSectionRisk,             DPRSectionRiskSerializer,             risk_validators),
}


def _build_identification_payload(project) -> dict:
    """Flatten DPRProject §2.2 fields with human labels for admin oversight.

    FK fields resolve to `{id, name}`; M2M lists resolve to `[{id, name}, ...]`.
    Kept read-only + admin-only — avoids touching the FPO-facing serializer
    which sends bare IDs on purpose (frontend caches master lists separately).
    """
    # MasterLookup names live in the Translation table (not a column) —
    # `get_name()` resolves via translations, falls back to code.
    primary = None
    if project.primary_commodity_id:
        m = project.primary_commodity
        primary = {'id': m.id, 'name': m.get_name('en') or m.code}

    secondary = [
        {'id': m.id, 'name': m.get_name('en') or m.code}
        for m in project.secondary_commodities.all()
    ]
    project_types = [
        {'id': t.id, 'name': getattr(t, 'label_en', None) or getattr(t, 'code', str(t.id))}
        for t in project.project_types.all()
    ]
    project_objectives = [
        {'id': o.id, 'name': getattr(o, 'label_en', None) or getattr(o, 'code', str(o.id))}
        for o in project.project_objectives.all()
    ]
    expected_outcomes = [
        {'id': o.id, 'name': getattr(o, 'label_en', None) or getattr(o, 'code', str(o.id))}
        for o in project.expected_outcomes.all()
    ]

    return {
        'title':                    project.title,
        'brief_description':        project.brief_description,
        'primary_commodity':        primary,
        'secondary_commodities':    secondary,
        'project_types':            project_types,
        'project_objectives':       project_objectives,
        'project_objectives_other': project.project_objectives_other,
        'expected_outcomes':        expected_outcomes,
        'expected_outcomes_other':  project.expected_outcomes_other,
    }


@extend_schema(
    tags=['Admin - DPR Projects'],
    summary='Get one DPR project with all sections (read-only)',
    description=(
        'Returns project meta, FPO summary, and per-section {data, readiness} pairs. '
        'Sections not yet created for this project return {data: null, readiness: null}. '
        'For admin oversight only — no writes.'
    ),
)
class DPRProjectAdminDetailView(APIView):
    permission_classes = [IsAuthenticated, IsSubAdminOrSuperAdmin]

    def get(self, request, project_uuid):
        try:
            project = DPRProject.objects.select_related('fpo').get(uuid=project_uuid)
        except DPRProject.DoesNotExist:
            return StandardResponse.error('DPR project not found', status_code=404)

        fpo = project.fpo
        sections_payload = {}

        # §2.2 Project Identification lives on the DPRProject itself (not a
        # separate DPRSection* table) — special-case it so the admin UI's
        # `sections.identification` key is populated the same way as other
        # sections. Enriches FK / M2M fields with human labels so the admin
        # oversight view isn't showing raw IDs like "primary_commodity: 238".
        ident_data = _build_identification_payload(project)
        try:
            ident_readiness = identification_validators.validate_project(project)
        except Exception:
            ident_readiness = None
        sections_payload['identification'] = {'data': ident_data, 'readiness': ident_readiness}

        for key, (Model, Serializer, validator) in SECTION_REGISTRY.items():
            section = Model.objects.filter(project=project).first()
            if section is None:
                sections_payload[key] = {'data': None, 'readiness': None}
                continue

            data = Serializer(section, context={'request': request}).data
            # Enrich FK / M2M IDs with human labels so the admin oversight
            # UI renders "Grading" instead of "24". Safe no-op for sections
            # without a registered enricher; safe fallback on any error.
            data = enrich_section_data(key, data)
            try:
                readiness = validator.validate_section(section)
            except Exception:
                readiness = None
            sections_payload[key] = {'data': data, 'readiness': readiness}

        payload = {
            'project': {
                'uuid':       str(project.uuid),
                'title':      project.title,
                'status':     project.status,
                'created_at': project.created_at,
                'updated_at': project.updated_at,
            },
            'fpo': {
                'id':             fpo.id,
                'name':           fpo.name,
                'application_id': fpo.application_id,
                'district':       fpo.district,
                'tier':           fpo.tier,
                'legal_structure': fpo.legal_structure,
                'office_email':   fpo.office_email,
                'office_phone':   fpo.office_phone,
                'total_members':  fpo.total_members,
            } if fpo else None,
            'sections': sections_payload,
        }
        return Response({'status': 'success', 'message': 'DPR project retrieved', 'data': payload})
