"""
DPR §2.3.5 Proposed Products and Services — section endpoints.

Routes:
    GET   /projects/<uuid>/sections/products/
    PATCH /projects/<uuid>/sections/products/
    GET   /projects/<uuid>/sections/products/readiness/
"""

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.utils.responses import StandardResponse
from apps.database.models import DPRSectionProducts
from apps.fpo.services.dpr.products_validators import validate_section

from .projects import get_project_or_error
from .serializers import DPRSectionProductsSerializer


def _get_or_create_section(project, user):
    section, _ = DPRSectionProducts.objects.get_or_create(
        project=project,
        defaults={'created_by': user, 'updated_by': user},
    )
    return section


@extend_schema(tags=['FPO - DPR §2.3.5 Products & Services'])
class DPRProductsSectionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='Retrieve Products & Services section')
    def get(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)
        data = DPRSectionProductsSerializer(section, context={'request': request}).data
        return StandardResponse.success(data, 'Section retrieved')

    @extend_schema(summary='Update Products & Services (full-replace items list)')
    def patch(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)
        ser = DPRSectionProductsSerializer(
            section, data=request.data, partial=True, context={'request': request},
        )
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=400)
        ser.save()
        section.refresh_from_db()
        data = DPRSectionProductsSerializer(section, context={'request': request}).data
        return StandardResponse.success(data, 'Section updated')


@extend_schema(
    tags=['FPO - DPR §2.3.5 Products & Services'],
    summary='Run validators (no save)',
)
class DPRProductsSectionReadinessView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)
        result = validate_section(section)
        return StandardResponse.success(result, 'Readiness computed')
