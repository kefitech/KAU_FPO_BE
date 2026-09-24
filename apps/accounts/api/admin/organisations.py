"""
Admin - CBBO/NGO Organisation CRUD
GET/POST  /api/admin/organisations/
GET/PATCH/DELETE  /api/admin/organisations/{id}/
"""
from rest_framework import serializers, status
from rest_framework.views import APIView
from django.db.models import Q

from drf_spectacular.utils import extend_schema

from apps.core.utils.constants import UserRole
from apps.core.utils.pagination import StandardPagination
from apps.core.utils.responses import StandardResponse
from apps.database.models.organisation import Organisation, ORG_TYPE_CHOICES


def _is_admin(user):
    return user.groups.filter(name__in=[UserRole.SUPER_ADMIN, UserRole.SUB_ADMIN]).exists()


class OrganisationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organisation
        fields = [
            'id', 'name', 'org_type', 'contact_person', 'contact_designation',
            'contact_email', 'contact_phone', 'districts_covered', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['org_type_display'] = instance.get_org_type_display()
        return data


class OrganisationWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organisation
        fields = [
            'name', 'org_type', 'contact_person', 'contact_designation',
            'contact_email', 'contact_phone', 'districts_covered', 'is_active',
        ]

    def validate_org_type(self, value):
        valid = [c[0] for c in ORG_TYPE_CHOICES]
        if value not in valid:
            raise serializers.ValidationError(f'Must be one of: {", ".join(valid)}')
        return value


class OrganisationListView(APIView):
    @extend_schema(
        tags=['Admin - Organisations'],
        summary='List organisations',
        responses={200: OrganisationSerializer(many=True)},
    )
    def get(self, request):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        qs = Organisation.objects.filter(is_deleted=False).order_by('name')
        search = request.query_params.get('search')
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(contact_person__icontains=search))
        org_type = request.query_params.get('org_type')
        if org_type:
            qs = qs.filter(org_type=org_type)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        data = OrganisationSerializer(page, many=True).data
        return paginator.get_paginated_response(data)

    @extend_schema(
        tags=['Admin - Organisations'],
        summary='Create organisation',
        request=OrganisationWriteSerializer,
        responses={201: OrganisationSerializer},
    )
    def post(self, request):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        serializer = OrganisationWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        org = serializer.save()
        return StandardResponse.success(
            data=OrganisationSerializer(org).data,
            message='Organisation created.',
            status_code=201,
        )


class OrganisationDetailView(APIView):
    @extend_schema(
        tags=['Admin - Organisations'],
        summary='Get organisation',
        responses={200: OrganisationSerializer},
    )
    def get(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        org = Organisation.objects.filter(pk=pk, is_deleted=False).first()
        if not org:
            return StandardResponse.error('Organisation not found.', status_code=status.HTTP_404_NOT_FOUND)
        return StandardResponse.success(data=OrganisationSerializer(org).data)

    @extend_schema(
        tags=['Admin - Organisations'],
        summary='Update organisation',
        request=OrganisationWriteSerializer,
        responses={200: OrganisationSerializer},
    )
    def patch(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        org = Organisation.objects.filter(pk=pk, is_deleted=False).first()
        if not org:
            return StandardResponse.error('Organisation not found.', status_code=status.HTTP_404_NOT_FOUND)
        serializer = OrganisationWriteSerializer(org, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        org = serializer.save()
        return StandardResponse.success(data=OrganisationSerializer(org).data, message='Organisation updated.')

    @extend_schema(
        tags=['Admin - Organisations'],
        summary='Delete organisation',
        request=None,
        responses={200: None},
    )
    def delete(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        org = Organisation.objects.filter(pk=pk, is_deleted=False).first()
        if not org:
            return StandardResponse.error('Organisation not found.', status_code=status.HTTP_404_NOT_FOUND)
        org.is_deleted = True
        org.save(update_fields=['is_deleted'])
        return StandardResponse.success(message='Organisation deleted.')
