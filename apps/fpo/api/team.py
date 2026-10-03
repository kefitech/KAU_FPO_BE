"""
FPO Team Management API
========================
Manage secondary users within an FPO.

GET   /api/fpo/me/team/                      — list all team members
POST  /api/fpo/me/team/invite/               — invite single user
POST  /api/fpo/me/team/bulk-invite/          — invite multiple via JSON
POST  /api/fpo/me/team/bulk-invite-file/     — invite multiple via Excel/CSV
POST  /api/fpo/me/team/bulk-activate/        — activate multiple by user_ids
POST  /api/fpo/me/team/bulk-deactivate/      — deactivate multiple by user_ids
POST  /api/fpo/me/team/{id}/deactivate/      — deactivate single user
GET   /api/fpo/me/team/available-permissions/ — actions the primary can grant a member
GET   /api/fpo/me/team/{id}/permissions/     — a member's permissions
POST  /api/fpo/me/team/{id}/permissions/     — add/remove/replace a member's permissions
POST  /api/fpo/me/team/bulk-permissions/     — grant/revoke permissions for many members

Rules:
- FPO must be APPROVED before inviting members
- Only the primary user can invite / activate / deactivate
- No secondary user limit (KAU confirmed)
- Invited users are auto-activated (no approval step)
- Invited users must change password on first login
- Member permissions: the super admin's role ceiling (RoleActionPermission)
  limits what the primary can grant; the primary's choices are stored as
  FPOMemberOverride rows. Members without overrides get the role defaults.
"""

import csv
import io
import secrets
import re

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from django.http import HttpResponse

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.parsers import MultiPartParser
from rest_framework.views import APIView

import openpyxl

from apps.core.models.generic import AuditLog
from apps.core.permissions.rbac import IsFPOManager
from apps.core.services.audit import AuditService as AuditLogService
from apps.core.services.fpo_permission import (
    get_effective_permissions, get_grantable_actions, set_member_permissions,
)
from apps.core.services.translation import t
from apps.core.utils.constants import FPOStatus, UserRole
from apps.core.utils.responses import StandardResponse
from django.contrib.contenttypes.models import ContentType
from apps.database.models.fpo import FPO, FPOUserMembership
from apps.notifications.services import send_notification

User = get_user_model()


EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_primary_fpo(user):
    """Return FPO only if this user is the primary user."""
    return FPO.objects.filter(primary_user=user, is_deleted=False).first()

def _last_deactivated_by_admin(membership):
    """
    Check if the most recent activate/deactivate AuditLog entry for this
    membership was a deactivation performed by an admin.
    """
    ct = ContentType.objects.get_for_model(membership)
    last = AuditLog.objects.filter(
        content_type=ct,
        object_id=str(membership.pk),
        action__in=[AuditLog.Action.FPO_USER_ACTIVATE, AuditLog.Action.FPO_USER_DEACTIVATE],
    ).order_by('-created_at').first()

    if last and last.action == AuditLog.Action.FPO_USER_DEACTIVATE and last.user:
        return last.user.groups.filter(
            name__in=[UserRole.SUPER_ADMIN, UserRole.SUB_ADMIN]
        ).exists()
    return False
# ─────────────────────────────────────────────────────────────────────────────
# Serializers
# ─────────────────────────────────────────────────────────────────────────────

class TeamInviteSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150)
    last_name  = serializers.CharField(max_length=150)
    email      = serializers.EmailField()
    phone      = serializers.CharField(max_length=10, required=False, allow_blank=True)
    permissions = serializers.ListField(
        child=serializers.CharField(), required=False,
        help_text='Action codes to grant. Omit to give the role defaults; any grantable code left out is revoked.',
    )

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('A user with this email already exists.')
        return value.lower()

    def validate_permissions(self, value):
        return _validate_grantable(value)


def _secondary_group():
    return Group.objects.get(name='secondary')


def _validate_grantable(codes, role=None):
    """Reject codes the primary is not allowed to grant (outside the role ceiling)."""
    grantable = set(get_grantable_actions(role or _secondary_group()).values_list('code', flat=True))
    invalid = sorted(set(codes) - grantable)
    if invalid:
        raise serializers.ValidationError(f'These permissions cannot be granted: {", ".join(invalid)}.')
    return list(dict.fromkeys(codes))


class MemberPermissionSerializer(serializers.Serializer):
    action      = serializers.ChoiceField(choices=['replace', 'add', 'remove'], default='replace')
    permissions = serializers.ListField(child=serializers.CharField(), allow_empty=True)


class BulkMemberPermissionSerializer(serializers.Serializer):
    user_ids = serializers.ListField(child=serializers.IntegerField(), min_length=1)
    grant    = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    revoke   = serializers.ListField(child=serializers.CharField(), required=False, default=list)

    def validate(self, attrs):
        if not attrs['grant'] and not attrs['revoke']:
            raise serializers.ValidationError('Nothing to change — send `grant` and/or `revoke`.')
        if set(attrs['grant']) & set(attrs['revoke']):
            raise serializers.ValidationError('A permission cannot be granted and revoked at once.')
        return attrs


def _permission_rows(role, lang, effective=None):
    """Grantable actions as [{code, label, description, page, is_allowed}] for the team UI."""
    rows = []
    for action in get_grantable_actions(role):
        rows.append({
            'code':        action.code,
            'label':       action.get_label(lang),
            'description': action.description,
            'page':        action.menu_item.path if action.menu_item else None,
            # Role default is "allowed" — the ceiling already allows every grantable action
            'is_allowed':  True if effective is None else effective.get(action.code, False),
        })
    return rows


class FPOTeamMemberSerializer(serializers.ModelSerializer):
    id         = serializers.IntegerField(source='user.id', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name  = serializers.CharField(source='user.last_name', read_only=True)
    email      = serializers.EmailField(source='user.email', read_only=True)
    phone      = serializers.SerializerMethodField()
    role       = serializers.CharField(source='role.name', read_only=True)
    joined_at  = serializers.DateTimeField(read_only=True)

    class Meta:
        model  = FPOUserMembership
        fields = ['id', 'first_name', 'last_name', 'email', 'phone', 'role', 'is_active', 'joined_at']

    def get_phone(self, obj):
        profile = getattr(obj.user, 'profile', None)
        return profile.phone if profile else ''


# ─────────────────────────────────────────────────────────────────────────────
# Views
# ─────────────────────────────────────────────────────────────────────────────

class TeamListView(APIView):
    permission_classes = [IsFPOManager]

    @extend_schema(
        tags=['FPO - Team'],
        summary='List team members',
        description='Returns all team members of this FPO. Primary users can manage them; secondary users get a read-only view.',
        responses={200: FPOTeamMemberSerializer(many=True)},
    )
    def get(self, request):
        fpo = _get_primary_fpo(request.user)
        if not fpo:
            # Team members get a read-only view of their own FPO's team
            membership = FPOUserMembership.objects.filter(
                user=request.user, is_active=True, is_deleted=False,
            ).select_related('fpo').first()
            fpo = membership.fpo if membership else None
        if not fpo:
            return StandardResponse.error(
                'Only FPO members can view the team.',
                status_code=status.HTTP_403_FORBIDDEN,
            )

        memberships = FPOUserMembership.objects.filter(
            fpo=fpo, is_deleted=False
        ).select_related('user', 'user__profile', 'role')
        # The primary manages the team, so they don't list themselves;
        # team members see their own row as well.
        is_primary = fpo.primary_user_id == request.user.id
        if is_primary:
            memberships = memberships.exclude(user=request.user)
        memberships = list(memberships)
        data = FPOTeamMemberSerializer(memberships, many=True).data

        # The primary manages permissions, so they also get each member's granted
        # actions (only those they can toggle) for the team table and bulk edit.
        if is_primary:
            grantable = set(get_grantable_actions(_secondary_group()).values_list('code', flat=True))
            for row, membership in zip(data, memberships):
                effective = get_effective_permissions(membership) if membership.role else {}
                row['permissions'] = [c for c, ok in effective.items() if ok and c in grantable]

        # The FPO owner has no membership row, so a team member wouldn't see
        # them. Prepend the owner in the same shape.
        owner = fpo.primary_user
        if owner and owner.id != request.user.id:
            profile = getattr(owner, 'profile', None)
            data = [{
                'id':         owner.id,
                'first_name': owner.first_name,
                'last_name':  owner.last_name,
                'email':      owner.email,
                'phone':      profile.phone if profile else '',
                'role':       'primary',
                'is_active':  owner.is_active,
                'joined_at':  fpo.created_at,
            }, *data]

        return StandardResponse.success(data, 'Team members retrieved.')


class TeamInviteView(APIView):
    permission_classes = [IsFPOManager]

    @extend_schema(
        tags=['FPO - Team'],
        summary='Invite secondary user',
        description=(
            'Creates a secondary user account and adds them to the FPO team. '
            'The invited user receives a welcome email with a temporary password '
            'and must change it on first login.\n\n'
            '**Rules:**\n'
            '- FPO must be in APPROVED status\n'
            '- Only the primary user can invite members\n'
            '- No limit on secondary users\n'
            '- Email must not already be registered'
        ),
        request=TeamInviteSerializer,
        responses={201: None},
    )
    def post(self, request):
        fpo = _get_primary_fpo(request.user)
        if not fpo:
            return StandardResponse.error(
                'Only the primary user can invite team members.',
                status_code=status.HTTP_403_FORBIDDEN,
            )

        if fpo.status != FPOStatus.APPROVED:
            return StandardResponse.error(
                'Team members can only be invited after the FPO is approved.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        serializer = TeamInviteSerializer(data=request.data)
        if not serializer.is_valid():
            return StandardResponse.validation_error(errors=serializer.errors)

        data = serializer.validated_data
        temp_password = secrets.token_urlsafe(10)

        with transaction.atomic():
            # Create user account
            user = User.objects.create_user(
                username=data['email'],
                email=data['email'],
                first_name=data['first_name'],
                last_name=data['last_name'],
                password=temp_password,
            )

            # Assign fpo_manager + secondary group
            fpo_manager_group = Group.objects.get(name=UserRole.FPO_MANAGER)
            secondary_group   = Group.objects.get(name='secondary')
            user.groups.add(fpo_manager_group, secondary_group)

            # Set profile
            profile = getattr(user, 'profile', None)
            if profile:
                if data.get('phone'):
                    profile.phone = data['phone']
                profile.must_change_password = True
                profile.save(update_fields=['phone', 'must_change_password'])

            # Create membership — auto-activated
            membership = FPOUserMembership.objects.create(
                fpo=fpo,
                user=user,
                role=secondary_group,
                is_active=True,
                created_by=request.user,
            )

            # No list sent → role defaults (no overrides)
            if 'permissions' in data:
                set_member_permissions(membership, data['permissions'])

        # Send welcome notification
        lang = getattr(request, 'language', 'en')
        send_notification(
            user=user,
            code='welcome',
            channel='email',
            context={
                'user_name':    f'{data["first_name"]} {data["last_name"]}',
                'email':        data['email'],
                'temp_password': temp_password,
            },
            lang=lang,
        )

        # Audit log
        AuditLogService.log(
            user=request.user,
            action=AuditLog.Action.FPO_USER_INVITE,
            instance=fpo,
            request=request,
            changes={
                'invited_user':  data['email'],
                'invited_name':  f'{data["first_name"]} {data["last_name"]}',
                **({'permissions': data['permissions']} if 'permissions' in data else {}),
            },
        )

        return StandardResponse.created(
            data={
                'id':         user.id,
                'email':      user.email,
                'first_name': user.first_name,
                'last_name':  user.last_name,
            },
            message='Team member invited successfully. A welcome email with login credentials has been sent.',
        )


class TeamAvailablePermissionsView(APIView):
    permission_classes = [IsFPOManager]

    @extend_schema(
        tags=['FPO - Team'],
        summary='Permissions the primary user can grant',
        description=(
            'Actions the super admin allows for secondary users (the role ceiling), with '
            'translated labels. `is_allowed` is the role default a new member gets.'
        ),
        responses={200: None},
    )
    def get(self, request):
        if not _get_primary_fpo(request.user):
            return StandardResponse.error(
                'Only the primary user can manage member permissions.',
                status_code=status.HTTP_403_FORBIDDEN,
            )
        lang = getattr(request, 'language', 'en')
        return StandardResponse.success(_permission_rows(_secondary_group(), lang), 'Permissions retrieved.')


class TeamMemberPermissionsView(APIView):
    permission_classes = [IsFPOManager]

    def _membership(self, request, user_id):
        fpo = _get_primary_fpo(request.user)
        if not fpo:
            return None, StandardResponse.error(
                'Only the primary user can manage member permissions.',
                status_code=status.HTTP_403_FORBIDDEN,
            )
        membership = (
            FPOUserMembership.objects.select_related('role', 'user')
            .filter(fpo=fpo, user_id=user_id, is_deleted=False)
            .exclude(user_id=fpo.primary_user_id)  # the owner always has every permission
            .first()
        )
        if not membership or not membership.role:
            return None, StandardResponse.error('Team member not found.', status_code=status.HTTP_404_NOT_FOUND)
        return membership, None

    def _response(self, request, membership, message):
        lang = getattr(request, 'language', 'en')
        rows = _permission_rows(membership.role, lang, get_effective_permissions(membership))
        return StandardResponse.success({'user_id': membership.user_id, 'permissions': rows}, message)

    @extend_schema(tags=['FPO - Team'], summary="A member's permissions", responses={200: None, 404: None})
    def get(self, request, user_id):
        membership, error = self._membership(request, user_id)
        if error:
            return error
        return self._response(request, membership, 'Permissions retrieved.')

    @extend_schema(
        tags=['FPO - Team'],
        summary="Update a member's permissions",
        description=(
            '**action: replace** (default) — grant exactly the given list, revoke the rest\n\n'
            '**action: add** — grant the given permissions\n\n'
            '**action: remove** — revoke the given permissions\n\n'
            'Only actions the role ceiling allows can be granted.'
        ),
        request=MemberPermissionSerializer,
        responses={200: None, 400: None, 404: None},
    )
    def post(self, request, user_id):
        membership, error = self._membership(request, user_id)
        if error:
            return error
        serializer = MemberPermissionSerializer(data=request.data)
        if not serializer.is_valid():
            return StandardResponse.validation_error(errors=serializer.errors)
        try:
            codes = _validate_grantable(serializer.validated_data['permissions'], membership.role)
        except serializers.ValidationError as exc:
            return StandardResponse.validation_error(errors={'permissions': exc.detail})

        mode = serializer.validated_data['action']
        with transaction.atomic():
            set_member_permissions(membership, codes, mode)
        AuditLogService.log(
            user=request.user,
            action=AuditLog.Action.UPDATE,
            instance=membership,
            request=request,
            changes={'permissions': {'action': mode, 'codes': codes}},
        )
        return self._response(request, membership, 'Permissions updated.')


class TeamBulkPermissionsView(APIView):
    permission_classes = [IsFPOManager]

    @extend_schema(
        tags=['FPO - Team'],
        summary='Bulk update member permissions',
        description=(
            'Apply the same change to several members at once.\n\n'
            '**grant** — permissions every selected member gets\n\n'
            '**revoke** — permissions every selected member loses\n\n'
            'Permissions in neither list are left as they are for each member. '
            'Members not in this FPO are reported in `errors`; the rest are updated.'
        ),
        request=BulkMemberPermissionSerializer,
        responses={200: None, 400: None},
    )
    def post(self, request):
        fpo = _get_primary_fpo(request.user)
        if not fpo:
            return StandardResponse.error(
                'Only the primary user can manage member permissions.',
                status_code=status.HTTP_403_FORBIDDEN,
            )
        serializer = BulkMemberPermissionSerializer(data=request.data)
        if not serializer.is_valid():
            return StandardResponse.validation_error(errors=serializer.errors)
        data = serializer.validated_data
        try:
            grant  = _validate_grantable(data['grant'])
            revoke = _validate_grantable(data['revoke'])
        except serializers.ValidationError as exc:
            return StandardResponse.validation_error(errors={'permissions': exc.detail})

        memberships = {
            m.user_id: m
            for m in FPOUserMembership.objects.select_related('user', 'role')
            .filter(fpo=fpo, user_id__in=data['user_ids'], is_deleted=False)
        }
        success, failed = [], []
        with transaction.atomic():
            for uid in dict.fromkeys(data['user_ids']):
                if uid == fpo.primary_user_id:
                    failed.append({'user_id': uid, 'reason': 'The primary user always has every permission.'})
                    continue
                membership = memberships.get(uid)
                if not membership or not membership.role:
                    failed.append({'user_id': uid, 'reason': 'Team member not found.'})
                    continue
                set_member_permissions(membership, grant, 'add')
                set_member_permissions(membership, revoke, 'remove')
                success.append({'user_id': uid, 'name': membership.user.get_full_name()})
                AuditLogService.log(
                    user=request.user,
                    action=AuditLog.Action.UPDATE,
                    instance=membership,
                    request=request,
                    changes={'permissions': {'grant': grant, 'revoke': revoke}},
                )

        return StandardResponse.success(
            data={'success': len(success), 'failed': len(failed), 'results': success, 'errors': failed},
            message=f'Permissions updated for {len(success)} member(s), {len(failed)} failed.',
        )


class TeamDeactivateView(APIView):
    permission_classes = [IsFPOManager]

    @extend_schema(
        tags=['FPO - Team'],
        summary='Deactivate team member',
        description='Deactivates a secondary user. They will no longer be able to log in. Only the primary user can do this.',
        responses={200: None},
    )
    def post(self, request, user_id):
        fpo = _get_primary_fpo(request.user)
        if not fpo:
            return StandardResponse.error(
                'Only the primary user can deactivate team members.',
                status_code=status.HTTP_403_FORBIDDEN,
            )

        try:
            membership = FPOUserMembership.objects.select_related('user').get(
                fpo=fpo, user_id=user_id, is_deleted=False,
            )
        except FPOUserMembership.DoesNotExist:
            return StandardResponse.error(
                'Team member not found.',
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if membership.user == request.user:
            return StandardResponse.error(
                'You cannot deactivate yourself.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if not membership.is_active:
            return StandardResponse.error(
                'This team member is already inactive.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        membership.is_active = False
        membership.updated_by = request.user
        membership.save(update_fields=['is_active', 'updated_by'])

        # Also deactivate their Django account
        membership.user.is_active = False
        membership.user.save(update_fields=['is_active'])

        AuditLogService.log(
            user=request.user,
            action=AuditLog.Action.FPO_USER_DEACTIVATE,
            instance=fpo,
            request=request,
            changes={'deactivated_user': membership.user.email},
        )

        return StandardResponse.success(
            message=f'{membership.user.get_full_name()} has been deactivated.',
        )


class TeamResetPasswordView(APIView):
    permission_classes = [IsFPOManager]

    @extend_schema(
        tags=['FPO - Team'],
        summary='Reset secondary user password',
        description=(
            'Generates a new temporary password for a secondary user and sends it to their email. '
            'The primary user never sees the password — it goes directly to the secondary user. '
            'The secondary user is forced to change it on next login.'
        ),
        responses={200: None},
    )
    def post(self, request, user_id):
        fpo = _get_primary_fpo(request.user)
        if not fpo:
            return StandardResponse.error(
                'Only the primary user can reset team member passwords.',
                status_code=status.HTTP_403_FORBIDDEN,
            )

        try:
            membership = FPOUserMembership.objects.select_related('user', 'user__profile').get(
                fpo=fpo, user_id=user_id, is_deleted=False,
            )
        except FPOUserMembership.DoesNotExist:
            return StandardResponse.error('Team member not found.', status_code=status.HTTP_404_NOT_FOUND)

        if membership.user == request.user:
            return StandardResponse.error('You cannot reset your own password here.',
                                          status_code=status.HTTP_400_BAD_REQUEST)

        if not (membership.is_active and membership.user.is_active):
            return StandardResponse.error(
                t('admin.reset_password_inactive_user', getattr(request, 'language', 'en')),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        temp_password = secrets.token_urlsafe(10)
        membership.user.set_password(temp_password)
        membership.user.save(update_fields=['password'])

        profile = getattr(membership.user, 'profile', None)
        if profile:
            profile.must_change_password = True
            profile.save(update_fields=['must_change_password'])

        lang = getattr(request, 'language', 'en')
        send_notification(
            user=membership.user,
            code='welcome',
            channel='email',
            context={
                'user_name':     membership.user.get_full_name(),
                'email':         membership.user.email,
                'temp_password': temp_password,
            },
            lang=lang,
        )

        return StandardResponse.success(
            message=f'Password reset. New credentials have been sent to {membership.user.email}.',
        )


# ─────────────────────────────────────────────────────────────────────────────
# Shared invite helper
# ─────────────────────────────────────────────────────────────────────────────

def _create_member(fpo, row, inviter, lang):
    """
    Create one secondary user from a dict with keys:
    first_name, last_name, email, phone (optional).

    Returns (user, temp_password) on success.
    Raises ValueError with a human-readable message on failure.
    """
    email      = (row.get('email') or '').strip().lower()      # CHANGED: handles None value, not just missing key
    first_name = (row.get('first_name') or '').strip()          # CHANGED
    last_name  = (row.get('last_name') or '').strip()           # CHANGED
    phone      = (row.get('phone') or '').strip()                # CHANGED

    missing = []                                                  # NEW
    if not first_name:                                             # NEW
        missing.append('first_name')                              # NEW
    if not last_name:                                              # NEW
        missing.append('last_name')                                # NEW
    if not email:                                                  # NEW
        missing.append('email')                                    # NEW

    if missing:                                                    # NEW (replaces old if/raise below)
        if len(missing) == 1:                                       # NEW
            raise ValueError(f'{missing[0]} is required.')          # NEW
        elif len(missing) == 2:                                     # NEW
            raise ValueError(f'{missing[0]} and {missing[1]} are required.')  # NEW
        else:                                                        # NEW
            raise ValueError(f'{", ".join(missing[:-1])}, and {missing[-1]} are required.')  # NEW
        
    if not EMAIL_REGEX.match(email):  
        raise ValueError('Invalid Email')                                # NEW

    if User.objects.filter(email__iexact=email).exists():
        raise ValueError(f'{email} is already registered.')

    if User.objects.filter(email__iexact=email).exists():
        raise ValueError(f'{email} is already registered.')

    temp_password = secrets.token_urlsafe(10)

    with transaction.atomic():
        user = User.objects.create_user(
            username=email,
            email=email,
            first_name=first_name,
            last_name=last_name,
            password=temp_password,
        )
        fpo_manager_group = Group.objects.get(name=UserRole.FPO_MANAGER)
        secondary_group   = Group.objects.get(name='secondary')
        user.groups.add(fpo_manager_group, secondary_group)

        profile = getattr(user, 'profile', None)
        if profile:
            if phone:
                profile.phone = phone
            profile.must_change_password = True
            profile.save(update_fields=['phone', 'must_change_password'])

        FPOUserMembership.objects.create(
            fpo=fpo,
            user=user,
            role=secondary_group,
            is_active=True,
            created_by=inviter,
        )

    send_notification(
        user=user,
        code='welcome',
        channel='email',
        context={
            'user_name':     f'{first_name} {last_name}',
            'email':         email,
            'temp_password': temp_password,
        },
        lang=lang,
    )

    return user, temp_password


# ─────────────────────────────────────────────────────────────────────────────
# Bulk invite — JSON
# ─────────────────────────────────────────────────────────────────────────────

class BulkInviteSerializer(serializers.Serializer):
    members = serializers.ListField(
        child=serializers.DictField(),
        min_length=1,
        max_length=100,
        help_text='List of members. Each must have first_name, last_name, email. phone is optional.',
    )


class TeamBulkInviteView(APIView):
    permission_classes = [IsFPOManager]

    @extend_schema(
        tags=['FPO - Team'],
        summary='Bulk invite team members (JSON)',
        description=(
            'Invite multiple secondary users in one call. '
            'Each row is processed independently — failures do not block others.\n\n'
            '**Request body:**\n'
            '```json\n'
            '{ "members": [\n'
            '  { "first_name": "Rajan", "last_name": "Kumar", "email": "rajan@example.com", "phone": "9876543210" },\n'
            '  { "first_name": "Meera", "last_name": "S", "email": "meera@example.com" }\n'
            '] }\n'
            '```\n\n'
            'Returns a summary with per-row success/failure details.'
        ),
        request=BulkInviteSerializer,
        responses={200: None},
    )
    def post(self, request):
        fpo = _get_primary_fpo(request.user)
        if not fpo:
            return StandardResponse.error(
                'Only the primary user can invite team members.',
                status_code=status.HTTP_403_FORBIDDEN,
            )
        if fpo.status != FPOStatus.APPROVED:
            return StandardResponse.error(
                'Team members can only be invited after the FPO is approved.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        serializer = BulkInviteSerializer(data=request.data)
        if not serializer.is_valid():
            return StandardResponse.validation_error(errors=serializer.errors)

        lang    = getattr(request, 'language', 'en')
        members = serializer.validated_data['members']
        success, failed = [], []

        for i, row in enumerate(members, start=1):
            try:
                user, _ = _create_member(fpo, row, request.user, lang)
                success.append({'row': i, 'email': user.email, 'name': user.get_full_name()})
            except Exception as e:
                failed.append({
                    'row': i,
                    'email': row.get('email', ''),
                    'first_name': row.get('first_name', ''),   # NEW
                    'last_name': row.get('last_name', ''),     # NEW
                    'reason': str(e),
                })

        if success:
            AuditLogService.log(
                user=request.user,
                action=AuditLog.Action.FPO_USER_INVITE,
                instance=fpo,
                request=request,
                changes={'bulk_invited': [r['email'] for r in success]},
            )

        return StandardResponse.success(
            data={'success': len(success), 'failed': len(failed), 'results': success, 'errors': failed},
            message=f'{len(success)} member(s) invited successfully, {len(failed)} failed.',
        )


# ─────────────────────────────────────────────────────────────────────────────
# Bulk invite — Excel / CSV file
# ─────────────────────────────────────────────────────────────────────────────

class TeamBulkInviteFileView(APIView):
    permission_classes = [IsFPOManager]
    parser_classes     = [MultiPartParser]

    @extend_schema(
        tags=['FPO - Team'],
        summary='Bulk invite team members (Excel/CSV)',
        description=(
            'Upload an `.xlsx` or `.csv` file to invite multiple secondary users.\n\n'
            '**Required columns:** `first_name`, `last_name`, `email`\n'
            '**Optional column:** `phone`\n\n'
            'Row 1 must be the header row. Each data row is processed independently.\n'
            'Returns a summary with per-row success/failure details.'
        ),
        responses={200: None},
    )
    def post(self, request):
        fpo = _get_primary_fpo(request.user)
        if not fpo:
            return StandardResponse.error(
                'Only the primary user can invite team members.',
                status_code=status.HTTP_403_FORBIDDEN,
            )
        if fpo.status != FPOStatus.APPROVED:
            return StandardResponse.error(
                'Team members can only be invited after the FPO is approved.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        file = request.FILES.get('file')
        if not file:
            return StandardResponse.error('No file uploaded. Send file as multipart form field "file".',
                                          status_code=status.HTTP_400_BAD_REQUEST)

        filename = file.name.lower()
        rows = []

        try:
            if filename.endswith('.csv'):
                content = file.read().decode('utf-8-sig')
                reader  = csv.DictReader(io.StringIO(content))
                rows    = list(reader)
            elif filename.endswith('.xlsx'):
                wb = openpyxl.load_workbook(file, read_only=True, data_only=True)
                ws = wb.active
                headers = [str(c.value).strip().lower() if c.value else '' for c in next(ws.iter_rows())]
                for row in ws.iter_rows(min_row=2, values_only=True):
                    rows.append(dict(zip(headers, [str(v).strip() if v is not None else '' for v in row])))
            else:
                return StandardResponse.error('Only .xlsx and .csv files are supported.',
                                              status_code=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return StandardResponse.error(f'Could not parse file: {e}',
                                          status_code=status.HTTP_400_BAD_REQUEST)

        if not rows:
            return StandardResponse.error('File is empty or has no data rows.',
                                          status_code=status.HTTP_400_BAD_REQUEST)

        lang = getattr(request, 'language', 'en')
        success, failed = [], []

        for i, row in enumerate(rows, start=2):  # start=2 because row 1 is header
            try:
                user, _ = _create_member(fpo, row, request.user, lang)
                success.append({'row': i, 'email': user.email, 'name': user.get_full_name()})
            except Exception as e:
                failed.append({
                    'row': i,
                    'email': row.get('email', ''),
                    'first_name': row.get('first_name', ''),   # NEW
                    'last_name': row.get('last_name', ''),     # NEW
                    'reason': str(e),
                })

        if success:
            AuditLogService.log(
                user=request.user,
                action=AuditLog.Action.FPO_USER_INVITE,
                instance=fpo,
                request=request,
                changes={'bulk_invited_via_file': [r['email'] for r in success]},
            )

        return StandardResponse.success(
            data={'success': len(success), 'failed': len(failed), 'results': success, 'errors': failed},
            message=f'{len(success)} member(s) invited successfully, {len(failed)} failed.',
        )


# ─────────────────────────────────────────────────────────────────────────────
# Bulk invite template — downloadable .xlsx (3 sheets)
# ─────────────────────────────────────────────────────────────────────────────

class TeamBulkInviteTemplateView(APIView):
    """
    GET /api/fpo/me/team/bulk-invite-template/

    Returns a styled .xlsx with:
      - Instructions sheet (how to fill, column reference, do's/don'ts)
      - Members sheet (header + 3 sample rows — delete before uploading)
      - Role Codes sheet (reference — currently all invites create a
        secondary member, so the sheet documents that explicitly)

    Mirrors the sub-admin bulk-invite-template pattern in
    apps/accounts/api/sub_admins.py so FPOs get a consistent experience
    across the two bulk-invite flows.
    """
    permission_classes = [IsFPOManager]

    @extend_schema(
        tags=['FPO - Team'],
        summary='Download the bulk-invite .xlsx template',
        description=(
            'Returns an .xlsx with Instructions / Members / Role Codes sheets. '
            'Primary user fills the Members sheet and re-uploads via '
            'POST /api/fpo/me/team/bulk-invite-file/.'
        ),
        responses={200: None},
    )
    def get(self, request):
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

        fpo = _get_primary_fpo(request.user)
        if fpo is None:
            return StandardResponse.error(
                'Only the FPO primary user can access the bulk-invite template.',
                status_code=status.HTTP_403_FORBIDDEN,
            )

        KAU_NAVY   = '1F3864'
        KAU_ORANGE = 'E86C1A'
        BG_LIGHT   = 'F5F7FA'

        thin   = Side(border_style='thin', color='D0D5DD')
        border = Border(left=thin, right=thin, top=thin, bottom=thin)

        wb = openpyxl.Workbook()

        # ── Sheet 1 — Instructions ────────────────────────────────────────
        info = wb.active
        info.title = 'Instructions'

        info['A1'] = 'KAU-FPO — Secondary User Bulk Invite Template'
        info['A1'].font      = Font(name='Calibri', size=16, bold=True, color=KAU_NAVY)
        info['A1'].alignment = Alignment(horizontal='left', vertical='center')
        info.row_dimensions[1].height = 28

        info['A3'] = 'How to use this template'
        info['A3'].font = Font(name='Calibri', size=12, bold=True, color=KAU_ORANGE)
        instructions = [
            '1. Open the "Members" sheet.',
            '2. Fill one row per secondary user under the header row. Remove the sample rows before uploading.',
            '3. email must be unique and not already in use on the platform.',
            '4. phone is optional — 10 digits if provided.',
            '5. All invited users land as secondary members of your FPO; they must change their password on first login.',
            '6. Save the file (keep it as .xlsx) and upload via FPO Portal → Team → Bulk Invite → Upload File.',
            '7. Rows that fail validation (duplicate email, invalid phone, missing name, etc.) come back listed in the upload result.',
        ]
        for i, line in enumerate(instructions, start=4):
            info[f'A{i}'] = line
            info[f'A{i}'].font      = Font(name='Calibri', size=11, color='344054')
            info[f'A{i}'].alignment = Alignment(wrap_text=True, vertical='top')

        info['A13'] = 'Column reference'
        info['A13'].font = Font(name='Calibri', size=12, bold=True, color=KAU_ORANGE)
        col_reference = [
            ('first_name', 'Required. Secondary user\'s first name.'),
            ('last_name',  'Optional. Secondary user\'s last name.'),
            ('email',      'Required. Login email. Must be unique across the platform.'),
            ('phone',      'Optional. 10-digit Indian mobile number.'),
        ]
        for i, (name, desc) in enumerate(col_reference, start=14):
            info[f'A{i}'] = name
            info[f'B{i}'] = desc
            info[f'A{i}'].font      = Font(name='Calibri', size=10, bold=True, color=KAU_NAVY)
            info[f'B{i}'].font      = Font(name='Calibri', size=10, color='344054')
            info[f'A{i}'].alignment = Alignment(vertical='top')
            info[f'B{i}'].alignment = Alignment(wrap_text=True, vertical='top')

        info.column_dimensions['A'].width = 20
        info.column_dimensions['B'].width = 90

        # ── Sheet 2 — Members (data entry) ────────────────────────────────
        ws = wb.create_sheet('Members')
        headers = ['first_name', 'last_name', 'email', 'phone']
        ws.append(headers)

        header_font = Font(name='Calibri', size=11, bold=True, color='FFFFFF')
        header_fill = PatternFill('solid', fgColor=KAU_NAVY)
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font      = header_font
            cell.fill      = header_fill
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border    = border
        ws.row_dimensions[1].height = 26

        sample_rows = [
            ['Rajesh', 'Kumar', 'rajesh@example.com', '9876543210'],
            ['Priya',  'Nair',  'priya@example.com',  '9876543211'],
            ['Anil',   'Menon', 'anil@example.com',   ''],
        ]
        for r_idx, row in enumerate(sample_rows, start=2):
            for c_idx, val in enumerate(row, start=1):
                cell = ws.cell(row=r_idx, column=c_idx, value=val)
                cell.font      = Font(name='Calibri', size=10, italic=True, color='667085')
                cell.alignment = Alignment(vertical='center')
                cell.border    = border
                if r_idx % 2 == 0:
                    cell.fill = PatternFill('solid', fgColor=BG_LIGHT)

        ws.freeze_panes = 'A2'
        for col, w in {'A': 18, 'B': 18, 'C': 36, 'D': 16}.items():
            ws.column_dimensions[col].width = w

        # ── Sheet 3 — Role Codes reference ────────────────────────────────
        ref = wb.create_sheet('Role Codes')
        ref.append(['role', 'description'])
        for col_idx in (1, 2):
            cell = ref.cell(row=1, column=col_idx)
            cell.font      = header_font
            cell.fill      = header_fill
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border    = border
        ref.row_dimensions[1].height = 24

        role_rows = [
            ('secondary', 'Default role for every row in this template. Secondary users share FPO data but cannot touch Tier Assessment, DPR, or FPO profile edits.'),
        ]
        for i, (code, desc) in enumerate(role_rows, start=2):
            ref.cell(row=i, column=1, value=code).font = Font(name='Calibri', size=10, bold=True, color=KAU_NAVY)
            ref.cell(row=i, column=2, value=desc).font = Font(name='Calibri', size=10, color='344054')
            for c_idx in (1, 2):
                cell = ref.cell(row=i, column=c_idx)
                cell.alignment = Alignment(wrap_text=True, vertical='top')
                cell.border    = border

        ref.column_dimensions['A'].width = 14
        ref.column_dimensions['B'].width = 90
        ref.freeze_panes = 'A2'

        # Save + return
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        response = HttpResponse(
            buf.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = 'attachment; filename="fpo_team_bulk_invite_template.xlsx"'
        return response


# ─────────────────────────────────────────────────────────────────────────────
# Bulk activate / deactivate
# ─────────────────────────────────────────────────────────────────────────────

class BulkActionSerializer(serializers.Serializer):
    user_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        help_text='List of user IDs to activate or deactivate.',
    )


class TeamBulkActivateView(APIView):
    permission_classes = [IsFPOManager]

    @extend_schema(
        tags=['FPO - Team'],
        summary='Bulk activate team members',
        description='Activate multiple secondary users by their user IDs.',
        request=BulkActionSerializer,
        responses={200: None},
    )
    def post(self, request):
        return _bulk_toggle(request, activate=True)


class TeamBulkDeactivateView(APIView):
    permission_classes = [IsFPOManager]

    @extend_schema(
        tags=['FPO - Team'],
        summary='Bulk deactivate team members',
        description='Deactivate multiple secondary users by their user IDs.',
        request=BulkActionSerializer,
        responses={200: None},
    )
    def post(self, request):
        return _bulk_toggle(request, activate=False)


def _bulk_toggle(request, activate: bool):
    fpo = _get_primary_fpo(request.user)
    if not fpo:
        return StandardResponse.error(
            'Only the primary user can manage team members.',
            status_code=status.HTTP_403_FORBIDDEN,
        )

    serializer = BulkActionSerializer(data=request.data)
    if not serializer.is_valid():
        return StandardResponse.validation_error(errors=serializer.errors)

    user_ids = serializer.validated_data['user_ids']
    success, failed = [], []

    for uid in user_ids:
        if uid == request.user.id:
            failed.append({'user_id': uid, 'reason': 'Cannot modify yourself.'})
            continue
        try:
            membership = FPOUserMembership.objects.select_related('user').get(
                fpo=fpo, user_id=uid, is_deleted=False,
            )
            if not activate and not membership.is_active:
                failed.append({
                    'user_id': uid,
                    'name' : membership.user.get_full_name(),
                    'reason': 'Already inactive.'})
                continue

            if activate and _last_deactivated_by_admin(membership):
                failed.append({
                    'user_id': uid,
                    'name' : membership.user.get_full_name(),
                    'reason': 'This member was deactivated by an admin. Contact admin to reactivate.',
                })
                continue

            membership.is_active      = activate
            membership.updated_by     = request.user
            membership.user.is_active = activate
            membership.save(update_fields=['is_active', 'updated_by'])
            membership.user.save(update_fields=['is_active'])
            success.append({'user_id': uid, 'name': membership.user.get_full_name()})

            AuditLogService.log(
                user=request.user,
                action=AuditLog.Action.FPO_USER_ACTIVATE if activate else AuditLog.Action.FPO_USER_DEACTIVATE,
                instance=membership,
                request=request,
                changes={'activated_user' if activate else 'deactivated_user': membership.user.email},
            )



        except FPOUserMembership.DoesNotExist:
            failed.append({'user_id': uid, 'reason': 'Team member not found.'})

    # if success:
    #     action = AuditLog.Action.FPO_USER_ACTIVATE if activate else AuditLog.Action.FPO_USER_DEACTIVATE
    #     AuditLogService.log(
    #         user=request.user,
    #         action=action,
    #         instance=fpo,
    #         request=request,
    #         changes={'user_ids': [r['user_id'] for r in success]},
    #     )

    verb = 'activated' if activate else 'deactivated'
    return StandardResponse.success(
        data={'success': len(success), 'failed': len(failed), 'results': success, 'errors': failed},
        message=f'{len(success)} member(s) {verb}, {len(failed)} failed.',
    )
