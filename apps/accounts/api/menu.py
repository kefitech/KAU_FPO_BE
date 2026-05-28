"""
Menu Item API
=============
Base Path: /api/admin/menu/

Super admin manages sidebar menu items here.
Each item has a label_key (translation key), path, icon, roles (M2M), parent, and order.
Frontend fetches the translated, role-filtered menu via GET /api/auth/me/.
"""

from rest_framework import serializers, filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.decorators import action
from django.contrib.auth.models import Group
from drf_spectacular.utils import extend_schema, extend_schema_view, extend_schema_field

from apps.core.views import TranslatedViewSet
from apps.core.permissions.rbac import IsSuperAdmin
from apps.core.utils.responses import StandardResponse
from apps.core.utils.pagination import StandardPagination
from apps.core.services.translation import t

from apps.database.models import MenuItem


class MenuItemSerializer(serializers.ModelSerializer):

    roles = serializers.PrimaryKeyRelatedField(
        queryset=Group.objects.all(),
        many=True,
        help_text="Group IDs that can see this menu item"
    )

    label      = serializers.SerializerMethodField()
    role_names = serializers.SerializerMethodField()
    children   = serializers.SerializerMethodField()

    class Meta:
        model  = MenuItem
        fields = [
            'id', 'label_key', 'label', 'path', 'icon',
            'roles', 'role_names',
            'parent', 'children',
            'order', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'label', 'role_names', 'children', 'created_at', 'updated_at']

    @extend_schema_field(serializers.CharField())
    def get_label(self, obj):
        request = self.context.get('request')
        lang = getattr(request, 'language', 'en') if request else 'en'
        return t(obj.label_key, language=lang)

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_role_names(self, obj):
        return list(obj.roles.values_list('name', flat=True))

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_children(self, obj):
        active_children = obj.children.filter(is_active=True).order_by('order')
        return MenuItemSerializer(active_children, many=True, context=self.context).data


@extend_schema_view(
    list=extend_schema(tags=['Admin - Menu']),
    create=extend_schema(tags=['Admin - Menu']),
    retrieve=extend_schema(tags=['Admin - Menu']),
    update=extend_schema(tags=['Admin - Menu']),
    partial_update=extend_schema(tags=['Admin - Menu']),
    destroy=extend_schema(tags=['Admin - Menu']),
)
class MenuItemViewSet(TranslatedViewSet):
    """
    Manage sidebar navigation menu items.

    - Create top-level items (parent=null) or child items (parent=<id>)
    - Assign roles (Django Groups) to control visibility per role
    - Order controls sort position within the same level
    - Frontend gets the translated, filtered menu via GET /api/auth/me/
    """

    queryset = MenuItem.objects.filter(
        parent=None
    ).prefetch_related('children', 'roles').order_by('order')

    serializer_class   = MenuItemSerializer
    permission_classes = [IsSuperAdmin]
    pagination_class   = StandardPagination
    filter_backends    = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields   = ['is_active']
    search_fields      = ['label_key', 'path']
    ordering_fields    = ['order', 'created_at']

    list_message    = 'admin.menu_items_retrieved'
    create_message  = 'admin.menu_item_created'
    update_message  = 'admin.menu_item_updated'
    destroy_message = 'admin.menu_item_deleted'

    @extend_schema(tags=['Admin - Menu'])
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        obj = self.get_object()
        obj.is_active = True
        obj.save()
        return StandardResponse.success(
            data=self.get_serializer(obj).data,
            message=t('admin.menu_item_activated', self.get_language())
        )

    @extend_schema(tags=['Admin - Menu'])
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        obj = self.get_object()
        obj.is_active = False
        obj.save()
        return StandardResponse.success(
            data=self.get_serializer(obj).data,
            message=t('admin.menu_item_deactivated', self.get_language())
        )
