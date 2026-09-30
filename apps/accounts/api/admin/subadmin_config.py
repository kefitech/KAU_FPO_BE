"""
Sub-Admin Config API — KAU suggestion #1.

Super admin edits the district cap + scheme/training expiry windows from
one screen. Values live in the SubAdminConfig singleton table; every
write busts the Redis config cache used by the cap helper.

GET   /api/admin/sub-admin-config/    → returns { global_cap, scheme_expiry_days,
                                                  training_expiry_days,
                                                  district_caps: { TSR: 40, ... } }
PATCH /api/admin/sub-admin-config/    → accepts any subset of the above shape
"""

from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.views import APIView

from apps.core.permissions.rbac import IsSuperAdmin
from apps.core.services.subadmin_district import bust_config_cache
from apps.core.utils.constants import District
from apps.core.utils.responses import StandardResponse
from apps.database.models import SubAdminConfig


VALID_DISTRICTS = {code for code, _ in District.choices}


class DistrictCapsSerializer(serializers.Serializer):
    """Free-form dict; keys are district codes, values are ints ≥ 0.

    Handled with `dict` field type + manual validation so we don't have to
    declare 14 explicit sub-fields.
    """

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError('district_caps must be a mapping of district code to integer.')
        clean = {}
        for k, v in data.items():
            code = str(k).upper().strip()
            if code not in VALID_DISTRICTS:
                raise serializers.ValidationError({code: f'Unknown district code "{code}".'})
            if v is None or v == '':
                clean[code] = None  # sentinel: delete the override
                continue
            try:
                iv = int(v)
                if iv < 0:
                    raise ValueError
                clean[code] = iv
            except (TypeError, ValueError):
                raise serializers.ValidationError({code: 'Cap must be a non-negative integer.'})
        return clean


class SubAdminConfigSerializer(serializers.Serializer):
    global_cap           = serializers.IntegerField(min_value=1,  required=False)
    scheme_expiry_days   = serializers.IntegerField(min_value=0,  required=False)
    training_expiry_days = serializers.IntegerField(min_value=0,  required=False)
    district_caps        = DistrictCapsSerializer(required=False)


def _to_response_shape() -> dict:
    """Read everything from SubAdminConfig and shape it for the FE."""
    rows = {r.key: r.value for r in SubAdminConfig.objects.all()}
    return {
        'global_cap':           rows.get('global_cap', 30),
        'scheme_expiry_days':   rows.get('scheme_expiry_days', 5),
        'training_expiry_days': rows.get('training_expiry_days', 5),
        'district_caps': {
            k.removeprefix('district_cap_'): v
            for k, v in rows.items()
            if k.startswith('district_cap_')
        },
    }


class SubAdminConfigView(APIView):
    permission_classes = [IsSuperAdmin]

    @extend_schema(
        tags=['Admin - Sub Admin Config'],
        summary='Read sub-admin config (cap + expiry windows)',
        responses={200: SubAdminConfigSerializer},
    )
    def get(self, request):
        return StandardResponse.success(
            data=_to_response_shape(),
            message='Sub-admin config retrieved.',
        )

    @extend_schema(
        tags=['Admin - Sub Admin Config'],
        summary='Update sub-admin config (partial)',
        description=(
            'Send any subset. `district_caps` accepts a mapping of district '
            'code → cap; sending `null` (or `""`) for a code deletes that override.'
        ),
        request=SubAdminConfigSerializer,
        responses={200: SubAdminConfigSerializer},
    )
    def patch(self, request):
        s = SubAdminConfigSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        data = s.validated_data

        with transaction.atomic():
            for key in ('global_cap', 'scheme_expiry_days', 'training_expiry_days'):
                if key in data:
                    obj, _ = SubAdminConfig.objects.get_or_create(key=key, defaults={'value': data[key]})
                    obj.value      = data[key]
                    obj.updated_by = request.user
                    obj.save(update_fields=['value', 'updated_by', 'updated_at'])

            if 'district_caps' in data:
                for code, val in data['district_caps'].items():
                    row_key = f'district_cap_{code}'
                    if val is None:
                        SubAdminConfig.objects.filter(key=row_key).delete()
                    else:
                        obj, _ = SubAdminConfig.objects.get_or_create(
                            key=row_key, defaults={'value': val},
                        )
                        obj.value      = val
                        obj.updated_by = request.user
                        obj.save(update_fields=['value', 'updated_by', 'updated_at'])

        bust_config_cache()

        return StandardResponse.success(
            data=_to_response_shape(),
            message='Sub-admin config updated.',
        )
