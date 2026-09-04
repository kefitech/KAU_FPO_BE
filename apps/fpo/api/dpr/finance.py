"""DPR §2.3.18 Financial Information and Means of Finance — section endpoints."""

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.utils.responses import StandardResponse
from apps.database.models import DPRSectionFinance
from apps.fpo.services.dpr.finance_validators import validate_section

from .projects import get_project_or_error
from .serializers import DPRSectionFinanceSerializer


def _get_or_create_section(project, user):
    section, _ = DPRSectionFinance.objects.get_or_create(
        project=project,
        defaults={'created_by': user, 'updated_by': user},
    )
    return section


@extend_schema(tags=['FPO - DPR §2.3.18 Finance'])
class DPRFinanceSectionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='Retrieve Finance section')
    def get(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)
        data = DPRSectionFinanceSerializer(section, context={'request': request}).data
        return StandardResponse.success(data, 'Section retrieved')

    @extend_schema(
        summary='Update Finance section',
        description=(
            'Covers 9 KAU categories A-I. Costs (Cat A), Means of Finance (Cat B), '
            'Working Capital (Cat C), Operating Expenses (Cat D), Revenue Assumptions (Cat E), '
            'Loan Details (Cat F), Subsidy (Cat G), Existing Financial Position (Cat H), '
            'Financial Assumptions (Cat I). Nested lists: revenue_assumptions, year_history.'
        ),
    )
    def patch(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)
        ser = DPRSectionFinanceSerializer(
            section, data=request.data, partial=True, context={'request': request},
        )
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=400)
        ser.save()
        section.refresh_from_db()
        data = DPRSectionFinanceSerializer(section, context={'request': request}).data
        return StandardResponse.success(data, 'Section updated')


@extend_schema(tags=['FPO - DPR §2.3.18 Finance'], summary='Run validators (no save)')
class DPRFinanceSectionReadinessView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)
        result = validate_section(section)
        return StandardResponse.success(result, 'Readiness computed')
