"""
KAU-FPO Platform - Role Management API
======================================
Author: Athul Gopan
Created: 22-04-2026
"""

from rest_framework import status,filters
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.models import Group
from drf_spectacular.utils import extend_schema, extend_schema_view

from apps.core.views import TranslatedViewSet
from apps.core.permissions.rbac import IsSuperAdminOrReadOnly
from apps.core.utils.responses import StandardResponse
from apps.core.utils.pagination import StandardPagination
from apps.core.services.translation import t
from .serializers import RoleSerializer


@extend_schema_view(
    list=extend_schema(tags=['Authentication']),
    create=extend_schema(tags=['Authentication']),
    retrieve=extend_schema(tags=['Authentication']),
    update=extend_schema(tags=['Authentication']),
    partial_update=extend_schema(tags=['Authentication']),
    destroy=extend_schema(tags=['Authentication']),
)
class RoleViewSet(TranslatedViewSet):

    queryset = Group.objects.all().order_by('name')
    serializer_class = RoleSerializer
    permission_classes = [IsAuthenticated, IsSuperAdminOrReadOnly]
    pagination_class = StandardPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter] 
    search_fields   = ['name']                                    
    ordering_fields = ['name']  
    http_method_names = ['get', 'post', 'put', 'patch', 'delete']

    # Translation keys
    list_message    = 'role.roles_retrieved'
    create_message  = 'role.role_created'
    update_message  = 'role.role_updated'
    destroy_message = 'role.role_deleted'

    def destroy(self, request, *args, **kwargs):
        """Cannot delete a role that has users assigned."""
        instance = self.get_object()
        user_count = instance.user_set.count()
        if user_count > 0:
            return StandardResponse.error(
                message=t('role.role_has_users', self.get_language(), count=user_count),
                status_code=status.HTTP_400_BAD_REQUEST
            )
        role_name = instance.name
        instance.delete()
        return StandardResponse.success(
            data={"deleted_role": role_name},
            message=t(self.destroy_message, self.get_language())
        )
