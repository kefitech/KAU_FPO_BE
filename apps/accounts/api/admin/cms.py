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
from urllib.parse import urlparse

from django.core.cache import cache

from drf_spectacular.utils import extend_schema, extend_schema_field, OpenApiExample, OpenApiTypes, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser

from apps.core.utils.constants import UserRole
from apps.core.utils.pagination import StandardPagination
from apps.core.utils.responses import StandardResponse
from apps.database.models.cms import (
    SiteBlock, Announcement, AnnouncementCategory, FAQ, FAQCategory,HeaderLogo,
    QuickLink, KVKLink, Partner, NewsSource, NewsSourceCategory, TeamMember, TeamSection, YoutubePlaylist, GalleryAlbum, GalleryPhoto, DocumentLibrary,
    Feedback, FeedbackStatus,
)
from apps.database.models.language import Language
from apps.core.services.youtube import (
    YOUTUBE_CHANNEL_BLOCK, YouTubeLookupError, extract_playlist_id, fetch_playlist_feed, get_youtube_channel_url,
)


def _is_admin(user):
    return user.groups.filter(name__in=[UserRole.SUPER_ADMIN, UserRole.SUB_ADMIN]).exists()


def _is_super_admin(user):
    # Announcements and FAQs are managed by the super admin only — sub-admins don't need them.
    return user.groups.filter(name=UserRole.SUPER_ADMIN).exists()


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
    category_display = serializers.CharField(source='get_category_display', read_only=True)

    class Meta:
        model  = Announcement
        fields = [
            'id', 'title', 'body', 'category', 'category_display', 'published_date',
            'end_date', 'is_active', 'order', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'category_display', 'created_at', 'updated_at']

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
        if not _is_super_admin(request.user):
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
        if not _is_super_admin(request.user):
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
        if not _is_super_admin(request.user):
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
        if not _is_super_admin(request.user):
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
        if not _is_super_admin(request.user):
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
        if not _is_super_admin(request.user):
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
        if not _is_super_admin(request.user):
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
        if not _is_super_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        obj = self._get(pk)
        if not obj:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        lang = request.query_params.get('lang')
        return StandardResponse.success(data=_serialize_faq(obj, lang))

    @extend_schema(tags=['Admin - CMS'], summary='Update a FAQ')
    def patch(self, request, pk):
        if not _is_super_admin(request.user):
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
        if not _is_super_admin(request.user):
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
        fields = ['id', 'name', 'url', 'logo', 'logo_url', 'end_date', 'is_active', 'order', 'created_at']
        extra_kwargs = {
            'logo':      {'write_only': True, 'required': True},
            'is_active': {'default': True},
            'order':     {'required': False},
            'end_date':  {'required': False, 'allow_null': True},
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


class QuickLinkReorderView(APIView):

    @extend_schema(
        tags=['Admin - CMS'],
        summary='Bulk reorder quick links',
        description=(
            'Accepts `{"items": [{"id": 1, "order": 0}, {"id": 3, "order": 1}, ...]}`. '
            'Updates each row\'s `order` field in a single transaction. '
            'Only ids listed are updated — omitted rows keep their existing order.'
        ),
    )
    def post(self, request):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        items = request.data.get('items') or []
        if not isinstance(items, list) or not items:
            return StandardResponse.error(
                'items must be a non-empty list of {id, order} objects.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        from django.db import transaction as _tx
        try:
            with _tx.atomic():
                for row in items:
                    QuickLink.objects.filter(pk=row['id']).update(order=int(row['order']))
        except (KeyError, TypeError, ValueError):
            return StandardResponse.error(
                'Each item must have an integer id and integer order.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        cache.delete('public:quick_links')
        return StandardResponse.success(message='Order updated.')


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
# KVK LINKS (Krishi Vigyan Kendra directory) — KAU 2026-09-27
# Mirrors QuickLink CRUD. Separate model + endpoints so the /krishi-vigyan-kendra
# public page has its own cache key + admin surface without co-mingling with
# the landing-page Quick Links.
# =============================================================================


class KVKLinkSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model  = KVKLink
        fields = [
            'id', 'name', 'url', 'logo', 'logo_url',
            'district', 'contact_email', 'contact_phone',
            'order', 'is_active', 'created_at',
        ]
        extra_kwargs = {
            'logo':          {'write_only': True, 'required': False, 'allow_null': True},
            'is_active':     {'default': True},
            'order':         {'default': 0},
            'district':      {'required': False, 'allow_blank': True},
            'contact_email': {'required': False, 'allow_blank': True},
            'contact_phone': {'required': False, 'allow_blank': True},
        }

    def get_logo_url(self, obj):
        request = self.context.get('request')
        if obj.logo and request:
            return request.build_absolute_uri(obj.logo.url)
        return obj.logo.url if obj.logo else None

    def validate_logo(self, file):
        if file is None:
            return None
        if file.size > _LOGO_MAX_SIZE:
            raise serializers.ValidationError('Logo must not exceed 5 MB.')
        return _compress_logo(file)


class KVKLinkListView(APIView):

    @extend_schema(
        tags=['Admin - CMS'],
        summary='List all KVK links',
        responses={200: KVKLinkSerializer(many=True)},
    )
    def get(self, request):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        qs = KVKLink.objects.all()
        serializer = KVKLinkSerializer(qs, many=True, context={'request': request})
        return StandardResponse.success(serializer.data, 'KVK links retrieved.')

    @extend_schema(
        tags=['Admin - CMS'],
        summary='Create a KVK link',
        description='Multipart form: `name`, `url`, `logo` (image file), `order` (int), `is_active` (optional).',
        request=KVKLinkSerializer,
        responses={201: KVKLinkSerializer},
    )
    def post(self, request):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        serializer = KVKLinkSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return StandardResponse.error('Validation failed.', errors=serializer.errors,
                                          status_code=status.HTTP_400_BAD_REQUEST)
        obj = serializer.save()
        cache.delete('public:kvk_links')
        return StandardResponse.created(
            data=KVKLinkSerializer(obj, context={'request': request}).data,
            message='KVK link created.',
        )


class KVKLinkDetailView(APIView):

    def _get(self, pk):
        try:
            return KVKLink.objects.get(pk=pk)
        except KVKLink.DoesNotExist:
            return None

    @extend_schema(tags=['Admin - CMS'], summary='Update a KVK link',
                   description='Multipart form — all fields optional (partial update).',
                   request=KVKLinkSerializer, responses={200: KVKLinkSerializer})
    def patch(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        obj = self._get(pk)
        if not obj:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        serializer = KVKLinkSerializer(obj, data=request.data, partial=True,
                                       context={'request': request})
        if not serializer.is_valid():
            return StandardResponse.error('Validation failed.', errors=serializer.errors,
                                          status_code=status.HTTP_400_BAD_REQUEST)
        obj = serializer.save()
        cache.delete('public:kvk_links')
        return StandardResponse.success(
            data=KVKLinkSerializer(obj, context={'request': request}).data,
            message='Updated.',
        )

    @extend_schema(tags=['Admin - CMS'], summary='Delete a KVK link')
    def delete(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        obj = self._get(pk)
        if not obj:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        if obj.logo:
            obj.logo.delete(save=False)
        obj.delete()
        cache.delete('public:kvk_links')
        return StandardResponse.success(message='Deleted.')


class KVKLinkLogoDeleteView(APIView):

    @extend_schema(tags=['Admin - CMS'], summary='Delete logo from a KVK link')
    def delete(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        try:
            obj = KVKLink.objects.get(pk=pk)
        except KVKLink.DoesNotExist:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        if not obj.logo:
            return StandardResponse.error('No logo to delete.', status_code=status.HTTP_400_BAD_REQUEST)
        obj.logo.delete(save=False)
        obj.logo = None
        obj.save(update_fields=['logo'])
        cache.delete('public:kvk_links')
        return StandardResponse.success(message='Logo deleted.')


class KVKLinkActivateView(APIView):

    @extend_schema(tags=['Admin - CMS'], summary='Activate a KVK link')
    def post(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        try:
            obj = KVKLink.objects.get(pk=pk)
        except KVKLink.DoesNotExist:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        obj.is_active = True
        obj.save(update_fields=['is_active'])
        cache.delete('public:kvk_links')
        return StandardResponse.success(message='Activated.')


class KVKLinkDeactivateView(APIView):

    @extend_schema(tags=['Admin - CMS'], summary='Deactivate a KVK link')
    def post(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        try:
            obj = KVKLink.objects.get(pk=pk)
        except KVKLink.DoesNotExist:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        obj.is_active = False
        obj.save(update_fields=['is_active'])
        cache.delete('public:kvk_links')
        return StandardResponse.success(message='Deactivated.')


# =============================================================================
# PARTNERS
# =============================================================================

class PartnerSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model  = Partner
        fields = ['id', 'name', 'url', 'logo', 'logo_url', 'order', 'is_active', 'created_at']
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


class PartnerListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Admin - CMS'], summary='List all partners',
                   responses={200: PartnerSerializer(many=True)})
    def get(self, request):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        qs = Partner.objects.all()
        serializer = PartnerSerializer(qs, many=True, context={'request': request})
        return StandardResponse.success(data=serializer.data)

    @extend_schema(tags=['Admin - CMS'], summary='Create a partner',
                   request=PartnerSerializer, responses={201: PartnerSerializer})
    def post(self, request):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        serializer = PartnerSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return StandardResponse.error(serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)
        obj = serializer.save()
        cache.delete('public:partners')
        return StandardResponse.success(
            data=PartnerSerializer(obj, context={'request': request}).data,
            status_code=status.HTTP_201_CREATED,
        )


class PartnerDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_obj(self, pk):
        try:
            return Partner.objects.get(pk=pk)
        except Partner.DoesNotExist:
            return None

    @extend_schema(tags=['Admin - CMS'], summary='Update a partner',
                   request=PartnerSerializer, responses={200: PartnerSerializer})
    def patch(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        obj = self._get_obj(pk)
        if not obj:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        serializer = PartnerSerializer(obj, data=request.data, partial=True,
                                       context={'request': request})
        if not serializer.is_valid():
            return StandardResponse.error(serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)
        obj = serializer.save()
        cache.delete('public:partners')
        return StandardResponse.success(
            data=PartnerSerializer(obj, context={'request': request}).data,
        )

    @extend_schema(tags=['Admin - CMS'], summary='Delete a partner')
    def delete(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        obj = self._get_obj(pk)
        if not obj:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        if obj.logo:
            obj.logo.delete(save=False)
        obj.delete()
        cache.delete('public:partners')
        return StandardResponse.success(message='Deleted.')


class PartnerLogoDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Admin - CMS'], summary='Delete logo from a partner',
                   description='Removes the logo file from storage. The partner record remains.')
    def delete(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        try:
            obj = Partner.objects.get(pk=pk)
        except Partner.DoesNotExist:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        if obj.logo:
            obj.logo.delete(save=False)
            obj.logo = None
            obj.save(update_fields=['logo'])
        cache.delete('public:partners')
        return StandardResponse.success(message='Logo removed.')


class PartnerActivateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Admin - CMS'], summary='Activate a partner')
    def post(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        try:
            obj = Partner.objects.get(pk=pk)
        except Partner.DoesNotExist:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        obj.is_active = True
        obj.save(update_fields=['is_active'])
        cache.delete('public:partners')
        return StandardResponse.success(message='Activated.')


class PartnerDeactivateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Admin - CMS'], summary='Deactivate a partner')
    def post(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        try:
            obj = Partner.objects.get(pk=pk)
        except Partner.DoesNotExist:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        obj.is_active = False
        obj.save(update_fields=['is_active'])
        cache.delete('public:partners')
        return StandardResponse.success(message='Deactivated.')

# =============================================================================
# HEADER LOGOS (landing-page header, next to the main menu)
# Mirrors QuickLink CRUD. Uploads are trimmed + resized to a fixed height so any
# logo the superadmin uploads fits the header without manual cropping.
# One logo can be flagged `is_platform` (KAU–FPO platform logo) — shown first.
# =============================================================================

_HEADER_LOGOS_CACHE_KEY = 'public:header_logos'
_HEADER_LOGOS_MAX       = 4     # admin can add at most 4 header logos
_HEADER_MOBILE_ORDER    = 4     # order 4 = separate logo for the mobile menu (not one of the 4)
_HEADER_FOOTER_ORDER    = 5     # order 5 = logo in the website footer
_HEADER_LOGO_HEIGHT     = 160   # stored height (2x the ~64-80px display height → sharp on HiDPI)
_HEADER_LOGO_MAX_WIDTH  = 960   # wide banners (e.g. Directorate of Extension) shrink to fit
_HEADER_LOGO_TRIM_PAD   = 4     # px of breathing room kept after trimming

# Exact pixel size for each header position (1st, 2nd, 3rd, 4th logo)
_HEADER_SLOT_SIZES      = [(2048, 285), (1594, 1038), (1594, 1038), (1594, 1038)]


def _header_slot_index(instance, is_platform, order):
    """0-based position this logo will have in the header (platform logo is always first)."""
    if is_platform:
        return 0
    qs = HeaderLogo.objects.filter(is_active=True)
    if instance is not None:
        qs = qs.exclude(pk=instance.pk)
    platform_count = qs.filter(is_platform=True).count()
    before = qs.filter(is_platform=False).filter(order__lt=order).count()
    if instance is not None:
        before += qs.filter(is_platform=False, order=order, id__lt=instance.pk).count()
    return platform_count + before


def _trim_logo_margins(img):
    """Crop transparent / near-white margins so every logo looks the same size at equal height."""
    from PIL import Image, ImageChops

    alpha_bbox = img.getchannel('A').point(lambda a: 255 if a > 10 else 0).getbbox()
    rgb = img.convert('RGB')
    diff = ImageChops.difference(rgb, Image.new('RGB', rgb.size, (255, 255, 255)))
    white_bbox = diff.convert('L').point(lambda p: 255 if p > 15 else 0).getbbox()

    boxes = [b for b in (alpha_bbox, white_bbox) if b]
    if not boxes:
        return img
    left, top = max(b[0] for b in boxes), max(b[1] for b in boxes)
    right, bottom = min(b[2] for b in boxes), min(b[3] for b in boxes)
    if right <= left or bottom <= top:
        return img
    pad = _HEADER_LOGO_TRIM_PAD
    return img.crop((max(left - pad, 0), max(top - pad, 0),
                     min(right + pad, img.width), min(bottom + pad, img.height)))


def _compress_header_logo(file, fixed_size=None):
    """Trim margins and save as WebP. fixed_size=(w, h) fits the logo inside an exact w×h canvas."""
    import magic
    import io
    from PIL import Image, ImageOps
    from django.core.files.uploadedfile import InMemoryUploadedFile

    mime = magic.from_buffer(file.read(2048), mime=True)
    file.seek(0)

    if mime not in _LOGO_ALLOWED_MIME:
        raise serializers.ValidationError(
            f'Only JPG, PNG, WebP, and SVG logos are allowed. Got: {mime}'
        )

    if mime == 'image/svg+xml':
        return file  # vector — scales to any height without quality loss

    img = ImageOps.exif_transpose(Image.open(file)).convert('RGBA')
    img = _trim_logo_margins(img)

    if fixed_size:
        box_w, box_h = fixed_size
        scale = min(box_w / img.width, box_h / img.height)
        img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)
        canvas = Image.new('RGBA', (box_w, box_h), (0, 0, 0, 0))
        canvas.paste(img, ((box_w - img.width) // 2, (box_h - img.height) // 2), img)
        img = canvas
    else:
        scale = min(_HEADER_LOGO_HEIGHT / img.height, _HEADER_LOGO_MAX_WIDTH / img.width)
        img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)

    output = io.BytesIO()
    img.save(output, format='WEBP', quality=90, method=6)
    output.seek(0)

    return InMemoryUploadedFile(
        output, 'ImageField',
        file.name.rsplit('.', 1)[0] + '.webp',
        'image/webp',
        output.getbuffer().nbytes,
        None,
    )


class HeaderLogoSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model  = HeaderLogo
        fields = ['id', 'name', 'name_ml', 'logo', 'logo_url', 'is_platform', 'order', 'is_active', 'created_at']
        read_only_fields = ['is_platform']
        extra_kwargs = {
            'logo':      {'write_only': True, 'required': True},
            'is_active': {'default': True},
            'order':     {'required': False},   # 0-3 = header positions, 4 = mobile logo, 5 = footer logo
        }

    def get_logo_url(self, obj):
        request = self.context.get('request')
        if obj.logo and request:
            return request.build_absolute_uri(obj.logo.url)
        return obj.logo.url if obj.logo else None

    def validate_logo(self, file):
        if file.size > _LOGO_MAX_SIZE:
            raise serializers.ValidationError('Logo must not exceed 5 MB.')
        return file  # resized in validate(), once we know the logo's position

    def validate(self, attrs):
        order = attrs.get('order', self.instance.order if self.instance else None)
        if order is None:
            raise serializers.ValidationError({'order': 'Choose a position (1, 2, 3, 4, mobile or footer).'})
        if not 0 <= order <= _HEADER_FOOTER_ORDER:
            raise serializers.ValidationError({'order': f'Position must be 0 to {_HEADER_FOOTER_ORDER}.'})

        taken = HeaderLogo.objects.filter(order=order)
        if self.instance is not None:
            taken = taken.exclude(pk=self.instance.pk)
        other = taken.first()
        if other:
            label = {_HEADER_MOBILE_ORDER: 'The mobile menu logo',
                     _HEADER_FOOTER_ORDER: 'The footer logo'}.get(order, f'Position {order + 1}')
            raise serializers.ValidationError(
                {'order': f'{label} is already used by "{other.name}". Edit or delete that logo first.'}
            )

        attrs['is_platform'] = order == 0   # position 1 is the main (first) logo
        size = _HEADER_SLOT_SIZES[order] if order < len(_HEADER_SLOT_SIZES) else None  # mobile/footer: default resize

        if attrs.get('logo'):
            attrs['logo'] = _compress_header_logo(attrs['logo'], fixed_size=size)
        elif self.instance is not None and order != self.instance.order and self.instance.logo:
            # moved to another position without a new file → refit the existing image
            with self.instance.logo.open('rb') as existing:
                attrs['logo'] = _compress_header_logo(existing, fixed_size=size)
        return attrs
    
class HeaderLogoListView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes     = [MultiPartParser, FormParser, JSONParser]

    @extend_schema(
        tags=['Admin - CMS'],
        summary='List all header logos',
        responses={200: HeaderLogoSerializer(many=True)},
    )
    def get(self, request):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        qs = HeaderLogo.objects.all()
        serializer = HeaderLogoSerializer(qs, many=True, context={'request': request})
        return StandardResponse.success(serializer.data, 'Header logos retrieved.')

    @extend_schema(
        tags=['Admin - CMS'],
        summary='Create a header logo',
        description=(
            'Multipart form: `name`, `name_ml` (optional Malayalam name), `logo` (image file), '
            '`order` (position), `is_active` (optional).\n\n'
            '`order`: 0 = Position 1 (main logo, 2048×285), 1 = Position 2 (1594×1038), '
            '2 = Position 3 (1594×1038), 3 = Position 4 (1594×1038), 4 = Mobile menu logo, 5 = Footer logo.\n\n'
            'Each position can hold only one logo. Any image size is accepted — it is trimmed and '
            'fitted to the chosen position (no stretching or cropping) and stored as WebP. SVGs are stored as-is.'
        ),
        request=HeaderLogoSerializer,
        responses={201: HeaderLogoSerializer},
    )
    def post(self, request):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        if HeaderLogo.objects.count() >= _HEADER_FOOTER_ORDER + 1:   # 4 header + 1 mobile + 1 footer
            return StandardResponse.error(
                f'Only {_HEADER_LOGOS_MAX} header logos, 1 mobile logo and 1 footer logo are allowed. '
                'Delete or replace an existing logo first.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        serializer = HeaderLogoSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return StandardResponse.error('Validation failed.', errors=serializer.errors,
                                          status_code=status.HTTP_400_BAD_REQUEST)
        obj = serializer.save()
        cache.delete(_HEADER_LOGOS_CACHE_KEY)
        return StandardResponse.created(
            data=HeaderLogoSerializer(obj, context={'request': request}).data,
            message='Header logo created.',
        )
class HeaderLogoDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, pk):
        try:
            return HeaderLogo.objects.get(pk=pk)
        except HeaderLogo.DoesNotExist:
            return None

    @extend_schema(tags=['Admin - CMS'], summary='Update a header logo',
                   description='Multipart form — all fields optional (partial update). '
                               'Sending a new `logo` replaces the old file.',
                   request=HeaderLogoSerializer, responses={200: HeaderLogoSerializer})
    def patch(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        obj = self._get(pk)
        if not obj:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        old_logo = obj.logo.name if obj.logo else None
        serializer = HeaderLogoSerializer(obj, data=request.data, partial=True,
                                          context={'request': request})
        if not serializer.is_valid():
            return StandardResponse.error('Validation failed.', errors=serializer.errors,
                                          status_code=status.HTTP_400_BAD_REQUEST)
        obj = serializer.save()
        if old_logo and obj.logo and obj.logo.name != old_logo:
            obj.logo.storage.delete(old_logo)  # remove the replaced file
        cache.delete(_HEADER_LOGOS_CACHE_KEY)
        return StandardResponse.success(
            data=HeaderLogoSerializer(obj, context={'request': request}).data,
            message='Updated.',
        )

    @extend_schema(tags=['Admin - CMS'], summary='Delete a header logo')
    def delete(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        obj = self._get(pk)
        if not obj:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        if obj.logo:
            obj.logo.delete(save=False)
        obj.delete()
        cache.delete(_HEADER_LOGOS_CACHE_KEY)
        return StandardResponse.success(message='Deleted.')


class HeaderLogoReorderView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['Admin - CMS'],
        summary='Bulk reorder header logos',
        description=(
            'Accepts `{"items": [{"id": 1, "order": 0}, {"id": 3, "order": 1}, ...]}`. '
            'The platform logo is always shown first regardless of order.'
        ),
    )
    def post(self, request):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        items = request.data.get('items') or []
        if not isinstance(items, list) or not items:
            return StandardResponse.error(
                'items must be a non-empty list of {id, order} objects.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        from django.db import transaction as _tx
        try:
            with _tx.atomic():
                for row in items:
                    HeaderLogo.objects.filter(pk=row['id']).update(order=int(row['order']))
        except (KeyError, TypeError, ValueError):
            return StandardResponse.error(
                'Each item must have an integer id and integer order.',
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        cache.delete(_HEADER_LOGOS_CACHE_KEY)
        return StandardResponse.success(message='Order updated.')


class HeaderLogoActivateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Admin - CMS'], summary='Activate a header logo')
    def post(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        try:
            obj = HeaderLogo.objects.get(pk=pk)
        except HeaderLogo.DoesNotExist:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        obj.is_active = True
        obj.save(update_fields=['is_active'])
        cache.delete(_HEADER_LOGOS_CACHE_KEY)
        return StandardResponse.success(message='Activated.')


class HeaderLogoDeactivateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Admin - CMS'], summary='Deactivate a header logo')
    def post(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        try:
            obj = HeaderLogo.objects.get(pk=pk)
        except HeaderLogo.DoesNotExist:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        obj.is_active = False
        obj.save(update_fields=['is_active'])
        cache.delete(_HEADER_LOGOS_CACHE_KEY)
        return StandardResponse.success(message='Deactivated.')
# =============================================================================
# NEWS SOURCES
# =============================================================================

class NewsSourceSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model  = NewsSource
        fields = ['id', 'name', 'url', 'logo', 'logo_url', 'category', 'end_date', 'is_active', 'created_at']
        extra_kwargs = {
            'logo':      {'write_only': True, 'required': False},
            'is_active': {'default': True},
            'end_date':  {'required': False, 'allow_null': True},
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
        cache.delete_pattern('public:news_sources:*')
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
        cache.delete_pattern('public:news_sources:*')
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
        cache.delete_pattern('public:news_sources:*')
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
        cache.delete_pattern('public:news_sources:*')
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
        cache.delete_pattern('public:news_sources:*')
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
        cache.delete_pattern('public:news_sources:*')
        return StandardResponse.success(message='Deactivated.')


# =============================================================================
# TEAM MEMBERS
# =============================================================================

_TEAM_CACHE_KEY = 'public:team_members:v2'

class TeamMemberSerializer(serializers.ModelSerializer):
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model  = TeamMember
        fields = ['id', 'name', 'designation', 'photo', 'photo_url', 'order', 'is_active', 'section', 'is_patrons', 'created_at']
        read_only_fields = ['is_patrons']
        extra_kwargs = {
            'photo':     {'write_only': True, 'required': False},
            'is_active': {'default': True},
        }

    def to_internal_value(self, data):
        # Multipart sends an empty string for "no section"
        if hasattr(data, 'get') and data.get('section') == '':
            data = data.copy()
            data['section'] = None
        return super().to_internal_value(data)

    def validate(self, attrs):
        section = attrs.get('section', getattr(self.instance, 'section', None))
        if not section:
            raise serializers.ValidationError({'section': f'Section is required. Choose one of: {", ".join(TeamSection.values)}.'})
        return attrs

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
        cache.delete(_TEAM_CACHE_KEY)
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
        cache.delete(_TEAM_CACHE_KEY)
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
        cache.delete(_TEAM_CACHE_KEY)
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
        cache.delete(_TEAM_CACHE_KEY)
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
        cache.delete(_TEAM_CACHE_KEY)
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
        cache.delete(_TEAM_CACHE_KEY)
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
# Gallery Albums
# ─────────────────────────────────────────────────────────────────────────────

class GalleryAlbumSerializer(serializers.ModelSerializer):
    cover_photo_url = serializers.SerializerMethodField()
    photo_count     = serializers.SerializerMethodField()

    class Meta:
        model  = GalleryAlbum
        fields = ['id', 'title', 'order', 'is_active', 'cover_photo_url', 'photo_count', 'created_at']
        read_only_fields = ['id', 'cover_photo_url', 'photo_count', 'created_at']

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_cover_photo_url(self, obj):
        cover = obj.cover_photo(include_inactive=True)
        if not cover or not cover.photo:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(cover.photo.url) if request else cover.photo.url

    @extend_schema_field(serializers.IntegerField())
    def get_photo_count(self, obj):
        return obj.photo_count()

    def validate_title(self, value):
        if not isinstance(value, dict) or not value.get('en'):
            raise serializers.ValidationError('title must be a JSON object with at least an "en" key.')
        return value


class GalleryAlbumListView(APIView):

    @extend_schema(tags=['Admin - CMS'], summary='List gallery albums',
                   responses={200: GalleryAlbumSerializer(many=True)})
    def get(self, request):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        qs = GalleryAlbum.objects.filter(is_deleted=False)
        return StandardResponse.success(
            GalleryAlbumSerializer(qs, many=True, context={'request': request}).data,
            'Albums retrieved.',
        )

    @extend_schema(tags=['Admin - CMS'], summary='Create a gallery album',
                   description='Fields: `title` (required), `order` (optional), `is_active` (optional).')
    def post(self, request):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)

        title_raw = request.data.get('title', {})
        try:
            title = json.loads(title_raw) if isinstance(title_raw, str) else title_raw
        except ValueError:
            return StandardResponse.error(
                'title must be valid JSON e.g. {"en": "Opening Ceremony 2024"}',
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        data = {**request.data, 'title': title}
        serializer = GalleryAlbumSerializer(data=data, context={'request': request})
        if not serializer.is_valid():
            return StandardResponse.error('Validation failed.', errors=serializer.errors,
                                          status_code=status.HTTP_400_BAD_REQUEST)
        obj = serializer.save(created_by=request.user)
        cache.delete_pattern('public:gallery_albums:*')
        return StandardResponse.created(
            data=GalleryAlbumSerializer(obj, context={'request': request}).data,
            message='Album created.',
        )


class GalleryAlbumDetailView(APIView):

    def _get(self, pk):
        try:
            return GalleryAlbum.objects.get(pk=pk, is_deleted=False)
        except GalleryAlbum.DoesNotExist:
            return None

    @extend_schema(tags=['Admin - CMS'], summary='Update a gallery album')
    def patch(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        obj = self._get(pk)
        if not obj:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)

        data = {k: v for k, v in request.data.items()}
        if 'title' in data and isinstance(data['title'], str):
            try:
                data['title'] = json.loads(data['title'])
            except ValueError:
                return StandardResponse.error(
                    'title must be valid JSON.',
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

        serializer = GalleryAlbumSerializer(obj, data=data, partial=True, context={'request': request})
        if not serializer.is_valid():
            return StandardResponse.error('Validation failed.', errors=serializer.errors,
                                          status_code=status.HTTP_400_BAD_REQUEST)
        obj = serializer.save(updated_by=request.user)
        cache.delete_pattern('public:gallery_albums:*')
        return StandardResponse.success(
            data=GalleryAlbumSerializer(obj, context={'request': request}).data,
            message='Updated.',
        )

    @extend_schema(tags=['Admin - CMS'], summary='Delete a gallery album',
                   description='Deletes the album and all its photos.')
    def delete(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        obj = self._get(pk)
        if not obj:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        for photo in obj.photos.filter(is_deleted=False):
            if photo.photo:
                photo.photo.delete(save=False)
            photo.soft_delete(user=request.user)
        obj.soft_delete(user=request.user)
        cache.delete_pattern('public:gallery_albums:*')
        cache.delete('public:gallery')
        return StandardResponse.success(message='Album and all its photos deleted.')


class GalleryAlbumActivateView(APIView):

    @extend_schema(tags=['Admin - CMS'], summary='Activate a gallery album')
    def post(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        try:
            obj = GalleryAlbum.objects.get(pk=pk, is_deleted=False)
        except GalleryAlbum.DoesNotExist:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        obj.is_active = True
        obj.save(update_fields=['is_active'])
        obj.photos.filter(is_deleted=False).update(is_active=True)
        cache.delete_pattern('public:gallery_albums:*')
        cache.delete('public:gallery')
        return StandardResponse.success(message='Activated.')


class GalleryAlbumDeactivateView(APIView):

    @extend_schema(tags=['Admin - CMS'], summary='Deactivate a gallery album')
    def post(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        try:
            obj = GalleryAlbum.objects.get(pk=pk, is_deleted=False)
        except GalleryAlbum.DoesNotExist:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        obj.is_active = False
        obj.save(update_fields=['is_active'])
        obj.photos.filter(is_deleted=False).update(is_active=False)
        cache.delete_pattern('public:gallery_albums:*')
        cache.delete('public:gallery')
        return StandardResponse.success(message='Deactivated.')


# ─────────────────────────────────────────────────────────────────────────────
# Gallery Photos (scoped to album)
# ─────────────────────────────────────────────────────────────────────────────

class GalleryPhotoSerializer(serializers.ModelSerializer):
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model  = GalleryPhoto
        fields = ['id', 'album', 'photo', 'photo_url', 'caption', 'order', 'is_active', 'created_at']
        extra_kwargs = {
            'photo':      {'write_only': True, 'required': True},
            'caption':    {'required': False, 'default': dict},
            'is_active':  {'default': True},
            'album':      {'required': False},
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
                   description='Pass `?album_id=<id>` to filter photos by album.',
                   responses={200: GalleryPhotoSerializer(many=True)})
    def get(self, request):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        qs = GalleryPhoto.objects.filter(is_deleted=False)
        album_id = request.query_params.get('album_id')
        if album_id:
            qs = qs.filter(album_id=album_id)
        return StandardResponse.success(
            GalleryPhotoSerializer(qs, many=True, context={'request': request}).data,
            'Gallery retrieved.',
        )

    @extend_schema(
        tags=['Admin - CMS'],
        summary='Upload one or multiple gallery photos',
        description=(
            'Multipart form — supports single or bulk upload:\n\n'
            '**Single upload:** send `photo` (one file)\n'
            '**Bulk upload:** send `photos` (multiple files via `photos[]`)\n\n'
            '- `photo` / `photos` — JPG/PNG/WebP, max 5 MB each (auto-compressed to max 1200×800, quality 85)\n'
            '- `caption` — optional JSON string e.g. `{"en": "Opening ceremony", "ml": "..."}` (applied to all in bulk)\n'
            '- `order` — display order (default 0)\n'
            '- `is_active` — default true\n\n'
            'Returns a single object for single upload, or an array for bulk upload.'
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

        album_id = request.data.get('album_id') or request.data.get('album')

        # Support both `photos[]` (bulk) and `photo` (single)
        photo_files = request.FILES.getlist('photos') or request.FILES.getlist('photos[]')
        single_file = request.FILES.get('photo')

        if not photo_files and single_file:
            # Single upload — original behaviour
            try:
                single_file = _compress_photo(single_file)
            except serializers.ValidationError as e:
                return StandardResponse.error(str(e.detail[0]), status_code=status.HTTP_400_BAD_REQUEST)

            data = {
                'photo':     single_file,
                'caption':   caption,
                'order':     request.data.get('order', 0),
                'is_active': request.data.get('is_active', True),
            }
            if album_id:
                data['album'] = album_id
            serializer = GalleryPhotoSerializer(data=data, context={'request': request})
            if not serializer.is_valid():
                return StandardResponse.error('Validation failed.', errors=serializer.errors,
                                              status_code=status.HTTP_400_BAD_REQUEST)
            obj = serializer.save(created_by=request.user)
            cache.delete('public:gallery')
            cache.delete_pattern('public:gallery_albums:*')
            return StandardResponse.created(
                data=GalleryPhotoSerializer(obj, context={'request': request}).data,
                message='Photo uploaded.',
            )

        if not photo_files:
            return StandardResponse.error('No photo(s) provided.', status_code=status.HTTP_400_BAD_REQUEST)

        # Bulk upload
        created = []
        errors = []
        for i, f in enumerate(photo_files):
            try:
                compressed = _compress_photo(f)
            except serializers.ValidationError as e:
                errors.append({'file': f.name, 'error': str(e.detail[0])})
                continue

            data = {
                'photo':     compressed,
                'caption':   caption,
                'order':     request.data.get('order', 0),
                'is_active': request.data.get('is_active', True),
            }
            if album_id:
                data['album'] = album_id
            serializer = GalleryPhotoSerializer(data=data, context={'request': request})
            if serializer.is_valid():
                obj = serializer.save(created_by=request.user)
                created.append(GalleryPhotoSerializer(obj, context={'request': request}).data)
            else:
                errors.append({'file': f.name, 'error': serializer.errors})

        cache.delete('public:gallery')
        cache.delete_pattern('public:gallery_albums:*')
        return StandardResponse.created(
            data={'uploaded': created, 'errors': errors},
            message=f'{len(created)} photo(s) uploaded.',
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
        album= obj.album
        obj.soft_delete(user=request.user)
 
        # If this was the last active photo in the album, deactivate the album too
        # (mirrors GalleryDeactivateView) so the landing page stops showing it.
        if album.is_active:
            has_active_photos = album.photos.filter(is_deleted=False, is_active=True).exists()
            if not has_active_photos:
                album.is_active = False
                album.save(update_fields=['is_active'])
                cache.delete_pattern('public:gallery_albums:*')
 
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

        # If the album was inactive, this is its first active photo again — reactivate it.
        if not obj.album.is_active:
            obj.album.is_active = True
            obj.album.save(update_fields=['is_active'])
            cache.delete_pattern('public:gallery_albums:*')
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
        # If this was the last active photo in the album, deactivate the album too.
        if obj.album.is_active:
            has_active_photos = obj.album.photos.filter(is_deleted=False, is_active=True).exists()
            if not has_active_photos:
                obj.album.is_active = False
                obj.album.save(update_fields=['is_active'])
                cache.delete_pattern('public:gallery_albums:*')


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


# =============================================================================
# YOUTUBE PLAYLISTS
# =============================================================================

_YOUTUBE_CACHE_PATTERN = 'public:youtube_playlists:*'


def _clear_youtube_cache():
    cache.delete_pattern(_YOUTUBE_CACHE_PATTERN)


class YoutubePlaylistSerializer(serializers.ModelSerializer):
    class Meta:
        model  = YoutubePlaylist
        fields = ['id', 'title', 'playlist_id', 'playlist_url', 'order', 'is_active', 'created_at']
        read_only_fields = ['playlist_id']
        extra_kwargs = {'is_active': {'default': True}}

    def validate_title(self, value):
        value = {k: v.strip() for k, v in (value or {}).items() if isinstance(v, str) and v.strip()}
        if value:
            _validate_multilingual_field(value, 'title')
        return value

    def validate_playlist_url(self, value):
        playlist_id = extract_playlist_id(value)
        if not playlist_id:
            raise serializers.ValidationError(
                'Enter a YouTube playlist link, e.g. https://www.youtube.com/playlist?list=PL...'
            )
        self._playlist_id = playlist_id
        return f'https://www.youtube.com/playlist?list={playlist_id}'

    def validate(self, attrs):
        playlist_id = getattr(self, '_playlist_id', None)
        if playlist_id and (self.instance is None or self.instance.playlist_id != playlist_id):
            try:
                feed = fetch_playlist_feed(playlist_id, use_cache=False, strict=True)
            except YouTubeLookupError as exc:
                raise serializers.ValidationError({'playlist_url': str(exc)}) from exc
            if feed is None:
                raise serializers.ValidationError(
                    {'playlist_url': 'Playlist not found or is private. Make sure it is public on YouTube.'}
                )
            attrs['playlist_id'] = playlist_id
            title = attrs.get('title', self.instance.title if self.instance else {})
            if not title and feed['title']:
                attrs['title'] = {'en': feed['title']}
        return attrs


class YoutubePlaylistListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Admin - CMS'], summary='List YouTube playlists',
                   responses={200: YoutubePlaylistSerializer(many=True)})
    def get(self, request):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        qs = YoutubePlaylist.objects.filter(is_deleted=False)
        return StandardResponse.success(data=YoutubePlaylistSerializer(qs, many=True).data)

    @extend_schema(
        tags=['Admin - CMS'],
        summary='Add a YouTube playlist',
        description='JSON: `playlist_url` (playlist link or id), `title` (optional {"en","ml"} — '
                    'taken from YouTube when empty), `order`, `is_active`.',
        request=YoutubePlaylistSerializer,
        responses={201: YoutubePlaylistSerializer},
    )
    def post(self, request):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        serializer = YoutubePlaylistSerializer(data=request.data)
        if not serializer.is_valid():
            return StandardResponse.error('Validation failed.', errors=serializer.errors,
                                          status_code=status.HTTP_400_BAD_REQUEST)
        obj = serializer.save(created_by=request.user)
        _clear_youtube_cache()
        return StandardResponse.created(data=YoutubePlaylistSerializer(obj).data, message='Playlist added.')


class YoutubePlaylistDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, pk):
        return YoutubePlaylist.objects.filter(pk=pk, is_deleted=False).first()

    @extend_schema(tags=['Admin - CMS'], summary='Update a YouTube playlist',
                   request=YoutubePlaylistSerializer, responses={200: YoutubePlaylistSerializer})
    def patch(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        obj = self._get(pk)
        if not obj:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        serializer = YoutubePlaylistSerializer(obj, data=request.data, partial=True)
        if not serializer.is_valid():
            return StandardResponse.error('Validation failed.', errors=serializer.errors,
                                          status_code=status.HTTP_400_BAD_REQUEST)
        obj = serializer.save(updated_by=request.user)
        _clear_youtube_cache()
        return StandardResponse.success(data=YoutubePlaylistSerializer(obj).data, message='Updated.')

    @extend_schema(tags=['Admin - CMS'], summary='Delete a YouTube playlist')
    def delete(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        obj = self._get(pk)
        if not obj:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        obj.soft_delete(user=request.user)
        _clear_youtube_cache()
        return StandardResponse.success(message='Deleted.')


class YoutubePlaylistActivateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Admin - CMS'], summary='Activate a YouTube playlist')
    def post(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        updated = YoutubePlaylist.objects.filter(pk=pk, is_deleted=False).update(is_active=True)
        if not updated:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        _clear_youtube_cache()
        return StandardResponse.success(message='Activated.')


class YoutubePlaylistDeactivateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Admin - CMS'], summary='Deactivate a YouTube playlist')
    def post(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        updated = YoutubePlaylist.objects.filter(pk=pk, is_deleted=False).update(is_active=False)
        if not updated:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        _clear_youtube_cache()
        return StandardResponse.success(message='Deactivated.')


class YoutubeChannelView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['Admin - CMS'], summary='Get the YouTube channel link')
    def get(self, request):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        return StandardResponse.success(data={'channel_url': get_youtube_channel_url()})

    @extend_schema(
        tags=['Admin - CMS'],
        summary='Update the YouTube channel link',
        request=inline_serializer('YoutubeChannelUpdate', {'channel_url': serializers.URLField()}),
    )
    def patch(self, request):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        field = serializers.URLField(max_length=500)
        try:
            url = field.run_validation((request.data.get('channel_url') or '').strip())
        except serializers.ValidationError as exc:
            return StandardResponse.error('Validation failed.', errors={'channel_url': exc.detail},
                                          status_code=status.HTTP_400_BAD_REQUEST)
        host = (urlparse(url).hostname or '').lower()
        if host not in ('youtube.com', 'www.youtube.com', 'm.youtube.com'):
            return StandardResponse.error(
                'Validation failed.',
                errors={'channel_url': ['Enter a YouTube channel link, e.g. https://www.youtube.com/@KauIndia']},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        SiteBlock.objects.update_or_create(block_key=YOUTUBE_CHANNEL_BLOCK, defaults={'content': {'en': url}})
        _clear_youtube_cache()
        return StandardResponse.success(data={'channel_url': url}, message='Channel link updated.')
