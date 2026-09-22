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
from apps.database.models import DPRSectionComponents
from apps.fpo.services.dpr import rule_engine
from apps.fpo.services.dpr import components_validators, identification_validators

from .projects import get_project_or_error


# Section keys that MUST be completed before the rest of the wizard unlocks.
# Everything else stays greyed-out on the sidebar until these two return
# `is_complete: True` from their validators. Deliberately kept short —
# adding a third seed step would push wizard onboarding time up and users
# already have plenty of section-level guardrails downstream.
SEED_SECTION_KEYS = ('identification', 'components')


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

        # Soft-lock seed sections: the rest of the wizard is greyed out
        # in the sidebar until Identification + Components are both
        # complete. Once unlocked, stays unlocked forever — subsequent
        # edits that break completeness don't re-lock the wizard.
        seed_status: dict[str, bool] = {}
        # Identification lives on DPRProject itself.
        seed_status['identification'] = identification_validators.validate_project(project)['is_complete']
        # Components is a section — 1:1 with project; may not exist yet
        # for brand-new DPRs.
        try:
            components_section = DPRSectionComponents.objects.get(project=project)
            seed_status['components'] = components_validators.validate_section(components_section)['is_complete']
        except DPRSectionComponents.DoesNotExist:
            seed_status['components'] = False
        seed_sections_complete = all(seed_status[k] for k in SEED_SECTION_KEYS)

        return StandardResponse.success({
            'engine_enabled': rule_engine.is_engine_enabled(),
            'applicability': applicability,
            'visible_sections': visible,
            'mandatory_sections': mandatory,
            # Sidebar soft-lock signals — FE greys out non-seed sections
            # until `seed_sections_complete` flips to True.
            'seed_section_keys': list(SEED_SECTION_KEYS),
            'seed_section_status': seed_status,
            'seed_sections_complete': seed_sections_complete,
        }, 'Applicability computed')
