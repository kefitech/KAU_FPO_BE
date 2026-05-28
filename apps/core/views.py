"""
Base ViewSet for KAU-FPO Platform
==================================

All feature ViewSets inherit from TranslatedViewSet.
Language detection and response formatting handled here once —
never repeated in any feature module.
"""

from rest_framework import viewsets, status
from apps.core.utils.responses import StandardResponse
from apps.core.services.translation import t


class TranslatedViewSet(viewsets.ModelViewSet):
    """
    Base ViewSet with built-in language detection and translated responses.

    Subclasses only define translation keys:

        class LanguageViewSet(TranslatedViewSet):
            list_message    = 'admin.languages_retrieved'
            create_message  = 'admin.language_created'
            update_message  = 'admin.language_updated'
            destroy_message = 'admin.language_deleted'

    All CRUD actions are handled automatically.
    Override only when custom business logic is needed.
    """

    # Subclasses override these with their specific translation keys
    list_message    = 'common.success'
    create_message  = 'common.success'
    update_message  = 'common.success'
    destroy_message = 'common.success'

    def get_language(self) -> str:
        """Get detected language from request — set by LanguageDetectionMiddleware."""
        return getattr(self.request, 'language', 'en')

    # =========================================================================
    # CRUD ACTIONS
    # =========================================================================

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self._paginated_response(
                data=serializer.data,
                message=t(self.list_message, self.get_language())
            )
        serializer = self.get_serializer(queryset, many=True)
        return StandardResponse.success(
            data=serializer.data,
            message=t(self.list_message, self.get_language())
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return StandardResponse.success(
            data=serializer.data,
            message=t(self.create_message, self.get_language()),
            status_code=status.HTTP_201_CREATED
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return StandardResponse.success(
            data=serializer.data,
            message=t(self.list_message, self.get_language())
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return StandardResponse.success(
            data=serializer.data,
            message=t(self.update_message, self.get_language())
        )

    def partial_update(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return StandardResponse.success(
            message=t(self.destroy_message, self.get_language())
        )

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _paginated_response(self, data, message):
        """Build paginated StandardResponse."""
        paginator = self.paginator
        return StandardResponse.success(
            data=data,
            message=message,
            meta={
                "pagination": {
                    "page": paginator.page.number,
                    "page_size": paginator.page_size,
                    "total_count": paginator.page.paginator.count,
                    "total_pages": paginator.page.paginator.num_pages,
                    "has_next": paginator.page.has_next(),
                    "has_previous": paginator.page.has_previous(),
                }
            }
        )

    def validation_error_response(self, errors, message_key='common.validation_failed'):
        """Shorthand for returning validation errors with translated message."""
        return StandardResponse.validation_error(
            errors=errors,
            message=t(message_key, self.get_language())
        )
