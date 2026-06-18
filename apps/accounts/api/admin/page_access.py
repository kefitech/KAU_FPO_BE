"""
Role Page Access API
====================
Base Path: /api/admin/page-access/

Controls which pages (MenuItems) each role can access.
Uses the existing MenuItem.roles M2M — the same source the sidebar reads from.

GET  /api/admin/page-access/           — full grid (all roles × all pages)
GET  /api/admin/page-access/{role_id}/ — pages for one role with is_allowed state
POST /api/admin/page-access/           — bulk update page access for a role

Bulk update request shape:
    {
        "role_id": 5,
        "updates": [
            {"menu_item_id": 1, "is_allowed": true},
            {"menu_item_id": 2, "is_allowed": false}
        ]
    }

Updating is_allowed here automatically updates the user's sidebar (MeView reads the same M2M).
"""

from django.contrib.auth.models import Group
from rest_framework import serializers, status
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from apps.core.permissions.rbac import IsSuperAdmin
from apps.core.utils.responses import StandardResponse
from apps.core.services.translation import t
from apps.database.models import MenuItem


class PageAccessUpdateItemSerializer(serializers.Serializer):
    menu_item_id = serializers.IntegerField()
    is_allowed   = serializers.BooleanField()

    def validate_menu_item_id(self, value):
        if not MenuItem.objects.filter(id=value, is_active=True).exists():
            raise serializers.ValidationError(f'MenuItem {value} not found or inactive.')
        return value


class PageAccessBulkUpdateSerializer(serializers.Serializer):
    role_id = serializers.IntegerField()
    updates = PageAccessUpdateItemSerializer(many=True, min_length=1)

    def validate_role_id(self, value):
        if not Group.objects.filter(id=value).exists():
            raise serializers.ValidationError('Invalid role id.')
        return value


class RolePageAccessListView(APIView):
    """Full grid — all roles × all pages."""
    permission_classes = [IsSuperAdmin]

    @extend_schema(
        tags=['Admin - Page Access'],
        summary='Get full page access grid',
        description=(
            'Returns all active roles × all active pages as a grid. '
            '`is_allowed` reflects whether the role is in the page\'s roles M2M.'
        ),
    )
    def get(self, request):
        roles = Group.objects.all().order_by('name')
        pages = MenuItem.objects.filter(is_active=True).prefetch_related('roles').order_by('order', 'label_key')
        lang  = request.language

        pages_data = [
            {
                'id':        p.id,
                'label_key': p.label_key,
                'label':     t(p.label_key, lang) if p.label_key else p.path,
                'path':      p.path,
                'icon':      p.icon,
            }
            for p in pages
        ]

        # Build set of (role_id, page_id) pairs that are allowed
        allowed_pairs = set()
        for page in pages:
            for role in page.roles.all():
                allowed_pairs.add((role.id, page.id))

        roles_data = [
            {
                'id':          role.id,
                'name':        role.name,
                'page_access': {
                    p.id: (role.id, p.id) in allowed_pairs
                    for p in pages
                },
            }
            for role in roles
        ]

        return StandardResponse.success(
            data={'pages': pages_data, 'roles': roles_data},
            message=t('admin.page_access_retrieved', lang),
        )

    @extend_schema(
        tags=['Admin - Page Access'],
        summary='Bulk update page access for a role',
        description=(
            'Add or remove a role from each page\'s roles M2M. '
            'Changes take effect immediately — the sidebar updates on the next `GET /api/auth/me/` call.'
        ),
        request=PageAccessBulkUpdateSerializer,
    )
    def post(self, request):
        serializer = PageAccessBulkUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return StandardResponse.error(
                t('common.validation_error', request.language),
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data
        role = Group.objects.get(id=data['role_id'])

        updated = 0
        for item in data['updates']:
            page = MenuItem.objects.get(id=item['menu_item_id'])
            if item['is_allowed']:
                page.roles.add(role)
            else:
                page.roles.remove(role)
            updated += 1

        return StandardResponse.success(
            data={'updated': updated},
            message=t('admin.page_access_updated', request.language),
        )


class RolePageAccessDetailView(APIView):
    """Pages for one specific role."""
    permission_classes = [IsSuperAdmin]

    @extend_schema(
        tags=['Admin - Page Access'],
        summary='Get page access for one role',
        description='Returns all active pages with is_allowed state for the given role.',
    )
    def get(self, request, role_id):
        role = Group.objects.filter(id=role_id).first()
        if not role:
            return StandardResponse.error(
                t('common.not_found', request.language),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        pages       = MenuItem.objects.filter(is_active=True).order_by('order', 'label_key')
        allowed_ids = set(
            MenuItem.objects.filter(is_active=True, roles=role).values_list('id', flat=True)
        )
        lang = request.language

        pages_data = [
            {
                'menu_item_id': p.id,
                'label_key':    p.label_key,
                'label':        t(p.label_key, lang) if p.label_key else p.path,
                'path':         p.path,
                'icon':         p.icon,
                'is_allowed':   p.id in allowed_ids,
            }
            for p in pages
        ]

        return StandardResponse.success(
            data={
                'role':  {'id': role.id, 'name': role.name},
                'pages': pages_data,
            },
            message=t('admin.page_access_retrieved', request.language),
        )
