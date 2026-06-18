"""
External API Settings — Admin API
==================================

Manage credentials for PAN / GSTIN / CIN verification APIs.

Endpoints:
    GET    /api/admin/external-apis/          — list all 3 services
    POST   /api/admin/external-apis/          — create / upsert a service config
    GET    /api/admin/external-apis/{id}/     — retrieve one
    PATCH  /api/admin/external-apis/{id}/     — update config / url
    POST   /api/admin/external-apis/{id}/activate/
    POST   /api/admin/external-apis/{id}/deactivate/

Config shapes per service:
    pan_verification   → { api_key, client_id, base_url }
    gstin_verification → { api_key, client_id, base_url }
    cin_verification   → { api_key, client_id, base_url }

Sensitive fields (encrypted at rest, masked as •••••••• in responses):
    api_key, client_id, password, secret
"""

import logging

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_field, OpenApiResponse
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.permissions.rbac import IsSuperAdmin
from apps.core.utils.responses import StandardResponse
from apps.database.models import ExternalAPISettings
from apps.notifications.utils import encrypt_config, decrypt_config

logger = logging.getLogger(__name__)

SENSITIVE_FIELDS = {'api_key', 'client_id', 'password', 'secret'}


def _mask_config(config: dict) -> dict:
    """Replace sensitive field values with •••••••• for API responses."""
    return {
        k: '••••••••' if k in SENSITIVE_FIELDS and v else v
        for k, v in config.items()
    }


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------

class ExternalAPISettingsSerializer(serializers.ModelSerializer):
    config = serializers.SerializerMethodField()

    class Meta:
        model  = ExternalAPISettings
        fields = ['id', 'service', 'service_display', 'api_url', 'config', 'is_active', 'created_at', 'updated_at']

    def get_config(self, obj):
        return _mask_config(obj.config or {})

    @extend_schema_field(serializers.CharField())
    def get_service_display(self, obj):
        return obj.get_service_display()

    service_display = serializers.SerializerMethodField()


class ExternalAPISettingsCreateSerializer(serializers.Serializer):
    service   = serializers.ChoiceField(
        choices=ExternalAPISettings.SERVICE_CHOICES,
        help_text='pan_verification | gstin_verification | cin_verification'
    )
    api_url   = serializers.URLField(required=False, allow_blank=True, default='')
    config    = serializers.DictField(
        child=serializers.CharField(allow_blank=True),
        required=False,
        default=dict,
        help_text='Credentials dict. Sensitive keys: api_key, client_id, password, secret'
    )


class ExternalAPISettingsPatchSerializer(serializers.Serializer):
    api_url = serializers.URLField(required=False, allow_blank=True)
    config  = serializers.DictField(
        child=serializers.CharField(allow_blank=True),
        required=False,
        help_text='Partial update — only keys provided will be updated'
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serialize(obj):
    return ExternalAPISettingsSerializer(obj).data


def _get_obj(pk):
    return get_object_or_404(ExternalAPISettings, pk=pk)


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

class ExternalAPISettingsListView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    @extend_schema(
        tags=['Admin - External APIs'],
        summary='List all external API settings',
        responses={200: ExternalAPISettingsSerializer(many=True)},
    )
    def get(self, request):
        qs = ExternalAPISettings.objects.all().order_by('service')
        return StandardResponse.success(
            data=[_serialize(obj) for obj in qs],
            message='External API settings retrieved.',
        )

    @extend_schema(
        tags=['Admin - External APIs'],
        summary='Create external API settings',
        description=(
            'Creates settings for a service. Each service can only have one entry (unique). '
            'Sensitive config fields are encrypted before saving.'
        ),
        request=ExternalAPISettingsCreateSerializer,
        responses={201: ExternalAPISettingsSerializer},
    )
    def post(self, request):
        serializer = ExternalAPISettingsCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return StandardResponse.error(
                message='Invalid data.',
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        data    = serializer.validated_data
        service = data['service']

        if ExternalAPISettings.objects.filter(service=service).exists():
            return StandardResponse.error(
                message=f'Settings for {service} already exist. Use PATCH to update.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        obj = ExternalAPISettings.objects.create(
            service = service,
            api_url = data.get('api_url', ''),
            config  = encrypt_config(data.get('config', {})),
        )

        return StandardResponse.created(
            data=_serialize(obj),
            message='External API settings created.',
        )


class ExternalAPISettingsDetailView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    @extend_schema(
        tags=['Admin - External APIs'],
        summary='Retrieve external API settings',
        responses={200: ExternalAPISettingsSerializer},
    )
    def get(self, request, pk):
        return StandardResponse.success(data=_serialize(_get_obj(pk)))

    @extend_schema(
        tags=['Admin - External APIs'],
        summary='Update external API settings',
        description='Partial update — only provided keys in config are merged, others kept.',
        request=ExternalAPISettingsPatchSerializer,
        responses={200: ExternalAPISettingsSerializer},
    )
    def patch(self, request, pk):
        obj        = _get_obj(pk)
        serializer = ExternalAPISettingsPatchSerializer(data=request.data)
        if not serializer.is_valid():
            return StandardResponse.error(
                message='Invalid data.',
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data

        if 'api_url' in data:
            obj.api_url = data['api_url']

        if 'config' in data:
            existing = decrypt_config(obj.config or {})
            existing.update(data['config'])
            obj.config = encrypt_config(existing)

        obj.save()
        return StandardResponse.success(
            data=_serialize(obj),
            message='External API settings updated.',
        )


class ExternalAPISettingsActivateView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    @extend_schema(
        tags=['Admin - External APIs'],
        summary='Activate external API',
        description='Enables live API verification. Requires api_url and config to be set first.',
        responses={200: OpenApiResponse(description='Activated')},
    )
    def post(self, request, pk):
        obj = _get_obj(pk)

        if not obj.api_url:
            return StandardResponse.error(
                message='Set api_url before activating.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if not obj.config:
            return StandardResponse.error(
                message='Set credentials (config) before activating.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        obj.is_active = True
        obj.save(update_fields=['is_active', 'updated_at'])
        return StandardResponse.success(
            data=_serialize(obj),
            message=f'{obj.get_service_display()} activated — live verification enabled.',
        )


class ExternalAPISettingsDeactivateView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    @extend_schema(
        tags=['Admin - External APIs'],
        summary='Deactivate external API',
        description='Disables live API. Falls back to format-only validation.',
        responses={200: OpenApiResponse(description='Deactivated')},
    )
    def post(self, request, pk):
        obj           = _get_obj(pk)
        obj.is_active = False
        obj.save(update_fields=['is_active', 'updated_at'])
        return StandardResponse.success(
            data=_serialize(obj),
            message=f'{obj.get_service_display()} deactivated — format-only fallback active.',
        )
