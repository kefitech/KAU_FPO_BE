"""
User Notification Inbox API
============================
Base Path: /api/notifications/inbox/

Authenticated users fetch their in-app notifications here.
Frontend uses this for the bell icon count + notification list.
"""

from rest_framework import serializers, mixins
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet
from drf_spectacular.utils import extend_schema, extend_schema_view
from django.utils import timezone

from apps.core.utils.responses import StandardResponse
from apps.core.utils.pagination import StandardPagination
from apps.core.services.translation import t

from apps.database.models import InAppNotification


class InAppNotificationSerializer(serializers.ModelSerializer):

    class Meta:
        model  = InAppNotification
        fields = ['id', 'title', 'body', 'is_read', 'read_at', 'created_at']
        read_only_fields = fields


@extend_schema_view(
    list=extend_schema(tags=['Notifications - Inbox']),
    retrieve=extend_schema(tags=['Notifications - Inbox']),
)
class InboxViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, GenericViewSet):
    """
    User's in-app notification inbox.

    - GET  /inbox/           — list notifications (newest first)
    - GET  /inbox/unread_count/ — returns unread count for bell icon
    - POST /inbox/{id}/read/    — mark single notification as read
    - POST /inbox/read_all/     — mark all as read
    """

    serializer_class   = InAppNotificationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = StandardPagination

    def get_language(self):
        return getattr(self.request, 'language', 'en')

    def get_queryset(self):
        return InAppNotification.objects.filter(
            user=self.request.user
        ).order_by('-created_at')

    @extend_schema(tags=['Notifications - Inbox'])
    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        """Returns unread notification count — used for bell icon badge."""
        count = self.get_queryset().filter(is_read=False).count()
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
        """Mark all unread notifications as read."""
        updated = self.get_queryset().filter(is_read=False).update(
            is_read=True,
            read_at=timezone.now()
        )
        return StandardResponse.success(
            data={'marked_read': updated},
            message=t('common.success', self.get_language())
        )
