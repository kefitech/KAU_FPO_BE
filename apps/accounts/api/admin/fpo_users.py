"""
Admin — FPO User Management
=============================
GET   /api/admin/fpo-users/                      — list all FPO users (primary + secondary)
GET   /api/admin/fpo-users/{id}/                 — detail
POST  /api/admin/fpo-users/{id}/activate/        — activate account
POST  /api/admin/fpo-users/{id}/deactivate/      — deactivate account
POST  /api/admin/fpo-users/{id}/reset-password/  — generate temp password + notify user

Filters (list):
    role        — primary / secondary
    fpo_id      — filter by FPO
    is_active   — true / false
    search      — name or email
"""

import secrets
import string

from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import serializers, status
from rest_framework.views import APIView

from apps.core.utils.constants import UserRole
from apps.core.utils.pagination import StandardPagination
from apps.core.utils.responses import StandardResponse
from apps.core.utils.validators import validate_password_strength
from apps.database.models.fpo import FPO, FPOUserMembership
from apps.notifications.services import send_notification

User = get_user_model()


def _is_admin(user):
    return user.groups.filter(name__in=[UserRole.SUPER_ADMIN, UserRole.SUB_ADMIN]).exists()


def _generate_temp_password():
    chars = string.ascii_letters + string.digits + '!@#$%'
    while True:
        pwd = ''.join(secrets.choice(chars) for _ in range(12))
        try:
            validate_password_strength(pwd)
            return pwd
        except Exception:
            continue


class FPOUserSerializer(serializers.Serializer):
    id            = serializers.IntegerField(source='user.id')
    first_name    = serializers.CharField(source='user.first_name')
    last_name     = serializers.CharField(source='user.last_name')
    email         = serializers.EmailField(source='user.email')
    phone         = serializers.SerializerMethodField()
    role          = serializers.SerializerMethodField()
    fpo_id        = serializers.IntegerField(source='fpo.id')
    fpo_name      = serializers.CharField(source='fpo.name')
    is_active     = serializers.BooleanField()
    joined_at     = serializers.DateTimeField()
    last_login    = serializers.DateTimeField(source='user.last_login')

    def get_phone(self, obj):
        profile = getattr(obj.user, 'profile', None)
        return profile.phone if profile else None

    def get_role(self, obj):
        return obj.role.name if obj.role else None


class FPOUserListView(APIView):
    permission_classes = []

    @extend_schema(
        tags=['Admin - FPO Users'],
        summary='List all FPO users',
        description='Returns all FPO primary and secondary users with their FPO and account status.',
        parameters=[
            OpenApiParameter('role',      str,  description='Filter by role: primary / secondary'),
            OpenApiParameter('fpo_id',    int,  description='Filter by FPO ID'),
            OpenApiParameter('is_active', bool, description='Filter by active status: true / false'),
            OpenApiParameter('search',    str,  description='Search by name or email'),
        ],
    )
    def get(self, request):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        qs = FPOUserMembership.objects.select_related(
            'user', 'user__profile', 'fpo', 'role'
        ).filter(is_deleted=False)

        role = request.query_params.get('role')
        if role:
            qs = qs.filter(role__name=role)

        fpo_id = request.query_params.get('fpo_id')
        if fpo_id:
            qs = qs.filter(fpo_id=fpo_id)

        is_active = request.query_params.get('is_active')
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() == 'true')

        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                user__first_name__icontains=search
            ) | qs.filter(
                user__last_name__icontains=search
            ) | qs.filter(
                user__email__icontains=search
            )

        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(FPOUserSerializer(page, many=True).data)


class FPOUserDetailView(APIView):

    def _get(self, user_id):
        try:
            return FPOUserMembership.objects.select_related(
                'user', 'user__profile', 'fpo', 'role'
            ).get(user_id=user_id, is_deleted=False)
        except FPOUserMembership.DoesNotExist:
            return None

    @extend_schema(tags=['Admin - FPO Users'], summary='Retrieve an FPO user')
    def get(self, request, user_id):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        membership = self._get(user_id)
        if not membership:
            return StandardResponse.error('User not found.', status_code=status.HTTP_404_NOT_FOUND)
        return StandardResponse.success(data=FPOUserSerializer(membership).data)


class FPOUserActivateView(APIView):

    @extend_schema(tags=['Admin - FPO Users'], summary='Activate an FPO user account')
    def post(self, request, user_id):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        try:
            membership = FPOUserMembership.objects.select_related('user').get(
                user_id=user_id, is_deleted=False
            )
        except FPOUserMembership.DoesNotExist:
            return StandardResponse.error('User not found.', status_code=status.HTTP_404_NOT_FOUND)

        membership.user.is_active = True
        membership.user.save(update_fields=['is_active'])
        membership.is_active = True
        membership.save(update_fields=['is_active'])
        return StandardResponse.success(message='User activated.')


class FPOUserDeactivateView(APIView):

    @extend_schema(tags=['Admin - FPO Users'], summary='Deactivate an FPO user account')
    def post(self, request, user_id):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        try:
            membership = FPOUserMembership.objects.select_related('user').get(
                user_id=user_id, is_deleted=False
            )
        except FPOUserMembership.DoesNotExist:
            return StandardResponse.error('User not found.', status_code=status.HTTP_404_NOT_FOUND)

        membership.user.is_active = False
        membership.user.save(update_fields=['is_active'])
        membership.is_active = False
        membership.save(update_fields=['is_active'])
        return StandardResponse.success(message='User deactivated.')


class FPOUserResetPasswordView(APIView):

    @extend_schema(
        tags=['Admin - FPO Users'],
        summary='Reset an FPO user password',
        description='Generates a temporary password, sets must_change_password=True, and notifies the user via email and SMS.',
    )
    def post(self, request, user_id):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        try:
            membership = FPOUserMembership.objects.select_related(
                'user', 'user__profile'
            ).get(user_id=user_id, is_deleted=False)
        except FPOUserMembership.DoesNotExist:
            return StandardResponse.error('User not found.', status_code=status.HTTP_404_NOT_FOUND)

        user = membership.user
        temp_password = _generate_temp_password()
        user.set_password(temp_password)
        user.save(update_fields=['password'])

        profile = getattr(user, 'profile', None)
        if profile:
            profile.must_change_password = True
            profile.save(update_fields=['must_change_password'])

        context = {
            'user_name':      f'{user.first_name} {user.last_name}'.strip() or user.email,
            'temp_password':  temp_password,
            'button_link':    '',
            'button_text':    'Login',
        }
        try:
            send_notification(user=user, code='password_reset_by_admin', channel='email', context=context)
        except Exception:
            pass
        try:
            phone = profile.phone if profile else None
            if phone:
                send_notification(
                    user=user, code='password_reset_by_admin', channel='sms',
                    context=context, override_recipient=phone,
                )
        except Exception:
            pass

        return StandardResponse.success(message='Password reset. User will be prompted to change it on next login.')
