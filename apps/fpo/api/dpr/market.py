"""
DPR §2.3.11 Market Assessment — section endpoints.

Routes (mounted at /api/fpo/dpr/):
    GET   /projects/<uuid>/sections/market/            — retrieve section + all 5 child lists
    PATCH /projects/<uuid>/sections/market/            — update section (full-replace nested lists)
    GET   /projects/<uuid>/sections/market/readiness/  — dry-run validators, no save

Ownership enforced via get_project_or_error() from projects.py.
"""

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.utils.responses import StandardResponse
from apps.database.models import DPRSectionMarket
from apps.fpo.services.dpr.market_validators import validate_section

from .projects import get_project_or_error
from .serializers import DPRSectionMarketSerializer


def _get_or_create_section(project, user):
    """One section row per project; create on first access."""
    section, _ = DPRSectionMarket.objects.get_or_create(
        project=project,
        defaults={'created_by': user, 'updated_by': user},
    )
    return section


@extend_schema(tags=['FPO - DPR §2.3.11 Market Assessment'])
class DPRMarketSectionView(APIView):
    """GET (retrieve) + PATCH (update, full-replace nested lists)."""
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='Retrieve Market section for a project')
    def get(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)
        data = DPRSectionMarketSerializer(section, context={'request': request}).data
        return StandardResponse.success(data, 'Section retrieved')

    @extend_schema(
        summary='Update Market section (full-replace nested lists)',
        description=(
            'If a nested list key (products / buyers / channel_selections / '
            'competitors / risks) is present in the payload, the whole list is '
            'wiped and recreated. Absent keys leave that list untouched.'
        ),
    )
    def patch(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)
        ser = DPRSectionMarketSerializer(
            section, data=request.data, partial=True, context={'request': request},
        )
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=400)
        ser.save()
        section.refresh_from_db()
        data = DPRSectionMarketSerializer(section, context={'request': request}).data
        return StandardResponse.success(data, 'Section updated')


@extend_schema(
    tags=['FPO - DPR §2.3.11 Market Assessment'],
    summary='Run validators on Market section (no save)',
    description='Returns errors, warnings, is_complete flag per KAU spec §2.3.11 rules (Cat A-I).',
)
class DPRMarketSectionReadinessView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        section = _get_or_create_section(project, request.user)
        result = validate_section(section)
        return StandardResponse.success(result, 'Readiness computed')
