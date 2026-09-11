"""
Government Official Management API (admin-side)
Base Path: /api/admin/government/
Supports three jurisdiction levels: district, block, state.
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
from apps.core.services.lookup import LookupService
from apps.core.views import TranslatedViewSet
from apps.notifications.services import send_notification
from apps.database.models.government import GovernmentOfficialProfile

logger = logging.getLogger(__name__)

JURISDICTION_CHOICES = [('district', 'District'), ('block', 'Block'), ('state', 'State')]


def _block_display(code, request):
    if not code:
        return None
    lang = getattr(request, 'language', 'en')
    return LookupService.get_name('block', code, lang) or code


class GovernmentCreateSerializer(serializers.Serializer):
    email                = serializers.EmailField()
    first_name           = serializers.CharField(max_length=150)
    last_name            = serializers.CharField(max_length=150, required=False, default='')
    phone                = serializers.CharField(max_length=15, required=False, allow_blank=True, default='')
    notification_channel = serializers.ChoiceField(choices=['email', 'sms'], default='email')
    designation          = serializers.CharField(max_length=200)
    department           = serializers.CharField(max_length=200)
    jurisdiction_type    = serializers.ChoiceField(choices=JURISDICTION_CHOICES)
    assigned_district     = serializers.ChoiceField(choices=District.choices, required=False, allow_null=True)
    assigned_block        = serializers.CharField(max_length=100, required=False, allow_null=True, allow_blank=True)

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
                'notification_channel': 'Cannot use SMS - no phone number provided.'
            })
        if attrs['jurisdiction_type'] == 'district' and not attrs.get('assigned_district'):
            raise serializers.ValidationError({
                'assigned_district': 'Required when jurisdiction_type=district.'
            })
        if attrs['jurisdiction_type'] == 'block' and not attrs.get('assigned_block'):
            raise serializers.ValidationError({
                'assigned_block': 'Required when jurisdiction_type=block.'
            })
        return attrs


class GovernmentSerializer(serializers.ModelSerializer):
    phone                      = serializers.SerializerMethodField()
    designation                = serializers.SerializerMethodField()
    department                 = serializers.SerializerMethodField()
    jurisdiction_type          = serializers.SerializerMethodField()
    assigned_district          = serializers.SerializerMethodField()
    assigned_district_display  = serializers.SerializerMethodField()
    assigned_block             = serializers.SerializerMethodField()
    assigned_block_display     = serializers.SerializerMethodField()
    registration_status        = serializers.SerializerMethodField()
    user_category               = serializers.SerializerMethodField()
    id_number                   = serializers.SerializerMethodField()

    class Meta:
        model  = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'phone', 'is_active', 'date_joined',
            'designation', 'department', 'jurisdiction_type',
            'assigned_district', 'assigned_district_display',
            'assigned_block', 'assigned_block_display',
            'registration_status', 'user_category', 'id_number',
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.CharField())
    def get_phone(self, obj):
        return getattr(getattr(obj, 'profile', None), 'phone', '')

    @extend_schema_field(serializers.CharField())
    def get_designation(self, obj):
        return getattr(getattr(obj, 'govt_profile', None), 'designation', '')

    @extend_schema_field(serializers.CharField())
    def get_department(self, obj):
        return getattr(getattr(obj, 'govt_profile', None), 'department', '')

    @extend_schema_field(serializers.CharField())
    def get_jurisdiction_type(self, obj):
        return getattr(getattr(obj, 'govt_profile', None), 'jurisdiction_type', '')

    @extend_schema_field(serializers.CharField())
    def get_assigned_district(self, obj):
        return getattr(getattr(obj, 'govt_profile', None), 'assigned_district', None)

    @extend_schema_field(serializers.CharField())
    def get_assigned_district_display(self, obj):
        profile = getattr(obj, 'govt_profile', None)
        if not profile or not profile.assigned_district:
            return None
        lang = getattr(self.context.get('request'), 'language', 'en')
        return get_district_name(profile.assigned_district, language=lang)

    @extend_schema_field(serializers.CharField())
    def get_assigned_block(self, obj):
        return getattr(getattr(obj, 'govt_profile', None), 'assigned_block', None)

    @extend_schema_field(serializers.CharField())
    def get_assigned_block_display(self, obj):
        profile = getattr(obj, 'govt_profile', None)
        if not profile or not profile.assigned_block:
            return None
        return _block_display(profile.assigned_block, self.context.get('request'))

    @extend_schema_field(serializers.CharField())
    def get_registration_status(self, obj):
        return getattr(getattr(obj, 'govt_profile', None), 'registration_status', None)

    @extend_schema_field(serializers.CharField())
    def get_user_category(self, obj):
        return getattr(getattr(obj, 'govt_profile', None), 'user_category', None)

    @extend_schema_field(serializers.CharField())
    def get_id_number(self, obj):
        return getattr(getattr(obj, 'govt_profile', None), 'id_number', None)


class GovernmentJurisdictionActionSerializer(serializers.Serializer):
    jurisdiction_type  = serializers.ChoiceField(choices=JURISDICTION_CHOICES)
    assigned_district   = serializers.ChoiceField(choices=District.choices, required=False, allow_null=True)
    assigned_block      = serializers.CharField(max_length=100, required=False, allow_null=True, allow_blank=True)

    def validate(self, attrs):
        if attrs['jurisdiction_type'] == 'district' and not attrs.get('assigned_district'):
            raise serializers.ValidationError({
                'assigned_district': 'Required when jurisdiction_type=district.'
            })
        if attrs['jurisdiction_type'] == 'block' and not attrs.get('assigned_block'):
            raise serializers.ValidationError({
                'assigned_block': 'Required when jurisdiction_type=block.'
            })
        return attrs


class AvailableDistrictSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()


class GovernmentUpdateSerializer(serializers.Serializer):
    first_name  = serializers.CharField(max_length=150, required=False)
    last_name   = serializers.CharField(max_length=150, required=False, allow_blank=True)
    phone       = serializers.CharField(max_length=15,  required=False, allow_blank=True)
    designation = serializers.CharField(max_length=200, required=False)
    department  = serializers.CharField(max_length=200, required=False)


@extend_schema_view(
    list=extend_schema(tags=['Admin - Government']),
    retrieve=extend_schema(tags=['Admin - Government']),
    create=extend_schema(tags=['Admin - Government']),
    partial_update=extend_schema(
        tags=['Admin - Government'],
        request=GovernmentUpdateSerializer,
        responses=GovernmentSerializer,
        summary="Update government official profile",
    ),
    destroy=extend_schema(tags=['Admin - Government']),
)
class GovernmentViewSet(TranslatedViewSet):
    permission_classes = [IsSuperAdmin]
    pagination_class   = StandardPagination
    filter_backends    = [filters.SearchFilter, filters.OrderingFilter]
    search_fields      = ['email', 'first_name', 'last_name']
    ordering_fields    = ['date_joined', 'email']

    list_message    = 'admin.government_retrieved'
    create_message  = 'admin.government_created'
    update_message  = 'admin.government_updated'
    destroy_message = 'admin.government_deleted'

    def get_queryset(self):
        return User.objects.filter(
            govt_profile__isnull=False
        ).select_related('govt_profile').order_by('-date_joined')

    def get_serializer_class(self):
        if self.action == 'create':
            return GovernmentCreateSerializer
        return GovernmentSerializer

    def create(self, request, *args, **kwargs):
        lang = self.get_language()
        serializer = GovernmentCreateSerializer(data=request.data)
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

        govt_group, _ = Group.objects.get_or_create(name=UserRole.GOVERNMENT)
        user.groups.add(govt_group)

        jtype = data['jurisdiction_type']
        GovernmentOfficialProfile.objects.create(
            user=user,
            designation=data['designation'],
            department=data['department'],
            jurisdiction_type=jtype,
            assigned_district=data.get('assigned_district') if jtype == 'district' else None,
            assigned_block=data.get('assigned_block') if jtype == 'block' else None,
        )

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

        user.refresh_from_db()
        return StandardResponse.success(
            data=GovernmentSerializer(user, context={"request": request}).data,
            message=t(self.create_message, lang),
            status_code=201,
        )

    def partial_update(self, request, *args, **kwargs):
        lang = self.get_language()
        user = self.get_object()

        first_name = request.data.get('first_name')
        last_name  = request.data.get('last_name')
        phone      = request.data.get('phone')
        designation = request.data.get('designation')
        department  = request.data.get('department')

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

        govt_fields = []
        govt_profile = user.govt_profile
        if designation is not None:
            govt_profile.designation = designation
            govt_fields.append('designation')
        if department is not None:
            govt_profile.department = department
            govt_fields.append('department')
        if govt_fields:
            govt_profile.save(update_fields=govt_fields)

        return StandardResponse.success(
            data=GovernmentSerializer(user, context={"request": request}).data,
            message=t(self.update_message, lang),
        )

    def destroy(self, request, *args, **kwargs):
        lang = self.get_language()
        obj  = self.get_object()
        obj.delete()
        return StandardResponse.success(message=t(self.destroy_message, lang))

    @extend_schema(
        methods=['get'],
        tags=['Admin - Government'],
        responses=GovernmentSerializer,
        summary="Get official's jurisdiction",
    )
    @extend_schema(
        methods=['post'],
        tags=['Admin - Government'],
        request=GovernmentJurisdictionActionSerializer,
        responses=GovernmentSerializer,
        summary="Change official's jurisdiction",
        description="Switch between district, block, or state-wide access.",
    )
    @action(detail=True, methods=['get', 'post'], url_path='jurisdiction')
    def jurisdiction(self, request, pk=None):
        lang = self.get_language()
        user = self.get_object()

        if request.method == 'POST':
            if not user.is_active:
                return StandardResponse.error(
                    message='Cannot change jurisdiction for a deactivated official.',
                    status_code=400,
                )
            serializer = GovernmentJurisdictionActionSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            data = serializer.validated_data
            jtype = data['jurisdiction_type']

            govt_profile = user.govt_profile
            govt_profile.jurisdiction_type = jtype
            govt_profile.assigned_district = data.get('assigned_district') if jtype == 'district' else None
            govt_profile.assigned_block = data.get('assigned_block') if jtype == 'block' else None
            govt_profile.save(update_fields=['jurisdiction_type', 'assigned_district', 'assigned_block'])

            return StandardResponse.success(
                data=GovernmentSerializer(user, context={"request": request}).data,
                message=t('admin.government_jurisdiction_updated', lang),
            )

        return StandardResponse.success(
            data=GovernmentSerializer(user, context={"request": request}).data,
            message=t('admin.government_retrieved', lang),
        )

    @extend_schema(tags=['Admin - Government'], responses=AvailableDistrictSerializer(many=True))
    @action(detail=False, methods=['get'], url_path='available-districts')
    def available_districts(self, request):
        lang = self.get_language()
        data = [{'code': code, 'name': get_district_name(code, language=lang)} for code in District.values]
        return StandardResponse.success(data=data, message=t('admin.districts_retrieved', lang))

    @extend_schema(tags=['Admin - Government'], responses=AvailableDistrictSerializer(many=True))
    @action(detail=False, methods=['get'], url_path='available-blocks')
    def available_blocks(self, request):
        lang = self.get_language()
        items = LookupService.get_by_category('block', lang)
        data = [{'code': item['code'], 'name': item['name']} for item in items]
        return StandardResponse.success(data=data, message=t('admin.blocks_retrieved', lang))

    @extend_schema(tags=['Admin - Government'])
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        lang = self.get_language()
        user = self.get_object()
        user.is_active = True
        user.save()
        return StandardResponse.success(
            data=GovernmentSerializer(user, context={"request": request}).data,
            message=t('admin.government_activated', lang),
        )

    @extend_schema(tags=['Admin - Government'])
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        lang = self.get_language()
        user = self.get_object()
        user.is_active = False
        user.save()
        return StandardResponse.success(
            data=GovernmentSerializer(user, context={"request": request}).data,
            message=t('admin.government_deactivated', lang),
        )

    @extend_schema(
        tags=['Admin - Government'],
        request=None,
        responses=GovernmentSerializer,
        summary="Reset official's password",
    )
    @action(detail=True, methods=['post'], url_path='reset-password')
    def reset_password(self, request, pk=None):
        lang    = self.get_language()
        user    = self.get_object()
        channel = request.data.get('notification_channel', 'email')

        if channel == 'sms' and not getattr(getattr(user, 'profile', None), 'phone', ''):
            return StandardResponse.error(
                message='Cannot use SMS - this official has no phone number on record.',
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
            data=GovernmentSerializer(user, context={"request": request}).data,
            message=t('admin.government_password_reset', lang),
        )

    @extend_schema(tags=['Admin - Government'], responses=GovernmentSerializer(many=True))
    @action(detail=False, methods=['get'], url_path='pending')
    def pending_registrations(self, request):
        lang = self.get_language()
        qs = self.get_queryset().filter(govt_profile__registration_status='pending')
        return StandardResponse.success(
            data=GovernmentSerializer(qs, many=True, context={"request": request}).data,
            message=t('admin.government_retrieved', lang),
        )

    @extend_schema(tags=['Admin - Government'], responses=GovernmentSerializer)
    @action(detail=True, methods=['post'], url_path='approve-registration')
    def approve_registration(self, request, pk=None):
        lang = self.get_language()
        user = self.get_object()
        profile = user.govt_profile

        if profile.registration_status != 'pending':
            return StandardResponse.error(
                message='This registration is not pending approval.',
                status_code=400,
            )

        from django.utils import timezone
        profile.registration_status = 'approved'
        profile.approved_by = request.user
        profile.approved_at = timezone.now()
        profile.save(update_fields=['registration_status', 'approved_by', 'approved_at'])

        # Set a fresh temporary password — the account was created with a random,
        # unknown password during OTP-based self-registration, so the official
        # needs a new one to log in for the first time.
        temp_password = secrets.token_urlsafe(10)
        user.set_password(temp_password)
        user.is_active = True
        user.save(update_fields=['password', 'is_active'])

        user_profile = user.profile
        user_profile.must_change_password = True
        user_profile.save(update_fields=['must_change_password'])

        try:
            frontend_url = getattr(django_settings, 'FRONTEND_URL', '')
            send_notification(
                user=user,
                code='welcome',
                channel='email',
                context={
                    'user_name': user.first_name or user.username,
                    'email': user.email,
                    'temp_password': temp_password,
                    'button_link': frontend_url,
                    'button_text': 'Login Now',
                },
                lang=lang,
            )
        except Exception:
            logger.exception(f"Failed to send approval notification to {user.email}")

        return StandardResponse.success(
            data=GovernmentSerializer(user, context={"request": request}).data,
            message='Registration approved. The official can now log in.',
        )

    @extend_schema(tags=['Admin - Government'], responses=GovernmentSerializer)
    @action(detail=True, methods=['post'], url_path='reject-registration')
    def reject_registration(self, request, pk=None):
        lang = self.get_language()
        user = self.get_object()
        profile = user.govt_profile

        if profile.registration_status != 'pending':
            return StandardResponse.error(
                message='This registration is not pending approval.',
                status_code=400,
            )

        profile.registration_status = 'rejected'
        profile.save(update_fields=['registration_status'])

        return StandardResponse.success(
            data=GovernmentSerializer(user, context={"request": request}).data,
            message='Registration rejected.',
        )
