"""
Admin — DPR Project Applicability preview (Phase 6e).

Admin-scoped read of the rule engine's decisions for any FPO's project.
Mirrors the FPO-facing `applicability` endpoint but permission-checks for
`IsSubAdminOrSuperAdmin` so KAU staff can inspect + validate rules during
UAT without needing to log in as the FPO.

Endpoint:
    GET /api/admin/dpr/projects/<uuid>/applicability/

Response shape adds two admin-only fields on top of the FPO view:
    - `selected_component_codes`: which components the project has → helps
      the admin see WHY a section is hidden (e.g. "raw-material is H
      because cold_storage is selected").
    - `triggering_rules`: per hidden/mandatory section, which specific
      DPRComponentApplicability rows drove that decision.

Author: Athul Gopan (Kefi Tech Solutions)
"""
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.permissions.rbac import IsSubAdminOrSuperAdmin
from apps.core.utils.responses import StandardResponse
from apps.database.models import (
    DPRComponentApplicability,
    DPRProject,
    DPRSectionComponents,
)
from apps.fpo.services.dpr import rule_engine


@extend_schema(tags=['Admin — DPR Applicability'])
class AdminProjectApplicabilityView(APIView):
    """GET applicability decision + rule provenance for one project."""

    permission_classes = [IsAuthenticated, IsSubAdminOrSuperAdmin]

    def get(self, request, project_uuid):
        try:
            project = DPRProject.objects.get(uuid=project_uuid, is_deleted=False)
        except DPRProject.DoesNotExist:
            return StandardResponse.error('DPR project not found', status_code=404)

        applicability = rule_engine.evaluate_data_element(project)
        visible = rule_engine.visible_sections(project)
        mandatory = rule_engine.mandatory_sections(project)

        # Which components does this project have?
        section_components = getattr(project, 'section_components', None)
        selected_component_ids = []
        selected_component_codes = []
        if section_components:
            selected = list(
                section_components.components.values('id', 'code', 'label_en')
            )
            selected_component_ids = [c['id'] for c in selected]
            selected_component_codes = [
                {'id': c['id'], 'code': c['code'], 'label': c['label_en']}
                for c in selected
            ]

        # For each non-Optional section, list the rule rows that produced it —
        # gives admin an explanation for the decision.
        triggering_rules: dict[str, list[dict]] = {}
        if selected_component_ids:
            rules = (
                DPRComponentApplicability.objects
                .filter(component_id__in=selected_component_ids)
                .select_related('component')
                .values(
                    'data_element_key', 'applicability',
                    'component__code', 'component__label_en', 'notes',
                )
            )
            for r in rules:
                key = r['data_element_key']
                triggering_rules.setdefault(key, []).append({
                    'component_code': r['component__code'],
                    'component_label': r['component__label_en'],
                    'applicability': r['applicability'],
                    'notes': r['notes'],
                })

        return StandardResponse.success({
            'engine_enabled': rule_engine.is_engine_enabled(),
            'applicability': applicability,
            'visible_sections': visible,
            'mandatory_sections': mandatory,
            'selected_components': selected_component_codes,
            'triggering_rules': triggering_rules,
        }, 'Applicability preview computed')
