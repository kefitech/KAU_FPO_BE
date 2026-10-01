"""
Admin — Schemes & Subsidies CRUD
==================================
GET/POST  /api/admin/schemes/
GET/PATCH/DELETE  /api/admin/schemes/{id}/
POST  /api/admin/schemes/{id}/activate/
POST  /api/admin/schemes/{id}/deactivate/
"""

import re

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from django.db.models import Q
from apps.core.utils.constants import UserRole
from apps.core.utils.pagination import StandardPagination
from apps.core.utils.responses import StandardResponse
from apps.database.models.schemes import Scheme, SchemeCategory, validate_scheme_deadline


def _is_admin(user):
    return user.groups.filter(name__in=[UserRole.SUPER_ADMIN, UserRole.SUB_ADMIN]).exists()


def _is_super_admin(user):
    return user.groups.filter(name=UserRole.SUPER_ADMIN).exists()


def _can_manage_schemes(user):
    """Super admin always, sub-admin only with `can_manage_schemes`."""
    if _is_super_admin(user):
        return True
    if user.groups.filter(name=UserRole.SUB_ADMIN).exists():
        return user.has_perm('accounts.can_manage_schemes')
    return False


def _can_edit_this_scheme(user, scheme):
    """Ownership rule: super admin edits anything; sub-admin only their own rows."""
    if _is_super_admin(user):
        return True
    return _can_manage_schemes(user) and scheme.created_by_id == user.id


class SchemeSerializer(serializers.ModelSerializer):
    created_by_email = serializers.SerializerMethodField()

    class Meta:
        model = Scheme
        fields = [
            'id', 'name_en', 'name_ml', 'administering_body', 'category',
            'objective', 'eligibility', 'benefit_details', 'application_process',
            'official_link', 'last_updated', 'deadline', 'is_active', 'order',
            'created_by_email', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_by_email', 'created_at', 'updated_at']

    def get_created_by_email(self, obj):
        return obj.created_by.email if obj.created_by else None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['category_display'] = instance.get_category_display()
        # Same shape as the government scheme API — the table shows the name, or "You"
        creator = instance.created_by
        data['created_by'] = instance.created_by_id
        data['created_by_name'] = (creator.get_full_name() or creator.email) if creator else None
        return data


# Letters/digits (any script) plus a small punctuation set real scheme names use,
# e.g. "Agriculture Infrastructure Fund (AIF)", "PM-KISAN", "Ministry of A & B".
# Deliberately NOT applied to name_ml or the long-text fields: Malayalam vowel
# signs and ZWNJ are combining marks that \w does not match, so an allow-list
# there would reject every genuine Malayalam name.
_NAME_ALLOWED = re.compile(r"^(?:[^\W_]| |[&(),.\-–'’/:])+$")
_HAS_LETTER = re.compile(r'[^\W\d_]')
_HAS_LETTER_OR_DIGIT = re.compile(r'[^\W_]')


def _validate_english_name(value, label):
    if not _HAS_LETTER.search(value):
        raise serializers.ValidationError(f'{label} must contain at least one letter.')
    if not _NAME_ALLOWED.match(value):
        raise serializers.ValidationError(
            f"{label} may only contain letters, numbers, spaces and & ( ) , . - ' / :"
        )
    return value


def _validate_not_only_symbols(value, label):
    if value and not _HAS_LETTER_OR_DIGIT.search(value):
        raise serializers.ValidationError(f'{label} must contain letters or numbers, not only symbols.')
    return value


class SchemeWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Scheme
        fields = [
            'name_en', 'name_ml', 'administering_body', 'category',
            'objective', 'eligibility', 'benefit_details', 'application_process',
            'official_link', 'last_updated', 'deadline', 'is_active', 'order',
        ]

    def validate_deadline(self, value):
        error = validate_scheme_deadline(value, self.instance)
        if error:
            raise serializers.ValidationError(error)
        return value

    def validate_category(self, value):
        valid = [c.value for c in SchemeCategory]
        if value not in valid:
            raise serializers.ValidationError(f'Must be one of: {", ".join(valid)}')
        return value

    def validate_name_en(self, value):
        return _validate_english_name(value, 'English name')

    def validate_administering_body(self, value):
        return _validate_english_name(value, 'Administering body')

    def validate_name_ml(self, value):
        if value and not _HAS_LETTER.search(value):
            raise serializers.ValidationError('Malayalam name must contain at least one letter.')
        return value

    def validate_objective(self, value):
        return _validate_not_only_symbols(value, 'Objective')

    def validate_eligibility(self, value):
        return _validate_not_only_symbols(value, 'Eligibility')

    def validate_benefit_details(self, value):
        return _validate_not_only_symbols(value, 'Benefit details')

    def validate_application_process(self, value):
        return _validate_not_only_symbols(value, 'Application process')


class SchemeListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['Admin - Schemes'],
        summary='List all schemes',
        responses={200: SchemeSerializer(many=True)},
    )
    def get(self, request):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        qs = Scheme.objects.filter(is_deleted=False).select_related('created_by').order_by('order', 'name_en')

        search = request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(name_en__icontains=search) |
                Q(name_ml__icontains=search) |
                Q(administering_body__icontains=search) |
                Q(objective__icontains=search)
            )

        category = request.query_params.get('category')
        if category:
            qs = qs.filter(category=category)

        is_active = request.query_params.get('is_active')
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() == 'true')

        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = SchemeSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        tags=['Admin - Schemes'],
        summary='Create a scheme',
        request=SchemeWriteSerializer,
        responses={201: SchemeSerializer},
    )
    def post(self, request):
        if not _can_manage_schemes(request.user):
            return StandardResponse.error(
                'Permission denied. Sub-admins need can_manage_schemes to create schemes.',
                status_code=status.HTTP_403_FORBIDDEN,
            )

        serializer = SchemeWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return StandardResponse.error('Validation failed.', errors=serializer.errors,
                                          status_code=status.HTTP_400_BAD_REQUEST)

        scheme = serializer.save(created_by=request.user)
        return StandardResponse.success(
            data=SchemeSerializer(scheme).data,
            message='Scheme created.',
            status_code=status.HTTP_201_CREATED,
        )


class SchemeDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_scheme(self, pk):
        try:
            return Scheme.objects.get(pk=pk, is_deleted=False)
        except Scheme.DoesNotExist:
            return None

    @extend_schema(tags=['Admin - Schemes'], summary='Retrieve a scheme')
    def get(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        scheme = self._get_scheme(pk)
        if not scheme:
            return StandardResponse.error('Scheme not found.', status_code=status.HTTP_404_NOT_FOUND)

        return StandardResponse.success(data=SchemeSerializer(scheme).data)

    @extend_schema(tags=['Admin - Schemes'], summary='Update a scheme', request=SchemeWriteSerializer)
    def patch(self, request, pk):
        scheme = self._get_scheme(pk)
        if not scheme:
            return StandardResponse.error('Scheme not found.', status_code=status.HTTP_404_NOT_FOUND)

        if not _can_edit_this_scheme(request.user, scheme):
            return StandardResponse.error(
                'Permission denied. Sub-admins can only edit schemes they created.',
                status_code=status.HTTP_403_FORBIDDEN,
            )

        serializer = SchemeWriteSerializer(scheme, data=request.data, partial=True)
        if not serializer.is_valid():
            return StandardResponse.error('Validation failed.', errors=serializer.errors,
                                          status_code=status.HTTP_400_BAD_REQUEST)

        serializer.save(updated_by=request.user)
        return StandardResponse.success(data=SchemeSerializer(scheme).data, message='Scheme updated.')

    @extend_schema(tags=['Admin - Schemes'], summary='Delete a scheme')
    def delete(self, request, pk):
        scheme = self._get_scheme(pk)
        if not scheme:
            return StandardResponse.error('Scheme not found.', status_code=status.HTTP_404_NOT_FOUND)

        if not _can_edit_this_scheme(request.user, scheme):
            return StandardResponse.error(
                'Permission denied. Sub-admins can only delete schemes they created.',
                status_code=status.HTTP_403_FORBIDDEN,
            )

        scheme.soft_delete()
        return StandardResponse.success(message='Scheme deleted.')


class SchemeActivateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Admin - Schemes'], summary='Activate a scheme')
    def post(self, request, pk):
        try:
            scheme = Scheme.objects.get(pk=pk, is_deleted=False)
        except Scheme.DoesNotExist:
            return StandardResponse.error('Scheme not found.', status_code=status.HTTP_404_NOT_FOUND)

        if not _can_edit_this_scheme(request.user, scheme):
            return StandardResponse.error(
                'Permission denied. Sub-admins can only edit schemes they created.',
                status_code=status.HTTP_403_FORBIDDEN,
            )

        scheme.is_active = True
        scheme.save(update_fields=['is_active'])
        return StandardResponse.success(message='Scheme activated.')


class SchemeDeactivateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Admin - Schemes'], summary='Deactivate a scheme')
    def post(self, request, pk):
        try:
            scheme = Scheme.objects.get(pk=pk, is_deleted=False)
        except Scheme.DoesNotExist:
            return StandardResponse.error('Scheme not found.', status_code=status.HTTP_404_NOT_FOUND)

        if not _can_edit_this_scheme(request.user, scheme):
            return StandardResponse.error(
                'Permission denied. Sub-admins can only edit schemes they created.',
                status_code=status.HTTP_403_FORBIDDEN,
            )

        scheme.is_active = False
        scheme.save(update_fields=['is_active'])
        return StandardResponse.success(message='Scheme deactivated.')
