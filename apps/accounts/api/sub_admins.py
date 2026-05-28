"""
Sub-Admin Management API
========================
Base Path: /api/admin/sub-admins/

Super admin creates sub-admin accounts and configures which permissions each
sub-admin has. Permissions are assigned per-user from a fixed list defined in
SUB_ADMIN_PERMISSIONS (constants.py).
"""

import secrets
import logging

from django.conf import settings as django_settings
from django.contrib.auth.models import User, Group, Permission
from django.contrib.contenttypes.models import ContentType

from rest_framework import serializers, filters
from rest_framework.decorators import action

from drf_spectacular.utils import extend_schema, extend_schema_view, extend_schema_field

from apps.core.permissions.rbac import IsSuperAdmin
from apps.core.utils.constants import UserRole, SUB_ADMIN_PERMISSIONS
from apps.core.utils.responses import StandardResponse
from apps.core.utils.pagination import StandardPagination
from apps.core.services.translation import t
from apps.core.views import TranslatedViewSet
from apps.notifications.services import send_notification

logger = logging.getLogger(__name__)


def _get_sub_admin_permissions():
    """Return queryset of all assignable sub-admin Permission objects."""
    try:
        ct = ContentType.objects.get(app_label='accounts', model='subadmin')
        return Permission.objects.filter(content_type=ct)
    except ContentType.DoesNotExist:
        return Permission.objects.none()


# ─── Serializers ─────────────────────────────────────────────────────────────

class SubAdminCreateSerializer(serializers.Serializer):
    email                = serializers.EmailField()
    first_name           = serializers.CharField(max_length=150)
    last_name            = serializers.CharField(max_length=150, required=False, default='')
    phone                = serializers.CharField(max_length=15, required=False, allow_blank=True, default='')
    notification_channel = serializers.ChoiceField(
        choices=['email', 'sms'],
        default='email',
        help_text="Channel to send login credentials. 'sms' requires phone to be provided.",
    )
    permissions = serializers.ListField(
        child=serializers.ChoiceField(choices=[c for c, _ in SUB_ADMIN_PERMISSIONS]),
        required=False,
        default=list,
        help_text="List of permission codenames to assign (e.g. ['can_approve_fpo'])",
    )

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError('A user with this email already exists.')
        return value.lower()

    def validate_phone(self, value):
        if value:
            from apps.core.utils.validators import validate_indian_phone
            from django.core.exceptions import ValidationError as DjangoValidationError
            try:
                validate_indian_phone(value)
            except DjangoValidationError as e:
                raise serializers.ValidationError(str(e))
        return value

    def validate(self, attrs):
        if attrs.get('notification_channel') == 'sms' and not attrs.get('phone'):
            raise serializers.ValidationError({
                'notification_channel': 'Cannot use SMS — no phone number provided.'
            })
        return attrs


class SubAdminSerializer(serializers.ModelSerializer):
    permissions = serializers.SerializerMethodField()
    phone       = serializers.SerializerMethodField()

    class Meta:
        model  = User
        fields = ['id', 'email', 'first_name', 'last_name', 'phone', 'is_active', 'date_joined', 'permissions']
        read_only_fields = fields

    @extend_schema_field(serializers.CharField())
    def get_phone(self, obj):
        return getattr(getattr(obj, 'profile', None), 'phone', '')

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_permissions(self, obj):
        sub_admin_perms = _get_sub_admin_permissions()
        assigned = obj.user_permissions.filter(id__in=sub_admin_perms)
        return list(assigned.values_list('codename', flat=True))


class SubAdminPermissionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=['add', 'remove', 'replace'],
        default='replace',
        help_text=(
            "add     — add these permissions to existing ones\n"
            "remove  — remove these permissions from existing ones\n"
            "replace — replace all permissions with this list (default)"
        ),
    )
    permissions = serializers.ListField(
        child=serializers.CharField(),
        help_text="List of permission codenames to add, remove, or replace.",
    )

    def validate_permissions(self, value):
        valid = {c for c, _ in SUB_ADMIN_PERMISSIONS}
        invalid = [p for p in value if p not in valid]
        if invalid:
            raise serializers.ValidationError(
                f"Invalid permission codenames: {invalid}. "
                f"Valid options: {sorted(valid)}"
            )
        return value


class AvailablePermissionSerializer(serializers.Serializer):
    codename    = serializers.CharField()
    description = serializers.CharField()


# ─── ViewSet ─────────────────────────────────────────────────────────────────

class SubAdminUpdateSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150, required=False, help_text="Sub-admin's first name")
    last_name  = serializers.CharField(max_length=150, required=False, allow_blank=True, help_text="Sub-admin's last name")
    phone      = serializers.CharField(max_length=15,  required=False, allow_blank=True, help_text="Indian phone number (10 digits)")


@extend_schema_view(
    list=extend_schema(tags=['Admin - Sub Admins']),
    retrieve=extend_schema(tags=['Admin - Sub Admins']),
    create=extend_schema(tags=['Admin - Sub Admins']),
    partial_update=extend_schema(
        tags=['Admin - Sub Admins'],
        request=SubAdminUpdateSerializer,
        responses=SubAdminSerializer,
        summary="Update sub-admin profile",
        description="Update first name, last name, and/or phone number of a sub-admin.",
    ),
    destroy=extend_schema(tags=['Admin - Sub Admins']),
)
class SubAdminViewSet(TranslatedViewSet):
    """
    Manage sub-admin accounts and their configurable permissions.

    - Create sub-admin accounts (super_admin only)
    - Assign/revoke permissions per sub-admin
    - List available permissions
    """

    permission_classes = [IsSuperAdmin]
    pagination_class   = StandardPagination
    filter_backends    = [filters.SearchFilter, filters.OrderingFilter]
    search_fields      = ['email', 'first_name', 'last_name']
    ordering_fields    = ['date_joined', 'email']

    list_message    = 'admin.sub_admins_retrieved'
    create_message  = 'admin.sub_admin_created'
    update_message  = 'admin.sub_admin_updated'
    destroy_message = 'admin.sub_admin_deleted'

    def get_queryset(self):
        try:
            sub_admin_group = Group.objects.get(name=UserRole.SUB_ADMIN)
            return User.objects.filter(
                groups=sub_admin_group
            ).prefetch_related('user_permissions').order_by('-date_joined')
        except Group.DoesNotExist:
            return User.objects.none()

    def get_serializer_class(self):
        if self.action == 'create':
            return SubAdminCreateSerializer
        return SubAdminSerializer

    def create(self, request, *args, **kwargs):
        lang = self.get_language()
        serializer = SubAdminCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        temp_password = secrets.token_urlsafe(10)

        user = User.objects.create_user(
            username=data['email'],
            email=data['email'],
            password=temp_password,
            first_name=data['first_name'],
            last_name=data.get('last_name', ''),
        )

        sub_admin_group, _ = Group.objects.get_or_create(name=UserRole.SUB_ADMIN)
        user.groups.add(sub_admin_group)

        if data.get('permissions'):
            self._assign_permissions(user, data['permissions'])

        profile = user.profile
        if data.get('phone'):
            profile.phone = data['phone']
        profile.must_change_password = True
        profile.save(update_fields=['phone', 'must_change_password'])

        channel = data.get('notification_channel', 'email')
        try:
            frontend_url = getattr(django_settings, 'FRONTEND_URL', '')
            send_notification(
                user=user,
                code='welcome',
                channel=channel,
                context={
                    'user_name':     user.first_name,
                    'email':         user.email,
                    'temp_password': temp_password,
                    'button_link':   frontend_url,
                    'button_text':   'Login Now',
                },
                lang=lang,
            )
        except Exception:
            logger.exception(f"Failed to send welcome notification to {user.email}")

        return StandardResponse.success(
            data=SubAdminSerializer(user).data,
            message=t(self.create_message, lang),
            status_code=201,
        )

    def partial_update(self, request, *args, **kwargs):
        """PATCH /api/admin/sub-admins/{id}/ — edit name and/or phone."""
        lang = self.get_language()
        user = self.get_object()

        first_name = request.data.get('first_name')
        last_name  = request.data.get('last_name')
        phone      = request.data.get('phone')

        user_fields = []
        if first_name is not None:
            user.first_name = first_name
            user_fields.append('first_name')
        if last_name is not None:
            user.last_name = last_name
            user_fields.append('last_name')
        if user_fields:
            user.save(update_fields=user_fields)

        if phone is not None:
            if phone:
                from apps.core.utils.validators import validate_indian_phone
                from django.core.exceptions import ValidationError as DjangoValidationError
                from rest_framework import serializers as drf_serializers
                try:
                    validate_indian_phone(phone)
                except DjangoValidationError as e:
                    raise drf_serializers.ValidationError({'phone': str(e)})
            profile = user.profile
            profile.phone = phone
            profile.save(update_fields=['phone'])

        return StandardResponse.success(
            data=SubAdminSerializer(user).data,
            message=t(self.update_message, lang),
        )

    def destroy(self, request, *args, **kwargs):
        lang = self.get_language()
        obj  = self.get_object()
        obj.delete()
        return StandardResponse.success(message=t(self.destroy_message, lang))

    @extend_schema(
        methods=['get'],
        tags=['Admin - Sub Admins'],
        responses=SubAdminSerializer,
        summary="Get sub-admin permissions",
        description="Returns the sub-admin's currently assigned permissions.",
    )
    @extend_schema(
        methods=['post'],
        tags=['Admin - Sub Admins'],
        request=SubAdminPermissionSerializer,
        responses=SubAdminSerializer,
        summary="Update sub-admin permissions",
        description=(
            "Add, remove, or replace sub-admin permissions.\n\n"
            "**action: replace** (default) — replaces all permissions with the given list\n\n"
            "**action: add** — adds the given permissions to existing ones\n\n"
            "**action: remove** — removes the given permissions from existing ones"
        ),
    )
    @action(detail=True, methods=['get', 'post'], url_path='permissions')
    def permissions(self, request, pk=None):
        """GET — view assigned permissions. POST — add/remove/replace permissions."""
        lang = self.get_language()
        user = self.get_object()

        if request.method == 'POST':
            serializer = SubAdminPermissionSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            self._assign_permissions(
                user,
                serializer.validated_data['permissions'],
                action=serializer.validated_data.get('action', 'replace'),
            )
            return StandardResponse.success(
                data=SubAdminSerializer(user).data,
                message=t('admin.sub_admin_permissions_updated', lang),
            )

        return StandardResponse.success(
            data=SubAdminSerializer(user).data,
            message=t('admin.sub_admin_retrieved', lang),
        )

    @extend_schema(tags=['Admin - Sub Admins'],
                   responses=AvailablePermissionSerializer(many=True))
    @action(detail=False, methods=['get'], url_path='available-permissions')
    def available_permissions(self, request):
        """List all permissions that can be assigned to sub-admins."""
        lang = self.get_language()
        data = [{'codename': c, 'description': d} for c, d in SUB_ADMIN_PERMISSIONS]
        return StandardResponse.success(
            data=data,
            message=t('admin.sub_admin_permissions_retrieved', lang),
        )

    @extend_schema(tags=['Admin - Sub Admins'])
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        lang = self.get_language()
        user = self.get_object()
        user.is_active = True
        user.save()
        return StandardResponse.success(
            data=SubAdminSerializer(user).data,
            message=t('admin.sub_admin_activated', lang),
        )

    @extend_schema(tags=['Admin - Sub Admins'])
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        lang = self.get_language()
        user = self.get_object()
        user.is_active = False
        user.save()
        return StandardResponse.success(
            data=SubAdminSerializer(user).data,
            message=t('admin.sub_admin_deactivated', lang),
        )

    @extend_schema(
        tags=['Admin - Sub Admins'],
        request=None,
        responses=SubAdminSerializer,
        summary="Reset sub-admin password",
        description=(
            "Generates a new temporary password for the sub-admin and sends it via email or SMS. "
            "The sub-admin will be required to change it on next login. "
            "Pass `notification_channel` in the request body to choose delivery method (default: email)."
        ),
    )
    @action(detail=True, methods=['post'], url_path='reset-password')
    def reset_password(self, request, pk=None):
        lang    = self.get_language()
        user    = self.get_object()
        channel = request.data.get('notification_channel', 'email')

        if channel == 'sms' and not getattr(getattr(user, 'profile', None), 'phone', ''):
            return StandardResponse.error(
                message='Cannot use SMS — this sub-admin has no phone number on record.',
                status_code=400,
            )

        temp_password = secrets.token_urlsafe(10)
        user.set_password(temp_password)
        user.save(update_fields=['password'])

        profile = user.profile
        profile.must_change_password = True
        profile.save(update_fields=['must_change_password'])

        try:
            frontend_url = getattr(django_settings, 'FRONTEND_URL', '')
            send_notification(
                user=user,
                code='welcome',
                channel=channel,
                context={
                    'user_name':     user.first_name or user.username,
                    'email':         user.email,
                    'temp_password': temp_password,
                    'button_link':   frontend_url,
                    'button_text':   'Login Now',
                },
                lang=lang,
            )
        except Exception:
            logger.exception(f"Failed to send reset-password notification to {user.email}")

        return StandardResponse.success(
            data=SubAdminSerializer(user).data,
            message=t('admin.sub_admin_password_reset', lang),
        )

    def _assign_permissions(self, user, codenames, action='replace'):
        """Add, remove, or replace sub-admin permissions."""
        all_sub_admin_perms = _get_sub_admin_permissions()

        if action == 'replace':
            user.user_permissions.remove(*all_sub_admin_perms)
            if codenames:
                user.user_permissions.add(*all_sub_admin_perms.filter(codename__in=codenames))

        elif action == 'add':
            if codenames:
                user.user_permissions.add(*all_sub_admin_perms.filter(codename__in=codenames))

        elif action == 'remove':
            if codenames:
                user.user_permissions.remove(*all_sub_admin_perms.filter(codename__in=codenames))
