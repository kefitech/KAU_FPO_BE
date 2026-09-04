"""DPR §2.3.19 Statutory Approvals, Licences and Regulatory Compliance — section endpoints."""

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.utils.responses import StandardResponse
from apps.database.models import DPRSectionCompliance
from apps.fpo.services.dpr.compliance_validators import validate_section

from .projects import get_project_or_error
from .serializers import DPRSectionComplianceSerializer


def _get_or_create_section(project, user):
    section, _ = DPRSectionCompliance.objects.get_or_create(
        project=project,
        defaults={'created_by': user, 'updated_by': user},
    )
    return section


@extend_schema(tags=['FPO - DPR §2.3.19 Statutory Compliance'])
class DPRComplianceSectionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='Retrieve Compliance section')
    def get(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)
        data = DPRSectionComplianceSerializer(section, context={'request': request}).data
        return StandardResponse.success(data, 'Section retrieved')

    @extend_schema(
        summary='Update Statutory Compliance section',
        description='Unified compliance items list covers Cat A-F (business/project/env/food/labour/insurance). Each item = FK to DPRStatutoryRegistration (or custom_name) + status + optional issuing_authority/date/remarks. Cat G handled at section level.',
    )
    def patch(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)
        ser = DPRSectionComplianceSerializer(
            section, data=request.data, partial=True, context={'request': request},
        )
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=400)
        ser.save()
        section.refresh_from_db()
        data = DPRSectionComplianceSerializer(section, context={'request': request}).data
        return StandardResponse.success(data, 'Section updated')


@extend_schema(tags=['FPO - DPR §2.3.19 Statutory Compliance'], summary='Run validators (no save)')
class DPRComplianceSectionReadinessView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)
        result = validate_section(section)
        return StandardResponse.success(result, 'Readiness computed')
