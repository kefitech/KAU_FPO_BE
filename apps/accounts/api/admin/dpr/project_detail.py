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
        # Promoter Profile detail (KAU AI review 2026-09-19)
        'ceo_name':                 project.ceo_name,
        'ceo_qualification':        project.ceo_qualification,
        'ceo_experience_years':     project.ceo_experience_years,
        'total_area_acreage':       str(project.total_area_acreage) if project.total_area_acreage is not None else None,
        'women_shareholding_pct':   str(project.women_shareholding_pct) if project.women_shareholding_pct is not None else None,
        'landholding_summary':      project.landholding_summary,
        'board_meeting_frequency':  project.board_meeting_frequency,
        'psc_members':              project.psc_members or [],
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

        # KAU 2026-09-19 P2.5 — AI content health summary. Compact per-chapter
        # roll-up of the placeholder-scrubber (P1.5) + consistency-check (P2.3)
        # results so the admin oversight page can render badges without
        # shipping full narrative text. Only fields KAU reviewers need at a
        # glance: chapter key, human label, has any content, needs_review,
        # counts of placeholder + consistency hits, and the truncated hit
        # lists themselves for expand-on-click.
        from apps.database.models import DPRAIContent
        from apps.database.models.dpr.ai_content import CHAPTER_KEYS, CHAPTER_LABELS
        ai_rows = {r.chapter: r for r in DPRAIContent.objects.filter(project=project)}
        ai_content_health = []
        for chapter in CHAPTER_KEYS:
            row = ai_rows.get(chapter)
            if not row:
                ai_content_health.append({
                    'chapter': chapter,
                    'chapter_display': CHAPTER_LABELS.get(chapter, chapter),
                    'has_content': False,
                    'needs_review': False,
                    'placeholder_hits_count': 0,
                    'consistency_warnings_count': 0,
                    'placeholder_hits': [],
                    'consistency_warnings': [],
                })
                continue
            hits = row.placeholder_hits or []
            warns = row.consistency_warnings or []
            # Narrative text — admin gets read-only visibility into whatever
            # the FPO currently has as active. user_edited wins over
            # original_ai (same rule as PDF rendering). candidate_regen is a
            # user-decision-pending slot so we surface it separately for
            # oversight but never as the "active" text.
            active_text = row.user_edited or row.original_ai or ''
            active_version = 'user_edited' if row.user_edited else 'original_ai'
            ai_content_health.append({
                'chapter': chapter,
                'chapter_display': row.get_chapter_display(),
                'has_content': bool(row.user_edited or row.candidate_regen),
                'needs_review': row.needs_review,
                'placeholder_hits_count': sum(h.get('count', 1) for h in hits),
                'consistency_warnings_count': len(warns),
                # Cap the inline detail — KAU can go to the full AI Content
                # page for the complete list. 8 is enough for the summary card.
                'placeholder_hits': hits[:8],
                'consistency_warnings': warns[:8],
                'active_text': active_text,
                'active_version': active_version,
                'candidate_text': row.candidate_regen or '',
            })

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
            'ai_content_health': ai_content_health,
        }
        return Response({'status': 'success', 'message': 'DPR project retrieved', 'data': payload})
