"""DPR §2.3.13 Land, Site Suitability and Infrastructure Readiness — section endpoints."""

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.utils.responses import StandardResponse
from apps.database.models import DPRSectionSite
from apps.fpo.services.dpr.site_validators import validate_section

from .projects import get_project_or_error
from .serializers import DPRSectionSiteSerializer


def _get_or_create_section(project, user):
    section, _ = DPRSectionSite.objects.get_or_create(
        project=project,
        defaults={'created_by': user, 'updated_by': user},
    )
    return section


@extend_schema(tags=['FPO - DPR §2.3.13 Land & Site'])
class DPRSiteSectionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='Retrieve Land & Site section')
    def get(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)
        data = DPRSectionSiteSerializer(section, context={'request': request}).data
        return StandardResponse.success(data, 'Section retrieved')

    @extend_schema(
        summary='Update Land & Site section',
        description='3 nested lists: parcels (Cat A, multi-parcel support), existing_infrastructure (Cat C), constraints (Cat H). Full-replace pattern per list.',
    )
    def patch(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)
        ser = DPRSectionSiteSerializer(
            section, data=request.data, partial=True, context={'request': request},
        )
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=400)
        ser.save()
        section.refresh_from_db()
        data = DPRSectionSiteSerializer(section, context={'request': request}).data
        return StandardResponse.success(data, 'Section updated')


@extend_schema(tags=['FPO - DPR §2.3.13 Land & Site'], summary='Run validators (no save)')
class DPRSiteSectionReadinessView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)
        result = validate_section(section)
        return StandardResponse.success(result, 'Readiness computed')
