"""
Admin — Expert Directory CRUD
================================
GET/POST  /api/admin/experts/
GET/PATCH/DELETE  /api/admin/experts/{id}/
POST  /api/admin/experts/{id}/activate/
POST  /api/admin/experts/{id}/deactivate/
POST  /api/admin/experts/{id}/reset-password/
GET   /api/admin/experts/{id}/bookings/

Enquiries ("Contact Expert" messages) go straight to the expert by email and
have no admin listing.
"""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from django.db.models import Q
from apps.core.permissions.fpo_scope import get_sub_admin_district, is_super_admin
from apps.core.utils.constants import UserRole
from apps.core.utils.pagination import StandardPagination
from apps.core.utils.responses import StandardResponse
from apps.database.models.schemes import Expert, ExpertCategory
import secrets
from django.contrib.auth.models import User, Group
from django.conf import settings as django_settings
from apps.notifications.services import send_notification
from apps.database.models.expert_booking import ExpertBooking
from apps.experts.api.booking_views import ExpertBookingSerializer
from apps.core.models.generic import AuditLog
from apps.core.services.audit import AuditService
from apps.core.services.translation import t
from .fpo_users import _generate_temp_password



def _is_admin(user):
    return user.groups.filter(name__in=[UserRole.SUPER_ADMIN, UserRole.SUB_ADMIN]).exists()


def _sync_login_account(expert, is_active):
    # Expert.is_active only hides the directory entry; the linked User is what login checks.
    if expert.user_id and expert.user.is_active != is_active:
        expert.user.is_active = is_active
        expert.user.save(update_fields=['is_active'])


def _sub_admin_district_error(user, district, current=None):
    """
    A sub-admin may only put an expert in their own district. `current` is the
    expert's district when editing — leaving it unchanged is always fine.
    Returns an error message, or None when allowed.
    """
    if is_super_admin(user) or not district or district == current:
        return None
    own = get_sub_admin_district(user)
    if district != own:
        return f'You can only add experts to your own district ({own}).' if own else \
            'You have no district assigned, so you cannot set an expert\'s district.'
    return None


class ExpertSerializer(serializers.ModelSerializer):
    # Experts added before logins were created on save have no account — nothing to reset.
    has_login = serializers.SerializerMethodField()

    class Meta:
        model = Expert
        fields = [
            'id', 'name_en', 'name_ml', 'designation', 'organisation',
            'primary_expertise', 'secondary_expertise', 'district',
            'email', 'phone', 'category', 'is_active', 'order',
            'has_login', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_has_login(self, obj):
        return obj.user_id is not None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['category_display'] = instance.get_category_display()
        return data


class ExpertWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Expert
        fields = [
            'name_en', 'name_ml', 'designation', 'organisation',
            'primary_expertise', 'secondary_expertise', 'district',
            'email', 'phone', 'category', 'is_active', 'order',
        ]

    def validate_category(self, value):
        valid = [c.value for c in ExpertCategory]
        if value not in valid:
            raise serializers.ValidationError(f'Must be one of: {", ".join(valid)}')
        return value

    def validate_email(self, value):
        # Creating an expert also creates their login (username = email), so an email that
        # already belongs to an account would leave the expert without one — reject it.
        # Lowercased like the other admin-created accounts; on edit, the expert's own
        # record and login don't count as a clash.
        value = value.lower()
        expert = self.instance
        if expert and (expert.email or '').lower() == value:
            return value
        users = User.objects.filter(Q(email__iexact=value) | Q(username__iexact=value))
        if expert and expert.user_id:
            users = users.exclude(pk=expert.user_id)
        if users.exists():
            raise serializers.ValidationError('A user with this email already exists.')
        experts = Expert.objects.filter(email__iexact=value, is_deleted=False)
        if expert:
            experts = experts.exclude(pk=expert.pk)
        if experts.exists():
            raise serializers.ValidationError('An expert with this email already exists.')
        return value


class ExpertListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['Admin - Experts'],
        summary='List all experts',
        responses={200: ExpertSerializer(many=True)},
    )
    def get(self, request):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        qs = Expert.objects.filter(is_deleted=False).order_by('order', 'name_en')
        search = request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(name_en__icontains=search) |
                Q(name_ml__icontains=search) |
                Q(email__icontains=search) |
                Q(phone__icontains=search) |
                Q(organisation__icontains=search)
            )

        category = request.query_params.get('category')
        if category:
            qs = qs.filter(category=category)

        district = request.query_params.get('district')
        if district:
            qs = qs.filter(district=district)

        is_active = request.query_params.get('is_active')
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() == 'true')

        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = ExpertSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        tags=['Admin - Experts'],
        summary='Create an expert',
        request=ExpertWriteSerializer,
        responses={201: ExpertSerializer},
    )
    def post(self, request):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        serializer = ExpertWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return StandardResponse.error('Validation failed.', errors=serializer.errors,
                                          status_code=status.HTTP_400_BAD_REQUEST)

        # Sub-admins add experts to their own district — filled in when left blank.
        extra = {}
        if not is_super_admin(request.user):
            district = serializer.validated_data.get('district') or get_sub_admin_district(request.user)
            error = _sub_admin_district_error(request.user, district)
            if error:
                return StandardResponse.error(error, errors={'district': [error]}, status_code=status.HTTP_403_FORBIDDEN)
            extra['district'] = district or ''
        expert = serializer.save(**extra)

        if not expert.user and expert.email and not User.objects.filter(username=expert.email).exists():
            temp_password = secrets.token_urlsafe(10)
            new_user = User.objects.create_user(
                username=expert.email,
                email=expert.email,
                password=temp_password,
                first_name=expert.name_en,
            )
            expert_group, _ = Group.objects.get_or_create(name=UserRole.EXPERT)
            new_user.groups.add(expert_group)
            new_user.profile.must_change_password = True
            new_user.profile.phone = expert.phone or ''
            new_user.profile.save(update_fields=['must_change_password', 'phone'])
            expert.user = new_user
            expert.save(update_fields=['user'])

            try:
                frontend_url = getattr(django_settings, 'FRONTEND_URL', '')
                send_notification(
                    user=new_user, code='welcome', channel='email',
                    context={
                        'user_name': expert.name_en, 'email': expert.email,
                        'temp_password': temp_password, 'button_link': frontend_url,
                        'button_text': 'Login Now',
                    },
                )
            except Exception:
                pass
        return StandardResponse.success(
            data=ExpertSerializer(expert).data,
            message='Expert created.',
            status_code=status.HTTP_201_CREATED,
        )


class ExpertDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_expert(self, pk):
        try:
            return Expert.objects.get(pk=pk, is_deleted=False)
        except Expert.DoesNotExist:
            return None

    @extend_schema(tags=['Admin - Experts'], summary='Retrieve an expert')
    def get(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        expert = self._get_expert(pk)
        if not expert:
            return StandardResponse.error('Expert not found.', status_code=status.HTTP_404_NOT_FOUND)

        return StandardResponse.success(data=ExpertSerializer(expert).data)

    @extend_schema(tags=['Admin - Experts'], summary='Update an expert', request=ExpertWriteSerializer)
    def patch(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        expert = self._get_expert(pk)
        if not expert:
            return StandardResponse.error('Expert not found.', status_code=status.HTTP_404_NOT_FOUND)

        serializer = ExpertWriteSerializer(expert, data=request.data, partial=True)
        if not serializer.is_valid():
            return StandardResponse.error('Validation failed.', errors=serializer.errors,
                                          status_code=status.HTTP_400_BAD_REQUEST)

        error = _sub_admin_district_error(request.user, serializer.validated_data.get('district'), current=expert.district)
        if error:
            return StandardResponse.error(error, errors={'district': [error]}, status_code=status.HTTP_403_FORBIDDEN)

        serializer.save()
        if 'is_active' in serializer.validated_data:
            _sync_login_account(expert, expert.is_active)
        return StandardResponse.success(data=ExpertSerializer(expert).data, message='Expert updated.')

    @extend_schema(tags=['Admin - Experts'], summary='Delete an expert')
    def delete(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        expert = self._get_expert(pk)
        if not expert:
            return StandardResponse.error('Expert not found.', status_code=status.HTTP_404_NOT_FOUND)

        expert.soft_delete()
        return StandardResponse.success(message='Expert deleted.')


class ExpertActivateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Admin - Experts'], summary='Activate an expert')
    def post(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        try:
            expert = Expert.objects.get(pk=pk, is_deleted=False)
        except Expert.DoesNotExist:
            return StandardResponse.error('Expert not found.', status_code=status.HTTP_404_NOT_FOUND)

        expert.is_active = True
        expert.save(update_fields=['is_active'])
        _sync_login_account(expert, True)
        return StandardResponse.success(message='Expert activated.')


class ExpertDeactivateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Admin - Experts'], summary='Deactivate an expert')
    def post(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        try:
            expert = Expert.objects.get(pk=pk, is_deleted=False)
        except Expert.DoesNotExist:
            return StandardResponse.error('Expert not found.', status_code=status.HTTP_404_NOT_FOUND)

        expert.is_active = False
        expert.save(update_fields=['is_active'])
        _sync_login_account(expert, False)
        return StandardResponse.success(message='Expert deactivated.')


class ExpertResetPasswordView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['Admin - Experts'],
        summary="Reset an expert's password",
        description='Generates a temporary password, sets must_change_password=True, and emails it to the expert.',
        request=None,
    )
    def post(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        try:
            expert = Expert.objects.select_related('user__profile').get(pk=pk, is_deleted=False)
        except Expert.DoesNotExist:
            return StandardResponse.error('Expert not found.', status_code=status.HTTP_404_NOT_FOUND)

        user = expert.user
        if user is None:
            return StandardResponse.error(
                'This expert has no login account, so there is no password to reset.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        if not expert.is_active or not user.is_active:
            return StandardResponse.error(
                t('admin.reset_password_inactive_user', getattr(request, 'language', 'en')),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        temp_password = _generate_temp_password()
        user.set_password(temp_password)
        user.save(update_fields=['password'])
        user.profile.must_change_password = True
        user.profile.save(update_fields=['must_change_password'])

        try:
            send_notification(
                user=user, code='password_reset_by_admin', channel='email',
                context={
                    'user_name': expert.name_en or user.get_full_name() or user.email,
                    'temp_password': temp_password,
                    'button_link': getattr(django_settings, 'FRONTEND_URL', ''),
                    'button_text': 'Login Now',
                },
            )
        except Exception:
            pass

        AuditService.log(
            user=request.user,
            action=AuditLog.Action.PASSWORD_RESET,
            instance=expert,
            request=request,
            changes={'reset_password_for': user.email},
        )
        return StandardResponse.success(message='Password reset. The expert will be asked to change it on next login.')


class ExpertBookingsView(APIView):
    """GET /api/admin/experts/{id}/bookings/ — every booking for an expert (admin only)."""
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Admin - Experts'], summary='List bookings for an expert')
    def get(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        if not Expert.objects.filter(pk=pk, is_deleted=False).exists():
            return StandardResponse.error('Expert not found.', status_code=status.HTTP_404_NOT_FOUND)

        qs = (
            ExpertBooking.objects
            .filter(expert_id=pk, is_deleted=False)
            .select_related('expert', 'fpo', 'fpo__primary_user', 'user')
            .order_by('-created_at')
        )
        serializer = ExpertBookingSerializer(qs, many=True, context={'request': request})
        return StandardResponse.success(data=serializer.data)
