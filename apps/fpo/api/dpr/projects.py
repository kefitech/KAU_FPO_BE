"""
DPR Project endpoints — Phase 1 minimal.

Routes (mounted at /api/fpo/dpr/):
    GET    /projects/                  — list current FPO's DPR projects
    POST   /projects/                  — create a new DPR project
    GET    /projects/<uuid>/           — project detail

Ownership: user must be primary owner or an active secondary member of the FPO.
"""

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.utils.responses import StandardResponse
from apps.database.models import DPRProject
from apps.database.models.fpo import FPOUserMembership

from .serializers import DPRProjectDetailSerializer, DPRProjectSerializer


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_fpo_for_user(user):
    """Return the FPO this user belongs to, or None."""
    fpo = getattr(user, 'fpo', None)
    if fpo:
        return fpo
    membership = (
        FPOUserMembership.objects.filter(user=user, is_deleted=False)
        .select_related('fpo').first()
    )
    return membership.fpo if membership else None


def get_project_or_error(user, project_uuid):
    """Return (project, err) — err is a StandardResponse on failure."""
    fpo = get_fpo_for_user(user)
    if not fpo:
        return None, StandardResponse.error('No FPO linked to this user', status_code=403)
    try:
        project = DPRProject.objects.get(uuid=project_uuid, fpo=fpo, is_deleted=False)
    except DPRProject.DoesNotExist:
        return None, StandardResponse.error('DPR project not found', status_code=404)
    return project, None


# ─────────────────────────────────────────────────────────────────────────────
# Views
# ─────────────────────────────────────────────────────────────────────────────

@extend_schema(tags=['FPO - DPR Projects'])
class DPRProjectListCreateView(APIView):
    """List DPR projects for the current FPO, or create a new one."""
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='List DPR projects for the current FPO')
    def get(self, request):
        fpo = get_fpo_for_user(request.user)
        if not fpo:
            return StandardResponse.error('No FPO linked to this user', status_code=403)
        projects = DPRProject.objects.filter(fpo=fpo, is_deleted=False)
        data = DPRProjectSerializer(projects, many=True).data
        return StandardResponse.success(data, 'DPR projects retrieved')

    @extend_schema(
        summary='Create a new DPR project',
        description='Creates an empty project shell. Section data is filled in via /projects/<uuid>/sections/<key>/.',
    )
    def post(self, request):
        fpo = get_fpo_for_user(request.user)
        if not fpo:
            return StandardResponse.error('No FPO linked to this user', status_code=403)

        ser = DPRProjectSerializer(data=request.data)
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=400)

        project = DPRProject.objects.create(
            fpo=fpo,
            title=ser.validated_data.get('title', ''),
            created_by=request.user,
            updated_by=request.user,
        )
        return StandardResponse.success(
            DPRProjectSerializer(project).data,
            'DPR project created',
            status_code=201,
        )


@extend_schema(tags=['FPO - DPR Projects'])
class DPRProjectDetailView(APIView):
    """
    Retrieve / update §2.2 Project Identification fields for one DPR project.

    GET  returns full detail (all §2.2 fields + status meta).
    PATCH updates any subset of §2.2 fields (validated on submit only, not on save).
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='Retrieve DPR project (§2.2 Project Identification)')
    def get(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        return StandardResponse.success(
            DPRProjectDetailSerializer(project).data,
            'DPR project retrieved',
        )

    @extend_schema(summary='Update §2.2 Project Identification fields (partial)')
    def patch(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        ser = DPRProjectDetailSerializer(project, data=request.data, partial=True)
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=400)
        ser.save(updated_by=request.user)
        return StandardResponse.success(
            DPRProjectDetailSerializer(project).data,
            'DPR project updated',
        )


@extend_schema(
    tags=['FPO - DPR Projects'],
    summary='Readiness — §2.2 Project Identification',
    description='Dry-run validator. Returns errors + warnings + is_complete flag. No writes.',
)
class DPRProjectIdentificationReadinessView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_uuid):
        from apps.fpo.services.dpr import identification_validators
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        result = identification_validators.validate_project(project)
        return StandardResponse.success(result, 'Readiness computed')
