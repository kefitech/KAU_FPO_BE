"""
Language Management API
=======================
Base Path: /api/admin/languages/
Author: Athul Gopan (Kefi Tech Solutions)
"""

from rest_framework import status, filters
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view

from apps.core.views import TranslatedViewSet
from apps.core.permissions.rbac import IsAdmin
from apps.core.utils.responses import StandardResponse
from apps.core.utils.pagination import StandardPagination
from apps.core.services.translation import t

from apps.database.models import Language
from .serializers import LanguageSerializer


@extend_schema_view(
    list=extend_schema(tags=['Admin - Languages']),
    create=extend_schema(tags=['Admin - Languages']),
    retrieve=extend_schema(tags=['Admin - Languages']),
    update=extend_schema(tags=['Admin - Languages']),
    partial_update=extend_schema(tags=['Admin - Languages']),
    destroy=extend_schema(tags=['Admin - Languages']),
)
class LanguageViewSet(TranslatedViewSet):

    queryset = Language.objects.all().order_by('display_order', 'name')
    serializer_class = LanguageSerializer
    permission_classes = [IsAdmin]
    pagination_class = StandardPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend]
    search_fields = ['code', 'name', 'native_name']
    ordering_fields = ['display_order', 'name', 'created_at']
    filterset_fields = ['is_active', 'is_default']

    # Translation keys
    list_message    = 'admin.languages_retrieved'
    create_message  = 'admin.language_created'
    update_message  = 'admin.language_updated'
    destroy_message = 'admin.language_deactivated'

    def destroy(self, request, *args, **kwargs):
        """Deactivate language (soft delete) — cannot delete default."""
        language = self.get_object()
        if language.is_default:
            return StandardResponse.error(
                message=t('admin.cannot_delete_default', self.get_language()),
                status_code=status.HTTP_400_BAD_REQUEST
            )
        language.is_active = False
        language.save()
        return StandardResponse.success(
            message=t(self.destroy_message, self.get_language())
        )

    @extend_schema(tags=['Admin - Languages'])
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """Activate a language."""
        language = self.get_object()
        language.is_active = True
        language.save()
        return StandardResponse.success(
            data=self.get_serializer(language).data,
            message=t('admin.language_activated', self.get_language())
        )

    @extend_schema(tags=['Admin - Languages'])
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Deactivate a language."""
        language = self.get_object()
        if language.is_default:
            return StandardResponse.error(
                message=t('admin.cannot_deactivate_default', self.get_language()),
                status_code=status.HTTP_400_BAD_REQUEST
            )
        language.is_active = False
        language.save()
        return StandardResponse.success(
            data=self.get_serializer(language).data,
            message=t('admin.language_deactivated', self.get_language())
        )

    @extend_schema(tags=['Admin - Languages'])
    @action(detail=True, methods=['post'])
    def set_default(self, request, pk=None):
        """Set as default language."""
        language = self.get_object()
        if not language.is_active:
            return StandardResponse.error(
                message=t('admin.cannot_set_inactive_default', self.get_language()),
                status_code=status.HTTP_400_BAD_REQUEST
            )
        language.is_default = True
        language.save()
        return StandardResponse.success(
            data=self.get_serializer(language).data,
            message=t('admin.language_set_default', self.get_language())
        )
