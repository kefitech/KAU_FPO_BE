"""
Public CMS APIs — no auth required
=====================================
GET /api/public/languages/             — active languages (for public locale switcher)
GET /api/public/site-content/          — all active site blocks
GET /api/public/site-content/{key}/    — single block by key
GET /api/public/announcements/         — active announcements
GET /api/public/faqs/                  — active FAQs (filter: category)
GET /api/public/stats/                 — platform counters for landing page
"""

from django.core.cache import cache

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.core.utils.pagination import StandardPagination
from apps.core.utils.responses import StandardResponse
from apps.database.models.cms import SiteBlock, Announcement, FAQ
from apps.database.models.fpo import FPO
from apps.database.models.language import Language
from apps.core.utils.constants import FPOStatus


def _lang(request):
    return getattr(request, 'language', 'en')


class PublicSiteContentView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['Public - CMS'],
        summary='Get all site content blocks',
        description=(
            'Returns all active content blocks for the landing page.\n\n'
            '**Available block_keys:**\n'
            '- `hero_headline`, `hero_subheading`, `hero_description`\n'
            '- `about_title`, `about_body`\n'
            '- `how_to_register`\n\n'
            'Send `X-Language: ml` to get Malayalam text.'
        ),
    )
    def get(self, request):
        lang = _lang(request)
        cache_key = f'public:site_content:{lang}'
        cached = cache.get(cache_key)
        if cached is not None:
            return StandardResponse.success(data=cached)

        blocks = SiteBlock.objects.filter(is_active=True)
        data = {b.block_key: b.get_content(lang) for b in blocks}
        cache.set(cache_key, data, timeout=60 * 60 * 24)
        return StandardResponse.success(data=data)


class PublicSiteBlockDetailView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=['Public - CMS'], summary='Get a single site content block')
    def get(self, request, key):
        lang = _lang(request)
        cache_key = f'public:site_content_detail:{lang}:{key}'
        cached = cache.get(cache_key)
        if cached is not None:
            return StandardResponse.success(data=cached)

        try:
            block = SiteBlock.objects.get(block_key=key, is_active=True)
        except SiteBlock.DoesNotExist:
            from rest_framework import status
            return StandardResponse.error('Block not found.', status_code=status.HTTP_404_NOT_FOUND)

        data = {'block_key': block.block_key, 'content': block.get_content(lang)}
        cache.set(cache_key, data, timeout=60 * 60 * 24)
        return StandardResponse.success(data=data)


class PublicAnnouncementView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['Public - CMS'],
        summary='Get announcements & news',
        description=(
            'Returns active announcements. Results are paginated (default 20/page).\n\n'
            '**Filter:** `?category=announcement` or `?category=news`\n\n'
            '**Pagination:** `?page=1&page_size=20` (max 100)\n\n'
            'Send `X-Language: ml` to get Malayalam text where available.\n\n'
            'Results are Redis-cached (24h). Cache is cleared automatically on admin writes.'
        ),
    )
    def get(self, request):
        lang     = _lang(request)
        category = request.query_params.get('category', '').strip()

        cache_key = f'public:announcements:{lang}:{category or "all"}'
        cached = cache.get(cache_key)
        if cached is not None:
            paginator = StandardPagination()
            page = paginator.paginate_queryset(cached, request)
            return paginator.get_paginated_response(page)

        qs = Announcement.objects.filter(is_active=True)
        if category:
            qs = qs.filter(category=category)

        data = [
            {
                'id':             a.id,
                'title':          a.get_title(lang),
                'body':           a.get_body(lang),
                'category':       a.category,
                'published_date': a.published_date,
            }
            for a in qs
        ]
        cache.set(cache_key, data, timeout=60 * 60 * 24)

        paginator = StandardPagination()
        page = paginator.paginate_queryset(data, request)
        return paginator.get_paginated_response(page)


class PublicFAQView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['Public - CMS'],
        summary='Get FAQs',
        description=(
            'Returns active FAQs. Results are paginated (default 20/page).\n\n'
            '**Filter:** `?category=fpo_general` / `schemes` / `platform_usage`\n\n'
            '**Pagination:** `?page=1&page_size=20` (max 100)\n\n'
            'Send `X-Language: ml` to get Malayalam text where available.\n\n'
            'Results are Redis-cached (24h). Cache is cleared automatically when an FAQ is created, updated, or deleted.'
        ),
    )
    def get(self, request):
        lang     = _lang(request)
        category = request.query_params.get('category', '').strip()

        cache_key = f'public:faqs:{lang}:{category or "all"}'
        cached = cache.get(cache_key)
        if cached is not None:
            paginator = StandardPagination()
            page = paginator.paginate_queryset(cached, request)
            return paginator.get_paginated_response(page)

        qs = FAQ.objects.filter(is_active=True)
        if category:
            qs = qs.filter(category=category)

        data = [
            {
                'id':       f.id,
                'question': f.get_question(lang),
                'answer':   f.get_answer(lang),
                'category': f.category,
                'order':    f.order,
            }
            for f in qs
        ]

        cache.set(cache_key, data, timeout=60 * 60 * 24)  # 24h

        paginator = StandardPagination()
        page = paginator.paginate_queryset(data, request)
        return paginator.get_paginated_response(page)


class PublicPlatformStatsView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['Public - CMS'],
        summary='Platform statistics for landing page counters',
        description='Returns live counts for the landing page metrics section. No auth required.',
    )
    def get(self, request):
        cache_key = 'public:platform_stats'
        cached = cache.get(cache_key)
        if cached is not None:
            return StandardResponse.success(data=cached)

        fpos = FPO.objects.filter(is_deleted=False)
        data = {
            'total_registrations': fpos.count(),
            'approved_fpos':       fpos.filter(status=FPOStatus.APPROVED).count(),
            'total_districts':     fpos.exclude(district='').values('district').distinct().count(),
        }
        cache.set(cache_key, data, timeout=60 * 5)
        return StandardResponse.success(data=data)


class PublicLanguagesView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['Public - CMS'],
        summary='Get active languages',
        description=(
            'Returns all active languages for the public locale switcher.\n\n'
            'No auth required — safe to call from the public navbar before login.\n'
            'Results are Redis-cached (24h). Use `code` as the X-Language header value.\n'
            'The language with `is_default: true` is the required/fallback language.'
        ),
    )
    def get(self, request):
        languages = Language.get_active_languages()
        return StandardResponse.success(data=languages)
