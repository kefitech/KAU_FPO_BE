"""DPR §2.3.9 Project Capacity and Production System — section endpoints."""

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.utils.responses import StandardResponse
from apps.database.models import DPRSectionCapacity
from apps.fpo.services.dpr.capacity_validators import validate_section

from .projects import get_project_or_error
from .serializers import DPRSectionCapacitySerializer


def _get_or_create_section(project, user):
    section, _ = DPRSectionCapacity.objects.get_or_create(
        project=project,
        defaults={'created_by': user, 'updated_by': user},
    )
    return section


@extend_schema(tags=['FPO - DPR §2.3.9 Capacity & Production'])
class DPRCapacitySectionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='Retrieve Capacity & Production section')
    def get(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)
        data = DPRSectionCapacitySerializer(section, context={'request': request}).data
        return StandardResponse.success(data, 'Section retrieved')

    @extend_schema(
        summary='Update Capacity & Production section',
        description='Covers 5 KAU categories A-E. Conditional fields for Losses (has_production_loss) and Expansion (has_future_expansion).',
    )
    def patch(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)
        ser = DPRSectionCapacitySerializer(
            section, data=request.data, partial=True, context={'request': request},
        )
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=400)
        ser.save()
        section.refresh_from_db()
        data = DPRSectionCapacitySerializer(section, context={'request': request}).data
        return StandardResponse.success(data, 'Section updated')


@extend_schema(tags=['FPO - DPR §2.3.9 Capacity & Production'], summary='Run validators (no save)')
class DPRCapacitySectionReadinessView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)
        result = validate_section(section)
        return StandardResponse.success(result, 'Readiness computed')
