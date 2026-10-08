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
POST  /api/fpo/me/team/bulk-delete/          — delete multiple by user_ids
POST  /api/fpo/me/team/{id}/deactivate/      — deactivate single user
DELETE /api/fpo/me/team/{id}/                — delete single user (permanent)
GET   /api/fpo/me/team/available-permissions/ — actions the primary can grant a member
GET   /api/fpo/me/team/{id}/permissions/     — a member's permissions
POST  /api/fpo/me/team/{id}/permissions/     — add/remove/replace a member's permissions
POST  /api/fpo/me/team/bulk-permissions/     — grant/revoke permissions for many members

Rules:
- FPO must be APPROVED before inviting members
- Only the primary user can invite / activate / deactivate / delete
- Deleting a member permanently removes their account (as the admin CBBO /
  sub-admin delete does), so the email can be invited again
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

from django.conf import settings as django_settings
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
from apps.core.utils.messages import FPOMessages, msg
from apps.core.utils.responses import StandardResponse
from django.contrib.contenttypes.models import ContentType
from apps.database.models.fpo import FPO, FPOUserMembership
from apps.notifications.services import send_notification

User = get_user_model()


EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

# Team member name / phone rules. Mirrored in the invite forms
# (KAU_FPO_FE …/team/_components/member-rules.ts) and stated in the bulk-invite template.
NAME_MAX_LENGTH = 20
# English or Malayalam letters only — no spaces, digits or symbols
# (U+0D00–U+0D63 letters and vowel signs, U+0D7A–U+0D7F chillus, ZWNJ/ZWJ used in Malayalam spelling)
NAME_REGEX  = re.compile(r'^[A-Za-z\u0D00-\u0D63\u0D7A-\u0D7F\u200C\u200D]+$')
PHONE_REGEX = re.compile(r'^\d{10}$')


# (too long, not letters-only) message per name field
_NAME_MESSAGES = {
    'first_name': (FPOMessages.TEAM_FIRST_NAME_TOO_LONG, FPOMessages.TEAM_FIRST_NAME_LETTERS_ONLY),
    'last_name':  (FPOMessages.TEAM_LAST_NAME_TOO_LONG, FPOMessages.TEAM_LAST_NAME_LETTERS_ONLY),
}


def _name_error(value, field, lang='en'):
    """Why `value` is not a valid member name, or None. Blank is checked separately."""
    too_long, letters_only = _NAME_MESSAGES[field]
    if len(value) > NAME_MAX_LENGTH:
        return msg(too_long, lang, max=NAME_MAX_LENGTH)
    if not NAME_REGEX.match(value):
        return msg(letters_only, lang)
    return None


def _phone_error(value, lang='en'):
    """Why `value` is not a valid phone, or None. Phone is optional, so blank passes."""
    if value and not PHONE_REGEX.match(value):
        return msg(FPOMessages.TEAM_PHONE_INVALID, lang)
    return None


def _cell_text(value):
    """An .xlsx cell as text. Excel may store a typed phone number as a float (9876543210.0)."""
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _welcome_cta_context():
    """
    Common extras added to every secondary-user welcome email so the HTML
    template renders a "Login to KAU-FPO" button that opens the login page
    in one click. Settings.FRONTEND_URL defaults to '' — if unset, the
    email template skips the button block cleanly.
    """
    return {
        'button_link': getattr(django_settings, 'FRONTEND_URL', ''),
        'button_text': 'Login to KAU-FPO',
    }


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
    first_name = serializers.CharField()
    last_name  = serializers.CharField()
    email      = serializers.EmailField()
    phone      = serializers.CharField(required=False, allow_blank=True)
    permissions = serializers.ListField(
        child=serializers.CharField(), required=False,
        help_text='Action codes to grant. Omit to give the role defaults; any grantable code left out is revoked.',
    )

    @property
    def _lang(self):
        return self.context.get('lang', 'en')

    def validate_first_name(self, value):
        return self._check(_name_error(value, 'first_name', self._lang), value)

    def validate_last_name(self, value):
        return self._check(_name_error(value, 'last_name', self._lang), value)

    def validate_phone(self, value):
        return self._check(_phone_error(value, self._lang), value)

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(msg(FPOMessages.TEAM_EMAIL_REGISTERED, self._lang))
        return value.lower()

    def validate_permissions(self, value):
        return _validate_grantable(value, lang=self._lang)

    @staticmethod
    def _check(error, value):
        if error:
            raise serializers.ValidationError(error)
        return value


def _secondary_group():
    return Group.objects.get(name='secondary')


def _validate_grantable(codes, role=None, lang='en'):
    """Reject codes the primary is not allowed to grant (outside the role ceiling)."""
    grantable = set(get_grantable_actions(role or _secondary_group()).values_list('code', flat=True))
    invalid = sorted(set(codes) - grantable)
    if invalid:
        raise serializers.ValidationError(
            msg(FPOMessages.TEAM_PERMISSIONS_NOT_GRANTABLE, lang, codes=', '.join(invalid))
        )
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
            'description': action.get_description(lang),
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

        lang = getattr(request, 'language', 'en')
        if fpo.status != FPOStatus.APPROVED:
            return StandardResponse.error(
                msg(FPOMessages.TEAM_FPO_NOT_APPROVED, lang),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        serializer = TeamInviteSerializer(data=request.data, context={'lang': lang})
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
        send_notification(
            user=user,
            code='welcome',
            channel='email',
            context={
                'user_name':     f'{data["first_name"]} {data["last_name"]}',
                'email':         data['email'],
                'temp_password': temp_password,
                **_welcome_cta_context(),
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
            return None, StandardResponse.error(
                msg(FPOMessages.TEAM_MEMBER_NOT_FOUND, getattr(request, 'language', 'en')),
                status_code=status.HTTP_404_NOT_FOUND,
            )
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
            codes = _validate_grantable(
                serializer.validated_data['permissions'], membership.role, getattr(request, 'language', 'en'),
            )
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
        lang = getattr(request, 'language', 'en')
        try:
            grant  = _validate_grantable(data['grant'], lang=lang)
            revoke = _validate_grantable(data['revoke'], lang=lang)
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
                    failed.append({'user_id': uid, 'reason': msg(FPOMessages.TEAM_PRIMARY_HAS_ALL_PERMISSIONS, lang)})
                    continue
                membership = memberships.get(uid)
                if not membership or not membership.role:
                    failed.append({'user_id': uid, 'reason': msg(FPOMessages.TEAM_MEMBER_NOT_FOUND, lang)})
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

        lang = getattr(request, 'language', 'en')
        try:
            membership = FPOUserMembership.objects.select_related('user').get(
                fpo=fpo, user_id=user_id, is_deleted=False,
            )
        except FPOUserMembership.DoesNotExist:
            return StandardResponse.error(
                msg(FPOMessages.TEAM_MEMBER_NOT_FOUND, lang),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if membership.user == request.user:
            return StandardResponse.error(
                msg(FPOMessages.TEAM_CANNOT_DEACTIVATE_SELF, lang),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if not membership.is_active:
            return StandardResponse.error(
                msg(FPOMessages.TEAM_ALREADY_INACTIVE, lang),
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


def _delete_members(fpo, user_ids, requester, lang='en'):
    """
    Permanently delete team members' accounts. Their membership, profile and
    permission overrides go with them; FPO records they created (products,
    bookings, …) stay, with the creator cleared. The emails are free to invite again.

    Every member is checked first, then all allowed accounts are deleted in ONE
    query: each delete call clears created_by/updated_by on ~140 tables (~450
    queries, 2–3 s) whether it removes one user or fifty, so a per-user loop
    outlasts the frontend's 30 s request timeout on a bulk delete.

    Call inside a transaction. Returns (deleted, failed) — deleted is a list of
    (user_id, name, email), failed a list of (user_id, reason).
    """
    # Lock the rows so a concurrent delete of the same members (e.g. a retried
    # request) waits, then finds them gone instead of deleting them twice.
    memberships = {
        m.user_id: m
        for m in FPOUserMembership.objects.select_for_update(of=('self',))
        .select_related('user', 'role')
        .filter(fpo=fpo, user_id__in=user_ids, is_deleted=False)
    }

    deleted, failed = [], []
    for uid in dict.fromkeys(user_ids):
        membership = memberships.get(uid)
        if uid == requester.id:
            reason = msg(FPOMessages.TEAM_CANNOT_DELETE_SELF, lang)
        elif not membership:
            reason = msg(FPOMessages.TEAM_MEMBER_NOT_FOUND, lang)
        # Deleting would let the primary re-invite someone an admin locked out
        elif _last_deactivated_by_admin(membership):
            reason = msg(FPOMessages.TEAM_ADMIN_DEACTIVATED_DELETE, lang)
        elif membership.user.groups.exclude(
            name__in=[UserRole.FPO_MANAGER] + ([membership.role.name] if membership.role else []),
        ).exists():
            reason = msg(FPOMessages.TEAM_OTHER_ROLES, lang)
        else:
            user = membership.user
            deleted.append((uid, user.get_full_name() or user.email, user.email))
            continue
        failed.append((uid, reason))

    if deleted:
        User.objects.filter(id__in=[uid for uid, _, _ in deleted]).delete()
    return deleted, failed


class TeamDeleteView(APIView):
    permission_classes = [IsFPOManager]

    @extend_schema(
        tags=['FPO - Team'],
        summary='Delete team member',
        description=(
            'Permanently deletes a secondary user\'s account. They can no longer log in, and '
            'the email can be invited again. Products, bookings and other FPO records they '
            'created are kept. Only the primary user can do this; members deactivated by an '
            'admin can only be removed by an admin.'
        ),
        responses={200: None, 400: None, 404: None},
    )
    def delete(self, request, user_id):
        fpo = _get_primary_fpo(request.user)
        if not fpo:
            return StandardResponse.error(
                'Only the primary user can delete team members.',
                status_code=status.HTTP_403_FORBIDDEN,
            )

        lang = getattr(request, 'language', 'en')
        with transaction.atomic():
            deleted, failed = _delete_members(fpo, [user_id], request.user, lang)
        if failed:
            reason = failed[0][1]
            not_found = reason == msg(FPOMessages.TEAM_MEMBER_NOT_FOUND, lang)
            return StandardResponse.error(
                reason,
                status_code=status.HTTP_404_NOT_FOUND if not_found else status.HTTP_400_BAD_REQUEST,
            )

        _, name, email = deleted[0]
        AuditLogService.log(
            user=request.user,
            action=AuditLog.Action.DELETE,
            instance=fpo,
            request=request,
            changes={'deleted_user': email},
        )
        return StandardResponse.success(message=f'{name} has been deleted.')


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

        lang = getattr(request, 'language', 'en')
        try:
            membership = FPOUserMembership.objects.select_related('user', 'user__profile').get(
                fpo=fpo, user_id=user_id, is_deleted=False,
            )
        except FPOUserMembership.DoesNotExist:
            return StandardResponse.error(
                msg(FPOMessages.TEAM_MEMBER_NOT_FOUND, lang), status_code=status.HTTP_404_NOT_FOUND,
            )

        if membership.user == request.user:
            return StandardResponse.error(
                msg(FPOMessages.TEAM_CANNOT_RESET_OWN_PASSWORD, lang), status_code=status.HTTP_400_BAD_REQUEST,
            )

        if not (membership.is_active and membership.user.is_active):
            return StandardResponse.error(
                t('admin.reset_password_inactive_user', lang),
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
                **_welcome_cta_context(),
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
    # str() — JSON rows may send the phone as a number
    email      = str(row.get('email') or '').strip().lower()
    first_name = str(row.get('first_name') or '').strip()
    last_name  = str(row.get('last_name') or '').strip()
    phone      = str(row.get('phone') or '').strip()

    # Reasons are shown per row in the "Some Invitations Failed" dialog, next
    # to the row's name and email — keep them short and in plain words, and
    # list every problem in the row so it can be fixed in one go.
    problems = [
        error for error in (
            not first_name and msg(FPOMessages.TEAM_FIRST_NAME_REQUIRED, lang),
            first_name and _name_error(first_name, 'first_name', lang),
            not last_name and msg(FPOMessages.TEAM_LAST_NAME_REQUIRED, lang),
            last_name and _name_error(last_name, 'last_name', lang),
            not email and msg(FPOMessages.TEAM_EMAIL_REQUIRED, lang),
            email and not EMAIL_REGEX.match(email) and msg(FPOMessages.TEAM_EMAIL_INVALID, lang),
            _phone_error(phone, lang),
        ) if error
    ]
    if problems:
        raise ValueError(' '.join(problems))

    if User.objects.filter(email__iexact=email).exists():
        raise ValueError(msg(FPOMessages.TEAM_EMAIL_REGISTERED, lang))

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
            **_welcome_cta_context(),
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
        lang = getattr(request, 'language', 'en')
        if fpo.status != FPOStatus.APPROVED:
            return StandardResponse.error(
                msg(FPOMessages.TEAM_FPO_NOT_APPROVED, lang),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        serializer = BulkInviteSerializer(data=request.data)
        if not serializer.is_valid():
            return StandardResponse.validation_error(errors=serializer.errors)

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
        lang = getattr(request, 'language', 'en')
        if fpo.status != FPOStatus.APPROVED:
            return StandardResponse.error(
                msg(FPOMessages.TEAM_FPO_NOT_APPROVED, lang),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        file = request.FILES.get('file')
        if not file:
            return StandardResponse.error(msg(FPOMessages.TEAM_FILE_MISSING, lang),
                                          status_code=status.HTTP_400_BAD_REQUEST)

        filename = file.name.lower()
        rows = []  # (sheet row number, {column: value}) — row 1 is the header

        try:
            if filename.endswith('.csv'):
                content = file.read().decode('utf-8-sig')
                reader  = csv.DictReader(io.StringIO(content))
                for i, row in enumerate(reader, start=2):
                    rows.append((i, {
                        (k or '').strip().lower(): (v or '').strip() for k, v in row.items()
                    }))
            elif filename.endswith('.xlsx'):
                wb = openpyxl.load_workbook(file, read_only=True, data_only=True)
                # The downloaded template opens on its Instructions sheet, so
                # wb.active would read the instructions. Read the Members sheet
                # by name; a plain single-sheet file falls back to the active one.
                ws = next(
                    (wb[name] for name in wb.sheetnames if name.strip().lower() == 'members'),
                    wb.active,
                )
                headers = [str(c.value).strip().lower() if c.value else '' for c in next(ws.iter_rows())]
                for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                    rows.append((i, dict(zip(headers, [_cell_text(v) for v in row]))))
                wb.close()
            else:
                return StandardResponse.error(msg(FPOMessages.TEAM_FILE_TYPE, lang),
                                              status_code=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return StandardResponse.error(msg(FPOMessages.TEAM_FILE_UNREADABLE, lang),
                                          status_code=status.HTTP_400_BAD_REQUEST)

        # Rows the user cleared (e.g. the template's sample rows) are still
        # returned by the sheet — skip them rather than report them as failures.
        rows = [(i, row) for i, row in rows if any(row.values())]

        if not rows:
            return StandardResponse.error(msg(FPOMessages.TEAM_FILE_EMPTY, lang),
                                          status_code=status.HTTP_400_BAD_REQUEST)

        success, failed = [], []

        for i, row in rows:
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
        from openpyxl.worksheet.datavalidation import DataValidation

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
            f'3. first_name and last_name: letters only (English or Malayalam), up to {NAME_MAX_LENGTH} characters each — no spaces, numbers or symbols.',
            '4. email must be unique and not already in use on the platform.',
            '5. phone is optional — exactly 10 digits if provided.',
            '6. All invited users land as secondary members of your FPO; they must change their password on first login.',
            '7. Save the file (keep it as .xlsx) and upload via FPO Portal → Team → Bulk Invite → Upload File.',
            '8. Rows that fail validation (duplicate email, invalid phone, invalid name, etc.) come back listed in the upload result.',
        ]
        for i, line in enumerate(instructions, start=4):
            info[f'A{i}'] = line
            info[f'A{i}'].font      = Font(name='Calibri', size=11, color='344054')
            info[f'A{i}'].alignment = Alignment(wrap_text=True, vertical='top')

        info['A13'] = 'Column reference'
        info['A13'].font = Font(name='Calibri', size=12, bold=True, color=KAU_ORANGE)
        col_reference = [
            ('first_name', f'Required. Secondary user\'s first name. Letters only, up to {NAME_MAX_LENGTH} characters.'),
            ('last_name',  f'Required. Secondary user\'s last name. Letters only, up to {NAME_MAX_LENGTH} characters.'),
            ('email',      'Required. Login email. Must be unique across the platform.'),
            ('phone',      'Optional. Exactly 10 digits, e.g. 9876543210.'),
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

        # Excel-side checks so mistakes show up while typing. Excel can't test
        # "letters only" without regex, so names get the length rule here and
        # the full rule on upload (_create_member).
        last_row = 1001
        name_rule = DataValidation(
            type='textLength', operator='lessThanOrEqual', formula1=str(NAME_MAX_LENGTH), allow_blank=True,
            showInputMessage=True, promptTitle='Name',
            prompt=f'Letters only, up to {NAME_MAX_LENGTH} characters. No spaces, numbers or symbols.',
            showErrorMessage=True, errorTitle='Name too long',
            error=f'Names can have at most {NAME_MAX_LENGTH} characters.',
        )
        name_rule.add(f'A2:B{last_row}')
        phone_rule = DataValidation(
            type='custom', allow_blank=True,
            formula1='OR(D2="",AND(LEN(D2)=10,ISNUMBER(--D2),--D2>=1000000000,--D2=INT(--D2)))',
            showInputMessage=True, promptTitle='Phone (optional)', prompt='Exactly 10 digits, e.g. 9876543210.',
            showErrorMessage=True, errorTitle='Invalid phone number',
            error='Phone number must be exactly 10 digits.',
        )
        phone_rule.add(f'D2:D{last_row}')
        ws.add_data_validation(name_rule)
        ws.add_data_validation(phone_rule)
        # Text format keeps typed phone numbers exactly as entered
        for (cell,) in ws.iter_rows(min_row=2, max_row=last_row, min_col=4, max_col=4):
            cell.number_format = '@'

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


class TeamBulkDeleteView(APIView):
    permission_classes = [IsFPOManager]

    @extend_schema(
        tags=['FPO - Team'],
        summary='Bulk delete team members',
        description=(
            'Permanently deletes several secondary users by their user IDs (see the single '
            'delete for what is kept). Members that cannot be deleted are reported in '
            '`errors`; the rest are deleted together.'
        ),
        request=BulkActionSerializer,
        responses={200: None},
    )
    def post(self, request):
        fpo = _get_primary_fpo(request.user)
        if not fpo:
            return StandardResponse.error(
                'Only the primary user can delete team members.',
                status_code=status.HTTP_403_FORBIDDEN,
            )

        serializer = BulkActionSerializer(data=request.data)
        if not serializer.is_valid():
            return StandardResponse.validation_error(errors=serializer.errors)

        with transaction.atomic():
            deleted, not_deleted = _delete_members(
                fpo, serializer.validated_data['user_ids'], request.user, getattr(request, 'language', 'en'),
            )

        success = [{'user_id': uid, 'name': name} for uid, name, _ in deleted]
        failed  = [{'user_id': uid, 'reason': reason} for uid, reason in not_deleted]
        for _, _, email in deleted:
            AuditLogService.log(
                user=request.user,
                action=AuditLog.Action.DELETE,
                instance=fpo,
                request=request,
                changes={'deleted_user': email},
            )

        return StandardResponse.success(
            data={'success': len(success), 'failed': len(failed), 'results': success, 'errors': failed},
            message=f'{len(success)} member(s) deleted, {len(failed)} failed.',
        )


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
    lang = getattr(request, 'language', 'en')
    success, failed = [], []

    for uid in user_ids:
        if uid == request.user.id:
            failed.append({'user_id': uid, 'reason': msg(FPOMessages.TEAM_CANNOT_MODIFY_SELF, lang)})
            continue
        try:
            membership = FPOUserMembership.objects.select_related('user').get(
                fpo=fpo, user_id=uid, is_deleted=False,
            )
            if not activate and not membership.is_active:
                failed.append({
                    'user_id': uid,
                    'name' : membership.user.get_full_name(),
                    'reason': msg(FPOMessages.TEAM_ALREADY_INACTIVE, lang)})
                continue

            if activate and _last_deactivated_by_admin(membership):
                failed.append({
                    'user_id': uid,
                    'name' : membership.user.get_full_name(),
                    'reason': msg(FPOMessages.TEAM_ADMIN_DEACTIVATED_REACTIVATE, lang),
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
            failed.append({'user_id': uid, 'reason': msg(FPOMessages.TEAM_MEMBER_NOT_FOUND, lang)})

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
