"""
Translation Management API
==========================
Base Path: /api/admin/translations/
Author: Athul Gopan (Kefi Tech Solutions)
"""

from rest_framework import status, filters
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from apps.core.views import TranslatedViewSet
from apps.core.permissions.rbac import IsAdmin
from apps.core.utils.responses import StandardResponse
from apps.core.utils.pagination import StandardPagination
from apps.core.utils.excel import generate_translation_template, parse_translation_file
from apps.core.services.translation import t

from apps.database.models import Translation, TranslationCategory, Language
from .serializers import (
    TranslationSerializer,
    TranslationCreateSerializer,
    BulkTranslationSerializer,
)


@extend_schema_view(
    list=extend_schema(tags=['Admin - Translations']),
    create=extend_schema(tags=['Admin - Translations']),
    retrieve=extend_schema(tags=['Admin - Translations']),
    update=extend_schema(tags=['Admin - Translations']),
    partial_update=extend_schema(tags=['Admin - Translations']),
    destroy=extend_schema(tags=['Admin - Translations']),
)
class TranslationViewSet(TranslatedViewSet):

    queryset = Translation.objects.select_related(
        'category', 'language', 'verified_by'
    ).all().order_by('-created_at')

    permission_classes = [IsAdmin]
    pagination_class = StandardPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend]
    search_fields = ['key', 'value', 'context']
    ordering_fields = ['created_at', 'updated_at']
    filterset_fields = ['category', 'language', 'is_verified']

    # Translation keys
    list_message    = 'admin.translations_retrieved'
    create_message  = 'admin.translation_created'
    update_message  = 'admin.translation_updated'
    destroy_message = 'admin.translation_deleted'

    def get_serializer_class(self):
        if self.action == 'create':
            return TranslationCreateSerializer
        return TranslationSerializer

    def create(self, request, *args, **kwargs):
        """Override to return full TranslationSerializer after create."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        translation = serializer.save()
        return StandardResponse.success(
            data=TranslationSerializer(translation).data,
            message=t(self.create_message, self.get_language()),
            status_code=status.HTTP_201_CREATED
        )

    @extend_schema(tags=['Admin - Translations'])
    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        """Mark translation as verified."""
        translation = self.get_object()
        translation.is_verified = True
        translation.verified_by = request.user
        translation.verified_at = timezone.now()
        translation.save()
        return StandardResponse.success(
            data=self.get_serializer(translation).data,
            message=t('admin.translation_verified', self.get_language())
        )

    @extend_schema(
        tags=['Admin - Translations'],
        request={'application/json': {'type': 'object', 'properties': {'ids': {'type': 'array', 'items': {'type': 'integer'}}}, 'required': ['ids']}},
    )
    @action(detail=False, methods=['post'], url_path='bulk-verify')
    def bulk_verify(self, request):
        """Mark multiple translations as verified. Body: { ids: [1, 2, 3] }"""
        ids = request.data.get('ids', [])
        if not ids or not isinstance(ids, list):
            return StandardResponse.error('ids must be a non-empty list.', status_code=status.HTTP_400_BAD_REQUEST)

        updated = Translation.objects.filter(pk__in=ids).update(
            is_verified=True,
            verified_by=request.user,
            verified_at=timezone.now(),
        )
        return StandardResponse.success(
            data={'verified': updated},
            message=f'{updated} translation(s) marked as verified.',
        )

    @extend_schema(
        tags=['Admin - Translations'],
        request={'application/json': {'type': 'object', 'properties': {'ids': {'type': 'array', 'items': {'type': 'integer'}}}, 'required': ['ids']}},
    )
    @action(detail=False, methods=['post'], url_path='bulk-delete')
    def bulk_delete(self, request):
        """Delete multiple translations. Body: { ids: [1, 2, 3] }"""
        ids = request.data.get('ids', [])
        if not ids or not isinstance(ids, list):
            return StandardResponse.error('ids must be a non-empty list.', status_code=status.HTTP_400_BAD_REQUEST)

        deleted, _ = Translation.objects.filter(pk__in=ids).delete()
        return StandardResponse.success(
            data={'deleted': deleted},
            message=f'{deleted} translation(s) deleted.',
        )

    @extend_schema(tags=['Admin - Translations'])
    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        """Create multiple translations at once."""
        serializer = BulkTranslationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        category = serializer.validated_data['category']
        language = serializer.validated_data['language']
        translations_data = serializer.validated_data['translations']

        created_count = 0
        skipped_count = 0
        created_translations = []

        for trans_data in translations_data:
            if Translation.objects.filter(
                category=category,
                key=trans_data['key'],
                language=language
            ).exists():
                skipped_count += 1
                continue

            translation = Translation.objects.create(
                category=category,
                key=trans_data['key'],
                language=language,
                value=trans_data['value'],
                context=trans_data.get('context', ''),
                is_verified=False
            )
            created_translations.append(translation)
            created_count += 1

        return StandardResponse.success(
            data={
                'created': created_count,
                'skipped': skipped_count,
                'translations': TranslationSerializer(created_translations, many=True).data
            },
            message=t('admin.bulk_translations_created', self.get_language()),
            status_code=status.HTTP_201_CREATED
        )

    @extend_schema(
        tags=['Admin - Translations'],
        parameters=[
            OpenApiParameter(
                name='language_code',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Target language code (e.g. 'ta', 'ml', 'hi')",
            ),
            OpenApiParameter(
                name='category_code',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Filter by category code (e.g. 'auth', 'common'). Leave blank for all categories.",
            ),
            OpenApiParameter(
                name='file_format',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                description="File format: 'xlsx' (default) or 'csv'",
                enum=['xlsx', 'csv'],
            ),
        ],
        responses={200: OpenApiTypes.BINARY},
    )
    @action(detail=False, methods=['get'])
    def export(self, request):
        """
        Download translation template for a specific language.

        Only returns keys that don't have a translation yet for that language.

        Query params:
            language_code: required — e.g. 'ta'
            category_code: optional — e.g. 'auth' (blank = all categories)
            file_format: optional — 'xlsx' (default) or 'csv'
        """
        language_code = request.query_params.get('language_code')
        category_code = request.query_params.get('category_code')
        file_format = request.query_params.get('file_format', 'xlsx').lower()

        if not language_code:
            return StandardResponse.error(
                message="language_code is required",
                status_code=status.HTTP_400_BAD_REQUEST
            )

        # Validate language
        try:
            language = Language.objects.get(code=language_code, is_active=True)
        except Language.DoesNotExist:
            return StandardResponse.error(
                message=f"Language '{language_code}' not found or inactive",
                status_code=status.HTTP_400_BAD_REQUEST
            )

        # Get all existing keys for this language
        existing_keys = set(
            Translation.objects.filter(language=language)
            .values_list('category__code', 'key')
        )

        # Build queryset for keys that need translation
        qs = Translation.objects.filter(
            language__code='en'  # use English as source
        ).select_related('category', 'language').order_by('category__code', 'key')

        if category_code:
            qs = qs.filter(category__code=category_code)

        include_category = not bool(category_code)

        # Build keys_data — only keys missing for target language
        keys_data = []
        for trans in qs:
            if (trans.category.code, trans.key) not in existing_keys:
                keys_data.append({
                    'category': trans.category.code,
                    'key': trans.key,
                    'context': trans.context or '',
                    'english_value': trans.value,
                })

        if not keys_data:
            return StandardResponse.success(
                message=f"All translations for '{language.name}' are already complete.",
                data={'total_keys': 0}
            )

        # Generate file
        buffer = generate_translation_template(
            keys_data=keys_data,
            language_name=language.name,
            include_category=include_category,
            format=file_format
        )

        # Build filename
        cat_part = f"_{category_code}" if category_code else "_all"
        filename = f"translations_{language_code}{cat_part}.{file_format}"

        # Return file response
        if file_format == 'csv':
            content_type = 'text/csv'
        else:
            content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

        response = HttpResponse(buffer.read(), content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    @extend_schema(
        tags=['Admin - Translations'],
        request={
            'multipart/form-data': {
                'type': 'object',
                'properties': {
                    'file': {'type': 'string', 'format': 'binary', 'description': '.xlsx or .csv translation file'},
                    'language_code': {'type': 'string', 'description': "Target language code (e.g. 'ta')"},
                    'category_code': {'type': 'string', 'description': "Category code — if blank, reads from file"},
                    'overwrite': {'type': 'string', 'enum': ['true', 'false'], 'description': "Update existing translations (default: false)"},
                },
                'required': ['file', 'language_code'],
            }
        },
    )
    @action(detail=False, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def import_file(self, request):
        """
        Upload filled translation file (Excel or CSV).

        Form data:
            file: .xlsx or .csv file
            language_code: required — e.g. 'ta'
            category_code: optional — if blank, reads category from file
            overwrite: optional — 'true' to update existing translations (default: false)
        """
        lang = self.get_language()

        # Validate inputs
        uploaded_file = request.FILES.get('file')
        language_code = request.data.get('language_code')
        category_code = request.data.get('category_code') or None
        overwrite = request.data.get('overwrite', 'false').lower() == 'true'

        if not uploaded_file:
            return StandardResponse.error(
                message="No file uploaded.",
                status_code=status.HTTP_400_BAD_REQUEST
            )

        if not language_code:
            return StandardResponse.error(
                message="language_code is required.",
                status_code=status.HTTP_400_BAD_REQUEST
            )

        # Validate language
        try:
            language = Language.objects.get(code=language_code, is_active=True)
        except Language.DoesNotExist:
            return StandardResponse.error(
                message=f"Language '{language_code}' not found or inactive.",
                status_code=status.HTTP_400_BAD_REQUEST
            )

        # Validate category if provided
        if category_code:
            try:
                TranslationCategory.objects.get(code=category_code)
            except TranslationCategory.DoesNotExist:
                return StandardResponse.error(
                    message=f"Category '{category_code}' not found.",
                    status_code=status.HTTP_400_BAD_REQUEST
                )

        # Parse file
        try:
            rows, parse_errors = parse_translation_file(
                file=uploaded_file,
                language_code=language_code,
                category_code=category_code
            )
        except ValueError as e:
            return StandardResponse.error(
                message=str(e),
                status_code=status.HTTP_400_BAD_REQUEST
            )

        if not rows:
            return StandardResponse.error(
                message="No valid translations found in file.",
                data={'parse_errors': parse_errors},
                status_code=status.HTTP_400_BAD_REQUEST
            )

        # Process each row
        created_count = 0
        skipped_count = 0
        updated_count = 0
        row_errors = list(parse_errors)

        for item in rows:
            # Validate category exists
            try:
                category = TranslationCategory.objects.get(code=item['category'])
            except TranslationCategory.DoesNotExist:
                row_errors.append({
                    'key': item['key'],
                    'reason': f"Category '{item['category']}' not found"
                })
                continue

            existing = Translation.objects.filter(
                category=category,
                key=item['key'],
                language=language
            ).first()

            if existing:
                if overwrite:
                    existing.value = item['value']
                    existing.is_verified = False
                    existing.save()
                    updated_count += 1
                else:
                    skipped_count += 1
            else:
                Translation.objects.create(
                    category=category,
                    key=item['key'],
                    language=language,
                    value=item['value'],
                    is_verified=False
                )
                created_count += 1

        return StandardResponse.success(
            data={
                'created': created_count,
                'updated': updated_count,
                'skipped': skipped_count,
                'errors': row_errors,
            },
            message=t('admin.bulk_translations_created', lang),
            status_code=status.HTTP_201_CREATED
        )
