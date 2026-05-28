"""
FPO Permission Matrix API
=========================
Base Path: /api/admin/fpo-permissions/

Manages the system-wide role x action permission matrix.

GET  /api/admin/fpo-permissions/           — full matrix as grid (all roles x all actions)
POST /api/admin/fpo-permissions/           — bulk update (frontend sends changed cells)
GET  /api/admin/fpo-permissions/{role_id}/ — permissions for one specific role

Grid response shape:
    {
        "actions": [{"id": 1, "code": "can_submit", "label": "Submit Application"}, ...],
        "roles": [
            {
                "id": 5, "code": "primary", "name": "Primary User",
                "permissions": {"can_submit": true, "can_upload_docs": true, ...}
            },
            ...
        ]
    }

Bulk update request shape:
    {
        "updates": [
            {"role_id": 5, "action_code": "can_submit", "is_allowed": true},
            {"role_id": 6, "action_code": "can_submit", "is_allowed": false}
        ]
    }
"""

from rest_framework import serializers, status
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from apps.core.permissions.rbac import IsSuperAdmin
from apps.core.utils.responses import StandardResponse
from apps.core.services.translation import t
from apps.core.services.fpo_permission import invalidate_role_permission_cache
from apps.core.models.generic import MasterLookup
from apps.database.models.fpo import FPOAction, FPOMemberPermission

ROLE_CATEGORY = 'fpo_member_role'


class PermissionUpdateSerializer(serializers.Serializer):
    role_id     = serializers.IntegerField()
    action_code = serializers.CharField(max_length=50)
    is_allowed  = serializers.BooleanField()

    def validate_role_id(self, value):
        if not MasterLookup.objects.filter(id=value, category=ROLE_CATEGORY).exists():
            raise serializers.ValidationError('Invalid role id.')
        return value

    def validate_action_code(self, value):
        if not FPOAction.objects.filter(code=value, is_active=True).exists():
            raise serializers.ValidationError(f'Action "{value}" not found or inactive.')
        return value


class BulkPermissionUpdateSerializer(serializers.Serializer):
    updates = PermissionUpdateSerializer(many=True, min_length=1)


class FPOPermissionMatrixView(APIView):
    permission_classes = [IsSuperAdmin]

    @extend_schema(
        tags=['Admin - FPO Permission Matrix'],
        summary='Get full permission matrix grid',
        description='Returns all active roles x all active actions as a grid for the admin UI.',
    )
    def get(self, request):
        roles   = MasterLookup.objects.filter(category=ROLE_CATEGORY, is_active=True).order_by('code')
        actions = FPOAction.objects.filter(is_active=True).order_by('code')

        # Build permission lookup: {(role_id, action_code): is_allowed}
        perm_map = {
            (p.role_id, p.action.code): p.is_allowed
            for p in FPOMemberPermission.objects.filter(
                role__in=roles, action__in=actions
            ).select_related('action')
        }

        lang = request.language
        actions_data = [
            {'id': a.id, 'code': a.code, 'label': a.get_label(lang)}
            for a in actions
        ]

        roles_data = []
        for role in roles:
            permissions = {
                a.code: perm_map.get((role.id, a.code), False)
                for a in actions
            }
            roles_data.append({
                'id':          role.id,
                'code':        role.code,
                'name':        role.get_name(lang),
                'permissions': permissions,
            })

        return StandardResponse.success(
            data={'actions': actions_data, 'roles': roles_data},
            message=t('admin.fpo_permissions_retrieved', request.language),
        )

    @extend_schema(
        tags=['Admin - FPO Permission Matrix'],
        summary='Bulk update permission matrix',
        description='Update one or more role x action cells. Frontend sends only changed cells.',
        request=BulkPermissionUpdateSerializer,
    )
    def post(self, request):
        serializer = BulkPermissionUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return StandardResponse.error(
                t('common.validation_error', request.language),
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        updated = 0
        for item in serializer.validated_data['updates']:
            role   = MasterLookup.objects.get(id=item['role_id'])
            action = FPOAction.objects.get(code=item['action_code'])
            _, created = FPOMemberPermission.objects.update_or_create(
                role=role, action=action,
                defaults={'is_allowed': item['is_allowed']},
            )
            invalidate_role_permission_cache(role.id, item['action_code'])
            updated += 1

        return StandardResponse.success(
            data={'updated': updated},
            message=t('admin.fpo_permissions_updated', request.language),
        )


class FPORolePermissionsView(APIView):
    """GET permissions for a single role — used by admin role detail screen."""
    permission_classes = [IsSuperAdmin]

    @extend_schema(
        tags=['Admin - FPO Permission Matrix'],
        summary='Get permissions for one role',
    )
    def get(self, request, role_id):
        role = MasterLookup.objects.filter(id=role_id, category=ROLE_CATEGORY).first()
        if not role:
            return StandardResponse.error(
                t('common.not_found', request.language),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        actions = FPOAction.objects.filter(is_active=True).order_by('code')
        perm_map = {
            p.action.code: p.is_allowed
            for p in FPOMemberPermission.objects.filter(role=role).select_related('action')
        }

        lang = request.language
        permissions = [
            {
                'action_id':  a.id,
                'code':       a.code,
                'label':      a.get_label(lang),
                'is_allowed': perm_map.get(a.code, False),
            }
            for a in actions
        ]

        return StandardResponse.success(
            data={
                'role':        {'id': role.id, 'code': role.code, 'name': role.get_name(lang)},
                'permissions': permissions,
            },
            message=t('admin.fpo_permissions_retrieved', request.language),
        )
