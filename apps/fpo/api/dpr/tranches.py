"""
DPR Capital Tranches — FPO-facing CRUD per KAU RCD A.3 / B.8 (2026-09-02).

FPO users enter dated inflows (promoter contribution, loan drawdown, subsidy
release) and outflows (capex) per project. The calc engine reads these to
build a time-phased capital schedule; if absent, it falls back to a uniform
monthly split with `is_estimated=True`.

Ownership is enforced via `get_project_or_error` — user must be the primary
owner or an active secondary member of the FPO owning the project.

Endpoints (mounted under /api/fpo/dpr/projects/<uuid>/):
    GET    tranches/         — list all tranches for this project
    POST   tranches/         — create a tranche
    GET    tranches/<pk>/    — retrieve one
    PATCH  tranches/<pk>/    — update
    DELETE tranches/<pk>/    — remove

Author: Athul Gopan (Kefi Tech Solutions)
"""
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.utils.responses import StandardResponse
from apps.database.models import DPRCapitalTranche

from .projects import get_project_or_error


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
        # Tranches represent monetary events — negative values are always
        # wrong here (direction is encoded via tranche_type inflow/outflow,
        # not sign). Zero is technically legal but useless; we allow it so
        # admins can defer entering the number.
        if value < 0:
            raise serializers.ValidationError('Amount must be non-negative.')
        return value

    def validate_expected_month(self, value):
        # Model uses PositiveSmallIntegerField which permits 0. But
        # `expected_month` is documented as 1-indexed — 0 makes no sense
        # in a project timeline. Reject explicitly so the admin sees a
        # clear error rather than a silent off-by-one in the calc engine.
        if value < 1:
            raise serializers.ValidationError('expected_month is 1-indexed; must be >= 1.')
        return value


@extend_schema(tags=['FPO - DPR Tranches'])
class DPRCapitalTrancheListView(APIView):
    """GET + POST for a project's tranches (FPO-scoped)."""

    permission_classes = [IsAuthenticated]

    def get(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        rows = project.capital_tranches.all().order_by('expected_month', 'id')
        return StandardResponse.success(
            DPRCapitalTrancheSerializer(rows, many=True).data,
            f'{rows.count()} tranche(s) retrieved',
        )

    def post(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        ser = DPRCapitalTrancheSerializer(data=request.data)
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=400)
        tranche = ser.save(project=project, created_by=request.user, updated_by=request.user)
        return StandardResponse.success(
            DPRCapitalTrancheSerializer(tranche).data, 'Tranche created', status_code=201,
        )


@extend_schema(tags=['FPO - DPR Tranches'])
class DPRCapitalTrancheDetailView(APIView):
    """GET / PATCH / DELETE a single tranche (FPO-scoped)."""

    permission_classes = [IsAuthenticated]

    def _get_obj(self, user, project_uuid, pk):
        project, err = get_project_or_error(user, project_uuid)
        if err:
            return None, err
        try:
            tranche = DPRCapitalTranche.objects.get(pk=pk, project=project)
        except DPRCapitalTranche.DoesNotExist:
            return None, StandardResponse.error('Tranche not found', status_code=404)
        return tranche, None

    def get(self, request, project_uuid, pk):
        obj, err = self._get_obj(request.user, project_uuid, pk)
        if err:
            return err
        return StandardResponse.success(DPRCapitalTrancheSerializer(obj).data, 'Retrieved')

    def patch(self, request, project_uuid, pk):
        obj, err = self._get_obj(request.user, project_uuid, pk)
        if err:
            return err
        ser = DPRCapitalTrancheSerializer(obj, data=request.data, partial=True)
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=400)
        tranche = ser.save(updated_by=request.user)
        return StandardResponse.success(DPRCapitalTrancheSerializer(tranche).data, 'Tranche updated')

    def delete(self, request, project_uuid, pk):
        obj, err = self._get_obj(request.user, project_uuid, pk)
        if err:
            return err
        obj.delete()
        return StandardResponse.success(None, 'Tranche deleted')
