"""
Notification Template API Views
================================
Base Path: /api/notifications/
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

from apps.database.models import NotificationTemplateCode, NotificationTemplate
from .serializers import NotificationTemplateCodeSerializer, NotificationTemplateSerializer


@extend_schema_view(
    list=extend_schema(tags=['Notifications - Template Codes']),
    create=extend_schema(tags=['Notifications - Template Codes']),
    retrieve=extend_schema(tags=['Notifications - Template Codes']),
    update=extend_schema(tags=['Notifications - Template Codes']),
    partial_update=extend_schema(tags=['Notifications - Template Codes']),
    destroy=extend_schema(tags=['Notifications - Template Codes']),
)
class NotificationTemplateCodeViewSet(TranslatedViewSet):
    """
    Manage notification template definitions (codes).

    These are the event types — e.g. fpo_approved/email, otp_sent/sms.
    Admin creates a definition here first, then adds language versions
    via the NotificationTemplateViewSet.

    Frontend populates the "select template" dropdown from this endpoint.
    """

    queryset = NotificationTemplateCode.objects.prefetch_related('templates').order_by('channel', 'code')
    serializer_class = NotificationTemplateCodeSerializer
    permission_classes = [IsAdmin]
    pagination_class = StandardPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend]
    search_fields = ['code', 'name', 'description']
    ordering_fields = ['code', 'channel', 'created_at']
    filterset_fields = ['channel', 'is_active']

    list_message    = 'admin.template_codes_retrieved'
    create_message  = 'admin.template_code_created'
    update_message  = 'admin.template_code_updated'
    destroy_message = 'admin.template_code_deleted'

    @extend_schema(tags=['Notifications - Template Codes'])
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        obj = self.get_object()
        obj.is_active = True
        obj.save()
        return StandardResponse.success(
            data=self.get_serializer(obj).data,
            message=t('admin.template_code_activated', self.get_language())
        )

    @extend_schema(tags=['Notifications - Template Codes'])
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        obj = self.get_object()
        obj.is_active = False
        obj.save()
        return StandardResponse.success(
            data=self.get_serializer(obj).data,
            message=t('admin.template_code_deactivated', self.get_language())
        )


@extend_schema_view(
    list=extend_schema(tags=['Notifications - Templates']),
    create=extend_schema(tags=['Notifications - Templates']),
    retrieve=extend_schema(tags=['Notifications - Templates']),
    update=extend_schema(tags=['Notifications - Templates']),
    partial_update=extend_schema(tags=['Notifications - Templates']),
    destroy=extend_schema(tags=['Notifications - Templates']),
)
class NotificationTemplateViewSet(TranslatedViewSet):
    """
    Manage language-specific notification template content.

    Each template is a language version of a NotificationTemplateCode.
    Admin selects the template code from a dropdown (GET /template-codes/),
    selects the language, then writes the subject and body.

    The missing_languages field on the template code shows which languages
    still need content.
    """

    queryset = NotificationTemplate.objects.select_related(
        'template_code', 'language'
    ).order_by('template_code__code', 'language__code')
    serializer_class = NotificationTemplateSerializer
    permission_classes = [IsAdmin]
    pagination_class = StandardPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend]
    search_fields = ['subject', 'body', 'template_code__code', 'template_code__name']
    ordering_fields = ['created_at', 'updated_at']
    filterset_fields = ['template_code', 'language', 'is_active']

    list_message    = 'admin.templates_retrieved'
    create_message  = 'admin.template_created'
    update_message  = 'admin.template_updated'
    destroy_message = 'admin.template_deleted'

    @extend_schema(tags=['Notifications - Templates'])
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        obj = self.get_object()
        obj.is_active = True
        obj.save()
        return StandardResponse.success(
            data=self.get_serializer(obj).data,
            message=t('admin.template_activated', self.get_language())
        )

    @extend_schema(tags=['Notifications - Templates'])
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        obj = self.get_object()
        obj.is_active = False
        obj.save()
        return StandardResponse.success(
            data=self.get_serializer(obj).data,
            message=t('admin.template_deactivated', self.get_language())
        )

    @extend_schema(tags=['Notifications - Templates'])
    @action(detail=True, methods=['post'])
    def test_render(self, request, pk=None):
        """
        Test template rendering with sample context data.

        Request body: { "context": { "user_name": "Rajan", "fpo_name": "Kerala FPO" } }
        Returns rendered subject and body with variables substituted.
        """
        template = self.get_object()
        context  = request.data.get('context', {})
        rendered = template.render(context)

        return StandardResponse.success(
            data={
                'template': self.get_serializer(template).data,
                'rendered': rendered,
                'context_used': context,
            },
            message=t('admin.template_rendered', self.get_language())
        )
