"""
DPR §2.3.4 Proposed Project Investment — section endpoints.

Routes:
    GET   /projects/<uuid>/sections/investment/
    PATCH /projects/<uuid>/sections/investment/
    GET   /projects/<uuid>/sections/investment/readiness/
"""

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.utils.responses import StandardResponse
from apps.database.models import DPRSectionInvestment
from apps.fpo.services.dpr.investment_validators import validate_section

from .projects import get_project_or_error
from .serializers import DPRSectionInvestmentSerializer


def _get_or_create_section(project, user):
    section, _ = DPRSectionInvestment.objects.get_or_create(
        project=project,
        defaults={'created_by': user, 'updated_by': user},
    )
    return section


@extend_schema(tags=['FPO - DPR §2.3.4 Proposed Project Investment'])
class DPRInvestmentSectionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='Retrieve Proposed Project Investment section')
    def get(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)
        data = DPRSectionInvestmentSerializer(section, context={'request': request}).data
        return StandardResponse.success(data, 'Section retrieved')

    @extend_schema(
        summary='Update Proposed Project Investment (conditional — may be blank)',
        description='If estimated_project_cost is provided, it must be > 0. Section may be left entirely blank per KAU spec.',
    )
    def patch(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)
        ser = DPRSectionInvestmentSerializer(
            section, data=request.data, partial=True, context={'request': request},
        )
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=400)
        ser.save()
        section.refresh_from_db()
        data = DPRSectionInvestmentSerializer(section, context={'request': request}).data
        return StandardResponse.success(data, 'Section updated')


@extend_schema(
    tags=['FPO - DPR §2.3.4 Proposed Project Investment'],
    summary='Run validators (no save)',
)
class DPRInvestmentSectionReadinessView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)
        result = validate_section(section)
        return StandardResponse.success(result, 'Readiness computed')
