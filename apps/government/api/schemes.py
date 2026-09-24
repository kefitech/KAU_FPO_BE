"""
Government - Schemes and Subsidies (write access)
GET/POST  /api/government/schemes/
GET/PATCH/DELETE  /api/government/schemes/{id}/
Government officials can add/edit scheme catalog entries.
"""
from rest_framework import serializers, status
from rest_framework.views import APIView
from django.db.models import Q

from apps.core.utils.pagination import StandardPagination
from apps.core.utils.responses import StandardResponse
from apps.database.models.schemes import Scheme, SchemeCategory

from apps.government.api.scoping import is_government_user


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
        data['created_by'] = instance.created_by_id
        data['created_by_name'] = instance.created_by.get_full_name() if instance.created_by else None
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


class GovernmentSchemeListView(APIView):
    def get(self, request):
        if not is_government_user(request.user):
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
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        data = SchemeSerializer(page, many=True).data
        return paginator.get_paginated_response(data)

    def post(self, request):
        if not is_government_user(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        serializer = SchemeWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        scheme = serializer.save(created_by=request.user)
        return StandardResponse.success(
            data=SchemeSerializer(scheme).data,
            message='Scheme created.',
            status_code=201,
        )


class GovernmentSchemeDetailView(APIView):
    def get(self, request, pk):
        if not is_government_user(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        scheme = Scheme.objects.filter(pk=pk, is_deleted=False).first()
        if not scheme:
            return StandardResponse.error('Scheme not found.', status_code=status.HTTP_404_NOT_FOUND)
        return StandardResponse.success(data=SchemeSerializer(scheme).data)

    def patch(self, request, pk):
        if not is_government_user(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        scheme = Scheme.objects.filter(pk=pk, is_deleted=False).first()
        if not scheme:
            return StandardResponse.error('Scheme not found.', status_code=status.HTTP_404_NOT_FOUND)
        is_owner = scheme.created_by_id == request.user.id
        is_super_admin = request.user.groups.filter(name='super_admin').exists()
        if not is_owner and not is_super_admin:
            return StandardResponse.error(
                'Only the government official who created this scheme can edit it.',
                status_code=status.HTTP_403_FORBIDDEN,
            )
        serializer = SchemeWriteSerializer(scheme, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        scheme = serializer.save(updated_by=request.user)
        return StandardResponse.success(data=SchemeSerializer(scheme).data, message='Scheme updated.')
