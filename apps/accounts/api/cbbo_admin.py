"""
CBBO Management API (admin-side)
==================================
Base Path: /api/admin/cbbos/

Lives at apps/cbbo/api/admin.py, alongside the CBBO-facing files in this
same package: assignments.py (CBBO sees their assigned FPOs), reports.py
(capacity building reports), training.py (sessions + attendance). Those
three are the CBBO's own view of their world; this file is the super-admin's
view for creating and managing CBBO accounts themselves.

Super admin creates CBBO accounts and configures which districts (or
state-wide access) each CBBO has. Structured the same way as the Sub-Admin
Management API (SubAdminViewSet) — but assigns *districts* via
CBBOAssignment instead of *permissions* via Django Permission objects.

A "CBBO" is a Django User with one or more CBBOAssignment rows
(apps/database/models/cbbo.py). There's no separate CBBO profile table.
"""

import secrets
import logging
from django.conf import settings as django_settings
from django.contrib.auth.models import User, Group

from rest_framework import serializers, filters
from rest_framework.decorators import action

from drf_spectacular.utils import extend_schema, extend_schema_view, extend_schema_field

from apps.core.permissions.rbac import IsSuperAdmin
from apps.core.utils.constants import UserRole, District, get_district_name
from apps.core.utils.responses import StandardResponse
from apps.core.utils.pagination import StandardPagination
from apps.core.services.translation import t
from apps.core.views import TranslatedViewSet
from apps.notifications.services import send_notification
from apps.database.models.cbbo import CBBOAssignment

logger = logging.getLogger(__name__)


# ─── Serializers ─────────────────────────────────────────────────────────────

class CBBOCreateSerializer(serializers.Serializer):
    email                = serializers.EmailField()
    first_name           = serializers.CharField(max_length=150)
    last_name            = serializers.CharField(max_length=150, required=False, default='')
    phone                = serializers.CharField(max_length=15, required=False, allow_blank=True, default='')
    notification_channel = serializers.ChoiceField(
        choices=['email', 'sms'],
        default='email',
        help_text="Channel to send login credentials. 'sms' requires phone to be provided.",
    )
    level = serializers.ChoiceField(
        choices=CBBOAssignment.LEVEL_CHOICES,
        default=CBBOAssignment.LEVEL_DISTRICT,
    )
    district_codes = serializers.ListField(
        child=serializers.ChoiceField(choices=District.choices),
        required=False,
        default=list,
        help_text="Required when level=district. Ignored when level=state.",
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
        # SMS is only usable if a phone number was actually given
        if attrs.get('notification_channel') == 'sms' and not attrs.get('phone'):
            raise serializers.ValidationError({
                'notification_channel': 'Cannot use SMS — no phone number provided.'
            })
        # district-level accounts need at least one district up front
        if attrs['level'] == CBBOAssignment.LEVEL_DISTRICT and not attrs.get('district_codes'):
            raise serializers.ValidationError({
                'district_codes': 'Required when level=district.'
            })
        return attrs


class _AssignmentRowSerializer(serializers.ModelSerializer):
    district_display = serializers.SerializerMethodField()

    class Meta:
        model  = CBBOAssignment
        fields = ['id', 'level', 'district', 'district_display', 'is_active', 'created_at']

    def get_district_display(self, obj):
        if not obj.district:
            return None
        lang = getattr(self.context.get('request'), 'language', 'en')
        return get_district_name(obj.district, language=lang)


class CBBOSerializer(serializers.ModelSerializer):
    """Read-only representation — never used to accept input (see
    CBBOCreateSerializer/CBBOUpdateSerializer for that)."""
    phone       = serializers.SerializerMethodField()
    scope       = serializers.SerializerMethodField()
    assignments = serializers.SerializerMethodField()

    class Meta:
        model  = User
        fields = ['id', 'email', 'first_name', 'last_name', 'phone', 'is_active', 'date_joined', 'scope', 'assignments']
        read_only_fields = fields

    @extend_schema_field(serializers.CharField())
    def get_phone(self, obj):
        return getattr(getattr(obj, 'profile', None), 'phone', '')

    @extend_schema_field(serializers.CharField())
    def get_scope(self, obj):
        if obj.cbbo_assignments.filter(level=CBBOAssignment.LEVEL_STATE, is_active=True).exists():
            return 'STATE'
        return list(
            obj.cbbo_assignments.filter(level=CBBOAssignment.LEVEL_DISTRICT, is_active=True)
                .values_list('district', flat=True)
        )

    @extend_schema_field(_AssignmentRowSerializer(many=True))
    def get_assignments(self, obj):
        rows = obj.cbbo_assignments.filter(is_active=True).order_by('district')
        return _AssignmentRowSerializer(rows, many=True, context=self.context).data


class CBBODistrictActionSerializer(serializers.Serializer):
    """Backs POST .../districts/ — action controls how district_codes is
    applied (add/remove/replace) rather than always overwriting."""
    action = serializers.ChoiceField(
        choices=['add', 'remove', 'replace'],
        default='replace',
        help_text=(
            "add     — assign these districts in addition to existing ones\n"
            "remove  — revoke these districts, leave the rest untouched\n"
            "replace — this CBBO's districts become exactly this list (default)"
        ),
    )
    district_codes = serializers.ListField(
        child=serializers.CharField(),
        help_text="List of district codes to add, remove, or replace.",
    )

    def validate_district_codes(self, value):
        # reject anything outside the known district list — same gate as
        # SubAdminPermissionSerializer.validate_permissions
        valid = set(District.values)
        invalid = [d for d in value if d not in valid]
        if invalid:
            raise serializers.ValidationError(
                f"Invalid district codes: {invalid}. Valid options: {sorted(valid)}"
            )
        return value


class AvailableDistrictSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()


class CBBOUpdateSerializer(serializers.Serializer):
    """Documents the PATCH shape for drf-spectacular only — partial_update()
    below reads straight from request.data rather than validating through
    this serializer."""
    first_name = serializers.CharField(max_length=150, required=False, help_text="CBBO's first name")
    last_name  = serializers.CharField(max_length=150, required=False, allow_blank=True, help_text="CBBO's last name")
    phone      = serializers.CharField(max_length=15,  required=False, allow_blank=True, help_text="Indian phone number (10 digits)")


# ─── ViewSet ─────────────────────────────────────────────────────────────────

@extend_schema_view(
    list=extend_schema(tags=['Admin - CBBOs']),
    retrieve=extend_schema(tags=['Admin - CBBOs']),
    create=extend_schema(tags=['Admin - CBBOs']),
    partial_update=extend_schema(
        tags=['Admin - CBBOs'],
        request=CBBOUpdateSerializer,
        responses=CBBOSerializer,
        summary="Update CBBO profile",
        description="Update first name, last name, and/or phone number of a CBBO.",
    ),
    destroy=extend_schema(tags=['Admin - CBBOs']),
)
class CBBOViewSet(TranslatedViewSet):
    """
    Manage CBBO accounts and their district (or state-wide) assignments.

    - Create CBBO accounts (super_admin only)
    - Assign/revoke districts per CBBO
    - List available districts
    """

    permission_classes = [IsSuperAdmin]  # super_admin only, enforced for every action on this viewset
    pagination_class   = StandardPagination
    filter_backends    = [filters.SearchFilter, filters.OrderingFilter]
    search_fields      = ['email', 'first_name', 'last_name']
    ordering_fields    = ['date_joined', 'email']

    list_message    = 'admin.cbbos_retrieved'
    create_message  = 'admin.cbbo_created'
    update_message  = 'admin.cbbo_updated'
    destroy_message = 'admin.cbbo_deleted'

    def get_queryset(self):
        # "is a CBBO" == has at least one CBBOAssignment row, same
        # definition used by is_cbbo_user() in assignments.py
        return User.objects.filter(
            cbbo_assignments__isnull=False
        ).distinct().prefetch_related('cbbo_assignments').order_by('-date_joined')

    def get_serializer_class(self):
        if self.action == 'create':
            return CBBOCreateSerializer
        return CBBOSerializer

    # ── CREATE CBBO ──────────────────────────────────────────────────────────
    # Creates the User, the initial CBBOAssignment row(s) (state-wide = one
    # row, district = one per code), and emails/SMSs a temp password with
    # must_change_password=True — same credential-delivery flow as sub-admin create().
    def create(self, request, *args, **kwargs):
        lang = self.get_language()
        serializer = CBBOCreateSerializer(data=request.data)
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

        cbbo_group, _ = Group.objects.get_or_create(name=UserRole.CBBO)
        user.groups.add(cbbo_group)

        if data['level'] == CBBOAssignment.LEVEL_STATE:
            CBBOAssignment.objects.create(
                cbbo=user, level=CBBOAssignment.LEVEL_STATE,
                district='', is_active=True, assigned_by=request.user,
            )
        else:
            CBBOAssignment.objects.bulk_create([
                CBBOAssignment(
                    cbbo=user, level=CBBOAssignment.LEVEL_DISTRICT,
                    district=code, is_active=True, assigned_by=request.user,
                )
                for code in dict.fromkeys(data['district_codes'])  # de-dupe, keep order
            ])

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
            # notification failure shouldn't roll back account creation —
            # the account exists either way, just log it for follow-up
            logger.exception(f"Failed to send welcome notification to {user.email}")

        return StandardResponse.success(
            data=CBBOSerializer(user, context={"request": request}).data,
            message=t(self.create_message, lang),
            status_code=201,
        )

    # ── EDIT CBBO PROFILE ────────────────────────────────────────────────────
    # Only name/phone — districts, activation, and password are all handled
    # by their own dedicated actions below, not this endpoint.
    def partial_update(self, request, *args, **kwargs):
        """PATCH /api/admin/cbbos/{id}/ — edit name and/or phone."""
        lang = self.get_language()
        user = self.get_object()

        first_name = request.data.get('first_name')
        last_name  = request.data.get('last_name')
        phone      = request.data.get('phone')

        # only touch/save fields that were actually sent
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
            data=CBBOSerializer(user, context={"request": request}).data,
            message=t(self.update_message, lang),
        )

    # ── DELETE CBBO ──────────────────────────────────────────────────────────
    # Hard delete, matching SubAdminViewSet.destroy(). NOTE: CBBOAssignment.cbbo
    # is on_delete=CASCADE, so this also permanently removes the CBBO's
    # assignment history — if you need that history retained for audit,
    # deactivate() (below) is the safer everyday action; reserve destroy()
    # for accounts created in error.
    def destroy(self, request, *args, **kwargs):
        lang = self.get_language()
        obj  = self.get_object()
        obj.delete()
        return StandardResponse.success(message=t(self.destroy_message, lang))

    @extend_schema(
        methods=['get'],
        tags=['Admin - CBBOs'],
        responses=CBBOSerializer,
        summary="Get CBBO's district assignments",
        description="Returns the CBBO's currently active district (or state-wide) assignments.",
    )
    @extend_schema(
        methods=['post'],
        tags=['Admin - CBBOs'],
        request=CBBODistrictActionSerializer,
        responses=CBBOSerializer,
        summary="Update CBBO's district assignments",
        description=(
            "Add, remove, or replace district assignments.\n\n"
            "**action: replace** (default) — this CBBO's districts become exactly this list\n\n"
            "**action: add** — assign these districts in addition to existing ones\n\n"
            "**action: remove** — revoke these districts, leave the rest untouched"
        ),
    )
    @action(detail=True, methods=['get', 'post'], url_path='districts')
    def districts(self, request, pk=None):
        """GET — view assigned districts. POST — add/remove/replace districts."""
        lang = self.get_language()
        user = self.get_object()

        if request.method == 'POST':
            if not user.is_active:
                return StandardResponse.error(
                    message='Cannot assign districts to a deactivated CBBO.',
                    status_code=400,
                )
            if user.cbbo_assignments.filter(level=CBBOAssignment.LEVEL_STATE, is_active=True).exists():
                return StandardResponse.error(
                    message='This CBBO already has state-wide access; district-level assignment is redundant.',
                    status_code=400,
                )

            serializer = CBBODistrictActionSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            self._assign_districts(
                user,
                serializer.validated_data['district_codes'],
                action=serializer.validated_data.get('action', 'replace'),
            )
            return StandardResponse.success(
                data=CBBOSerializer(user, context={"request": request}).data,
                message=t('admin.cbbo_districts_updated', lang),
            )

        return StandardResponse.success(
            data=CBBOSerializer(user, context={"request": request}).data,
            message=t('admin.cbbo_retrieved', lang),
        )

    # ── LIST AVAILABLE DISTRICTS ─────────────────────────────────────────────
    # Sourced from District (constants.py) — lets the admin UI build a
    # picker without hardcoding district codes on the frontend. Names are
    # localized via get_district_name() the same way _AssignmentRowSerializer does.
    @extend_schema(tags=['Admin - CBBOs'],
                   responses=AvailableDistrictSerializer(many=True))
    @action(detail=False, methods=['get'], url_path='available-districts')
    def available_districts(self, request):
        """List all districts that can be assigned to CBBOs."""
        lang = self.get_language()
        data = [{'code': code, 'name': get_district_name(code, language=lang)} for code in District.values]
        return StandardResponse.success(
            data=data,
            message=t('admin.districts_retrieved', lang),
        )

    # ── ACTIVATE / DEACTIVATE ────────────────────────────────────────────────
    # Two explicit actions rather than a single PATCH-status endpoint — kept
    # separate from partial_update() so login-access changes get their own
    # clear audit trail via distinct success messages. Deactivating does NOT
    # touch district assignments, so reactivating restores exactly the same
    # jurisdiction the CBBO had before.
    @extend_schema(tags=['Admin - CBBOs'])
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        lang = self.get_language()
        user = self.get_object()
        user.is_active = True
        user.save()
        return StandardResponse.success(
            data=CBBOSerializer(user, context={"request": request}).data,
            message=t('admin.cbbo_activated', lang),
        )

    @extend_schema(tags=['Admin - CBBOs'])
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        lang = self.get_language()
        user = self.get_object()
        user.is_active = False
        user.save()
        return StandardResponse.success(
            data=CBBOSerializer(user, context={"request": request}).data,
            message=t('admin.cbbo_deactivated', lang),
        )

    # ── RESET PASSWORD ───────────────────────────────────────────────────────
    # Generates a fresh temp password and forces must_change_password again —
    # same credential-delivery flow as create(), reused here for consistency.
    @extend_schema(
        tags=['Admin - CBBOs'],
        request=None,
        responses=CBBOSerializer,
        summary="Reset CBBO password",
        description=(
            "Generates a new temporary password for the CBBO and sends it via email or SMS. "
            "The CBBO will be required to change it on next login. "
            "Pass `notification_channel` in the request body to choose delivery method (default: email)."
        ),
    )
    @action(detail=True, methods=['post'], url_path='reset-password')
    def reset_password(self, request, pk=None):
        lang    = self.get_language()
        user    = self.get_object()
        channel = request.data.get('notification_channel', 'email')

        # fail fast rather than silently falling back to email when SMS was
        # explicitly requested but there's nowhere to send it
        if channel == 'sms' and not getattr(getattr(user, 'profile', None), 'phone', ''):
            return StandardResponse.error(
                message='Cannot use SMS — this CBBO has no phone number on record.',
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
            data=CBBOSerializer(user, context={"request": request}).data,
            message=t('admin.cbbo_password_reset', lang),
        )

    def _assign_districts(self, user, codes, action='replace'):
        """Add, remove, or replace this CBBO's active district assignments.

        Unlike sub-admin permissions (an M2M field you can .add()/.remove()
        directly), CBBOAssignment is its own row per district, and removal
        is a soft is_active=False rather than a delete — so add/remove here
        reactivate or deactivate rows instead of creating/destroying them
        outright, preserving assignment history either way.
        """
        codes = set(codes)
        rows = {r.district: r for r in user.cbbo_assignments.filter(level=CBBOAssignment.LEVEL_DISTRICT)}
        active_now = {d for d, r in rows.items() if r.is_active}

        if action == 'replace':
            to_activate   = codes - active_now
            to_deactivate = active_now - codes
        elif action == 'add':
            to_activate   = codes - active_now
            to_deactivate = set()
        elif action == 'remove':
            to_activate   = set()
            to_deactivate = codes & active_now

        for code in to_deactivate:
            rows[code].is_active = False
            rows[code].save(update_fields=['is_active'])

        for code in to_activate:
            if code in rows:
                rows[code].is_active = True
                rows[code].save(update_fields=['is_active'])
            else:
                CBBOAssignment.objects.create(
                    cbbo=user, level=CBBOAssignment.LEVEL_DISTRICT,
                    district=code, is_active=True,
                )