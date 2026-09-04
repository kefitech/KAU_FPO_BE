"""
DPR §2.3.3 Nature of Business — section endpoints.

Routes:
    GET   /projects/<uuid>/sections/nature-of-business/
    PATCH /projects/<uuid>/sections/nature-of-business/
    GET   /projects/<uuid>/sections/nature-of-business/readiness/
"""

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.utils.responses import StandardResponse
from apps.database.models import DPRSectionNatureOfBusiness
from apps.fpo.services.dpr.nature_of_business_validators import validate_section

from .projects import get_project_or_error
from .serializers import DPRSectionNatureOfBusinessSerializer


def _get_or_create_section(project, user):
    section, _ = DPRSectionNatureOfBusiness.objects.get_or_create(
        project=project,
        defaults={'created_by': user, 'updated_by': user},
    )
    return section


@extend_schema(tags=['FPO - DPR §2.3.3 Nature of Business'])
class DPRNatureOfBusinessSectionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='Retrieve Nature of Business section')
    def get(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)
        data = DPRSectionNatureOfBusinessSerializer(section, context={'request': request}).data
        return StandardResponse.success(data, 'Section retrieved')

    @extend_schema(summary='Update Nature of Business section (multi-select + Others text)')
    def patch(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)
        ser = DPRSectionNatureOfBusinessSerializer(
            section, data=request.data, partial=True, context={'request': request},
        )
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=400)
        ser.save()
        section.refresh_from_db()
        data = DPRSectionNatureOfBusinessSerializer(section, context={'request': request}).data
        return StandardResponse.success(data, 'Section updated')


@extend_schema(
    tags=['FPO - DPR §2.3.3 Nature of Business'],
    summary='Run validators on Nature of Business section (no save)',
)
class DPRNatureOfBusinessSectionReadinessView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)
        result = validate_section(section)
        return StandardResponse.success(result, 'Readiness computed')
