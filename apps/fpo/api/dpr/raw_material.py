"""
DPR §2.3.10 Raw Material — section endpoints.

Routes (mounted at /api/fpo/dpr/):
    GET   /projects/<uuid>/sections/raw-material/            — retrieve section + all child lists
    PATCH /projects/<uuid>/sections/raw-material/            — update section (full-replace for nested lists)
    GET   /projects/<uuid>/sections/raw-material/readiness/  — dry-run validators, no save

Ownership enforced via get_project_or_error() — same rules as DPR project detail.
"""

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.utils.responses import StandardResponse
from apps.database.models import DPRSectionRawMaterial
from apps.fpo.services.dpr.raw_material_validators import validate_section

from .projects import get_project_or_error
from .serializers import DPRSectionRawMaterialSerializer


def _get_or_create_section(project, user):
    """One section row per project; create on first access."""
    section, created = DPRSectionRawMaterial.objects.get_or_create(
        project=project,
        defaults={'created_by': user, 'updated_by': user},
    )
    return section


@extend_schema(tags=['FPO - DPR §2.3.10 Raw Material'])
class DPRRawMaterialSectionView(APIView):
    """GET (retrieve) + PATCH (update, full-replace nested lists)."""
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='Retrieve Raw Material section for a project')
    def get(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)
        data = DPRSectionRawMaterialSerializer(section, context={'request': request}).data
        return StandardResponse.success(data, 'Section retrieved')

    @extend_schema(
        summary='Update Raw Material section (full-replace nested lists)',
        description=(
            'If a nested list key (materials / risks / packaging_materials / consumables) '
            'is present in the payload, the whole list is wiped and recreated. '
            'Absent keys leave that list untouched.'
        ),
    )
    def patch(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)
        ser = DPRSectionRawMaterialSerializer(
            section, data=request.data, partial=True, context={'request': request},
        )
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=400)
        ser.save()
        # Return the fresh serialized view (nested reload)
        section.refresh_from_db()
        data = DPRSectionRawMaterialSerializer(section, context={'request': request}).data
        return StandardResponse.success(data, 'Section updated')


@extend_schema(
    tags=['FPO - DPR §2.3.10 Raw Material'],
    summary='Run validators on Raw Material section (no save)',
    description='Returns errors, warnings, and is_complete flag per KAU spec §2.3.10 rules.',
)
class DPRRawMaterialSectionReadinessView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)
        result = validate_section(section)
        return StandardResponse.success(result, 'Readiness computed')
