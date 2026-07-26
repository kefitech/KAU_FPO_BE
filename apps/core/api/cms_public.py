"""
Public CMS APIs — no auth required
=====================================
GET /api/public/languages/             — active languages (for public locale switcher)
GET /api/public/site-content/          — all active site blocks
GET /api/public/site-content/{key}/    — single block by key
GET /api/public/announcements/         — active announcements
GET /api/public/faqs/                  — active FAQs (filter: category)
GET /api/public/stats/                 — platform counters for landing page
GET /api/public/quick-links/           — logo + URL links
GET /api/public/news-sources/          — newspaper/magazine links grouped by category
GET /api/public/team/                  — leadership/team members
GET /api/public/gallery/               — photo gallery
GET /api/public/documents/             — downloadable documents (is_view_only flag)
POST /api/public/feedback/             — submit feedback (no auth)
"""

from django.contrib.auth.models import User
from django.core.cache import cache

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.core.utils.pagination import StandardPagination
from apps.core.utils.responses import StandardResponse
from apps.database.models.cms import SiteBlock, Announcement, FAQ, QuickLink, NewsSource, TeamMember, GalleryPhoto, DocumentLibrary, Feedback, VisitorCount
from apps.database.models.fpo import FPO
from apps.database.models.language import Language
from apps.database.models.schemes import Expert
from apps.core.utils.constants import FPOStatus, UserRole


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
            'total_registrations':  fpos.count(),
            'approved_fpos':        fpos.filter(status=FPOStatus.APPROVED).count(),
            'total_districts':      fpos.exclude(district='').values('district').distinct().count(),
            'total_govt_officials': User.objects.filter(groups__name=UserRole.GOVERNMENT, is_active=True).count(),
            'total_experts':        Expert.objects.filter(is_active=True, is_deleted=False).count(),
            'total_visitors':       VisitorCount.get_count(),
        }
        cache.set(cache_key, data, timeout=60 * 5)
        return StandardResponse.success(data=data)


class PublicQuickLinksView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['Public - CMS'],
        summary='Get active quick links',
        description='Returns all active quick links (logo + URL). Redis-cached (24h). No auth required.',
    )
    def get(self, request):
        cached = cache.get('public:quick_links')
        if cached is not None:
            return StandardResponse.success(data=cached)

        qs   = QuickLink.objects.filter(is_active=True)
        data = [
            {
                'id':       ql.id,
                'name':     ql.name,
                'url':      ql.url,
                'logo_url': request.build_absolute_uri(ql.logo.url) if ql.logo else None,
            }
            for ql in qs
        ]
        cache.set('public:quick_links', data, timeout=60 * 60 * 24)
        return StandardResponse.success(data=data)


class PublicNewsSourcesView(APIView):
     permission_classes = [AllowAny]

     @extend_schema(
         tags=['Public - CMS'],
         summary='Get active news sources by category',
         description=(
             'Returns active news sources (newspapers or magazines) with logo URLs.\n\n'
             '**Filter:** `?category=newspaper` or `?category=magazine`\n\n'
             '**Pagination:** `?page=1&page_size=6` (max 100)\n\n'
             'Redis-cached (24h). No auth required.'
         ),
     )
     def get(self, request):
        category = request.query_params.get('category', '').strip()
 
        cache_key = f'public:news_sources:{category or "all"}'
        cached = cache.get(cache_key)
        if cached is not None:
            paginator = StandardPagination()
            page = paginator.paginate_queryset(cached, request)
            return paginator.get_paginated_response(page) 
        qs = NewsSource.objects.filter(is_active=True, is_deleted=False)
        if category:
            qs = qs.filter(category=category)
            data = [
            {
                'id':       ns.id,
                'name':     ns.name,
                'url':      ns.url,
                'logo_url': request.build_absolute_uri(ns.logo.url) if ns.logo else None,
            }
            for ns in qs
        ]
        cache.set(cache_key, data, timeout=60 * 60 * 24)
 
        paginator = StandardPagination()
        page = paginator.paginate_queryset(data, request)
        return paginator.get_paginated_response(page)

class PublicTeamMembersView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['Public - CMS'],
        summary='Get team members',
        description='Returns active team members ordered by display order. Redis-cached (24h). No auth required.',
    )
    def get(self, request):
        cached = cache.get('public:team_members')
        if cached is not None:
            return StandardResponse.success(data=cached)

        qs   = TeamMember.objects.filter(is_active=True, is_deleted=False)
        data = [
            {
                'id':          m.id,
                'name':        m.name,
                'designation': m.designation,
                'photo_url':   request.build_absolute_uri(m.photo.url) if m.photo else None,
                'order':       m.order,
            }
            for m in qs
        ]
        cache.set('public:team_members', data, timeout=60 * 60 * 24)
        return StandardResponse.success(data=data)


class PublicGalleryView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['Public - CMS'],
        summary='Get gallery photos',
        description='Returns active gallery photos ordered by display order. Redis-cached (24h). No auth required.',
    )
    def get(self, request):
        cached = cache.get('public:gallery')
        if cached is not None:
            return StandardResponse.success(data=cached)

        qs   = GalleryPhoto.objects.filter(is_active=True, is_deleted=False)
        data = [
            {
                'id':        p.id,
                'photo_url': request.build_absolute_uri(p.photo.url) if p.photo else None,
                'caption':   p.get_caption(_lang(request)),
                'order':     p.order,
            }
            for p in qs
        ]
        cache.set('public:gallery', data, timeout=60 * 60 * 24)
        return StandardResponse.success(data=data)


class PublicDocumentLibraryView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['Public - CMS'],
        summary='Get document library',
        description=(
            'Returns active documents ordered by display order.\n\n'
            '`is_view_only: true` — frontend should show an inline viewer only, no download button.\n'
            '`is_view_only: false` — both view and download are allowed.\n\n'
            'Send `X-Language` header to get title in the requested language. Redis-cached (24h).'
        ),
    )
    def get(self, request):
        lang      = _lang(request)
        cache_key = f'public:document_library:{lang}'
        cached    = cache.get(cache_key)
        if cached is not None:
            return StandardResponse.success(data=cached)

        qs   = DocumentLibrary.objects.filter(is_active=True, is_deleted=False)
        data = [
            {
                'id':           d.id,
                'title':        d.get_title(lang),
                'file_url':     request.build_absolute_uri(d.file.url) if d.file else None,
                'is_view_only': d.is_view_only,
                'order':        d.order,
            }
            for d in qs
        ]
        cache.set(cache_key, data, timeout=60 * 60 * 24)
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


class PublicFeedbackView(APIView):
    permission_classes = [AllowAny]

    class _Serializer(serializers.Serializer):
        name    = serializers.CharField(max_length=200)
        email   = serializers.EmailField()
        phone   = serializers.CharField(max_length=20, required=False, allow_blank=True, default='')
        subject = serializers.CharField(max_length=300)
        message = serializers.CharField()

    @extend_schema(
        tags=['Public - CMS'],
        summary='Submit feedback',
        description=(
            'Public feedback form — no auth required.\n\n'
            'Fields: `name`, `email`, `phone` (optional), `subject`, `message`.\n\n'
            'Submissions appear in the admin inbox at `GET /api/admin/feedback/`.'
        ),
        request=_Serializer,
        responses={201: None},
    )
    def post(self, request):
        serializer = self._Serializer(data=request.data)
        if not serializer.is_valid():
            return StandardResponse.error('Validation failed.', errors=serializer.errors,
                                          status_code=status.HTTP_400_BAD_REQUEST)
        d = serializer.validated_data
        Feedback.objects.create(
            name=d['name'],
            email=d['email'],
            phone=d.get('phone', ''),
            subject=d['subject'],
            message=d['message'],
        )
        return StandardResponse.created(message='Thank you for your feedback. We will get back to you soon.')


class PublicVisitorTrackView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['Public - CMS'],
        summary='Track a page visit',
        description=(
            'Call this once when the landing page loads to increment the visitor counter.\n\n'
            'No body required. Returns the updated total count.\n\n'
            'The count is also returned by `GET /api/public/stats/` as `total_visitors`.'
        ),
        request=None,
        responses={200: None},
    )
    def post(self, request):
        redis_key = 'public:visitor_count'
        try:
            count = cache.incr(redis_key)
        except ValueError:
            cache.set(redis_key, 1)
            count = 1

        VisitorCount.increment()
        return StandardResponse.success(data={'total_visitors': count})
