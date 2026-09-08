"""
DPR Config — Admin CRUD endpoints for the KAU Central Administrator.

Per KAU RCD reply B.6 (2026-09-02):
    Read: any authenticated admin (sub_admin + super_admin) — for visibility.
    Write: super_admin group only — enforced by IsSuperAdminOrReadOnly.
    Audit: every mutation writes an AuditLog row (action=DPR_CONFIG_CHANGE)
           capturing {key, old_value, new_value, min/max/unit changes if any}.

Endpoints:
    GET  /api/admin/dpr/config/                  — list all config rows (grouped
                                                    by category in response)
    GET  /api/admin/dpr/config/<int:pk>/         — retrieve one
    PATCH /api/admin/dpr/config/<int:pk>/        — super_admin only; audits
    POST /api/admin/dpr/config/<int:pk>/reset/   — super_admin only; sets value
                                                    back to default_value; audits

Not exposed:
    POST/DELETE — config rows are created/deleted only through data migrations
                  or seed scripts. Admins tweak existing values, they don't
                  add or delete parameters.
"""
from typing import Any

from drf_spectacular.utils import extend_schema, OpenApiExample
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models.generic import AuditLog
from apps.core.permissions.rbac import IsSuperAdminOrReadOnly
from apps.core.utils.responses import StandardResponse
from apps.database.models import DPRConfig


# ─────────────────────────────────────────────────────────────────────────────
# Serializer — read-only + change-only-value shape
# ─────────────────────────────────────────────────────────────────────────────

class DPRConfigReadSerializer(serializers.ModelSerializer):
    """Full read shape. Includes provenance so admin UI can show 'Last changed by'."""

    updated_by_email = serializers.SerializerMethodField()

    class Meta:
        model = DPRConfig
        fields = (
            'id', 'key', 'category', 'value_type', 'value', 'default_value',
            'label', 'description', 'unit', 'min_value', 'max_value',
            'is_editable', 'updated_at', 'updated_by_email',
        )
        read_only_fields = fields  # entire serializer is read-only

    def get_updated_by_email(self, obj):
        return obj.updated_by.email if obj.updated_by_id else None


class DPRConfigUpdateSerializer(serializers.Serializer):
    """Value-only PATCH. Admins cannot change key / value_type / label /
    description / bounds — those are set by the seed migration. This keeps
    audit trails clean (only the value changes) and prevents admins from
    breaking calculation code that expects a specific key/type."""

    value = serializers.JSONField()

    def validate_value(self, val: Any) -> Any:
        cfg: DPRConfig = self.context['instance']
        # Type coercion + validation against value_type + min/max.
        vt = cfg.value_type
        if vt == DPRConfig.ValueType.DECIMAL:
            try:
                from decimal import Decimal
                dec = Decimal(str(val))
            except Exception as exc:
                raise serializers.ValidationError(f'Not a valid decimal: {val!r}') from exc
            if cfg.min_value is not None and dec < Decimal(str(cfg.min_value)):
                raise serializers.ValidationError(f'Value must be >= {cfg.min_value}.')
            if cfg.max_value is not None and dec > Decimal(str(cfg.max_value)):
                raise serializers.ValidationError(f'Value must be <= {cfg.max_value}.')
            return str(dec)  # store as string in JSON to preserve precision
        if vt == DPRConfig.ValueType.INT:
            try:
                iv = int(val)
            except (TypeError, ValueError) as exc:
                raise serializers.ValidationError(f'Not a valid integer: {val!r}') from exc
            if cfg.min_value is not None and iv < int(cfg.min_value):
                raise serializers.ValidationError(f'Value must be >= {cfg.min_value}.')
            if cfg.max_value is not None and iv > int(cfg.max_value):
                raise serializers.ValidationError(f'Value must be <= {cfg.max_value}.')
            return iv
        if vt == DPRConfig.ValueType.STRING:
            return str(val)
        if vt == DPRConfig.ValueType.BOOL:
            if isinstance(val, bool):
                return val
            if isinstance(val, str):
                return val.strip().lower() in {'true', '1', 'yes'}
            raise serializers.ValidationError(f'Not a valid boolean: {val!r}')
        raise serializers.ValidationError(f'Unknown value_type on config: {vt!r}')


# ─────────────────────────────────────────────────────────────────────────────
# Audit helper
# ─────────────────────────────────────────────────────────────────────────────

def _audit_change(cfg: DPRConfig, old_value: Any, new_value: Any, user, request) -> None:
    """Log a DPR config mutation. Uses AuditLog.log() so the standard fields
    (IP address, user agent, changes JSON) are populated consistently."""
    AuditLog.log(
        user=user,
        action=AuditLog.Action.DPR_CONFIG_CHANGE,
        instance=cfg,
        request=request,
        changes={
            'key': cfg.key,
            'old_value': old_value,
            'new_value': new_value,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# ViewSets
# ─────────────────────────────────────────────────────────────────────────────

class DPRConfigListView(APIView):
    """GET — list all config rows, grouped by category in the response."""

    permission_classes = [IsAuthenticated, IsSuperAdminOrReadOnly]

    @extend_schema(
        tags=['Admin — DPR Config'],
        summary='List all DPR config parameters (grouped by category)',
        description='Returns every DPR config row grouped under its category. '
                    'Read is open to all admins; PATCH is super_admin only.',
    )
    def get(self, request):
        rows = DPRConfig.objects.all().order_by('category', 'key')
        data = DPRConfigReadSerializer(rows, many=True).data
        # Group by category for the admin UI
        grouped: dict[str, list] = {}
        for row in data:
            grouped.setdefault(row['category'], []).append(row)
        return StandardResponse.success(
            {'categories': grouped, 'count': len(data)},
            'DPR config retrieved',
        )


class DPRConfigDetailView(APIView):
    """GET (retrieve) + PATCH (update value only). Reset via /reset/ action."""

    permission_classes = [IsAuthenticated, IsSuperAdminOrReadOnly]

    def _get_obj(self, pk):
        try:
            return DPRConfig.objects.get(pk=pk)
        except DPRConfig.DoesNotExist:
            return None

    @extend_schema(tags=['Admin — DPR Config'])
    def get(self, request, pk):
        cfg = self._get_obj(pk)
        if cfg is None:
            return StandardResponse.error('Config parameter not found', status_code=404)
        return StandardResponse.success(DPRConfigReadSerializer(cfg).data, 'Retrieved')

    @extend_schema(
        tags=['Admin — DPR Config'],
        summary='Update a DPR config parameter value (super_admin only)',
        description='PATCH accepts only `{ "value": <new_value> }`. '
                    'Type + bounds enforced against the row\'s value_type / min / max. '
                    'Every successful mutation writes an AuditLog row.',
        request=DPRConfigUpdateSerializer,
        examples=[
            OpenApiExample(
                'Update discount rate',
                value={'value': '12.5'},
                request_only=True,
            ),
        ],
    )
    def patch(self, request, pk):
        cfg = self._get_obj(pk)
        if cfg is None:
            return StandardResponse.error('Config parameter not found', status_code=404)
        if not cfg.is_editable:
            return StandardResponse.error(
                f'{cfg.key} is marked read-only and cannot be edited.',
                status_code=400,
            )
        ser = DPRConfigUpdateSerializer(data=request.data, context={'instance': cfg})
        if not ser.is_valid():
            return StandardResponse.error(ser.errors, status_code=400)

        old_value = cfg.value
        new_value = ser.validated_data['value']
        if old_value == new_value:
            return StandardResponse.success(
                DPRConfigReadSerializer(cfg).data,
                'No change — value already matched.',
            )
        cfg.value = new_value
        cfg.updated_by = request.user
        cfg.save(update_fields=['value', 'updated_by', 'updated_at'])
        _audit_change(cfg, old_value, new_value, request.user, request)
        return StandardResponse.success(
            DPRConfigReadSerializer(cfg).data,
            f'{cfg.label} updated.',
        )


class DPRConfigResetView(APIView):
    """POST — reset a config row to its default_value. Super_admin only."""

    permission_classes = [IsAuthenticated, IsSuperAdminOrReadOnly]

    @extend_schema(
        tags=['Admin — DPR Config'],
        summary='Reset a DPR config parameter to its default (super_admin only)',
        description='POST with empty body. Sets value back to default_value + audits.',
        request=None,
        responses=DPRConfigReadSerializer,
    )
    def post(self, request, pk):
        try:
            cfg = DPRConfig.objects.get(pk=pk)
        except DPRConfig.DoesNotExist:
            return StandardResponse.error('Config parameter not found', status_code=404)
        if not cfg.is_editable:
            return StandardResponse.error(
                f'{cfg.key} is marked read-only.', status_code=400,
            )
        old_value = cfg.value
        if old_value == cfg.default_value:
            return StandardResponse.success(
                DPRConfigReadSerializer(cfg).data,
                'Already at default.',
            )
        cfg.value = cfg.default_value
        cfg.updated_by = request.user
        cfg.save(update_fields=['value', 'updated_by', 'updated_at'])
        _audit_change(cfg, old_value, cfg.default_value, request.user, request)
        return StandardResponse.success(
            DPRConfigReadSerializer(cfg).data,
            f'{cfg.label} reset to default.',
        )
