"""
DPR Pre-Flight — check whether a project can currently be Generated as a
versioned banker PDF.

Route (mounted under /api/fpo/dpr/):
    GET  /projects/<uuid>/pre-flight/

Returns:
    {
        'can_generate': bool,
        'blockers': [
            {
                'message':       'Finance §E — no revenue assumption...',
                'target':        'wizard',
                'section_key':   'finance',
                'section_label': 'Finance',
            },
            {
                'message':       'Executive Summary narrative is stale...',
                'target':        'ai-content',
                'chapter':       'executive_summary',
                'chapter_label': 'Executive Summary',
            },
            ...
        ]
    }

The FE renders this as an amber banner on the DPR Documents page and
disables the Generate button while `can_generate == false`. Each blocker
carries a `target` + section_key / chapter so the FE can build a "Fix in
section →" jump link straight to the source of the problem.

Applicability-matrix hidden sections are filtered out — no point sending
the FPO to a section the admin explicitly turned off.

Author: Athul Gopan (Kefi Tech Solutions)
"""
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.utils.responses import StandardResponse
from apps.fpo.services.dpr.blockers import get_blockers

from .projects import get_project_or_error


@extend_schema(tags=['FPO - DPR Calculation'])
class DPRPreFlightView(APIView):
    """GET the current list of blockers that would prevent this project's
    versioned Generate flow from succeeding.

    Side-effect-free — just runs the same _pre_final_validation as Generate
    but returns the list instead of raising. Safe to poll from the FE."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='Pre-flight check for DPR generation',
        description=(
            'Returns the list of blockers (if any) that must be fixed before '
            'a versioned DPR PDF can be generated. Each blocker carries a '
            'target (`wizard` | `ai-content`) plus section_key / chapter so '
            'the FE can jump directly to the source. Hidden sections (per '
            'the applicability matrix) are filtered out.'
        ),
        responses={200: dict},
    )
    def get(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        result = get_blockers(project)
        return StandardResponse.success(result, message='Pre-flight computed')
