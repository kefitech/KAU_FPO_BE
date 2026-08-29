"""
DPR §2.3.2 Project Components — section endpoints.

Routes (mounted at /api/fpo/dpr/):
    GET   /projects/<uuid>/sections/components/            — retrieve section
    PATCH /projects/<uuid>/sections/components/            — update (M2M + "other" text fields)
    GET   /projects/<uuid>/sections/components/readiness/  — dry-run validators
"""

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.utils.responses import StandardResponse
from apps.database.models import DPRSectionComponents
from apps.fpo.services.dpr.components_validators import validate_section

from .projects import get_project_or_error
from .serializers import DPRSectionComponentsSerializer


def _get_or_create_section(project, user):
    section, _ = DPRSectionComponents.objects.get_or_create(
        project=project,
        defaults={'created_by': user, 'updated_by': user},
    )
    return section


@extend_schema(tags=['FPO - DPR §2.3.2 Project Components'])
class DPRComponentsSectionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='Retrieve Project Components section')
    def get(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)
        data = DPRSectionComponentsSerializer(section, context={'request': request}).data
        return StandardResponse.success(data, 'Section retrieved')

    @extend_schema(
        summary='Update Project Components section (M2M + Others text fields)',
        description=(
            'M2M `components` is a full replace on each PATCH. '
            'The 6 `other_<group>` CharFields are only meaningful when the '
            'corresponding "_other" component (e.g. `primary_prod_other`) is in `components`.'
        ),
    )
    def patch(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)
        ser = DPRSectionComponentsSerializer(
            section, data=request.data, partial=True, context={'request': request},
        )
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=400)
        ser.save()
        section.refresh_from_db()
        data = DPRSectionComponentsSerializer(section, context={'request': request}).data
        return StandardResponse.success(data, 'Section updated')


@extend_schema(
    tags=['FPO - DPR §2.3.2 Project Components'],
    summary='Run validators on Project Components section (no save)',
    description='At least one component; "Others (Specify)" text required when a group\'s "_other" component is picked.',
)
class DPRComponentsSectionReadinessView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)
        result = validate_section(section)
        return StandardResponse.success(result, 'Readiness computed')
