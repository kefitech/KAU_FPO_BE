"""
DPR Applicability — FPO-facing readonly endpoint (Phase 6d).

Per KAU RCD A.1. Exposes the rule engine's decisions for one project so
the wizard FE can filter the sidebar + badge sections as Mandatory /
Optional / Hidden.

Endpoint:
    GET /api/fpo/dpr/projects/<uuid>/applicability/

Response shape:
    {
        "engine_enabled": bool,      # feature flag — false = client should
                                      show all sections (current behaviour)
        "applicability": {           # per-section M/O/H
            "identification": "O",
            "raw-material": "H",
            ...
        },
        "visible_sections": [...],   # keys not H, in canonical order
        "mandatory_sections": [...], # keys marked M
    }

When the feature flag is OFF, `engine_enabled=False` and every section is
returned as "O" — the FE treats this as "show everything" (rollback path).

Author: Athul Gopan (Kefi Tech Solutions)
"""
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.utils.responses import StandardResponse
from apps.fpo.services.dpr import rule_engine

from .projects import get_project_or_error


@extend_schema(
    tags=['FPO - DPR Projects'],
    summary='Rule engine applicability for this project',
    description='Returns which sections are Mandatory / Optional / Hidden '
                'given the project\'s selected components. FE uses this to '
                'filter the wizard sidebar. Cheap to call — 2 queries.',
)
class DPRProjectApplicabilityView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err

        applicability = rule_engine.evaluate_data_element(project)
        visible = rule_engine.visible_sections(project)
        mandatory = rule_engine.mandatory_sections(project)

        return StandardResponse.success({
            'engine_enabled': rule_engine.is_engine_enabled(),
            'applicability': applicability,
            'visible_sections': visible,
            'mandatory_sections': mandatory,
        }, 'Applicability computed')
