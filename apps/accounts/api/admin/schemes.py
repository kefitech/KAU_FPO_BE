"""
Admin — Schemes & Subsidies CRUD
==================================
GET/POST  /api/admin/schemes/
GET/PATCH/DELETE  /api/admin/schemes/{id}/
POST  /api/admin/schemes/{id}/activate/
POST  /api/admin/schemes/{id}/deactivate/
"""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from django.db.models import Q
from apps.core.utils.constants import UserRole
from apps.core.utils.pagination import StandardPagination
from apps.core.utils.responses import StandardResponse
from apps.database.models.schemes import Scheme, SchemeCategory


def _is_admin(user):
    return user.groups.filter(name__in=[UserRole.SUPER_ADMIN, UserRole.SUB_ADMIN]).exists()


class SchemeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Scheme
        fields = [
            'id', 'name_en', 'name_ml', 'administering_body', 'category',
            'objective', 'eligibility', 'benefit_details', 'application_process',
            'official_link', 'last_updated', 'is_active', 'order',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['category_display'] = instance.get_category_display()
        return data


class SchemeWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Scheme
        fields = [
            'name_en', 'name_ml', 'administering_body', 'category',
            'objective', 'eligibility', 'benefit_details', 'application_process',
            'official_link', 'last_updated', 'is_active', 'order',
        ]

    def validate_category(self, value):
        valid = [c.value for c in SchemeCategory]
        if value not in valid:
            raise serializers.ValidationError(f'Must be one of: {", ".join(valid)}')
        return value


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

        qs = Scheme.objects.filter(is_deleted=False).order_by('order', 'name_en')

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
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        serializer = SchemeWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return StandardResponse.error('Validation failed.', errors=serializer.errors,
                                          status_code=status.HTTP_400_BAD_REQUEST)

        scheme = serializer.save()
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
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        scheme = self._get_scheme(pk)
        if not scheme:
            return StandardResponse.error('Scheme not found.', status_code=status.HTTP_404_NOT_FOUND)

        serializer = SchemeWriteSerializer(scheme, data=request.data, partial=True)
        if not serializer.is_valid():
            return StandardResponse.error('Validation failed.', errors=serializer.errors,
                                          status_code=status.HTTP_400_BAD_REQUEST)

        serializer.save()
        return StandardResponse.success(data=SchemeSerializer(scheme).data, message='Scheme updated.')

    @extend_schema(tags=['Admin - Schemes'], summary='Delete a scheme')
    def delete(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        scheme = self._get_scheme(pk)
        if not scheme:
            return StandardResponse.error('Scheme not found.', status_code=status.HTTP_404_NOT_FOUND)

        scheme.soft_delete()
        return StandardResponse.success(message='Scheme deleted.')


class SchemeActivateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Admin - Schemes'], summary='Activate a scheme')
    def post(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        try:
            scheme = Scheme.objects.get(pk=pk, is_deleted=False)
        except Scheme.DoesNotExist:
            return StandardResponse.error('Scheme not found.', status_code=status.HTTP_404_NOT_FOUND)

        scheme.is_active = True
        scheme.save(update_fields=['is_active'])
        return StandardResponse.success(message='Scheme activated.')


class SchemeDeactivateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Admin - Schemes'], summary='Deactivate a scheme')
    def post(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        try:
            scheme = Scheme.objects.get(pk=pk, is_deleted=False)
        except Scheme.DoesNotExist:
            return StandardResponse.error('Scheme not found.', status_code=status.HTTP_404_NOT_FOUND)

        scheme.is_active = False
        scheme.save(update_fields=['is_active'])
        return StandardResponse.success(message='Scheme deactivated.')
