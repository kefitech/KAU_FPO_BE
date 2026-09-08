"""
DPR Risk Matrix — Admin CRUD endpoints per KAU RCD reply B.9 (2026-09-02).

Read: any authenticated admin (visibility).
Write: super_admin only (matrix is a system-wide policy).

Every mutation invalidates the DPRRiskMatrixCell in-memory cache so the
next calc engine call reads fresh values without a server restart.

Endpoints:
    GET  /api/admin/dpr/risk-matrix/                    — list all cells
    POST /api/admin/dpr/risk-matrix/                    — add a cell (rare — 3×3 default seeded)
    PATCH /api/admin/dpr/risk-matrix/<int:pk>/          — edit cell.risk_class or score
    DELETE /api/admin/dpr/risk-matrix/<int:pk>/         — remove a cell

Audit log — reuses `DPR_CONFIG_CHANGE` action (this is admin-controlled
configuration in the same category as DPRConfig).

Author: Athul Gopan (Kefi Tech Solutions)
"""
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.models.generic import AuditLog
from apps.core.permissions.rbac import IsSuperAdminOrReadOnly
from apps.core.utils.responses import StandardResponse
from apps.database.models import DPRRiskMatrixCell


class DPRRiskMatrixCellSerializer(serializers.ModelSerializer):
    class Meta:
        model = DPRRiskMatrixCell
        fields = ('id', 'probability', 'impact', 'risk_class', 'score', 'updated_at')
        read_only_fields = ('id', 'updated_at')


def _audit(cfg: DPRRiskMatrixCell, before: dict, after: dict, user, request) -> None:
    AuditLog.log(
        user=user,
        action=AuditLog.Action.DPR_CONFIG_CHANGE,
        instance=cfg,
        request=request,
        changes={
            'model': 'DPRRiskMatrixCell',
            'cell': f'{cfg.probability}×{cfg.impact}',
            'before': before,
            'after': after,
        },
    )


@extend_schema(tags=['Admin — DPR Risk Matrix'])
class DPRRiskMatrixListView(APIView):
    """GET + POST for the risk matrix cells."""

    permission_classes = [IsAuthenticated, IsSuperAdminOrReadOnly]

    def get(self, request):
        cells = DPRRiskMatrixCell.objects.all().order_by('probability', 'impact')
        data = DPRRiskMatrixCellSerializer(cells, many=True).data
        # Group by probability so admin UI can render a proper grid
        by_prob: dict[str, list] = {}
        for row in data:
            by_prob.setdefault(row['probability'], []).append(row)
        return StandardResponse.success(
            {'cells': data, 'grouped_by_probability': by_prob, 'count': len(data)},
            'Risk matrix retrieved',
        )

    def post(self, request):
        ser = DPRRiskMatrixCellSerializer(data=request.data)
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=400)
        cell = ser.save()
        DPRRiskMatrixCell.invalidate_cache()
        _audit(cell, {}, DPRRiskMatrixCellSerializer(cell).data, request.user, request)
        return StandardResponse.success(
            DPRRiskMatrixCellSerializer(cell).data, 'Cell created', status_code=201,
        )


@extend_schema(tags=['Admin — DPR Risk Matrix'])
class DPRRiskMatrixDetailView(APIView):
    """GET / PATCH / DELETE a single cell."""

    permission_classes = [IsAuthenticated, IsSuperAdminOrReadOnly]

    def _get_obj(self, pk):
        try:
            return DPRRiskMatrixCell.objects.get(pk=pk)
        except DPRRiskMatrixCell.DoesNotExist:
            return None

    def get(self, request, pk):
        cell = self._get_obj(pk)
        if cell is None:
            return StandardResponse.error('Cell not found', status_code=404)
        return StandardResponse.success(DPRRiskMatrixCellSerializer(cell).data, 'Retrieved')

    def patch(self, request, pk):
        cell = self._get_obj(pk)
        if cell is None:
            return StandardResponse.error('Cell not found', status_code=404)
        before = DPRRiskMatrixCellSerializer(cell).data
        ser = DPRRiskMatrixCellSerializer(cell, data=request.data, partial=True)
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=400)
        cell = ser.save()
        DPRRiskMatrixCell.invalidate_cache()
        _audit(cell, before, DPRRiskMatrixCellSerializer(cell).data, request.user, request)
        return StandardResponse.success(DPRRiskMatrixCellSerializer(cell).data, 'Cell updated')

    def delete(self, request, pk):
        cell = self._get_obj(pk)
        if cell is None:
            return StandardResponse.error('Cell not found', status_code=404)
        before = DPRRiskMatrixCellSerializer(cell).data
        cell.delete()
        DPRRiskMatrixCell.invalidate_cache()
        # Log delete separately — instance no longer exists so pass a stub
        AuditLog.log(
            user=request.user,
            action=AuditLog.Action.DPR_CONFIG_CHANGE,
            request=request,
            changes={'model': 'DPRRiskMatrixCell', 'action': 'delete', 'before': before},
        )
        return StandardResponse.success(None, 'Cell deleted')
