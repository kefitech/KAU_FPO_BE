"""
█╗  ██╗ ███████╗███████╗██╗    ████████╗███████╗ ██████╗██╗  ██╗
██║ ██╔╝██╔════╝██╔════╝██║    ╚══██╔══╝██╔════╝██╔════╝██║  ██║
█████╔╝ █████╗  █████╗  ██║       ██║   █████╗  ██║     ███████║
██╔═██╗ ██╔══╝  ██╔══╝  ██║       ██║   ██╔══╝  ██║     ██╔══██║
██║  ██╗███████╗██║     ██║       ██║   ███████╗╚██████╗██║  ██║
╚═╝  ╚═╝╚══════╝╚═╝     ╚═╝       ╚═╝   ╚══════╝ ╚═════╝╚═╝  ╚═╝

                KEFI TECH

 █████╗ ████████╗██╗  ██╗██╗   ██╗██╗     
██╔══██╗╚══██╔══╝██║  ██║██║   ██║██║     
███████║   ██║   ███████║██║   ██║██║     
██╔══██║   ██║   ██╔══██║██║   ██║██║     
██║  ██║   ██║   ██║  ██║╚██████╔╝███████╗
╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚══════╝

        ATHUL GOPAN

-----------------------------------------------------
Language Detection Middleware for KAU-FPO Platform
==================================================

Detects user's preferred language from:
1. Query parameter (?lang=ml)
2. Accept-Language header
3. User's saved preference (if authenticated)
4. Default language (English)

The detected language is stored in request.language for use in views.

Usage:
    In views:
        language = request.language  # 'en' or 'ml'
        message = t('login_success', language)
Author:
    Athul Gopan

Created On:
    21-04-2026
"""

import re
from django.utils import translation

from apps.core.utils.constants import Language, DEFAULT_LANGUAGE


class LanguageDetectionMiddleware:
    """
    Middleware to detect and set language preference.

    Adds `request.language` attribute with detected language code.
    Activates Django's translation system for i18n support.
    """

    # Supported languages
    SUPPORTED_LANGUAGES = [lang.value for lang in Language]
    DEFAULT_LANGUAGE = DEFAULT_LANGUAGE.value

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Detect language
        language = self._detect_language(request)

        # Store on request object for easy access
        request.language = language

        # Activate Django translation
        translation.activate(language)

        # Process request
        response = self.get_response(request)

        # Deactivate translation
        translation.deactivate()

        # Add Content-Language header
        response['Content-Language'] = language

        return response

    def _detect_language(self, request) -> str:
        """
        Detect language from multiple sources.

        Priority:
        1. Query parameter (?lang=ml)
        2. Custom header (X-Language)
        3. Accept-Language header
        4. User preference (authenticated users)
        5. Default language

        Returns:
            Language code ('en' or 'ml')
        """
        # 1. Check query parameter
        lang_param = request.GET.get('lang')
        if lang_param and lang_param in self.SUPPORTED_LANGUAGES:
            return lang_param

        # 2. Check custom header
        custom_header = request.headers.get('X-Language')
        if custom_header and custom_header in self.SUPPORTED_LANGUAGES:
            return custom_header

        # 3. Check Accept-Language header
        accept_language = request.headers.get('Accept-Language', '')
        detected_lang = self._parse_accept_language(accept_language)
        if detected_lang:
            return detected_lang

        # 4. Check user preference (if authenticated)
        if hasattr(request, 'user') and request.user.is_authenticated:
            user_lang = getattr(request.user, 'preferred_language', None)
            if user_lang and user_lang in self.SUPPORTED_LANGUAGES:
                return user_lang

        # 5. Default
        return self.DEFAULT_LANGUAGE

    def _parse_accept_language(self, accept_language: str) -> str:
        """
        Parse Accept-Language header.

        Format: "en-US,en;q=0.9,ml;q=0.8"

        Args:
            accept_language: Accept-Language header value

        Returns:
            Detected language code or None
        """
        if not accept_language:
            return None

        # Parse language codes with quality values
        # Example: en-US,en;q=0.9,ml;q=0.8
        pattern = r'([a-zA-Z]{2})(?:-[a-zA-Z]{2})?(?:;q=([0-9.]+))?'
        matches = re.findall(pattern, accept_language)

        # Sort by quality (default q=1.0)
        languages = []
        for lang, quality in matches:
            q = float(quality) if quality else 1.0
            lang_lower = lang.lower()
            if lang_lower in self.SUPPORTED_LANGUAGES:
                languages.append((lang_lower, q))

        if languages:
            # Return highest quality supported language
            languages.sort(key=lambda x: x[1], reverse=True)
            return languages[0][0]

        return None


class RequestContextMiddleware:
    """
    Middleware to add useful context to requests.

    Adds:
    - request.client_ip: Client IP address
    - request.is_ajax: Whether request is AJAX
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Extract client IP
        request.client_ip = self._get_client_ip(request)

        # Check if AJAX request
        request.is_ajax = self._is_ajax(request)

        return self.get_response(request)

    def _get_client_ip(self, request) -> str:
        """Extract client IP from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '')

    def _is_ajax(self, request) -> bool:
        """Check if request is AJAX."""
        return request.headers.get('X-Requested-With') == 'XMLHttpRequest'
