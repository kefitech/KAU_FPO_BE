"""
Translation Service for KAU-FPO Platform
========================================

PostgreSQL + Redis Hybrid Architecture:
- Queries Redis first (<1ms)
- Falls back to PostgreSQL if cache miss
- Auto-caches result for 24 hours
- Supports variable substitution

Usage:
    from apps.core.services.translation import t, TranslationService

    # Simple translation
    message = t('auth.login_success', language='en')
    # -> "Login successful"

    # With variables
    message = t('auth.welcome_user', language='ml', user_name='John')
    # -> "സ്വാഗതം John"

    # Get all translations in a category
    ui_labels = TranslationService.get_category('ui', language='en')

Author: Athul Gopan (Kefi Tech Solutions)
Created: 28-04-2026
SRS Reference: Section 3.1.7 (Multilingual Support)
"""

from typing import Optional, Dict, List
from django.core.cache import cache
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class TranslationService:
    """
    Translation service with Redis caching.

    Performance:
    - Cache hit: <1ms (Redis in-memory lookup)
    - Cache miss: ~10ms (PostgreSQL query + Redis SET)
    - Cache TTL: 24 hours
    - Auto-invalidation: On admin updates (via signals)
    """

    CACHE_TTL = 60 * 60 * 24  # 24 hours
    CACHE_PREFIX = 'trans'

    @classmethod
    def get(
        cls,
        key: str,
        language: str = 'en',
        fallback_to_default: bool = True,
        **variables
    ) -> str:
        """
        Get translation by key.

        Args:
            key: Translation key (format: 'category.specific_key')
                 e.g., 'auth.login_success', 'validation.required_field'
            language: Language code ('en', 'ml', 'ta', etc.)
            fallback_to_default: If True, falls back to default language if translation not found
            **variables: Variable substitutions (e.g., user_name='John', count=5)

        Returns:
            Translated string with variables replaced

        Examples:
            # Simple
            t('auth.login_success', language='en')
            # -> "Login successful"

            # With variables
            t('auth.welcome_user', language='ml', user_name='John')
            # -> "സ്വാഗതം John"

            # Missing translation (fallback to English)
            t('auth.login_success', language='ta')
            # -> "Login successful" (if Tamil not available)
        """
        # Try cache first
        cache_key = f"{cls.CACHE_PREFIX}:{language}:{key}"
        text = cache.get(cache_key)

        if text is not None:
            # Cache hit - replace variables and return
            return cls._replace_variables(text, variables)

        # Cache miss - query database
        text = cls._fetch_from_db(key, language)

        if text is None and fallback_to_default and language != 'en':
            # Fallback to default language (English)
            text = cls._fetch_from_db(key, 'en')

        if text is None:
            # Translation not found - return key itself (for debugging)
            logger.warning(f"Translation not found: {key} ({language})")
            return key

        # Cache the result
        cache.set(cache_key, text, cls.CACHE_TTL)

        # Replace variables and return
        return cls._replace_variables(text, variables)

    @classmethod
    def _fetch_from_db(cls, key: str, language: str) -> Optional[str]:
        """
        Fetch translation from PostgreSQL.

        Args:
            key: Full translation key (category.specific_key)
            language: Language code

        Returns:
            Translation text or None if not found
        """
        try:
            from apps.database.models import Translation, TranslationCategory

            # Split key into category and specific_key
            if '.' not in key:
                logger.error(f"Invalid translation key format: {key} (expected 'category.key')")
                return None

            category_code, specific_key = key.split('.', 1)

            # Query database
            translation = Translation.objects.select_related(
                'category', 'language'
            ).filter(
                category__code=category_code,
                key=specific_key,
                language__code=language,
                language__is_active=True
            ).first()

            return translation.value if translation else None

        except Exception as e:
            logger.error(f"Error fetching translation {key} ({language}): {e}")
            return None

    @classmethod
    def _replace_variables(cls, text: str, variables: dict) -> str:
        """
        Replace {{variable}} placeholders with actual values.

        Args:
            text: Text with {{placeholders}}
            variables: Dictionary of variable values

        Returns:
            Text with variables replaced

        Example:
            _replace_variables("Hello {{name}}", {'name': 'John'})
            # -> "Hello John"
        """
        if not variables:
            return text

        for key, value in variables.items():
            placeholder = f"{{{{{key}}}}}"
            text = text.replace(placeholder, str(value))

        return text

    @classmethod
    def get_category(
        cls,
        category_code: str,
        language: str = 'en',
        verified_only: bool = False
    ) -> Dict[str, str]:
        """
        Get all translations in a category (bulk fetch).

        Useful for loading all UI labels at once.

        Args:
            category_code: Category code (e.g., 'ui', 'validation')
            language: Language code
            verified_only: Only return verified translations

        Returns:
            Dictionary of {key: translated_text}

        Example:
            ui_labels = get_category('ui', language='en')
            # -> {'dashboard_title': 'Dashboard', 'logout_button': 'Logout', ...}
        """
        cache_key = f"{cls.CACHE_PREFIX}_cat:{language}:{category_code}"

        if verified_only:
            cache_key += ':verified'

        # Try cache
        result = cache.get(cache_key)
        if result is not None:
            return result

        # Cache miss - query database
        try:
            from apps.database.models import Translation

            query = Translation.objects.filter(
                category__code=category_code,
                language__code=language,
                language__is_active=True
            ).select_related('category')

            if verified_only:
                query = query.filter(is_verified=True)

            translations = query.values('key', 'value')

            result = {t['key']: t['value'] for t in translations}

            # Cache the result
            cache.set(cache_key, result, cls.CACHE_TTL)

            return result

        except Exception as e:
            logger.error(f"Error fetching category {category_code} ({language}): {e}")
            return {}

    @classmethod
    def get_all_languages(cls) -> List[Dict]:
        """
        Get all active languages.

        Returns:
            List of language dictionaries

        Example:
            [
                {'code': 'en', 'name': 'English', 'native_name': 'English'},
                {'code': 'ml', 'name': 'Malayalam', 'native_name': 'മലയാളം'},
            ]
        """
        try:
            from apps.database.models import Language
            return Language.get_active_languages()
        except Exception as e:
            logger.error(f"Error fetching languages: {e}")
            return [{'code': 'en', 'name': 'English', 'native_name': 'English'}]

    @classmethod
    def invalidate_cache(cls, key: str = None, language: str = None, category: str = None):
        """
        Manually invalidate translation cache.

        Usually not needed (signals handle auto-invalidation).

        Args:
            key: Specific translation key to invalidate
            language: Invalidate all translations in this language
            category: Invalidate all translations in this category
        """
        if key and language:
            # Invalidate specific translation
            cache.delete(f"{cls.CACHE_PREFIX}:{language}:{key}")

        elif category and language:
            # Invalidate category cache
            cache.delete(f"{cls.CACHE_PREFIX}_cat:{language}:{category}")

        elif language:
            # Invalidate all for a language (pattern delete)
            pattern = f"{cls.CACHE_PREFIX}:{language}:*"
            cache.delete_pattern(pattern)

        else:
            # Nuclear option - clear all translation cache
            pattern = f"{cls.CACHE_PREFIX}:*"
            cache.delete_pattern(pattern)


# ============================================================================
# Shorthand Functions (Convenience)
# ============================================================================

def t(key: str, language: str = 'en', **variables) -> str:
    """
    Shorthand for TranslationService.get()

    Usage:
        from apps.core.services.translation import t

        message = t('auth.login_success', language='en')
        message = t('auth.welcome_user', language='ml', user_name='John')
    """
    return TranslationService.get(key, language, **variables)


def get_translations(category: str, language: str = 'en') -> Dict[str, str]:
    """
    Shorthand for TranslationService.get_category()

    Usage:
        from apps.core.services.translation import get_translations

        ui_labels = get_translations('ui', language='en')
    """
    return TranslationService.get_category(category, language)


# ============================================================================
# Notification Template Service
# ============================================================================

class NotificationTemplateService:
    """
    Service for fetching and rendering notification templates.

    Cached in Redis for performance.
    """

    CACHE_TTL = 60 * 60 * 24  # 24 hours
    CACHE_PREFIX = 'notif_template'

    @classmethod
    def get_template(cls, code: str, channel: str, language: str = 'en'):
        """
        Get notification template (cached).

        Args:
            code: Template code (e.g., 'fpo_approved')
            channel: Channel ('email', 'sms', 'in_app')
            language: Language code

        Returns:
            NotificationTemplate instance or None
        """
        cache_key = f"{cls.CACHE_PREFIX}:{channel}:{code}:{language}"

        # Try cache
        template = cache.get(cache_key)
        if template is not None:
            return template

        # Cache miss - query database
        try:
            from apps.database.models import NotificationTemplate

            template = NotificationTemplate.objects.filter(
                code=code,
                channel=channel,
                language__code=language,
                is_active=True
            ).select_related('language').first()

            if template:
                cache.set(cache_key, template, cls.CACHE_TTL)

            return template

        except Exception as e:
            logger.error(f"Error fetching template {code} ({channel}/{language}): {e}")
            return None

    @classmethod
    def render_template(
        cls,
        code: str,
        channel: str,
        context: dict,
        language: str = 'en'
    ) -> Optional[Dict[str, str]]:
        """
        Fetch and render notification template with variables.

        Args:
            code: Template code
            channel: Channel ('email', 'sms', 'in_app')
            context: Dictionary of variable values
            language: Language code

        Returns:
            Dictionary with 'subject' (email only) and 'body', or None if template not found

        Example:
            result = render_template(
                'fpo_approved',
                'email',
                {'user_name': 'John', 'application_id': 'KAU-123'},
                language='en'
            )
            # -> {'subject': 'Your FPO Application Approved', 'body': 'Dear John, ...'}
        """
        template = cls.get_template(code, channel, language)

        if not template:
            logger.warning(f"Template not found: {code} ({channel}/{language})")
            return None

        return template.render(context)
