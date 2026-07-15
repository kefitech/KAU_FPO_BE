"""
Notification Channel Settings API
===================================
Base Path: /api/notifications/channel-settings/

Admin configures email/SMS/in-app credentials here.
Sensitive fields are encrypted before saving to DB.
"""

from rest_framework import serializers, status
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.decorators import action
from drf_spectacular.utils import extend_schema, extend_schema_view

from django_filters.rest_framework import DjangoFilterBackend
from apps.core.views import TranslatedViewSet
from apps.core.permissions.rbac import IsSuperAdmin
from apps.core.utils.responses import StandardResponse
from apps.core.services.translation import t

from apps.database.models import NotificationChannelSettings
from apps.notifications.utils import encrypt_config, decrypt_config


class NotificationChannelSettingsSerializer(serializers.ModelSerializer):

    class Meta:
        model  = NotificationChannelSettings
        fields = ['id', 'channel', 'is_active', 'config', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def to_representation(self, instance):
        """Mask sensitive fields when reading — never expose raw secrets."""
        data = super().to_representation(instance)
        config = data.get('config', {})
        sensitive = {'password', 'api_key', 'secret', 'token', 'auth_key'}
        masked = {
            k: ('••••••••' if k in sensitive and v else v)
            for k, v in config.items()
        }
        data['config'] = masked
        return data

    def create(self, validated_data):
        config = validated_data.pop('config', {})
        validated_data['config'] = encrypt_config(config)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if 'config' in validated_data:
            new_config = validated_data['config']
            # Preserve existing encrypted values for fields not being updated
            existing = instance.config.copy()
            existing.update(new_config)
            validated_data['config'] = encrypt_config(existing)
        return super().update(instance, validated_data)


@extend_schema_view(
    list=extend_schema(tags=['Notifications - Channel Settings']),
    create=extend_schema(tags=['Notifications - Channel Settings']),
    retrieve=extend_schema(tags=['Notifications - Channel Settings']),
    update=extend_schema(tags=['Notifications - Channel Settings']),
    partial_update=extend_schema(tags=['Notifications - Channel Settings']),
    destroy=extend_schema(tags=['Notifications - Channel Settings']),
)
class NotificationChannelSettingsViewSet(TranslatedViewSet):
    """
    Manage notification channel credentials and configuration.

    Only super_admin can access. Sensitive fields (password, api_key etc.)
    are AES-encrypted at rest and masked (••••••••) in API responses.

    To update a credential: send the new value — it will be encrypted automatically.
    Fields not included in the update are preserved.

    **Config shapes per channel:**

    Email:
    ```json
    { "host": "smtp.gmail.com", "port": 587, "username": "noreply@kau.in",
      "password": "••••••••", "from_email": "noreply@kau.in",
      "from_name": "KAU-FPO Platform", "use_tls": true }
    ```

    SMS (MSG91):
    ```json
    { "api_key": "••••••••", "sender_id": "KAUFPO",
      "otp_template_id": "...", "base_url": "https://api.msg91.com/api/v5/" }
    ```

    WhatsApp (Meta Business API):
    ```json
    { "phone_number_id": "...", "access_token": "••••••••", "api_version": "v19.0" }
    ```

    In-App:
    ```json
    { "max_per_user": 100, "auto_expire_days": 30 }
    ```
    """

    queryset           = NotificationChannelSettings.objects.all().order_by('channel')
    serializer_class   = NotificationChannelSettingsSerializer
    permission_classes = [IsSuperAdmin]
    filter_backends    = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields   = ['channel', 'is_active']
    search_fields      = ['channel']


    list_message    = 'admin.channel_settings_retrieved'
    create_message  = 'admin.channel_settings_created'
    update_message  = 'admin.channel_settings_updated'
    destroy_message = 'admin.channel_settings_deleted'

    @extend_schema(tags=['Notifications - Channel Settings'])
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        obj = self.get_object()
        obj.is_active = True
        obj.save()
        return StandardResponse.success(
            data=self.get_serializer(obj).data,
            message=t('admin.channel_activated', self.get_language())
        )

    @extend_schema(tags=['Notifications - Channel Settings'])
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        obj = self.get_object()
        obj.is_active = False
        obj.save()
        return StandardResponse.success(
            data=self.get_serializer(obj).data,
            message=t('admin.channel_deactivated', self.get_language())
        )

    @extend_schema(tags=['Notifications - Channel Settings'])
    @action(detail=True, methods=['post'])
    def test(self, request, pk=None):
        """
        Send a test notification using this channel's current configuration.

        Request body: { "recipient": "test@example.com", "message": "Test message" }
        """
        obj      = self.get_object()
        recipient= request.data.get('recipient', '')
        message  = request.data.get('message', 'Test notification from KAU-FPO Platform')

        if not recipient:
            return StandardResponse.error(
                message='Recipient is required',
                status_code=status.HTTP_400_BAD_REQUEST
            )

        from apps.database.models import NotificationLog
        from apps.notifications.tasks import deliver_notification
        from django.contrib.auth import get_user_model

        log_kwargs = dict(
            channel          = obj.channel,
            status           = NotificationLog.Status.PENDING,
            rendered_subject = 'Test Notification — KAU-FPO',
            rendered_body    = message,
            recipient        = recipient,
        )
        
        # log = NotificationLog(
        #     channel          = obj.channel,
        #     status           = NotificationLog.Status.PENDING,
        #     rendered_subject = 'Test Notification — KAU-FPO',
        #     rendered_body    = message,
        #     recipient        = recipient,
        # )
        # log.save()
        if obj.channel == NotificationChannelSettings.Channel.IN_APP:
            User = get_user_model()
            user = None


            if recipient.isdigit():
               user = User.objects.filter(pk=int(recipient)).first()
            if not user:
               user = User.objects.filter(username=recipient).first()
            if not user:
               user = User.objects.filter(email=recipient).first()

            if not user:
               return StandardResponse.error(
                  message=f'No user found matching "{recipient}" (tried user ID, username, and email)',
                   status_code=status.HTTP_400_BAD_REQUEST
               )
            log_kwargs['user'] = user

        #    log_kwargs['user'] = user
        #    log = NotificationLog(**log_kwargs)
        #    log.save()

        
            

        log = NotificationLog(**log_kwargs)
        log.save()


        deliver_notification.delay(log.id, obj.id)

        return StandardResponse.success(
            message=f'Test {obj.channel} queued — check {recipient} shortly'
        )
