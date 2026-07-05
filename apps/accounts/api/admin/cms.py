"""
Admin — Site Content CMS
==========================
Site Blocks:
  GET   /api/admin/site-content/            — list all blocks (raw JSON or filtered by ?lang=)
  GET   /api/admin/site-content/{key}/      — single block
  PATCH /api/admin/site-content/{key}/      — update content

Announcements:
  GET/POST         /api/admin/announcements/
  GET/PATCH/DELETE /api/admin/announcements/{id}/

FAQs:
  GET/POST         /api/admin/faqs/
  GET/PATCH/DELETE /api/admin/faqs/{id}/

Language keys in content JSON are validated against the active Language table.
Pass ?lang=ml to GET endpoints to receive resolved text + available_languages instead of raw JSON.
"""

import json

from django.core.cache import cache

from drf_spectacular.utils import extend_schema, extend_schema_field, OpenApiExample, OpenApiTypes, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.utils.constants import UserRole
from apps.core.utils.pagination import StandardPagination
from apps.core.utils.responses import StandardResponse
from apps.database.models.cms import (
    SiteBlock, Announcement, AnnouncementCategory, FAQ, FAQCategory,
    QuickLink, NewsSource, NewsSourceCategory, TeamMember, GalleryPhoto, DocumentLibrary,
    Feedback, FeedbackStatus,
)
from apps.database.models.language import Language


def _is_admin(user):
    return user.groups.filter(name__in=[UserRole.SUPER_ADMIN, UserRole.SUB_ADMIN]).exists()


def _active_language_codes():
    return {lang['code'] for lang in Language.get_active_languages()}


def _default_language_code():
    lang = Language.get_default()
    return lang.code if lang else 'en'


def _validate_multilingual_field(value, field_name):
    """Validate that the dict has the default language key and all keys are active language codes."""
    if not isinstance(value, dict):
        raise serializers.ValidationError(f'{field_name} must be a JSON object: {{"en": "...", "ml": "..."}}')
    default_code = _default_language_code()
    if default_code not in value or not value[default_code]:
        raise serializers.ValidationError(
            f'{field_name} must include the default language "{default_code}".'
        )
    active_codes = _active_language_codes()
    invalid = [k for k in value if k not in active_codes]
    if invalid:
        raise serializers.ValidationError(
            f'Invalid language codes: {invalid}. Active languages: {sorted(active_codes)}'
        )
    return value


def _resolve_multilingual(content, lang):
    """Return resolved text + available_languages list for a given content dict."""
    available = [k for k, v in content.items() if v]
    text = content.get(lang) or content.get('en', '')
    return {'content': text, 'available_languages': available}


# ─── Site Blocks ─────────────────────────────────────────────────────────────

class SiteBlockSerializer(serializers.ModelSerializer):
    class Meta:
        model  = SiteBlock
        fields = ['block_key', 'content', 'is_active', 'updated_at']
        read_only_fields = ['block_key', 'updated_at']

    def validate_content(self, value):
        return _validate_multilingual_field(value, 'content')


class SiteBlockListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['Admin - CMS'],
        summary='List all site content blocks',
        description=(
            'Returns all site blocks with raw JSON content.\n\n'
            'Pass `?lang=ml` to get resolved text per block instead of raw JSON.\n'
            'Resolved response includes `available_languages` so admin knows which translations exist.'
        ),
    )
    def get(self, request):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        blocks = SiteBlock.objects.all().order_by('block_key')
        lang = request.query_params.get('lang')

        if lang:
            data = {}
            for b in blocks:
                data[b.block_key] = {
                    'is_active': b.is_active,
                    **_resolve_multilingual(b.content, lang),
                }
            return StandardResponse.success(data=data)

        return StandardResponse.success(data=SiteBlockSerializer(blocks, many=True).data)


class SiteBlockDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, key):
        try:
            return SiteBlock.objects.get(block_key=key)
        except SiteBlock.DoesNotExist:
            return None

    @extend_schema(
        tags=['Admin - CMS'],
        summary='Retrieve a site content block',
        description='Pass `?lang=ml` to get resolved text + available_languages instead of raw JSON.',
    )
    def get(self, request, key):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        block = self._get(key)
        if not block:
            return StandardResponse.error('Block not found.', status_code=status.HTTP_404_NOT_FOUND)

        lang = request.query_params.get('lang')
        if lang:
            data = {
                'block_key': block.block_key,
                'is_active': block.is_active,
                **_resolve_multilingual(block.content, lang),
            }
            return StandardResponse.success(data=data)

        return StandardResponse.success(data=SiteBlockSerializer(block).data)

    @extend_schema(
        tags=['Admin - CMS'],
        summary='Update a site content block',
        description=(
            'Send `{"content": {"en": "...", "ml": "..."}}` to update text.\n\n'
            'Language keys must match active languages in the Language table.\n'
            'English (`en`) is required. Other languages are optional.'
        ),
    )
    def patch(self, request, key):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        block = self._get(key)
        if not block:
            return StandardResponse.error('Block not found.', status_code=status.HTTP_404_NOT_FOUND)
        serializer = SiteBlockSerializer(block, data=request.data, partial=True)
        if not serializer.is_valid():
            return StandardResponse.error('Validation failed.', errors=serializer.errors,
                                          status_code=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        cache.delete_pattern('public:site_content:*')
        cache.delete_pattern(f'public:site_content_detail:*:{key}')
        return StandardResponse.success(data=SiteBlockSerializer(block).data, message='Block updated.')


# ─── Announcements ────────────────────────────────────────────────────────────

class AnnouncementSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Announcement
        fields = [
            'id', 'title', 'body', 'category', 'published_date',
            'is_active', 'order', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_title(self, value):
        return _validate_multilingual_field(value, 'title')

    def validate_body(self, value):
        return _validate_multilingual_field(value, 'body')


def _serialize_announcement(obj, lang=None):
    if not lang:
        return AnnouncementSerializer(obj).data
    return {
        'id':               obj.id,
        'category':         obj.category,
        'published_date':   obj.published_date,
        'is_active':        obj.is_active,
        'order':            obj.order,
        'title':            _resolve_multilingual(obj.title, lang),
        'body':             _resolve_multilingual(obj.body, lang),
    }


class AnnouncementListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['Admin - CMS'],
        summary='List announcements',
        description='Pass `?lang=ml` to get resolved text + available_languages per field.',
    )
    def get(self, request):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        qs = Announcement.objects.all()
        category = request.query_params.get('category')
        if category:
            qs = qs.filter(category=category)
        search = request.query_params.get('search', '').strip()  # ← add here
        if search:
            qs = qs.filter(title__en__icontains=search) | qs.filter(title__ml__icontains=search)
        lang = request.query_params.get('lang')
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        data = [_serialize_announcement(obj, lang) for obj in page]
        return paginator.get_paginated_response(data)

    @extend_schema(
        tags=['Admin - CMS'],
        summary='Create an announcement',
        description=(
            '`title` and `body` must be multilingual objects — **not flat strings**.\n\n'
            '```json\n'
            '{\n'
            '  "title": { "en": "New Announcement", "ml": "പുതിയ അറിയിപ്പ്" },\n'
            '  "body":  { "en": "Body text here", "ml": "വിവരണം ഇവിടെ" },\n'
            '  "category": "announcement",\n'
            '  "published_date": "2026-06-17",\n'
            '  "is_active": true,\n'
            '  "order": 1\n'
            '}\n'
            '```\n\n'
            '`title.en` and `body.en` are required. Malayalam and other active languages are optional.\n'
            'Language keys must exist in the Language table — invalid codes are rejected.'
        ),
        request=AnnouncementSerializer,
    )
    def post(self, request):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        serializer = AnnouncementSerializer(data=request.data)
        if not serializer.is_valid():
            return StandardResponse.error('Validation failed.', errors=serializer.errors,
                                          status_code=status.HTTP_400_BAD_REQUEST)
        obj = serializer.save()
        cache.delete_pattern('public:announcements:*')
        return StandardResponse.success(data=AnnouncementSerializer(obj).data,
                                        message='Announcement created.',
                                        status_code=status.HTTP_201_CREATED)


class AnnouncementDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, pk):
        try:
            return Announcement.objects.get(pk=pk)
        except Announcement.DoesNotExist:
            return None

    @extend_schema(
        tags=['Admin - CMS'],
        summary='Retrieve an announcement',
        description='Pass `?lang=ml` to get resolved text + available_languages.',
    )
    def get(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        obj = self._get(pk)
        if not obj:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        lang = request.query_params.get('lang')
        return StandardResponse.success(data=_serialize_announcement(obj, lang))

    @extend_schema(
        tags=['Admin - CMS'],
        summary='Update an announcement',
        description=(
            'Send only the fields you want to update.\n\n'
            'To add Malayalam to an existing announcement:\n'
            '```json\n'
            '{ "title": { "en": "Existing title", "ml": "മലയാളം തലക്കെട്ട്" } }\n'
            '```\n'
            'Always include `en` when updating multilingual fields.'
        ),
    )
    def patch(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        obj = self._get(pk)
        if not obj:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        serializer = AnnouncementSerializer(obj, data=request.data, partial=True)
        if not serializer.is_valid():
            return StandardResponse.error('Validation failed.', errors=serializer.errors,
                                          status_code=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        cache.delete_pattern('public:announcements:*')
        return StandardResponse.success(data=AnnouncementSerializer(obj).data, message='Updated.')

    @extend_schema(tags=['Admin - CMS'], summary='Delete an announcement')
    def delete(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        obj = self._get(pk)
        if not obj:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        obj.delete()
        cache.delete_pattern('public:announcements:*')
        return StandardResponse.success(message='Deleted.')


# ─── FAQs ────────────────────────────────────────────────────────────────────

class FAQSerializer(serializers.ModelSerializer):
    class Meta:
        model  = FAQ
        fields = ['id', 'question', 'answer', 'category', 'order', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_question(self, value):
        return _validate_multilingual_field(value, 'question')

    def validate_answer(self, value):
        return _validate_multilingual_field(value, 'answer')


def _serialize_faq(obj, lang=None):
    if not lang:
        return FAQSerializer(obj).data
    return {
        'id':       obj.id,
        'category': obj.category,
        'order':    obj.order,
        'is_active': obj.is_active,
        'question': _resolve_multilingual(obj.question, lang),
        'answer':   _resolve_multilingual(obj.answer, lang),
    }


class FAQListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['Admin - CMS'],
        summary='List FAQs',
        description='Pass `?lang=ml` to get resolved text + available_languages per field.',
    )
    def get(self, request):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        qs = FAQ.objects.all()
        category = request.query_params.get('category')
        if category:
            qs = qs.filter(category=category)
        search = request.query_params.get('search', '').strip()  # ← add here
        if search:
            qs = qs.filter(question__en__icontains=search) | qs.filter(question__ml__icontains=search)
        lang = request.query_params.get('lang')
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        data = [_serialize_faq(obj, lang) for obj in page]
        return paginator.get_paginated_response(data)

    @extend_schema(
        tags=['Admin - CMS'],
        summary='Create a FAQ',
        description=(
            '`question` and `answer` must be multilingual objects — **not flat strings**.\n\n'
            '```json\n'
            '{\n'
            '  "question": { "en": "What is an FPO?", "ml": "FPO എന്താണ്?" },\n'
            '  "answer":   { "en": "A Farmer Producer...", "ml": "കർഷക ഉൽപാദക..." },\n'
            '  "category": "fpo_general",\n'
            '  "order": 1,\n'
            '  "is_active": true\n'
            '}\n'
            '```\n\n'
            '`question.en` and `answer.en` are required. Other active languages are optional.\n'
            'Language keys must exist in the Language table — invalid codes are rejected.'
        ),
    )
    def post(self, request):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        serializer = FAQSerializer(data=request.data)
        if not serializer.is_valid():
            return StandardResponse.error('Validation failed.', errors=serializer.errors,
                                          status_code=status.HTTP_400_BAD_REQUEST)
        obj = serializer.save()
        cache.delete_pattern('public:faqs:*')
        return StandardResponse.success(data=FAQSerializer(obj).data,
                                        message='FAQ created.',
                                        status_code=status.HTTP_201_CREATED)


class FAQDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, pk):
        try:
            return FAQ.objects.get(pk=pk)
        except FAQ.DoesNotExist:
            return None

    @extend_schema(
        tags=['Admin - CMS'],
        summary='Retrieve a FAQ',
        description='Pass `?lang=ml` to get resolved text + available_languages.',
    )
    def get(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        obj = self._get(pk)
        if not obj:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        lang = request.query_params.get('lang')
        return StandardResponse.success(data=_serialize_faq(obj, lang))

    @extend_schema(tags=['Admin - CMS'], summary='Update a FAQ')
    def patch(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        obj = self._get(pk)
        if not obj:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        serializer = FAQSerializer(obj, data=request.data, partial=True)
        if not serializer.is_valid():
            return StandardResponse.error('Validation failed.', errors=serializer.errors,
                                          status_code=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        cache.delete_pattern('public:faqs:*')
        return StandardResponse.success(data=FAQSerializer(obj).data, message='Updated.')

    @extend_schema(tags=['Admin - CMS'], summary='Delete a FAQ')
    def delete(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        obj = self._get(pk)
        if not obj:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        obj.delete()
        cache.delete_pattern('public:faqs:*')
        return StandardResponse.success(message='Deleted.')


# =============================================================================
# QUICK LINKS
# =============================================================================

_LOGO_ALLOWED_MIME  = {'image/jpeg', 'image/png', 'image/webp', 'image/svg+xml'}
_PHOTO_ALLOWED_MIME = {'image/jpeg', 'image/png', 'image/webp'}
_LOGO_MAX_SIZE      = 5 * 1024 * 1024   # 5 MB raw upload limit
_PHOTO_MAX_SIZE     = 10 * 1024 * 1024  # 10 MB raw upload limit
_LOGO_MAX_DIM       = 400               # resize to max 400×400 px
_PHOTO_MAX_DIM      = 1200              # resize to max 1200×1200 px
_LOGO_QUALITY       = 85                # JPEG/WebP compression quality
_PHOTO_QUALITY      = 85


def _compress_logo(file):
    """Resize and compress an uploaded logo. SVGs are passed through unchanged."""
    import magic
    import io
    from PIL import Image
    from django.core.files.uploadedfile import InMemoryUploadedFile

    mime = magic.from_buffer(file.read(2048), mime=True)
    file.seek(0)

    if mime not in _LOGO_ALLOWED_MIME:
        raise serializers.ValidationError(
            f'Only JPG, PNG, WebP, and SVG logos are allowed. Got: {mime}'
        )

    if mime == 'image/svg+xml':
        return file  # SVGs are vector — no compression needed

    img = Image.open(file)
    if img.mode not in ('RGB', 'RGBA'):
        img = img.convert('RGB')

    img.thumbnail((_LOGO_MAX_DIM, _LOGO_MAX_DIM), Image.LANCZOS)

    output = io.BytesIO()
    save_format = 'PNG' if mime == 'image/png' else 'JPEG'
    img.save(output, format=save_format, quality=_LOGO_QUALITY, optimize=True)
    output.seek(0)

    ext = '.png' if save_format == 'PNG' else '.jpg'
    return InMemoryUploadedFile(
        output, 'ImageField',
        file.name.rsplit('.', 1)[0] + ext,
        f'image/{"png" if save_format == "PNG" else "jpeg"}',
        output.getbuffer().nbytes,
        None,
    )


def _compress_photo(file):
    """Resize and compress a gallery photo (JPG/PNG/WebP only, max 10 MB)."""
    import magic
    import io
    from PIL import Image
    from django.core.files.uploadedfile import InMemoryUploadedFile

    if file.size > _PHOTO_MAX_SIZE:
        raise serializers.ValidationError('Photo must not exceed 10 MB.')

    mime = magic.from_buffer(file.read(2048), mime=True)
    file.seek(0)

    if mime not in _PHOTO_ALLOWED_MIME:
        raise serializers.ValidationError(
            f'Only JPG, PNG, and WebP photos are allowed. Got: {mime}'
        )

    img = Image.open(file)
    if img.mode not in ('RGB', 'RGBA'):
        img = img.convert('RGB')

    img.thumbnail((_PHOTO_MAX_DIM, _PHOTO_MAX_DIM), Image.LANCZOS)

    output = io.BytesIO()
    save_format = 'PNG' if mime == 'image/png' else 'JPEG'
    img.save(output, format=save_format, quality=_PHOTO_QUALITY, optimize=True)
    output.seek(0)

    ext = '.png' if save_format == 'PNG' else '.jpg'
    return InMemoryUploadedFile(
        output, 'ImageField',
        file.name.rsplit('.', 1)[0] + ext,
        f'image/{"png" if save_format == "PNG" else "jpeg"}',
        output.getbuffer().nbytes,
        None,
    )


class QuickLinkSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model  = QuickLink
        fields = ['id', 'name', 'url', 'logo', 'logo_url', 'is_active', 'created_at']
        extra_kwargs = {
            'logo':      {'write_only': True, 'required': True},
            'is_active': {'default': True},
        }

    def get_logo_url(self, obj):
        request = self.context.get('request')
        if obj.logo and request:
            return request.build_absolute_uri(obj.logo.url)
        return obj.logo.url if obj.logo else None

    def validate_logo(self, file):
        if file.size > _LOGO_MAX_SIZE:
            raise serializers.ValidationError('Logo must not exceed 5 MB.')
        return _compress_logo(file)


class QuickLinkListView(APIView):

    @extend_schema(
        tags=['Admin - CMS'],
        summary='List all quick links',
        responses={200: QuickLinkSerializer(many=True)},
    )
    def get(self, request):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        qs = QuickLink.objects.all()
        serializer = QuickLinkSerializer(qs, many=True, context={'request': request})
        return StandardResponse.success(serializer.data, 'Quick links retrieved.')

    @extend_schema(
        tags=['Admin - CMS'],
        summary='Create a quick link',
        description='Multipart form: `name`, `url`, `logo` (image file), `is_active` (optional).',
        request=QuickLinkSerializer,
        responses={201: QuickLinkSerializer},
    )
    def post(self, request):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        serializer = QuickLinkSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return StandardResponse.error('Validation failed.', errors=serializer.errors,
                                          status_code=status.HTTP_400_BAD_REQUEST)
        obj = serializer.save()
        cache.delete('public:quick_links')
        return StandardResponse.created(
            data=QuickLinkSerializer(obj, context={'request': request}).data,
            message='Quick link created.',
        )


class QuickLinkDetailView(APIView):

    def _get(self, pk):
        try:
            return QuickLink.objects.get(pk=pk)
        except QuickLink.DoesNotExist:
            return None

    @extend_schema(tags=['Admin - CMS'], summary='Update a quick link',
                   description='Multipart form — all fields optional (partial update).',
                   request=QuickLinkSerializer, responses={200: QuickLinkSerializer})
    def patch(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        obj = self._get(pk)
        if not obj:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        serializer = QuickLinkSerializer(obj, data=request.data, partial=True,
                                         context={'request': request})
        if not serializer.is_valid():
            return StandardResponse.error('Validation failed.', errors=serializer.errors,
                                          status_code=status.HTTP_400_BAD_REQUEST)
        obj = serializer.save()
        cache.delete('public:quick_links')
        return StandardResponse.success(
            data=QuickLinkSerializer(obj, context={'request': request}).data,
            message='Updated.',
        )

    @extend_schema(tags=['Admin - CMS'], summary='Delete a quick link')
    def delete(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        obj = self._get(pk)
        if not obj:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        if obj.logo:
            obj.logo.delete(save=False)
        obj.delete()
        cache.delete('public:quick_links')
        return StandardResponse.success(message='Deleted.')


class QuickLinkLogoDeleteView(APIView):

    @extend_schema(tags=['Admin - CMS'], summary='Delete logo from a quick link',
                   description='Removes the logo file from storage. The quick link record remains. Upload a new logo via PATCH.')
    def delete(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        try:
            obj = QuickLink.objects.get(pk=pk)
        except QuickLink.DoesNotExist:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        if not obj.logo:
            return StandardResponse.error('No logo to delete.', status_code=status.HTTP_400_BAD_REQUEST)
        obj.logo.delete(save=False)
        obj.logo = None
        obj.save(update_fields=['logo'])
        cache.delete('public:quick_links')
        return StandardResponse.success(message='Logo deleted.')


class QuickLinkActivateView(APIView):

    @extend_schema(tags=['Admin - CMS'], summary='Activate a quick link')
    def post(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        try:
            obj = QuickLink.objects.get(pk=pk)
        except QuickLink.DoesNotExist:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        obj.is_active = True
        obj.save(update_fields=['is_active'])
        cache.delete('public:quick_links')
        return StandardResponse.success(message='Activated.')


class QuickLinkDeactivateView(APIView):

    @extend_schema(tags=['Admin - CMS'], summary='Deactivate a quick link')
    def post(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        try:
            obj = QuickLink.objects.get(pk=pk)
        except QuickLink.DoesNotExist:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        obj.is_active = False
        obj.save(update_fields=['is_active'])
        cache.delete('public:quick_links')
        return StandardResponse.success(message='Deactivated.')


# =============================================================================
# NEWS SOURCES
# =============================================================================

class NewsSourceSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model  = NewsSource
        fields = ['id', 'name', 'url', 'logo', 'logo_url', 'category', 'is_active', 'created_at']
        extra_kwargs = {
            'logo':      {'write_only': True, 'required': False},
            'is_active': {'default': True},
        }

    def get_logo_url(self, obj):
        request = self.context.get('request')
        if obj.logo and request:
            return request.build_absolute_uri(obj.logo.url)
        return obj.logo.url if obj.logo else None

    def validate_logo(self, file):
        if file.size > _LOGO_MAX_SIZE:
            raise serializers.ValidationError('Logo must not exceed 5 MB.')
        return _compress_logo(file)


class NewsSourceListView(APIView):

    @extend_schema(
        tags=['Admin - CMS'],
        summary='List all news sources',
        responses={200: NewsSourceSerializer(many=True)},
    )
    def get(self, request):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        qs = NewsSource.objects.filter(is_deleted=False)
        serializer = NewsSourceSerializer(qs, many=True, context={'request': request})
        return StandardResponse.success(serializer.data, 'News sources retrieved.')

    @extend_schema(
        tags=['Admin - CMS'],
        summary='Create a news source',
        description='Multipart form: `name`, `url`, `category` (newspaper/magazine), `logo` (optional image), `is_active` (optional).',
        request=NewsSourceSerializer,
        responses={201: NewsSourceSerializer},
    )
    def post(self, request):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        serializer = NewsSourceSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return StandardResponse.error('Validation failed.', errors=serializer.errors,
                                          status_code=status.HTTP_400_BAD_REQUEST)
        obj = serializer.save(created_by=request.user)
        cache.delete('public:news_sources')
        return StandardResponse.created(
            data=NewsSourceSerializer(obj, context={'request': request}).data,
            message='News source created.',
        )


class NewsSourceDetailView(APIView):

    def _get(self, pk):
        try:
            return NewsSource.objects.get(pk=pk, is_deleted=False)
        except NewsSource.DoesNotExist:
            return None

    @extend_schema(tags=['Admin - CMS'], summary='Update a news source',
                   request=NewsSourceSerializer, responses={200: NewsSourceSerializer})
    def patch(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        obj = self._get(pk)
        if not obj:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        serializer = NewsSourceSerializer(obj, data=request.data, partial=True,
                                          context={'request': request})
        if not serializer.is_valid():
            return StandardResponse.error('Validation failed.', errors=serializer.errors,
                                          status_code=status.HTTP_400_BAD_REQUEST)
        obj = serializer.save(updated_by=request.user)
        cache.delete('public:news_sources')
        return StandardResponse.success(
            data=NewsSourceSerializer(obj, context={'request': request}).data,
            message='Updated.',
        )

    @extend_schema(tags=['Admin - CMS'], summary='Delete a news source')
    def delete(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        obj = self._get(pk)
        if not obj:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        if obj.logo:
            obj.logo.delete(save=False)
        obj.soft_delete(user=request.user)
        cache.delete('public:news_sources')
        return StandardResponse.success(message='Deleted.')


class NewsSourceLogoDeleteView(APIView):

    @extend_schema(tags=['Admin - CMS'], summary='Delete logo from a news source')
    def delete(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        try:
            obj = NewsSource.objects.get(pk=pk, is_deleted=False)
        except NewsSource.DoesNotExist:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        if not obj.logo:
            return StandardResponse.error('No logo to delete.', status_code=status.HTTP_400_BAD_REQUEST)
        obj.logo.delete(save=False)
        obj.logo = None
        obj.save(update_fields=['logo'])
        cache.delete('public:news_sources')
        return StandardResponse.success(message='Logo deleted.')


class NewsSourceActivateView(APIView):

    @extend_schema(tags=['Admin - CMS'], summary='Activate a news source')
    def post(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        try:
            obj = NewsSource.objects.get(pk=pk, is_deleted=False)
        except NewsSource.DoesNotExist:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        obj.is_active = True
        obj.save(update_fields=['is_active'])
        cache.delete('public:news_sources')
        return StandardResponse.success(message='Activated.')


class NewsSourceDeactivateView(APIView):

    @extend_schema(tags=['Admin - CMS'], summary='Deactivate a news source')
    def post(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        try:
            obj = NewsSource.objects.get(pk=pk, is_deleted=False)
        except NewsSource.DoesNotExist:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        obj.is_active = False
        obj.save(update_fields=['is_active'])
        cache.delete('public:news_sources')
        return StandardResponse.success(message='Deactivated.')


# =============================================================================
# TEAM MEMBERS
# =============================================================================

class TeamMemberSerializer(serializers.ModelSerializer):
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model  = TeamMember
        fields = ['id', 'name', 'designation', 'photo', 'photo_url', 'order', 'is_active', 'created_at']
        extra_kwargs = {
            'photo':     {'write_only': True, 'required': False},
            'is_active': {'default': True},
        }

    def get_photo_url(self, obj):
        request = self.context.get('request')
        if obj.photo and request:
            return request.build_absolute_uri(obj.photo.url)
        return obj.photo.url if obj.photo else None

    def validate_photo(self, file):
        if file.size > _LOGO_MAX_SIZE:
            raise serializers.ValidationError('Photo must not exceed 5 MB.')
        return _compress_logo(file)


class TeamMemberListView(APIView):

    @extend_schema(
        tags=['Admin - CMS'],
        summary='List all team members',
        responses={200: TeamMemberSerializer(many=True)},
    )
    def get(self, request):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        qs = TeamMember.objects.filter(is_deleted=False)
        return StandardResponse.success(
            TeamMemberSerializer(qs, many=True, context={'request': request}).data,
            'Team members retrieved.',
        )

    @extend_schema(
        tags=['Admin - CMS'],
        summary='Create a team member',
        description='Multipart form: `name`, `designation`, `order` (optional), `photo` (optional image), `is_active` (optional).',
        request=TeamMemberSerializer,
        responses={201: TeamMemberSerializer},
    )
    def post(self, request):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        serializer = TeamMemberSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return StandardResponse.error('Validation failed.', errors=serializer.errors,
                                          status_code=status.HTTP_400_BAD_REQUEST)
        obj = serializer.save(created_by=request.user)
        cache.delete('public:team_members')
        return StandardResponse.created(
            data=TeamMemberSerializer(obj, context={'request': request}).data,
            message='Team member created.',
        )


class TeamMemberDetailView(APIView):

    def _get(self, pk):
        try:
            return TeamMember.objects.get(pk=pk, is_deleted=False)
        except TeamMember.DoesNotExist:
            return None

    @extend_schema(tags=['Admin - CMS'], summary='Update a team member',
                   request=TeamMemberSerializer, responses={200: TeamMemberSerializer})
    def patch(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        obj = self._get(pk)
        if not obj:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        serializer = TeamMemberSerializer(obj, data=request.data, partial=True,
                                          context={'request': request})
        if not serializer.is_valid():
            return StandardResponse.error('Validation failed.', errors=serializer.errors,
                                          status_code=status.HTTP_400_BAD_REQUEST)
        obj = serializer.save(updated_by=request.user)
        cache.delete('public:team_members')
        return StandardResponse.success(
            data=TeamMemberSerializer(obj, context={'request': request}).data,
            message='Updated.',
        )

    @extend_schema(tags=['Admin - CMS'], summary='Delete a team member')
    def delete(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        obj = self._get(pk)
        if not obj:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        if obj.photo:
            obj.photo.delete(save=False)
        obj.soft_delete(user=request.user)
        cache.delete('public:team_members')
        return StandardResponse.success(message='Deleted.')


class TeamMemberPhotoDeleteView(APIView):

    @extend_schema(tags=['Admin - CMS'], summary='Delete photo from a team member')
    def delete(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        try:
            obj = TeamMember.objects.get(pk=pk, is_deleted=False)
        except TeamMember.DoesNotExist:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        if not obj.photo:
            return StandardResponse.error('No photo to delete.', status_code=status.HTTP_400_BAD_REQUEST)
        obj.photo.delete(save=False)
        obj.photo = None
        obj.save(update_fields=['photo'])
        cache.delete('public:team_members')
        return StandardResponse.success(message='Photo deleted.')


class TeamMemberActivateView(APIView):

    @extend_schema(tags=['Admin - CMS'], summary='Activate a team member')
    def post(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        try:
            obj = TeamMember.objects.get(pk=pk, is_deleted=False)
        except TeamMember.DoesNotExist:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        obj.is_active = True
        obj.save(update_fields=['is_active'])
        cache.delete('public:team_members')
        return StandardResponse.success(message='Activated.')


class TeamMemberDeactivateView(APIView):

    @extend_schema(tags=['Admin - CMS'], summary='Deactivate a team member')
    def post(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        try:
            obj = TeamMember.objects.get(pk=pk, is_deleted=False)
        except TeamMember.DoesNotExist:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        obj.is_active = False
        obj.save(update_fields=['is_active'])
        cache.delete('public:team_members')
        return StandardResponse.success(message='Deactivated.')


# =============================================================================
# DOCUMENT LIBRARY
# =============================================================================

_DOC_ALLOWED_MIME = {'application/pdf'}
_DOC_MAX_SIZE     = 20 * 1024 * 1024  # 20 MB


class DocumentLibrarySerializer(serializers.ModelSerializer):
    title_display = serializers.SerializerMethodField()
    file_url      = serializers.SerializerMethodField()
    file_size     = serializers.SerializerMethodField()

    class Meta:
        model  = DocumentLibrary
        fields = [
            'id', 'title', 'title_display', 'file', 'file_url', 'file_size',
            'is_view_only', 'order', 'is_active', 'created_at',
        ]
        extra_kwargs = {
            'file':      {'write_only': True, 'required': True},
            'title':     {'required': True},
            'is_active': {'default': True},
        }

    @extend_schema_field(serializers.CharField())
    def get_title_display(self, obj):
        lang = _lang_from_context(self.context)
        return obj.get_title(lang)

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_file_url(self, obj):
        request = self.context.get('request')
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        return obj.file.url if obj.file else None

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_file_size(self, obj):
        try:
            return obj.file.size
        except Exception:
            return None

    def validate_title(self, value):
        if not isinstance(value, dict) or not value.get('en'):
            raise serializers.ValidationError('title must be a JSON object with at least an "en" key.')
        return value

    def validate_file(self, file):
        import magic
        if file.size > _DOC_MAX_SIZE:
            raise serializers.ValidationError('File must not exceed 20 MB.')
        mime = magic.from_buffer(file.read(2048), mime=True)
        file.seek(0)
        if mime not in _DOC_ALLOWED_MIME:
            raise serializers.ValidationError(f'Only PDF files are allowed. Got: {mime}')
        return file


def _lang_from_context(context):
    request = context.get('request')
    if request:
        return getattr(request, 'language', 'en')
    return 'en'


class DocumentLibraryListView(APIView):

    @extend_schema(
        tags=['Admin - CMS'],
        summary='List all documents',
        responses={200: DocumentLibrarySerializer(many=True)},
    )
    def get(self, request):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        qs = DocumentLibrary.objects.filter(is_deleted=False)
        return StandardResponse.success(
            DocumentLibrarySerializer(qs, many=True, context={'request': request}).data,
            'Documents retrieved.',
        )

    @extend_schema(
        tags=['Admin - CMS'],
        summary='Upload a document',
        description=(
            'Multipart form:\n'
            '- `title` — JSON string e.g. `{"en": "FPO User Manual", "ml": "..."}`\n'
            '- `file` — PDF only, max 20 MB\n'
            '- `is_view_only` — true/false (default false)\n'
            '- `order` — display order (default 0)\n'
            '- `is_active` — default true'
        ),
        request=DocumentLibrarySerializer,
        responses={201: DocumentLibrarySerializer},
    )
    def post(self, request):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        title_raw = request.data.get('title', '')
        try:
            title = json.loads(title_raw) if isinstance(title_raw, str) else title_raw
        except ValueError:
            return StandardResponse.error(
                'title must be valid JSON e.g. {"en": "FPO User Manual"}',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        data = {
            'title':        title,
            'file':         request.FILES.get('file'),
            'is_view_only': request.data.get('is_view_only', False),
            'order':        request.data.get('order', 0),
            'is_active':    request.data.get('is_active', True),
        }

        serializer = DocumentLibrarySerializer(data=data, context={'request': request})
        if not serializer.is_valid():
            return StandardResponse.error('Validation failed.', errors=serializer.errors,
                                          status_code=status.HTTP_400_BAD_REQUEST)
        obj = serializer.save(created_by=request.user)
        cache.delete_pattern('public:document_library:*')
        return StandardResponse.created(
            data=DocumentLibrarySerializer(obj, context={'request': request}).data,
            message='Document uploaded.',
        )


class DocumentLibraryDetailView(APIView):

    def _get(self, pk):
        try:
            return DocumentLibrary.objects.get(pk=pk, is_deleted=False)
        except DocumentLibrary.DoesNotExist:
            return None

    @extend_schema(tags=['Admin - CMS'], summary='Update a document',
                   description='PATCH to update title, is_view_only, order, is_active, or replace the file.',
                   request=DocumentLibrarySerializer, responses={200: DocumentLibrarySerializer})
    def patch(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        obj = self._get(pk)
        if not obj:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)

        data = {k: v for k, v in request.data.items()}
        if 'file' in request.FILES:
            data['file'] = request.FILES['file']
        if 'title' in data and isinstance(data['title'], str):
            try:
                data['title'] = json.loads(data['title'])
            except ValueError:
                return StandardResponse.error(
                    'title must be valid JSON.',
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

        serializer = DocumentLibrarySerializer(obj, data=data, partial=True, context={'request': request})
        if not serializer.is_valid():
            return StandardResponse.error('Validation failed.', errors=serializer.errors,
                                          status_code=status.HTTP_400_BAD_REQUEST)
        obj = serializer.save(updated_by=request.user)
        cache.delete_pattern('public:document_library:*')
        return StandardResponse.success(
            data=DocumentLibrarySerializer(obj, context={'request': request}).data,
            message='Updated.',
        )

    @extend_schema(tags=['Admin - CMS'], summary='Delete a document')
    def delete(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        obj = self._get(pk)
        if not obj:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        if obj.file:
            obj.file.delete(save=False)
        obj.soft_delete(user=request.user)
        cache.delete('public:document_library')
        return StandardResponse.success(message='Deleted.')


class DocumentLibraryActivateView(APIView):

    @extend_schema(tags=['Admin - CMS'], summary='Activate a document')
    def post(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        try:
            obj = DocumentLibrary.objects.get(pk=pk, is_deleted=False)
        except DocumentLibrary.DoesNotExist:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        obj.is_active = True
        obj.save(update_fields=['is_active'])
        cache.delete_pattern('public:document_library:*')
        return StandardResponse.success(message='Activated.')


class DocumentLibraryDeactivateView(APIView):

    @extend_schema(tags=['Admin - CMS'], summary='Deactivate a document')
    def post(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        try:
            obj = DocumentLibrary.objects.get(pk=pk, is_deleted=False)
        except DocumentLibrary.DoesNotExist:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        obj.is_active = False
        obj.save(update_fields=['is_active'])
        cache.delete_pattern('public:document_library:*')
        return StandardResponse.success(message='Deactivated.')


# ─────────────────────────────────────────────────────────────────────────────
# Gallery
# ─────────────────────────────────────────────────────────────────────────────

class GalleryPhotoSerializer(serializers.ModelSerializer):
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model  = GalleryPhoto
        fields = ['id', 'photo', 'photo_url', 'caption', 'order', 'is_active', 'created_at']
        extra_kwargs = {
            'photo':      {'write_only': True, 'required': True},
            'caption':    {'required': False, 'default': dict},
            'is_active':  {'default': True},
        }

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_photo_url(self, obj):
        request = self.context.get('request')
        if obj.photo and request:
            return request.build_absolute_uri(obj.photo.url)
        return obj.photo.url if obj.photo else None

    def validate_caption(self, value):
        if value and not isinstance(value, dict):
            raise serializers.ValidationError('caption must be a JSON object e.g. {"en": "...", "ml": "..."}')
        return value


class GalleryListView(APIView):

    @extend_schema(tags=['Admin - CMS'], summary='List gallery photos',
                   responses={200: GalleryPhotoSerializer(many=True)})
    def get(self, request):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        qs = GalleryPhoto.objects.filter(is_deleted=False)
        return StandardResponse.success(
            GalleryPhotoSerializer(qs, many=True, context={'request': request}).data,
            'Gallery retrieved.',
        )

    @extend_schema(
        tags=['Admin - CMS'],
        summary='Upload a gallery photo',
        description=(
            'Multipart form:\n'
            '- `photo` — JPG/PNG/WebP, max 5 MB (auto-compressed to max 1200×800, quality 85)\n'
            '- `caption` — optional JSON string e.g. `{"en": "Opening ceremony", "ml": "..."}`\n'
            '- `order` — display order (default 0)\n'
            '- `is_active` — default true'
        ),
        request=GalleryPhotoSerializer,
        responses={201: GalleryPhotoSerializer},
    )
    def post(self, request):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        caption_raw = request.data.get('caption', '{}')
        try:
            caption = json.loads(caption_raw) if isinstance(caption_raw, str) else caption_raw
        except ValueError:
            return StandardResponse.error(
                'caption must be valid JSON e.g. {"en": "..."}',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        photo_file = request.FILES.get('photo')
        if photo_file:
            try:
                photo_file = _compress_photo(photo_file)
            except serializers.ValidationError as e:
                return StandardResponse.error(str(e.detail[0]), status_code=status.HTTP_400_BAD_REQUEST)

        data = {
            'photo':     photo_file,
            'caption':   caption,
            'order':     request.data.get('order', 0),
            'is_active': request.data.get('is_active', True),
        }

        serializer = GalleryPhotoSerializer(data=data, context={'request': request})
        if not serializer.is_valid():
            return StandardResponse.error('Validation failed.', errors=serializer.errors,
                                          status_code=status.HTTP_400_BAD_REQUEST)
        obj = serializer.save(created_by=request.user)
        cache.delete('public:gallery')
        return StandardResponse.created(
            data=GalleryPhotoSerializer(obj, context={'request': request}).data,
            message='Photo uploaded.',
        )


class GalleryDetailView(APIView):

    def _get(self, pk):
        try:
            return GalleryPhoto.objects.get(pk=pk, is_deleted=False)
        except GalleryPhoto.DoesNotExist:
            return None

    @extend_schema(tags=['Admin - CMS'], summary='Update a gallery photo',
                   request=GalleryPhotoSerializer, responses={200: GalleryPhotoSerializer})
    def patch(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        obj = self._get(pk)
        if not obj:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)

        data = {k: v for k, v in request.data.items()}

        if 'caption' in data and isinstance(data['caption'], str):
            try:
                data['caption'] = json.loads(data['caption'])
            except ValueError:
                return StandardResponse.error('caption must be valid JSON.',
                                              status_code=status.HTTP_400_BAD_REQUEST)

        if 'photo' in request.FILES:
            try:
                data['photo'] = _compress_photo(request.FILES['photo'])
            except serializers.ValidationError as e:
                return StandardResponse.error(str(e.detail[0]), status_code=status.HTTP_400_BAD_REQUEST)

        serializer = GalleryPhotoSerializer(obj, data=data, partial=True, context={'request': request})
        if not serializer.is_valid():
            return StandardResponse.error('Validation failed.', errors=serializer.errors,
                                          status_code=status.HTTP_400_BAD_REQUEST)
        obj = serializer.save(updated_by=request.user)
        cache.delete('public:gallery')
        return StandardResponse.success(
            data=GalleryPhotoSerializer(obj, context={'request': request}).data,
            message='Updated.',
        )

    @extend_schema(tags=['Admin - CMS'], summary='Delete a gallery photo')
    def delete(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        obj = self._get(pk)
        if not obj:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        obj.soft_delete(user=request.user)
        cache.delete('public:gallery')
        return StandardResponse.success(message='Deleted.')


class GalleryActivateView(APIView):

    @extend_schema(tags=['Admin - CMS'], summary='Activate a gallery photo')
    def post(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        try:
            obj = GalleryPhoto.objects.get(pk=pk, is_deleted=False)
        except GalleryPhoto.DoesNotExist:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        obj.is_active = True
        obj.save(update_fields=['is_active'])
        cache.delete('public:gallery')
        return StandardResponse.success(message='Activated.')


class GalleryDeactivateView(APIView):

    @extend_schema(tags=['Admin - CMS'], summary='Deactivate a gallery photo')
    def post(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        try:
            obj = GalleryPhoto.objects.get(pk=pk, is_deleted=False)
        except GalleryPhoto.DoesNotExist:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        obj.is_active = False
        obj.save(update_fields=['is_active'])
        cache.delete('public:gallery')
        return StandardResponse.success(message='Deactivated.')


# ─────────────────────────────────────────────────────────────────────────────
# Feedback Inbox
# ─────────────────────────────────────────────────────────────────────────────

class FeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Feedback
        fields = ['id', 'name', 'email', 'phone', 'subject', 'message', 'status', 'created_at']
        read_only_fields = ['id', 'name', 'email', 'phone', 'subject', 'message', 'created_at']


class FeedbackListView(APIView):

    @extend_schema(
        tags=['Admin - CMS'],
        summary='List feedback submissions',
        description=(
            'Returns all feedback submissions ordered by newest first.\n\n'
            '**Filters:** `?status=unread` / `read` / `resolved`\n\n'
            '**Pagination:** `?page=1&page_size=20` (max 100)'
        ),
        responses={200: FeedbackSerializer(many=True)},
    )
    def get(self, request):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        qs = Feedback.objects.all()
        status_filter = request.query_params.get('status', '').strip()
        if status_filter:
            qs = qs.filter(status=status_filter)

        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        data = FeedbackSerializer(page, many=True).data
        return paginator.get_paginated_response(data)


class FeedbackDetailView(APIView):

    def _get(self, pk):
        try:
            return Feedback.objects.get(pk=pk)
        except Feedback.DoesNotExist:
            return None

    @extend_schema(tags=['Admin - CMS'], summary='Get a single feedback submission',
                   responses={200: FeedbackSerializer})
    def get(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        obj = self._get(pk)
        if not obj:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        return StandardResponse.success(data=FeedbackSerializer(obj).data)

    @extend_schema(
        tags=['Admin - CMS'],
        summary='Update feedback status',
        description='PATCH `status` to `read` or `resolved`.',
        request=FeedbackSerializer,
        responses={200: FeedbackSerializer},
    )
    def patch(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        obj = self._get(pk)
        if not obj:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)

        new_status = request.data.get('status', '').strip()
        if new_status not in FeedbackStatus.values:
            return StandardResponse.error(
                f'status must be one of: {", ".join(FeedbackStatus.values)}',
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        obj.status = new_status
        obj.save(update_fields=['status'])
        return StandardResponse.success(data=FeedbackSerializer(obj).data, message='Status updated.')
