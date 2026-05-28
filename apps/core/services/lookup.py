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
Lookup Service for KAU-FPO Platform
===================================

Service for accessing cached lookup data from MasterLookup table.

Features:
- Caches lookups in Redis for 24 hours
- Supports bilingual data (English + Malayalam)
- Invalidates cache on admin updates

Usage:
    from apps.core.services.lookup import LookupService

    # Get all commodities
    commodities = LookupService.get_by_category('commodity')

    # Get single item
    item = LookupService.get_by_code('commodity', 'rice')

Author:
    Athul Gopan
Created On:
    21-04-2026
"""

from typing import List, Dict, Optional, Any
from django.core.cache import cache

from apps.core.models.generic import MasterLookup
from apps.core.utils.constants import CACHE_TTL_LONG


class LookupService:
    """
    Service for cached lookup data.

    Queries database once, caches for 24 hours.
    Call invalidate_cache() when admin updates data.
    """

    CACHE_TTL = CACHE_TTL_LONG  # 24 hours
    CACHE_PREFIX = "lookup"

    @classmethod
    def get_by_category(
        cls,
        category: str,
        language: str = 'en',
        include_inactive: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get all items in a category.

        Args:
            category: Category code (e.g., 'commodity', 'expert_category')
            language: any active language code (e.g. 'en', 'ml', 'ta')
            include_inactive: Whether to include inactive items

        Returns:
            List of dictionaries with lookup data
        """
        cache_key = cls._get_cache_key(category, language, include_inactive)

        # Try cache first
        data = cache.get(cache_key)
        if data is not None:
            return data

        # Cache miss - query database
        qs = MasterLookup.objects.filter(category=category)

        if not include_inactive:
            qs = qs.filter(is_active=True)

        qs = qs.order_by('display_order', 'code')

        data = [
            {
                "code":        item.code,
                "name":        item.get_name(language),
                "description": item.description,
                "parent_code": item.parent.code if item.parent else None,
                "metadata":    item.metadata,
            }
            for item in qs
        ]

        # Cache the result
        cache.set(cache_key, data, cls.CACHE_TTL)

        return data

    @classmethod
    def get_by_code(
        cls,
        category: str,
        code: str,
        language: str = 'en'
    ) -> Optional[Dict[str, Any]]:
        """
        Get a single lookup item by code.

        Args:
            category: Category code
            code: Item code
            language: any active language code (e.g. 'en', 'ml', 'ta')

        Returns:
            Dictionary with lookup data or None
        """
        # Try to find in cached category data
        items = cls.get_by_category(category, language)

        for item in items:
            if item['code'] == code:
                return item

        return None

    @classmethod
    def get_choices(
        cls,
        category: str,
        language: str = 'en'
    ) -> List[tuple]:
        """
        Get lookup items as choices for Django forms/serializers.

        Args:
            category: Category code
            language: any active language code (e.g. 'en', 'ml', 'ta')

        Returns:
            List of (code, name) tuples
        """
        items = cls.get_by_category(category, language)
        return [(item['code'], item['name']) for item in items]

    @classmethod
    def get_children(
        cls,
        category: str,
        parent_code: str,
        language: str = 'en'
    ) -> List[Dict[str, Any]]:
        """
        Get child items of a parent.

        Args:
            category: Category code
            parent_code: Parent item code
            language: any active language code (e.g. 'en', 'ml', 'ta')

        Returns:
            List of child items
        """
        items = cls.get_by_category(category, language)
        return [item for item in items if item['parent_code'] == parent_code]

    @classmethod
    def get_tree(
        cls,
        category: str,
        language: str = 'en'
    ) -> List[Dict[str, Any]]:
        """
        Get hierarchical tree structure.

        Args:
            category: Category code
            language: any active language code (e.g. 'en', 'ml', 'ta')

        Returns:
            List of root items with nested children
        """
        items = cls.get_by_category(category, language)

        # Build lookup by code
        items_by_code = {item['code']: {**item, 'children': []} for item in items}

        # Build tree
        roots = []
        for item in items:
            parent_code = item.get('parent_code')
            item_with_children = items_by_code[item['code']]

            if parent_code and parent_code in items_by_code:
                items_by_code[parent_code]['children'].append(item_with_children)
            else:
                roots.append(item_with_children)

        return roots

    @classmethod
    def exists(cls, category: str, code: str) -> bool:
        """
        Check if a lookup item exists.

        Args:
            category: Category code
            code: Item code

        Returns:
            True if exists and active
        """
        return cls.get_by_code(category, code) is not None

    @classmethod
    def get_name(
        cls,
        category: str,
        code: str,
        language: str = 'en'
    ) -> Optional[str]:
        """
        Get display name for a code.

        Args:
            category: Category code
            code: Item code
            language: any active language code (e.g. 'en', 'ml', 'ta')

        Returns:
            Display name or None
        """
        item = cls.get_by_code(category, code, language)
        return item['name'] if item else None

    @classmethod
    def invalidate_cache(cls, category: str = None):
        """
        Invalidate lookup cache.

        Call this when admin updates lookup data.

        Args:
            category: Specific category or None for all
        """
        if category:
            try:
                from apps.database.models import Language
                lang_codes = list(Language.objects.filter(is_active=True).values_list('code', flat=True))
            except Exception:
                lang_codes = ['en', 'ml']
            for language in lang_codes:
                for include_inactive in [True, False]:
                    cache_key = cls._get_cache_key(category, language, include_inactive)
                    cache.delete(cache_key)
        else:
            # Delete all lookup cache
            try:
                if hasattr(cache, 'delete_pattern'):
                    cache.delete_pattern(f"{cls.CACHE_PREFIX}:*")
            except Exception:
                pass

    @classmethod
    def _get_cache_key(
        cls,
        category: str,
        language: str,
        include_inactive: bool
    ) -> str:
        """Generate cache key."""
        inactive_suffix = '_all' if include_inactive else ''
        return f"{cls.CACHE_PREFIX}:{category}:{language}{inactive_suffix}"

    @classmethod
    def seed_from_dict(cls, category: str, items: List[Dict]) -> int:
        """
        Seed lookup data from a dictionary.

        Useful for initial data setup.

        Args:
            category: Category code
            items: List of dicts with keys: code, name_en, name_ml, description, display_order

        Returns:
            Number of items created/updated
        """
        count = 0

        for i, item in enumerate(items):
            obj, created = MasterLookup.objects.update_or_create(
                category=category,
                code=item['code'],
                defaults={
                    'name_en': item.get('name_en', ''),
                    'name_ml': item.get('name_ml', ''),
                    'description': item.get('description', ''),
                    'display_order': item.get('display_order', i * 10),
                    'metadata': item.get('metadata', {}),
                    'is_active': item.get('is_active', True),
                }
            )
            count += 1

        # Invalidate cache
        cls.invalidate_cache(category)

        return count
