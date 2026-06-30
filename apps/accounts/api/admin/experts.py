"""
Admin — Expert Directory CRUD
================================
GET/POST  /api/admin/experts/
GET/PATCH/DELETE  /api/admin/experts/{id}/
POST  /api/admin/experts/{id}/activate/
POST  /api/admin/experts/{id}/deactivate/
GET   /api/admin/experts/{id}/enquiries/
"""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from django.db.models import Q
from apps.core.utils.constants import UserRole
from apps.core.utils.pagination import StandardPagination
from apps.core.utils.responses import StandardResponse
from apps.database.models.schemes import Expert, ExpertCategory, ExpertEnquiry


def _is_admin(user):
    return user.groups.filter(name__in=[UserRole.SUPER_ADMIN, UserRole.SUB_ADMIN]).exists()


class ExpertSerializer(serializers.ModelSerializer):
    class Meta:
        model = Expert
        fields = [
            'id', 'name_en', 'name_ml', 'designation', 'organisation',
            'primary_expertise', 'secondary_expertise', 'district',
            'email', 'phone', 'category', 'is_active', 'order',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

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


class EnquiryAdminSerializer(serializers.ModelSerializer):
    fpo_name    = serializers.SerializerMethodField()
    user_name   = serializers.SerializerMethodField()
    user_email  = serializers.SerializerMethodField()

    class Meta:
        model = ExpertEnquiry
        fields = ['id', 'fpo_name', 'user_name', 'user_email', 'message', 'submitted_at', 'email_sent']

    def get_fpo_name(self, obj):
        return obj.fpo.fpo_name if obj.fpo else None

    def get_user_name(self, obj):
        if obj.fpo_user:
            return f'{obj.fpo_user.first_name} {obj.fpo_user.last_name}'.strip()
        return None

    def get_user_email(self, obj):
        return obj.fpo_user.email if obj.fpo_user else None


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

        expert = serializer.save()
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

        serializer.save()
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
        return StandardResponse.success(message='Expert deactivated.')


class ExpertEnquiriesView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Admin - Experts'], summary='List enquiries for an expert')
    def get(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        try:
            expert = Expert.objects.get(pk=pk, is_deleted=False)
        except Expert.DoesNotExist:
            return StandardResponse.error('Expert not found.', status_code=status.HTTP_404_NOT_FOUND)

        qs = expert.enquiries.select_related('fpo', 'fpo_user').order_by('-submitted_at')
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = EnquiryAdminSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
