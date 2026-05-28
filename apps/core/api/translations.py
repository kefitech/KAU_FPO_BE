"""
Public Translations API
=======================
Base Path: /api/translations/public/

No authentication required.
Used by the frontend to fetch UI labels, messages, and field names
for a given language and screen(s).

Author: Athul Gopan (Kefi Tech Solutions)
"""

from django.core.cache import cache
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from apps.core.utils.responses import StandardResponse
from apps.database.models import Translation, Language


class PublicTranslationsView(APIView):
    """
    Fetch UI translations for the frontend.

    No authentication required — called on every page load.
    Redis-cached per (lang + screen) combination.

    All UI keys live in the 'ui' category and use dot-prefix convention:
        login.email_label, fpo_form.name_label, common.submit_button

    Response is grouped by screen prefix:
        { "login": { "email_label": "...", "title": "..." }, "common": { ... } }

    Query params:
        lang:   language code — 'en', 'ml', 'ta' (default: 'en')
        screen: comma-separated screen names — 'login', 'login,fpo_form'
                leave blank to get ALL ui keys (use for app-level caching)
    """

    permission_classes = [AllowAny]

    @extend_schema(
        tags=['Translations - Public'],
        parameters=[
            OpenApiParameter(
                name='lang',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Language code (default: en). e.g. 'ml', 'ta', 'hi'",
            ),
            OpenApiParameter(
                name='screen',
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Comma-separated screen names. e.g. 'login' or 'login,fpo_form'. Leave blank for all UI keys.",
            ),
        ],
        responses={200: {
            'type': 'object',
            'example': {
                'status': 'success',
                'data': {
                    'login': {
                        'title': 'Login to KAU-FPO',
                        'email_label': 'Email Address',
                        'submit_button': 'Login',
                    },
                    'common': {
                        'submit_button': 'Submit',
                        'cancel_button': 'Cancel',
                    }
                }
            }
        }},
    )
    def get(self, request):
        lang_code = request.query_params.get('lang', 'en').strip().lower()
        screen_param = request.query_params.get('screen', '').strip().lower()

        screens = [s.strip() for s in screen_param.split(',') if s.strip()] if screen_param else []

        # Build cache key
        screen_key = ','.join(sorted(screens)) if screens else 'all'
        cache_key  = f'translations:public:{lang_code}:{screen_key}'

        cached = cache.get(cache_key)
        if cached is not None:
            return StandardResponse.success(data=cached)

        # Resolve language — fall back to English if requested language not found
        language = Language.objects.filter(code=lang_code, is_active=True).first()
        if not language:
            language = Language.objects.filter(is_default=True).first()
            if not language:
                language = Language.objects.filter(code='en').first()

        # Fetch from DB
        qs = Translation.objects.filter(
            category__code='ui',
            language=language,
        ).select_related('category').values('key', 'value')

        # Filter by screen prefix if requested
        if screens:
            from django.db.models import Q
            screen_filter = Q()
            for screen in screens:
                screen_filter |= Q(key__startswith=f'{screen}.')
            qs = qs.filter(screen_filter)

        # Group by screen prefix
        # key format: "login.email_label" → grouped["login"]["email_label"] = value
        grouped = {}
        for row in qs:
            key   = row['key']
            value = row['value']

            if '.' in key:
                screen_name, field_name = key.split('.', 1)
            else:
                screen_name = 'misc'
                field_name  = key

            if screen_name not in grouped:
                grouped[screen_name] = {}
            grouped[screen_name][field_name] = value

        # If a key is missing in requested language, fall back to English
        if language.code != 'en':
            en_language = Language.objects.filter(code='en').first()
            if en_language:
                en_qs = Translation.objects.filter(
                    category__code='ui',
                    language=en_language,
                ).values('key', 'value')

                if screens:
                    en_qs = en_qs.filter(screen_filter)

                for row in en_qs:
                    key   = row['key']
                    value = row['value']

                    if '.' in key:
                        screen_name, field_name = key.split('.', 1)
                    else:
                        screen_name = 'misc'
                        field_name  = key

                    # Only fill in if missing from target language
                    if screen_name not in grouped:
                        grouped[screen_name] = {}
                    if field_name not in grouped[screen_name]:
                        grouped[screen_name][field_name] = value

        # Cache for 24 hours — invalidated automatically when admin edits a translation
        cache.set(cache_key, grouped, timeout=60 * 60 * 24)

        return StandardResponse.success(data=grouped)
