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

from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiTypes, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.utils.constants import UserRole
from apps.core.utils.pagination import StandardPagination
from apps.core.utils.responses import StandardResponse
from apps.database.models.cms import (
    SiteBlock, Announcement, AnnouncementCategory, FAQ, FAQCategory
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
        return StandardResponse.success(data=AnnouncementSerializer(obj).data, message='Updated.')

    @extend_schema(tags=['Admin - CMS'], summary='Delete an announcement')
    def delete(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        obj = self._get(pk)
        if not obj:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        obj.delete()
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
        return StandardResponse.success(data=FAQSerializer(obj).data, message='Updated.')

    @extend_schema(tags=['Admin - CMS'], summary='Delete a FAQ')
    def delete(self, request, pk):
        if not _is_admin(request.user):
            return StandardResponse.error('Permission denied.', status_code=status.HTTP_403_FORBIDDEN)
        obj = self._get(pk)
        if not obj:
            return StandardResponse.error('Not found.', status_code=status.HTTP_404_NOT_FOUND)
        obj.delete()
        return StandardResponse.success(message='Deleted.')
