"""
DPR Applicability — Admin CRUD per KAU RCD A.1 (Phase 6c, 2026-09-03).

Level 1 M/O/H matrix editor. Admin picks how each of the 22 DPR sections
applies to each of the 34 project components — Mandatory / Optional /
Hidden. Missing rules default to Optional in the engine, so the admin
only encodes explicit cases.

Level 2 field-level rules are NOT admin-editable in Phase 6c per the
"non-technical admin" scope decision (see plan doc). Field rules are
seeded via `scripts/seed_dpr_field_rules.py` — devs edit the seed when
KAU asks during UAT.

Access:
    Read  — any authenticated admin (sub_admin + super_admin).
    Write — super_admin only (IsSuperAdminOrReadOnly).
    Audit — every write logs AuditLog(DPR_APPLICABILITY_CHANGE) with
            {op, component_id, section_key, old, new}.

Endpoints (mounted under /api/admin/dpr/applicability/):
    GET  /matrix/           — full matrix in shape optimised for the
                              admin grid UI (see MatrixView docstring)
    PATCH /                 — bulk upsert: [{component_id, data_element_key,
                              applicability, notes?}, ...]
    DELETE /<int:pk>/       — remove a single rule (revert to default O)

Author: Athul Gopan (Kefi Tech Solutions)
"""
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.models.generic import AuditLog
from apps.core.permissions.rbac import IsSuperAdminOrReadOnly
from apps.core.utils.responses import StandardResponse
from apps.database.models import DPRComponent, DPRComponentApplicability
from apps.fpo.services.dpr.rule_engine import ALL_SECTION_KEYS


# ─────────────────────────────────────────────────────────────────────────────
# Serializers
# ─────────────────────────────────────────────────────────────────────────────

class ApplicabilityRuleSerializer(serializers.ModelSerializer):
    """Compact shape used for PATCH responses + detail views."""

    class Meta:
        model = DPRComponentApplicability
        fields = ('id', 'component', 'data_element_key', 'applicability', 'notes',
                  'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')


class ApplicabilityCellPatchSerializer(serializers.Serializer):
    """One matrix cell to upsert. `applicability=null` deletes the rule."""

    component_id      = serializers.IntegerField(required=True)
    data_element_key  = serializers.CharField(max_length=50, required=True)
    applicability     = serializers.ChoiceField(
        choices=DPRComponentApplicability.Applicability.choices + [(None, 'Default (delete rule)')],
        required=False, allow_null=True,
    )
    notes             = serializers.CharField(required=False, allow_blank=True, default='')

    def validate_data_element_key(self, value):
        # Not a hard constraint (schema is free-text so KAU can add sections
        # later) but flag anything unexpected as a warning so admin catches
        # typos.
        if value not in ALL_SECTION_KEYS:
            # Only warn — don't reject — new sections may be added later
            pass
        return value


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _audit(user, op: str, component_id: int, section_key: str,
           old_value: str | None, new_value: str | None, notes: str = ''):
    """AuditLog row for one cell change (create / update / delete)."""
    AuditLog.objects.create(
        user=user,
        action=AuditLog.Action.DPR_APPLICABILITY_CHANGE,
        object_repr=f'component={component_id} × {section_key}',
        changes={
            'op': op,  # 'create' | 'update' | 'delete'
            'component_id': component_id,
            'section_key': section_key,
            'old_applicability': old_value,
            'new_applicability': new_value,
            'notes': notes[:200] if notes else '',
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Views
# ─────────────────────────────────────────────────────────────────────────────

@extend_schema(tags=['Admin — DPR Applicability'])
class ApplicabilityMatrixView(APIView):
    """GET the full component × section matrix in one call.

    Response shape (optimised for a client-side matrix grid):
        {
            "components": [
                {"id": 1, "code": "cold_storage", "label": "Cold Storage",
                 "group": "storage_post_harvest", "group_label": "Storage & Post-Harvest"},
                ...
            ],
            "section_keys": ["identification", "components", ..., "risk"],
            "rules": {
                # sparse map — only cells with explicit rules
                "1::raw-material": {"applicability": "H", "notes": "...", "id": 42},
                ...
            }
        }

    Cells without an entry in `rules` default to Optional (per rule engine).
    """

    permission_classes = [IsAuthenticated, IsSuperAdminOrReadOnly]

    def get(self, request):
        components = list(
            DPRComponent.objects.filter(is_active=True)
            .order_by('group', 'order', 'code')
            .values('id', 'code', 'label_en', 'group')
        )
        # Group labels — derived from the model's Group choices.
        group_labels = dict(DPRComponent.Group.choices)
        components_payload = [
            {
                'id': c['id'],
                'code': c['code'],
                'label': c['label_en'],
                'group': c['group'],
                'group_label': group_labels.get(c['group'], c['group']),
            }
            for c in components
        ]

        rules = {}
        for r in DPRComponentApplicability.objects.all().values(
            'id', 'component_id', 'data_element_key', 'applicability', 'notes',
        ):
            key = f"{r['component_id']}::{r['data_element_key']}"
            rules[key] = {
                'id': r['id'],
                'applicability': r['applicability'],
                'notes': r['notes'],
            }

        return StandardResponse.success({
            'components': components_payload,
            'section_keys': list(ALL_SECTION_KEYS),
            'rules': rules,
        }, f'{len(components_payload)} components × {len(ALL_SECTION_KEYS)} sections')


@extend_schema(tags=['Admin — DPR Applicability'])
class ApplicabilityUpsertView(APIView):
    """PATCH — bulk upsert / delete matrix cells.

    Body: single cell or list of cells. Each cell:
        {component_id, data_element_key, applicability, notes?}

        applicability values:
            'M' | 'O' | 'H'  → upsert with this value
            null / missing   → DELETE the rule (revert to default O)

    Response: list of affected cells with their new state.

    Audit: one AuditLog row per cell change.
    """

    permission_classes = [IsAuthenticated, IsSuperAdminOrReadOnly]

    def patch(self, request):
        payload = request.data
        # Normalise: single object → single-item list
        if isinstance(payload, dict):
            payload = [payload]
        if not isinstance(payload, list) or not payload:
            return StandardResponse.error(
                'Body must be a cell object or non-empty list of cells.',
                status_code=400,
            )

        # Validate all cells before mutating anything — atomic semantics.
        cells = []
        for i, raw in enumerate(payload):
            ser = ApplicabilityCellPatchSerializer(data=raw)
            if not ser.is_valid():
                return StandardResponse.error(
                    {f'row_{i}': ser.errors}, status_code=400,
                )
            cells.append(ser.validated_data)

        # Verify all component IDs exist up front — one query, not N.
        component_ids = {c['component_id'] for c in cells}
        valid_ids = set(
            DPRComponent.objects.filter(id__in=component_ids)
            .values_list('id', flat=True)
        )
        missing = component_ids - valid_ids
        if missing:
            return StandardResponse.error(
                f'Unknown component IDs: {sorted(missing)}', status_code=400,
            )

        # Apply cell by cell, auditing each.
        results = []
        for cell in cells:
            component_id = cell['component_id']
            section_key = cell['data_element_key']
            new_value = cell.get('applicability')
            notes = cell.get('notes', '') or ''

            existing = DPRComponentApplicability.objects.filter(
                component_id=component_id, data_element_key=section_key,
            ).first()

            if new_value is None:
                # Delete → revert to default O
                if existing:
                    old_value = existing.applicability
                    existing.delete()
                    _audit(request.user, 'delete', component_id, section_key,
                           old_value, None, existing.notes)
                    results.append({
                        'component_id': component_id,
                        'data_element_key': section_key,
                        'applicability': None,  # deleted
                        'notes': '',
                    })
                # else: no-op, nothing to delete
                continue

            if existing:
                old_value = existing.applicability
                if old_value == new_value and existing.notes == notes:
                    # No change, skip audit noise
                    results.append({
                        'id': existing.id,
                        'component_id': component_id,
                        'data_element_key': section_key,
                        'applicability': new_value,
                        'notes': notes,
                    })
                    continue
                existing.applicability = new_value
                existing.notes = notes
                existing.updated_by = request.user
                existing.save(update_fields=['applicability', 'notes',
                                              'updated_by', 'updated_at'])
                _audit(request.user, 'update', component_id, section_key,
                       old_value, new_value, notes)
                results.append({
                    'id': existing.id,
                    'component_id': component_id,
                    'data_element_key': section_key,
                    'applicability': new_value,
                    'notes': notes,
                })
            else:
                created = DPRComponentApplicability.objects.create(
                    component_id=component_id,
                    data_element_key=section_key,
                    applicability=new_value,
                    notes=notes,
                    created_by=request.user,
                    updated_by=request.user,
                )
                _audit(request.user, 'create', component_id, section_key,
                       None, new_value, notes)
                results.append({
                    'id': created.id,
                    'component_id': component_id,
                    'data_element_key': section_key,
                    'applicability': new_value,
                    'notes': notes,
                })

        return StandardResponse.success(
            {'cells': results, 'count': len(results)},
            f'{len(results)} cell(s) updated',
        )


@extend_schema(tags=['Admin — DPR Applicability'])
class ApplicabilityDeleteView(APIView):
    """DELETE /<pk>/ — remove a single rule by id.

    Alternative to sending `applicability: null` via PATCH — convenient
    when the FE only has the rule id, not the cell coordinates.
    """

    permission_classes = [IsAuthenticated, IsSuperAdminOrReadOnly]

    def delete(self, request, pk):
        try:
            obj = DPRComponentApplicability.objects.get(pk=pk)
        except DPRComponentApplicability.DoesNotExist:
            return StandardResponse.error('Rule not found', status_code=404)
        _audit(request.user, 'delete', obj.component_id, obj.data_element_key,
               obj.applicability, None, obj.notes)
        obj.delete()
        return StandardResponse.success(None, 'Rule deleted (reverted to default)')
