"""
DPR Capital Tranche — Admin CRUD per KAU RCD B.8 / A.3 (2026-09-02).

Until the FPO-facing tranche UI (3b-4) lands, super_admins seed real tranches
per project here so the calc engine picks them up (build_capital_schedule
switches from `is_estimated=True` uniform-monthly fallback → actual timing).

Access: sub_admin can read; super_admin can write. Matches the pattern in
`config.py` (IsSuperAdminOrReadOnly).

Endpoints (mounted under /api/admin/dpr/projects/<uuid>/):
    GET    tranches/         — list all tranches for the project (ordered by month)
    POST   tranches/         — create a tranche
    GET    tranches/<pk>/    — retrieve one
    PATCH  tranches/<pk>/    — update
    DELETE tranches/<pk>/    — remove

Every mutation is auditable via the standard `AuditLog` middleware; no
extra hooks needed here since tranche edits aren't "config" changes.

Author: Athul Gopan (Kefi Tech Solutions)
"""
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.permissions.rbac import IsSuperAdminOrReadOnly
from apps.core.utils.responses import StandardResponse
from apps.database.models import DPRCapitalTranche, DPRProject


class DPRCapitalTrancheSerializer(serializers.ModelSerializer):
    """Full read/write shape. `project` set from URL, never from payload."""

    tranche_type_display = serializers.CharField(source='get_tranche_type_display', read_only=True)
    is_inflow = serializers.BooleanField(read_only=True)
    is_outflow = serializers.BooleanField(read_only=True)

    class Meta:
        model = DPRCapitalTranche
        fields = (
            'id',
            'tranche_type', 'tranche_type_display',
            'amount', 'expected_month',
            'is_actual', 'description', 'finance_field',
            'is_inflow', 'is_outflow',
            'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'tranche_type_display', 'is_inflow', 'is_outflow', 'created_at', 'updated_at')

    def validate_amount(self, value):
        # Direction is encoded via tranche_type (inflow / outflow), never
        # via sign. Negative amounts are always invalid.
        if value < 0:
            raise serializers.ValidationError('Amount must be non-negative.')
        return value

    def validate_expected_month(self, value):
        # 1-indexed within the project implementation period. Model field is
        # PositiveSmallIntegerField which allows 0, but 0 breaks the calc
        # engine's month-index arithmetic — reject explicitly.
        if value < 1:
            raise serializers.ValidationError('expected_month is 1-indexed; must be >= 1.')
        return value


def _get_project_or_404(project_uuid):
    try:
        return DPRProject.objects.get(uuid=project_uuid, is_deleted=False)
    except DPRProject.DoesNotExist:
        return None


@extend_schema(tags=['Admin — DPR Tranches'])
class DPRCapitalTrancheListView(APIView):
    """GET + POST for a project's tranches."""

    permission_classes = [IsAuthenticated, IsSuperAdminOrReadOnly]

    def get(self, request, project_uuid):
        project = _get_project_or_404(project_uuid)
        if project is None:
            return StandardResponse.error('DPR project not found', status_code=404)
        rows = project.capital_tranches.all().order_by('expected_month', 'id')
        return StandardResponse.success(
            DPRCapitalTrancheSerializer(rows, many=True).data,
            f'{rows.count()} tranche(s) retrieved',
        )

    def post(self, request, project_uuid):
        project = _get_project_or_404(project_uuid)
        if project is None:
            return StandardResponse.error('DPR project not found', status_code=404)
        ser = DPRCapitalTrancheSerializer(data=request.data)
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=400)
        tranche = ser.save(project=project, created_by=request.user, updated_by=request.user)
        return StandardResponse.success(
            DPRCapitalTrancheSerializer(tranche).data, 'Tranche created', status_code=201,
        )


@extend_schema(tags=['Admin — DPR Tranches'])
class DPRCapitalTrancheDetailView(APIView):
    """GET / PATCH / DELETE a single tranche."""

    permission_classes = [IsAuthenticated, IsSuperAdminOrReadOnly]

    def _get_obj(self, project_uuid, pk):
        project = _get_project_or_404(project_uuid)
        if project is None:
            return None, StandardResponse.error('DPR project not found', status_code=404)
        try:
            tranche = DPRCapitalTranche.objects.get(pk=pk, project=project)
        except DPRCapitalTranche.DoesNotExist:
            return None, StandardResponse.error('Tranche not found', status_code=404)
        return tranche, None

    def get(self, request, project_uuid, pk):
        obj, err = self._get_obj(project_uuid, pk)
        if err:
            return err
        return StandardResponse.success(DPRCapitalTrancheSerializer(obj).data, 'Retrieved')

    def patch(self, request, project_uuid, pk):
        obj, err = self._get_obj(project_uuid, pk)
        if err:
            return err
        ser = DPRCapitalTrancheSerializer(obj, data=request.data, partial=True)
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=400)
        tranche = ser.save(updated_by=request.user)
        return StandardResponse.success(DPRCapitalTrancheSerializer(tranche).data, 'Tranche updated')

    def delete(self, request, project_uuid, pk):
        obj, err = self._get_obj(project_uuid, pk)
        if err:
            return err
        obj.delete()
        return StandardResponse.success(None, 'Tranche deleted')
