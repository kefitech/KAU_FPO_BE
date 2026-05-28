"""
Translation Category Management API
====================================
Base Path: /api/admin/translation-categories/
Author: Athul Gopan (Kefi Tech Solutions)
"""

from rest_framework import filters
from drf_spectacular.utils import extend_schema, extend_schema_view

from apps.core.views import TranslatedViewSet
from apps.core.permissions.rbac import IsAdmin
from apps.core.utils.pagination import StandardPagination

from apps.database.models import TranslationCategory
from .serializers import TranslationCategorySerializer


@extend_schema_view(
    list=extend_schema(tags=['Admin - Translation Categories']),
    create=extend_schema(tags=['Admin - Translation Categories']),
    retrieve=extend_schema(tags=['Admin - Translation Categories']),
    update=extend_schema(tags=['Admin - Translation Categories']),
    partial_update=extend_schema(tags=['Admin - Translation Categories']),
    destroy=extend_schema(tags=['Admin - Translation Categories']),
)
class TranslationCategoryViewSet(TranslatedViewSet):

    queryset = TranslationCategory.objects.all().order_by('display_order', 'name')
    serializer_class = TranslationCategorySerializer
    permission_classes = [IsAdmin]
    pagination_class = StandardPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['code', 'name', 'description']
    ordering_fields = ['display_order', 'name', 'created_at']

    # Translation keys
    list_message    = 'admin.categories_retrieved'
    create_message  = 'admin.category_created'
    update_message  = 'admin.category_updated'
    destroy_message = 'admin.category_deleted'
