"""
Sub-Admin Management API
========================
Base Path: /api/admin/sub-admins/

Super admin creates sub-admin accounts and configures which permissions each
sub-admin has. Permissions are assigned per-user from a fixed list defined in
SUB_ADMIN_PERMISSIONS (constants.py).

Every sub-admin belongs to one district and sees every FPO in it (KAU
suggestion #1). Super admin moves them between districts via
/api/admin/sub-admins/{id}/transfer-district/.
"""

import secrets
import logging

from django.conf import settings as django_settings
from django.contrib.auth.models import User, Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction

from rest_framework import serializers, filters
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser

from drf_spectacular.utils import extend_schema, extend_schema_view, extend_schema_field

from apps.core.permissions.rbac import IsSuperAdmin
from apps.core.utils.constants import UserRole, SUB_ADMIN_PERMISSIONS, District
from apps.core.utils.responses import StandardResponse
from apps.core.utils.pagination import StandardPagination
from apps.core.utils.validators import validate_person_name, validate_indian_phone
from apps.core.services.translation import t
from apps.core.services.subadmin_district import (
    check_cap,
    get_effective_cap,
    count_active_in_district,
    bust_district_count_cache,
    get_all_district_counts,
)
from apps.core.views import TranslatedViewSet
from apps.database.models.fpo import FPO
from apps.database.models.subadmin import (
    SubAdminDistrictAssignment,
    SubAdminDistrictTransfer,
)
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

# RFC 5321 limits. Django's EmailValidator doesn't enforce the local-part one.
EMAIL_LOCAL_PART_MAX_LENGTH = 64
EMAIL_MAX_LENGTH            = 254


def _email_too_long(email):
    local_part = email.rsplit('@', 1)[0]
    return len(local_part) > EMAIL_LOCAL_PART_MAX_LENGTH or len(email) > EMAIL_MAX_LENGTH


NAME_MAX_LENGTH = 150   # User.first_name / last_name column size


def _bulk_name_problems(value, label):
    """Return the problems with a bulk-invite name cell (empty list when valid)."""
    if len(value) > NAME_MAX_LENGTH:
        return [f'{label} must be at most {NAME_MAX_LENGTH} characters.']
    try:
        validate_person_name(value, label)
    except DjangoValidationError as e:
        return e.messages
    return []


def _cell_to_str(value):
    """
    Turn an xlsx cell into text. Whole-number floats lose their '.0' so a
    phone typed as a number (9876543210.0) still validates.
    """
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def _validate_name(value, label):
    try:
        return validate_person_name(value, label)
    except DjangoValidationError as e:
        raise serializers.ValidationError(e.messages[0])


class SubAdminCreateSerializer(serializers.Serializer):
    email                = serializers.EmailField()
    first_name           = serializers.CharField(max_length=150)
    last_name            = serializers.CharField(max_length=150, required=False, default='')
    phone                = serializers.CharField(max_length=15, required=False, allow_blank=True, default='')
    district             = serializers.ChoiceField(
        choices=District.choices,
        help_text='3-letter Kerala district code (e.g. "TSR"). Required — every sub-admin belongs to one district.',
    )
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
        # Emails are stored lowercased, so check the normalised value — otherwise an
        # uppercase duplicate slips past this check and fails on the unique username.
        value = value.lower()
        if _email_too_long(value):
            raise serializers.ValidationError(
                'Enter a valid email address (at most 64 characters before the @).'
            )
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('A user with this email already exists.')
        return value

    def validate_first_name(self, value):
        return _validate_name(value, 'First name')

    def validate_last_name(self, value):
        return _validate_name(value, 'Last name') if value else value

    def validate_phone(self, value):
        if value:
            try:
                return validate_indian_phone(value)   # stores the cleaned 10 digits
            except DjangoValidationError as e:
                raise serializers.ValidationError(e.messages[0])
        return value

    def validate(self, attrs):
        if attrs.get('notification_channel') == 'sms' and not attrs.get('phone'):
            raise serializers.ValidationError({
                'notification_channel': 'Cannot use SMS — no phone number provided.'
            })
        return attrs


class SubAdminSerializer(serializers.ModelSerializer):
    permissions             = serializers.SerializerMethodField()
    phone                   = serializers.SerializerMethodField()
    visible_fpos_count      = serializers.SerializerMethodField()
    district                = serializers.SerializerMethodField()
    district_transfer_count = serializers.SerializerMethodField()

    class Meta:
        model  = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'phone', 'is_active',
            'date_joined', 'permissions',
            'visible_fpos_count',
            'district', 'district_transfer_count',
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.IntegerField())
    def get_visible_fpos_count(self, obj):
        """Total FPOs the sub-admin can currently see — every FPO in their district.

        A sub-admin with no district sees nothing until transferred to one.
        """
        assignment = getattr(obj, 'district_assignment', None)
        if not assignment:
            return 0
        return FPO.objects.filter(district=assignment.district, is_deleted=False).count()

    @extend_schema_field(serializers.CharField())
    def get_phone(self, obj):
        return getattr(getattr(obj, 'profile', None), 'phone', '')

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_permissions(self, obj):
        sub_admin_perms = _get_sub_admin_permissions()
        assigned = obj.user_permissions.filter(id__in=sub_admin_perms)
        return list(assigned.values_list('codename', flat=True))

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_district(self, obj):
        """District code (e.g. 'TSR') this sub-admin owns, or None if they have none yet."""
        assignment = getattr(obj, 'district_assignment', None)
        return assignment.district if assignment else None

    @extend_schema_field(serializers.IntegerField())
    def get_district_transfer_count(self, obj):
        # Cheap — most sub-admins never transfer. Ordered index on subadmin.
        return obj.district_transfers.count() if hasattr(obj, 'district_transfers') else 0


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


class TransferDistrictSerializer(serializers.Serializer):
    to_district = serializers.ChoiceField(choices=District.choices)
    reason      = serializers.CharField(required=False, allow_blank=True, default='')


class DistrictTransferHistorySerializer(serializers.ModelSerializer):
    transferred_by_email = serializers.CharField(source='transferred_by.email', default=None, read_only=True)

    class Meta:
        model  = SubAdminDistrictTransfer
        fields = ['id', 'from_district', 'to_district', 'reason', 'transferred_by_email', 'created_at']
        read_only_fields = fields


# ─── ViewSet ─────────────────────────────────────────────────────────────────

class SubAdminUpdateSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150, required=False, help_text="Sub-admin's first name")
    last_name  = serializers.CharField(max_length=150, required=False, allow_blank=True, help_text="Sub-admin's last name")
    phone      = serializers.CharField(max_length=15,  required=False, allow_blank=True, help_text="Indian phone number (10 digits)")

    def validate_first_name(self, value):
        return _validate_name(value, 'First name')

    def validate_last_name(self, value):
        return _validate_name(value, 'Last name') if value else value


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

        # Cap check BEFORE creating the user — cheaper to fail fast.
        try:
            check_cap(data['district'])
        except ValueError as e:
            return StandardResponse.error(message=str(e), errors={'district': [str(e)]}, status_code=400)

        temp_password = secrets.token_urlsafe(10)

        with transaction.atomic():
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

            # District assignment + first-time audit row.
            SubAdminDistrictAssignment.objects.create(
                subadmin=user, district=data['district'], created_by=request.user,
            )
            SubAdminDistrictTransfer.objects.create(
                subadmin=user,
                from_district='',
                to_district=data['district'],
                reason='Initial assignment on create.',
                transferred_by=request.user,
            )
            bust_district_count_cache(data['district'])

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

        serializer = SubAdminUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        first_name = serializer.validated_data.get('first_name')
        last_name  = serializer.validated_data.get('last_name')
        phone      = serializer.validated_data.get('phone')

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
                try:
                    phone = validate_indian_phone(phone)
                except DjangoValidationError as e:
                    raise serializers.ValidationError({'phone': e.messages[0]})
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

        if not user.is_active:
            return StandardResponse.error(
                message=t('admin.reset_password_inactive_user', lang),
                status_code=400,
            )

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

    # ─── District management ─────────────────────────────────────────────

    @extend_schema(
        tags=['Admin - Sub Admins'],
        request=TransferDistrictSerializer,
        responses=SubAdminSerializer,
        summary='Transfer sub-admin to another district',
        description=(
            'Moves this sub-admin from their current district to `to_district`. '
            'Checks destination cap, updates the assignment row, and writes an '
            'append-only SubAdminDistrictTransfer audit record.\n\n'
            'If the sub-admin has no district yet, this assigns their first one. '
            'Until then they see no FPOs.'
        ),
    )
    @action(detail=True, methods=['post'], url_path='transfer-district')
    def transfer_district(self, request, pk=None):
        lang = self.get_language()
        user = self.get_object()

        s = TransferDistrictSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        to_district = s.validated_data['to_district']
        reason      = s.validated_data.get('reason', '')

        current = getattr(user, 'district_assignment', None)
        from_district = current.district if current else ''

        if from_district == to_district:
            return StandardResponse.error(
                message='Sub-admin is already assigned to this district.',
                status_code=400,
            )

        try:
            check_cap(to_district)
        except ValueError as e:
            return StandardResponse.error(message=str(e), errors={'to_district': [str(e)]}, status_code=400)

        with transaction.atomic():
            if current:
                current.district   = to_district
                current.updated_by = request.user
                current.save(update_fields=['district', 'updated_by', 'updated_at'])
            else:
                SubAdminDistrictAssignment.objects.create(
                    subadmin=user, district=to_district, created_by=request.user,
                )
            SubAdminDistrictTransfer.objects.create(
                subadmin=user,
                from_district=from_district,
                to_district=to_district,
                reason=reason,
                transferred_by=request.user,
            )

        if from_district:
            bust_district_count_cache(from_district)
        bust_district_count_cache(to_district)

        return StandardResponse.success(
            data=SubAdminSerializer(user).data,
            message=t('admin.sub_admin_updated', lang),
        )

    @extend_schema(
        tags=['Admin - Sub Admins'],
        responses=DistrictTransferHistorySerializer(many=True),
        summary='Full district transfer history for a sub-admin',
        description='Append-only log — every district move including the very first assignment.',
    )
    @action(detail=True, methods=['get'], url_path='district-transfers')
    def district_transfers(self, request, pk=None):
        user = self.get_object()
        qs = user.district_transfers.select_related('transferred_by').order_by('-created_at')
        return StandardResponse.success(
            data=DistrictTransferHistorySerializer(qs, many=True).data,
            message='Transfer history retrieved.',
        )

    @extend_schema(
        tags=['Admin - Sub Admins'],
        responses=None,
        summary='District cap status for every district',
        description=(
            'Returns `{district_code: {count, cap}}` — used to render '
            '"Thrissur (28 / 30)" chips in the admin sub-admin list.'
        ),
    )
    @action(detail=False, methods=['get'], url_path='district-cap-status')
    def district_cap_status(self, request):
        counts = get_all_district_counts()
        data = {
            code: {
                'district_name': label,
                'count':         counts.get(code, 0),
                'cap':           get_effective_cap(code),
            }
            for code, label in District.choices
        }
        return StandardResponse.success(data=data, message='District cap status retrieved.')

    # ─── Bulk invite (Excel / CSV) ──────────────────────────────────────

    @extend_schema(
        tags=['Admin - Sub Admins'],
        summary='Download bulk-invite Excel template',
        description=(
            'Returns an xlsx with the required header row filled in. Fill it, '
            'upload via `/bulk-invite/`.'
        ),
        responses={200: None},
    )
    @action(detail=False, methods=['get'], url_path='bulk-invite-template')
    def bulk_invite_template(self, request):
        import io
        import openpyxl
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.utils import get_column_letter
        from openpyxl.worksheet.datavalidation import DataValidation
        from openpyxl.worksheet.table import Table, TableStyleInfo
        from django.http import HttpResponse

        KAU_NAVY   = '1F3864'
        KAU_ORANGE = 'E86C1A'
        BG_LIGHT   = 'F5F7FA'

        thin = Side(border_style='thin', color='D0D5DD')
        border = Border(left=thin, right=thin, top=thin, bottom=thin)

        wb = openpyxl.Workbook()

        # ────────────────────────────────────────────────────────────────
        # SHEET 1 — Instructions
        # ────────────────────────────────────────────────────────────────
        info = wb.active
        info.title = 'Instructions'

        info['A1'] = 'KAU-FPO — Sub-Admin Bulk Invite Template'
        info['A1'].font      = Font(name='Calibri', size=16, bold=True, color=KAU_NAVY)
        info['A1'].alignment = Alignment(horizontal='left', vertical='center')
        info.row_dimensions[1].height = 28

        info['A3'] = 'How to use this template'
        info['A3'].font = Font(name='Calibri', size=12, bold=True, color=KAU_ORANGE)

        instructions = [
            '1. Open the "Sub-Admins" sheet.',
            '2. Fill one row per sub-admin under the header row. Remove the sample rows before uploading.',
            '3. district must be a 3-letter code — see the "Districts" sheet for the list.',
            '4. notification_channel accepts "email" or "sms". Choose "sms" only when a phone is present.',
            '5. Save the file (keep it as .xlsx) and upload via Admin Portal → Sub-Admins → Bulk Invite.',
            '6. Rows that fail validation (duplicate email, cap reached, missing district, etc.) will come back listed in the upload result.',
        ]
        for i, line in enumerate(instructions, start=4):
            info[f'A{i}'] = line
            info[f'A{i}'].font = Font(name='Calibri', size=11, color='344054')
            info[f'A{i}'].alignment = Alignment(wrap_text=True, vertical='top')

        info['A12'] = 'Required columns'
        info['A12'].font = Font(name='Calibri', size=12, bold=True, color=KAU_ORANGE)
        required_rows = [
            ('first_name',           'Sub-admin\'s first name.'),
            ('last_name',            'Sub-admin\'s last name (optional but recommended).'),
            ('email',                'Login email. Must be unique.'),
            ('phone',                '10-digit Indian mobile. Required when notification_channel = sms.'),
            ('district',             '3-letter Kerala district code from the "Districts" sheet.'),
            ('notification_channel', '"email" (default) or "sms". How the temp password is sent.'),
        ]
        for i, (name, desc) in enumerate(required_rows, start=13):
            info[f'A{i}'] = name
            info[f'B{i}'] = desc
            info[f'A{i}'].font = Font(name='Calibri', size=10, bold=True, color=KAU_NAVY)
            info[f'B{i}'].font = Font(name='Calibri', size=10, color='344054')
            info[f'A{i}'].alignment = Alignment(vertical='top')
            info[f'B{i}'].alignment = Alignment(wrap_text=True, vertical='top')

        info.column_dimensions['A'].width = 26
        info.column_dimensions['B'].width = 90

        # ────────────────────────────────────────────────────────────────
        # SHEET 2 — Sub-Admins (data entry sheet)
        # ────────────────────────────────────────────────────────────────
        ws = wb.create_sheet('Sub-Admins')
        headers = ['first_name', 'last_name', 'email', 'phone', 'district', 'notification_channel']
        ws.append(headers)

        # Header styling
        header_font = Font(name='Calibri', size=11, bold=True, color='FFFFFF')
        header_fill = PatternFill('solid', fgColor=KAU_NAVY)
        for col_idx, _ in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font      = header_font
            cell.fill      = header_fill
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border    = border
        ws.row_dimensions[1].height = 26

        # Sample rows (styled slightly dimmer — user should replace them).
        sample_rows = [
            ['Rajesh', 'Kumar', 'rajesh@kau.in', '9876543210', 'TSR', 'email'],
            ['Priya',  'Nair',  'priya@kau.in',  '9876543211', 'PKD', 'email'],
            ['Anil',   'Menon', 'anil@kau.in',   '9876543212', 'EKM', 'sms'],
        ]
        for r_idx, row in enumerate(sample_rows, start=2):
            for c_idx, val in enumerate(row, start=1):
                cell = ws.cell(row=r_idx, column=c_idx, value=val)
                cell.font      = Font(name='Calibri', size=10, italic=True, color='667085')
                cell.border    = border
                cell.alignment = Alignment(vertical='center')
                if r_idx % 2 == 0:
                    cell.fill = PatternFill('solid', fgColor=BG_LIGHT)

        # Freeze header row so it stays visible while scrolling.
        ws.freeze_panes = 'A2'

        # Column widths — tuned for readability.
        widths = {'A': 16, 'B': 16, 'C': 34, 'D': 15, 'E': 12, 'F': 22}
        for col, w in widths.items():
            ws.column_dimensions[col].width = w

        # Data validation dropdowns
        district_codes = ','.join(f'"{code}"' for code, _ in District.choices)
        dv_district = DataValidation(
            type='list', formula1=f'"{",".join(c for c, _ in District.choices)}"',
            allow_blank=False, showDropDown=False,
            errorTitle='Invalid district',
            error='Use a 3-letter Kerala district code — see the "Districts" sheet.',
        )
        dv_district.add('E2:E1000')
        ws.add_data_validation(dv_district)

        dv_channel = DataValidation(
            type='list', formula1='"email,sms"',
            allow_blank=False, showDropDown=False,
            errorTitle='Invalid channel',
            error='Use "email" or "sms".',
        )
        dv_channel.add('F2:F1000')
        ws.add_data_validation(dv_channel)

        # ────────────────────────────────────────────────────────────────
        # SHEET 3 — Districts reference
        # ────────────────────────────────────────────────────────────────
        ref = wb.create_sheet('Districts')
        ref.append(['code', 'name'])
        ref.cell(row=1, column=1).font      = header_font
        ref.cell(row=1, column=2).font      = header_font
        ref.cell(row=1, column=1).fill      = header_fill
        ref.cell(row=1, column=2).fill      = header_fill
        ref.cell(row=1, column=1).alignment = Alignment(horizontal='center')
        ref.cell(row=1, column=2).alignment = Alignment(horizontal='center')
        ref.row_dimensions[1].height = 24

        for i, (code, label) in enumerate(District.choices, start=2):
            ref.cell(row=i, column=1, value=code).font      = Font(name='Calibri', size=10, bold=True, color=KAU_NAVY)
            ref.cell(row=i, column=2, value=label).font     = Font(name='Calibri', size=10, color='344054')
            ref.cell(row=i, column=1).alignment             = Alignment(horizontal='center')
            for c_idx in (1, 2):
                cell = ref.cell(row=i, column=c_idx)
                cell.border = border
                if i % 2 == 0:
                    cell.fill = PatternFill('solid', fgColor=BG_LIGHT)

        ref.column_dimensions['A'].width = 10
        ref.column_dimensions['B'].width = 28
        ref.freeze_panes = 'A2'

        # Save + return
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        response = HttpResponse(
            buf.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = 'attachment; filename="sub_admin_bulk_invite_template.xlsx"'
        return response

    @extend_schema(
        tags=['Admin - Sub Admins'],
        summary='Bulk invite sub-admins (Excel/CSV)',
        description=(
            'Upload an xlsx or csv with columns: '
            '`first_name`, `last_name`, `email`, `phone` (optional), `district`, '
            '`notification_channel` (optional: email/sms, default email).\n\n'
            'Each row is processed independently. Rows that fail cap or validation '
            'come back in the `errors` list — the rest are created.'
        ),
        responses={200: None},
    )
    @action(
        detail=False, methods=['post'], url_path='bulk-invite',
        parser_classes=[MultiPartParser],
    )
    def bulk_invite(self, request):
        import csv
        import io
        import openpyxl

        lang = self.get_language()
        file = request.FILES.get('file')
        if not file:
            return StandardResponse.error('No file uploaded. Send file as multipart form field "file".',
                                          status_code=400)

        filename = file.name.lower()
        rows = []
        try:
            if filename.endswith('.csv'):
                content = file.read().decode('utf-8-sig')
                reader  = csv.DictReader(io.StringIO(content))
                rows    = list(reader)
            elif filename.endswith('.xlsx'):
                wb = openpyxl.load_workbook(file, read_only=True, data_only=True)
                # Prefer a sheet named "Sub-Admins" (our template's data sheet).
                # Fall back to the first sheet that actually has the required
                # header cell so an admin who renamed the tab still works.
                ws = None
                for name in wb.sheetnames:
                    candidate = wb[name]
                    first_row = next(candidate.iter_rows(values_only=True), None)
                    if not first_row:
                        continue
                    header_cells = [str(v).strip().lower() if v is not None else '' for v in first_row]
                    if 'email' in header_cells and 'district' in header_cells:
                        ws = candidate
                        break
                if ws is None:
                    return StandardResponse.error(
                        'Could not find a sheet with "email" + "district" headers. '
                        'Use the downloaded template — the data goes in the "Sub-Admins" sheet.',
                        status_code=400,
                    )
                headers = [str(c.value).strip().lower() if c.value else '' for c in next(ws.iter_rows())]
                for row in ws.iter_rows(min_row=2, values_only=True):
                    if not any(v not in (None, '') for v in row):
                        continue  # skip fully-blank trailing rows
                    rows.append(dict(zip(headers, [_cell_to_str(v) for v in row])))
            else:
                return StandardResponse.error('Only .xlsx and .csv are supported.', status_code=400)
        except Exception as e:
            return StandardResponse.error(f'Could not parse file: {e}', status_code=400)

        if not rows:
            return StandardResponse.error('File has no data rows.', status_code=400)

        success, errors = [], []
        for i, row in enumerate(rows, start=2):
            try:
                user = self._invite_one(row, request.user, lang)
                success.append({'row': i, 'email': user.email, 'district': row.get('district')})
                continue
            except DjangoValidationError as e:
                reasons = e.messages
            except ValueError as e:
                reasons = [str(e)]
            except Exception:
                # Never echo raw DB / internal errors back to the admin.
                logger.exception(f'Bulk invite row {i} failed unexpectedly.')
                reasons = ['Could not create this sub-admin. Please check the row and try again.']
            errors.append({
                'row':        i,
                'email':      row.get('email', ''),
                'first_name': row.get('first_name', ''),
                'last_name':  row.get('last_name', ''),
                'district':   row.get('district', ''),
                'reasons':    reasons,
                'reason':     ' '.join(reasons),
            })

        return StandardResponse.success(
            data={'success': len(success), 'failed': len(errors), 'results': success, 'errors': errors},
            message=f'{len(success)} sub-admin(s) invited, {len(errors)} failed.',
        )

    def _invite_one(self, row, invited_by, lang):
        """
        Invite a single sub-admin from a bulk-invite row.

        Every field is checked before anything is created, and all problems
        are raised together as one DjangoValidationError so the admin can fix
        the row in a single pass. A full district cap raises ValueError.
        """
        from django.core.validators import EmailValidator

        email      = (row.get('email') or '').strip().lower()
        first_name = (row.get('first_name') or '').strip()
        last_name  = (row.get('last_name') or '').strip()
        phone      = (row.get('phone') or '').strip()
        district   = (row.get('district') or '').strip().upper()
        channel    = (row.get('notification_channel') or 'email').strip().lower() or 'email'

        problems = []

        if not first_name:
            problems.append('first_name is required.')
        else:
            problems += _bulk_name_problems(first_name, 'first_name')
        if last_name:
            problems += _bulk_name_problems(last_name, 'last_name')

        if not email:
            problems.append('email is required.')
        else:
            try:
                EmailValidator()(email)
            except DjangoValidationError:
                problems.append('email is not a valid address.')
            else:
                if _email_too_long(email):
                    problems.append('email is not a valid address (at most 64 characters before the @).')
                elif User.objects.filter(email__iexact=email).exists():
                    problems.append('A user with this email already exists.')

        if phone:
            try:
                phone = validate_indian_phone(phone)   # strips spaces / +91
            except DjangoValidationError:
                problems.append('phone must be a 10-digit Indian mobile number starting with 6, 7, 8 or 9.')

        if not district:
            problems.append('district is required.')
        elif district not in dict(District.choices):
            problems.append(f'Unknown district code "{district}".')

        if channel not in ('email', 'sms'):
            problems.append('notification_channel must be email or sms.')
        elif channel == 'sms' and not phone:
            problems.append('SMS channel needs a phone number.')

        if problems:
            raise DjangoValidationError(problems)

        check_cap(district)   # raises ValueError if full

        temp_password = secrets.token_urlsafe(10)

        with transaction.atomic():
            user = User.objects.create_user(
                username=email, email=email, password=temp_password,
                first_name=first_name, last_name=last_name,
            )
            sub_admin_group, _ = Group.objects.get_or_create(name=UserRole.SUB_ADMIN)
            user.groups.add(sub_admin_group)

            profile = user.profile
            if phone:
                profile.phone = phone
            profile.must_change_password = True
            profile.save(update_fields=['phone', 'must_change_password'])

            SubAdminDistrictAssignment.objects.create(
                subadmin=user, district=district, created_by=invited_by,
            )
            SubAdminDistrictTransfer.objects.create(
                subadmin=user, from_district='', to_district=district,
                reason='Initial assignment via bulk invite.',
                transferred_by=invited_by,
            )
            bust_district_count_cache(district)

        # Fire welcome notification outside the transaction so a send error
        # doesn't roll back the account creation.
        try:
            frontend_url = getattr(django_settings, 'FRONTEND_URL', '')
            send_notification(
                user=user, code='welcome', channel=channel,
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
            logger.exception(f'Failed to send welcome to {user.email} (bulk invite).')

        return user

    # ─── Permissions helper (unchanged) ─────────────────────────────────

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
