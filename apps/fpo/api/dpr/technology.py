"""DPR §2.3.12 Technology Selection — section endpoints."""

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.utils.responses import StandardResponse
from apps.database.models import DPRSectionTechnology
from apps.fpo.services.dpr.technology_validators import validate_section

from .projects import get_project_or_error
from .serializers import DPRSectionTechnologySerializer


def _get_or_create_section(project, user):
    section, _ = DPRSectionTechnology.objects.get_or_create(
        project=project,
        defaults={'created_by': user, 'updated_by': user},
    )
    return section


@extend_schema(tags=['FPO - DPR §2.3.12 Technology'])
class DPRTechnologySectionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='Retrieve Technology section')
    def get(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)
        data = DPRSectionTechnologySerializer(section, context={'request': request}).data
        return StandardResponse.success(data, 'Section retrieved')

    @extend_schema(
        summary='Update Technology section (full-replace technologies with nested risks)',
        description='Each technology has nested `risks` list and 2 M2Ms (`reasons`, `certifications`). Sending `technologies` key does a full replace including all their nested items.',
    )
    def patch(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)
        ser = DPRSectionTechnologySerializer(
            section, data=request.data, partial=True, context={'request': request},
        )
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=400)
        ser.save()
        section.refresh_from_db()
        data = DPRSectionTechnologySerializer(section, context={'request': request}).data
        return StandardResponse.success(data, 'Section updated')


@extend_schema(tags=['FPO - DPR §2.3.12 Technology'], summary='Run validators (no save)')
class DPRTechnologySectionReadinessView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)
        result = validate_section(section)
        return StandardResponse.success(result, 'Readiness computed')
