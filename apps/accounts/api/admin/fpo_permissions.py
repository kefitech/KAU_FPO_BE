"""
FPO Permission Matrix API
=========================
Base Path: /api/admin/fpo-permissions/

Manages the system-wide role x action permission matrix for ALL roles.
Actions are grouped by page (via FPOAction.menu_item FK).

GET  /api/admin/fpo-permissions/           — full matrix grid (roles x pages x actions)
POST /api/admin/fpo-permissions/           — bulk update (frontend sends changed cells only)
GET  /api/admin/fpo-permissions/{role_id}/ — permissions for one specific role, grouped by page

Grid response shape:
    {
        "pages": [
            {
                "id": 12, "label": "Dashboard", "path": "/fpo/dashboard",
                "actions": [{"id": 1, "code": "can_view_dashboard", "label": "View Dashboard"}]
            },
            ...
        ],
        "roles": [
            {
                "id": 9, "name": "primary",
                "permissions": {"can_view_dashboard": true, "can_submit": false, ...}
            },
            ...
        ]
    }

Bulk update request shape:
    {
        "updates": [
            {"role_id": 9, "action_code": "can_submit", "is_allowed": true}
        ]
    }
"""

from django.contrib.auth.models import Group
from rest_framework import serializers, status
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from apps.core.permissions.rbac import IsSuperAdmin
from apps.core.utils.responses import StandardResponse
from apps.core.services.translation import t
from apps.core.services.fpo_permission import invalidate_role_permission_cache
from apps.database.models.fpo import FPOAction, RoleActionPermission
from apps.database.models import MenuItem


def _build_pages_with_actions(actions, lang):
    """
    Group actions by their menu_item page.
    Actions with no page go into an 'unassigned' bucket.
    """
    page_map   = {}   # page_id → {page_data, actions[]}
    unassigned = []

    for action in actions:
        label = action.get_label(lang)
        action_entry = {'id': action.id, 'code': action.code, 'label': label}

        if action.menu_item_id:
            pid = action.menu_item_id
            if pid not in page_map:
                page = action.menu_item
                page_map[pid] = {
                    'id':      page.id,
                    'label':   t(page.label_key, lang) if page.label_key else page.path,
                    'path':    page.path,
                    'actions': [],
                }
            page_map[pid]['actions'].append(action_entry)
        else:
            unassigned.append(action_entry)

    pages = list(page_map.values())
    if unassigned:
        pages.append({'id': None, 'label': 'Other', 'path': None, 'actions': unassigned})

    return pages


class PermissionUpdateSerializer(serializers.Serializer):
    role_id     = serializers.IntegerField()
    action_code = serializers.CharField(max_length=50)
    is_allowed  = serializers.BooleanField()

    def validate_role_id(self, value):
        if not Group.objects.filter(id=value).exists():
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
        description='Returns all roles × all active actions grouped by page.',
    )
    def get(self, request):
        # Roles assigned to any /fpo/* page — DB-driven, no hardcoding
        roles   = Group.objects.filter(
            menu_items__path__startswith='/fpo/'
        ).distinct().order_by('name')
        actions = FPOAction.objects.filter(
            is_active=True
        ).select_related('menu_item').order_by('menu_item__order', 'code')

        lang = request.language

        # Build permission lookup: {(role_id, action_code): is_allowed}
        perm_map = {
            (p.role_id, p.action.code): p.is_allowed
            for p in RoleActionPermission.objects.filter(
                role__in=roles, action__in=actions
            ).select_related('action')
        }

        pages = _build_pages_with_actions(actions, lang)

        roles_data = [
            {
                'id':          role.id,
                'name':        role.name,
                'permissions': {
                    a.code: perm_map.get((role.id, a.code), False)
                    for a in actions
                },
            }
            for role in roles
        ]

        return StandardResponse.success(
            data={'pages': pages, 'roles': roles_data},
            message=t('admin.fpo_permissions_retrieved', lang),
        )

    @extend_schema(
        tags=['Admin - FPO Permission Matrix'],
        summary='Bulk update permission matrix',
        description='Update one or more role × action cells. Frontend sends only changed cells.',
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
            role   = Group.objects.get(id=item['role_id'])
            action = FPOAction.objects.get(code=item['action_code'])
            RoleActionPermission.objects.update_or_create(
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
    """Permissions for a single role, grouped by page."""
    permission_classes = [IsSuperAdmin]

    @extend_schema(
        tags=['Admin - FPO Permission Matrix'],
        summary='Get permissions for one role grouped by page',
        description='role_id is auth.Group.id',
    )
    def get(self, request, role_id):
        role = Group.objects.filter(id=role_id).first()
        if not role:
            return StandardResponse.error(
                t('common.not_found', request.language),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        actions = FPOAction.objects.filter(
            is_active=True
        ).select_related('menu_item').order_by('menu_item__order', 'code')

        perm_map = {
            p.action.code: p.is_allowed
            for p in RoleActionPermission.objects.filter(role=role).select_related('action')
        }

        lang       = request.language
        page_map   = {}
        unassigned = []

        for action in actions:
            entry = {
                'id':         action.id,
                'code':       action.code,
                'label':      action.get_label(lang),
                'is_allowed': perm_map.get(action.code, False),
            }
            if action.menu_item_id:
                pid = action.menu_item_id
                if pid not in page_map:
                    page = action.menu_item
                    page_map[pid] = {
                        'id':      page.id,
                        'label':   t(page.label_key, lang) if page.label_key else page.path,
                        'path':    page.path,
                        'actions': [],
                    }
                page_map[pid]['actions'].append(entry)
            else:
                unassigned.append(entry)

        pages = list(page_map.values())
        if unassigned:
            pages.append({'id': None, 'label': 'Other', 'path': None, 'actions': unassigned})

        return StandardResponse.success(
            data={
                'role':  {'id': role.id, 'name': role.name},
                'pages': pages,
            },
            message=t('admin.fpo_permissions_retrieved', request.language),
        )
