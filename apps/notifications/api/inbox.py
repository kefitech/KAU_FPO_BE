"""
User Notification Inbox API
============================
Base Path: /api/notifications/inbox/

Authenticated users fetch their in-app notifications here.
Frontend uses this for the bell icon count + notification list.

Categories (apps/notifications/categories.py) are derived from each
notification's event code. `?category=<key>` scopes list / unread_count /
read_all; omit it (or pass `all`) for every notification.
"""

from django.db.models import Count, Q
from rest_framework import serializers, mixins, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet
from drf_spectacular.utils import extend_schema, extend_schema_view
from django.utils import timezone

from apps.core.utils.responses import StandardResponse
from apps.core.utils.pagination import StandardPagination
from apps.core.services.translation import t

from apps.database.models import InAppNotification, NotificationTemplate
from apps.notifications.categories import CATEGORY_KEYS, category_for_code, category_q


class InAppNotificationSerializer(serializers.ModelSerializer):
    title = serializers.SerializerMethodField()
    body = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()

    class Meta:
        model  = InAppNotification
        fields = ['id', 'title', 'body', 'category', 'is_read', 'read_at', 'created_at']
        read_only_fields = ['id', 'is_read', 'read_at', 'created_at']

    def _get_language(self):
        request = self.context.get('request')
        return getattr(request, 'language', 'en') if request else 'en'
 
    def _render(self, obj):
        # Fall back to the stored static text if there's no log/template link
        # (e.g. legacy rows created before this change, or template deleted since).
        if not obj.log or not obj.log.template_code:
            return {'subject': obj.title, 'body': obj.body}
 
        lang = self._get_language()
        template = (
            NotificationTemplate.objects.filter(
                template_code=obj.log.template_code, language__code=lang, is_active=True
            ).select_related('language').first()
            or NotificationTemplate.objects.filter(
                template_code=obj.log.template_code, language__code='en', is_active=True
            ).select_related('language').first()
        )
        if not template:
            return {'subject': obj.title, 'body': obj.body}
 
        return template.render(obj.log.context or {})
 
    def get_title(self, obj):
        rendered = self._render(obj)
        return rendered.get('subject') or obj.title
 
    def get_body(self, obj):
        rendered = self._render(obj)
        return rendered.get('body') or obj.body

    def get_category(self, obj):
        code = obj.log.template_code.code if obj.log and obj.log.template_code else None
        return category_for_code(code)


@extend_schema_view(
    list=extend_schema(tags=['Notifications - Inbox']),
    retrieve=extend_schema(tags=['Notifications - Inbox']),
)
class InboxViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, GenericViewSet):
    """
    User's in-app notification inbox.

    - GET  /inbox/              — list notifications (newest first)
    - GET  /inbox/categories/   — per-category total + unread counts (inbox tabs)
    - GET  /inbox/unread_count/ — returns unread count for bell icon
    - POST /inbox/{id}/read/    — mark single notification as read
    - POST /inbox/read_all/     — mark all as read

    list / unread_count / read_all accept `?category=<key>` (see
    apps/notifications/categories.py); omitted or `all` = every notification.
    """

    serializer_class   = InAppNotificationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = StandardPagination

    def get_language(self):
        return getattr(self.request, 'language', 'en')

    def get_queryset(self):
        return InAppNotification.objects.filter(
            user=self.request.user
        ).select_related('log', 'log__template_code').order_by('-created_at')

    def _category_param(self):
        """Returns (category or None for all, error response or None)."""
        category = self.request.query_params.get('category') or 'all'
        if category == 'all':
            return None, None
        if category not in CATEGORY_KEYS:
            return None, StandardResponse.error(
                t('common.validation_error', self.get_language()),
                errors={'category': [f'Must be one of: all, {", ".join(CATEGORY_KEYS)}']},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        return category, None

    def _scoped_queryset(self, category):
        qs = self.get_queryset()
        return qs.filter(category_q(category)) if category else qs

    def list(self, request, *args, **kwargs):
        category, err = self._category_param()
        if err:
            return err
        page = self.paginate_queryset(self._scoped_queryset(category))
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(tags=['Notifications - Inbox'])
    @action(detail=False, methods=['get'])
    def categories(self, request):
        """Total + unread count per category, for the inbox tabs.

        Only categories the user actually has notifications in are returned,
        in display order, plus an `all` summary.
        """
        rows = (
            self.get_queryset()
            .order_by()
            .values('log__template_code__code')
            .annotate(total=Count('id'), unread=Count('id', filter=Q(is_read=False)))
        )
        counts = {key: {'total': 0, 'unread': 0} for key in CATEGORY_KEYS}
        for row in rows:
            bucket = counts[category_for_code(row['log__template_code__code'])]
            bucket['total'] += row['total']
            bucket['unread'] += row['unread']

        return StandardResponse.success(data={
            'all': {
                'total': sum(c['total'] for c in counts.values()),
                'unread': sum(c['unread'] for c in counts.values()),
            },
            'categories': [
                {'key': key, **counts[key]} for key in CATEGORY_KEYS if counts[key]['total']
            ],
        })

    @extend_schema(tags=['Notifications - Inbox'])
    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        """Returns unread notification count — used for bell icon badge."""
        category, err = self._category_param()
        if err:
            return err
        count = self._scoped_queryset(category).filter(is_read=False).count()
        return StandardResponse.success(data={'unread_count': count})

    @extend_schema(tags=['Notifications - Inbox'])
    @action(detail=True, methods=['post'])
    def read(self, request, pk=None):
        """Mark a single notification as read."""
        notif = self.get_object()
        notif.mark_as_read()
        return StandardResponse.success(
            data=self.get_serializer(notif).data,
            message=t('common.success', self.get_language())
        )

    @extend_schema(tags=['Notifications - Inbox'])
    @action(detail=False, methods=['post'])
    def read_all(self, request):
        """Mark all unread notifications (optionally in one ?category=) as read."""
        category, err = self._category_param()
        if err:
            return err
        updated = self._scoped_queryset(category).filter(is_read=False).update(
            is_read=True,
            read_at=timezone.now()
        )
        return StandardResponse.success(
            data={'marked_read': updated},
            message=t('common.success', self.get_language())
        )
