"""
Admin — Crop Package of Practices CRUD
======================================
GET/POST          /api/admin/crop-pop/
GET/PATCH/DELETE  /api/admin/crop-pop/{id}/
POST              /api/admin/crop-pop/{id}/activate/
POST              /api/admin/crop-pop/{id}/deactivate/

Content is transcribed from KAU's official "Package of Practices
Recommendations: Crops" publication. Entries default to is_active=False so
each one can be cross-checked against the source PDF before an FPO sees it.
"""
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import filters, serializers
from rest_framework.decorators import action

from apps.core.permissions.rbac import IsAdmin, IsAuthenticated
from apps.core.services.lookup import resolve_master_name
from apps.core.services.translation import t
from apps.core.utils.pagination import StandardPagination
from apps.core.utils.responses import StandardResponse
from apps.core.views import TranslatedViewSet
from apps.database.models import CropPackageOfPractices


class CropPackageOfPracticesSerializer(serializers.ModelSerializer):
    class Meta:
        model = CropPackageOfPractices
        fields = [
            'id', 'crop_name', 'crop_group', 'season', 'varieties', 'spacing',
            'manuring_fertilizer', 'plant_protection', 'harvesting', 'expected_yield',
            'sections', 'source_reference', 'source_page_range', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_crop_name(self, value):
        value = value.strip()
        # Unchanged values pass, so editing other fields of an older row is never blocked
        if not (self.instance and value == self.instance.crop_name):
            canonical = resolve_master_name('crop_name', value)
            if canonical is None:
                raise serializers.ValidationError("Choose a crop from the Master Data 'Crop Names' list.")
            value = canonical
        qs = CropPackageOfPractices.objects.filter(crop_name__iexact=value, is_deleted=False)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                f"A Package of Practices entry already exists for '{value}' (case-insensitive)."
            )
        return value

    def validate_crop_group(self, value):
        value = value.strip()
        if not value or (self.instance and value == self.instance.crop_group):
            return value
        canonical = resolve_master_name('crop_group', value)
        if canonical is None:
            raise serializers.ValidationError("Choose a group from the Master Data 'Crop Groups' list.")
        return canonical

    def validate_varieties(self, value):
        if not isinstance(value, list) or not all(
            isinstance(v, dict) and isinstance(v.get('name'), str) and v['name'].strip() for v in value
        ):
            raise serializers.ValidationError("Must be a list of {'name': str, 'description'?: str}.")
        return value

    def validate_sections(self, value):
        if not isinstance(value, list) or not all(
            isinstance(s, dict)
            and isinstance(s.get('heading'), str) and s['heading'].strip()
            and isinstance(s.get('body'), str)
            for s in value
        ):
            raise serializers.ValidationError("Must be a list of {'heading': str, 'body': str}.")
        return value


@extend_schema_view(
    list=extend_schema(tags=['Admin - Crop Package of Practices']),
    create=extend_schema(tags=['Admin - Crop Package of Practices']),
    retrieve=extend_schema(tags=['Admin - Crop Package of Practices']),
    update=extend_schema(tags=['Admin - Crop Package of Practices']),
    partial_update=extend_schema(tags=['Admin - Crop Package of Practices']),
    destroy=extend_schema(tags=['Admin - Crop Package of Practices']),
)
class CropPackageOfPracticesViewSet(TranslatedViewSet):
    serializer_class = CropPackageOfPracticesSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    pagination_class = StandardPagination
    filter_backends = [filters.SearchFilter]
    search_fields = ['crop_name', 'crop_group']

    list_message = 'recommendations.pop_list_retrieved'
    create_message = 'recommendations.pop_created'
    update_message = 'recommendations.pop_updated'
    destroy_message = 'recommendations.pop_deleted'

    def get_queryset(self):
        return CropPackageOfPractices.objects.filter(is_deleted=False).order_by('crop_name')

    def perform_destroy(self, instance):
        # Hard delete: crop_name is unique, so a soft-deleted row would block re-creating the name.
        instance.delete()

    @extend_schema(tags=['Admin - Crop Package of Practices'])
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        obj = self.get_object()
        obj.is_active = True
        obj.save(update_fields=['is_active', 'updated_at'])
        return StandardResponse.success(
            data=self.get_serializer(obj).data,
            message=t('recommendations.pop_activated', self.get_language()),
        )

    @extend_schema(tags=['Admin - Crop Package of Practices'])
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        obj = self.get_object()
        obj.is_active = False
        obj.save(update_fields=['is_active', 'updated_at'])
        return StandardResponse.success(
            data=self.get_serializer(obj).data,
            message=t('recommendations.pop_deactivated', self.get_language()),
        )
