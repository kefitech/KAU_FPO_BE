"""
Cache Utilities for KAU-FPO Platform
====================================

Helper functions for working with Django cache (Redis).

Features:
- Cache key generation with prefixes
- Cache invalidation patterns
- Decorator for caching function results

Usage:
    from apps.core.utils.cache import cache_key, get_or_set_cache

    key = cache_key('user', user_id)  # Returns: 'kau_fpo:user:123'
    data = get_or_set_cache(key, expensive_function, ttl=3600)
"""

from typing import Any, Callable, Optional, List
from functools import wraps
from django.core.cache import cache
from django.conf import settings

from .constants import CACHE_TTL_SHORT, CACHE_TTL_MEDIUM, CACHE_TTL_LONG, CACHE_KEY_PREFIX


# =============================================================================
# CACHE KEY MANAGEMENT
# =============================================================================

# Global prefix for all cache keys
APP_CACHE_PREFIX = getattr(settings, 'CACHE_KEY_PREFIX', 'kau_fpo')


def cache_key(*parts) -> str:
    """
    Generate a cache key with app prefix.

    Args:
        *parts: Key parts to join

    Returns:
        Cache key string

    Example:
        cache_key('user', 123) -> 'kau_fpo:user:123'
        cache_key('fpo', 'list', 'TSR') -> 'kau_fpo:fpo:list:TSR'
    """
    parts_str = [str(p) for p in parts if p is not None]
    return f"{APP_CACHE_PREFIX}:{':'.join(parts_str)}"


def cache_key_pattern(prefix: str) -> str:
    """
    Generate a cache key pattern for bulk invalidation.

    Args:
        prefix: Key prefix

    Returns:
        Pattern string for delete_pattern

    Example:
        cache_key_pattern('user') -> 'kau_fpo:user:*'
    """
    return f"{APP_CACHE_PREFIX}:{prefix}:*"


# =============================================================================
# CACHE OPERATIONS
# =============================================================================

def get_cache(key: str) -> Optional[Any]:
    """
    Get value from cache.

    Args:
        key: Cache key

    Returns:
        Cached value or None
    """
    return cache.get(key)


def set_cache(key: str, value: Any, ttl: int = CACHE_TTL_MEDIUM) -> bool:
    """
    Set value in cache.

    Args:
        key: Cache key
        value: Value to cache
        ttl: Time-to-live in seconds

    Returns:
        True if successful
    """
    cache.set(key, value, ttl)
    return True


def delete_cache(key: str) -> bool:
    """
    Delete a cache key.

    Args:
        key: Cache key

    Returns:
        True if deleted
    """
    cache.delete(key)
    return True


def delete_cache_pattern(pattern: str) -> int:
    """
    Delete all keys matching a pattern.

    Note: This requires a cache backend that supports pattern deletion
    (like django-redis with Redis backend).

    Args:
        pattern: Key pattern with wildcards

    Returns:
        Number of keys deleted
    """
    try:
        # django-redis specific
        if hasattr(cache, 'delete_pattern'):
            return cache.delete_pattern(pattern)
        else:
            # Fallback: not supported by all backends
            return 0
    except Exception:
        return 0


def get_or_set_cache(
    key: str,
    default_func: Callable,
    ttl: int = CACHE_TTL_MEDIUM,
    *args,
    **kwargs
) -> Any:
    """
    Get from cache or compute and cache the value.

    Args:
        key: Cache key
        default_func: Function to compute value if not cached
        ttl: Time-to-live in seconds
        *args: Arguments for default_func
        **kwargs: Keyword arguments for default_func

    Returns:
        Cached or computed value
    """
    value = cache.get(key)

    if value is None:
        value = default_func(*args, **kwargs)
        if value is not None:
            cache.set(key, value, ttl)

    return value


def cache_many(data: dict, ttl: int = CACHE_TTL_MEDIUM) -> bool:
    """
    Set multiple cache values at once.

    Args:
        data: Dictionary of key-value pairs
        ttl: Time-to-live in seconds

    Returns:
        True if successful
    """
    cache.set_many(data, ttl)
    return True


def get_cache_many(keys: List[str]) -> dict:
    """
    Get multiple cache values at once.

    Args:
        keys: List of cache keys

    Returns:
        Dictionary of key-value pairs (missing keys not included)
    """
    return cache.get_many(keys)


def delete_cache_many(keys: List[str]) -> bool:
    """
    Delete multiple cache keys at once.

    Args:
        keys: List of cache keys

    Returns:
        True if successful
    """
    cache.delete_many(keys)
    return True


def clear_all_cache() -> bool:
    """
    Clear all cache (use with caution!).

    Returns:
        True if successful
    """
    cache.clear()
    return True


# =============================================================================
# CACHE DECORATORS
# =============================================================================

def cached(
    key_prefix: str,
    ttl: int = CACHE_TTL_MEDIUM,
    key_builder: Callable = None
):
    """
    Decorator to cache function results.

    Args:
        key_prefix: Prefix for cache key
        ttl: Time-to-live in seconds
        key_builder: Optional function to build key from args

    Example:
        @cached('user_profile', ttl=3600)
        def get_user_profile(user_id):
            return User.objects.get(id=user_id)

        # Cache key: kau_fpo:user_profile:<user_id>
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Build cache key
            if key_builder:
                key_suffix = key_builder(*args, **kwargs)
            else:
                # Default: use positional args as key suffix
                key_suffix = ':'.join(str(a) for a in args)

            key = cache_key(key_prefix, key_suffix) if key_suffix else cache_key(key_prefix)

            # Try to get from cache
            result = cache.get(key)
            if result is not None:
                return result

            # Compute and cache
            result = func(*args, **kwargs)
            if result is not None:
                cache.set(key, result, ttl)

            return result

        # Add method to invalidate this function's cache
        def invalidate(*args, **kwargs):
            if key_builder:
                key_suffix = key_builder(*args, **kwargs)
            else:
                key_suffix = ':'.join(str(a) for a in args)
            key = cache_key(key_prefix, key_suffix) if key_suffix else cache_key(key_prefix)
            cache.delete(key)

        wrapper.invalidate = invalidate
        wrapper.invalidate_all = lambda: delete_cache_pattern(cache_key_pattern(key_prefix))

        return wrapper

    return decorator


# =============================================================================
# CACHE KEY BUILDERS FOR COMMON PATTERNS
# =============================================================================

def user_cache_key(user_id: int) -> str:
    """Cache key for user data."""
    return cache_key('user', user_id)


def fpo_cache_key(fpo_id: int) -> str:
    """Cache key for FPO data."""
    return cache_key('fpo', fpo_id)


def lookup_cache_key(category: str, language: str = 'en') -> str:
    """Cache key for master lookup data."""
    return cache_key('lookup', category, language)


def template_cache_key(code: str, channel: str) -> str:
    """Cache key for notification templates."""
    return cache_key('template', channel, code)


# =============================================================================
# CACHE INVALIDATION HELPERS
# =============================================================================

def invalidate_user_cache(user_id: int) -> bool:
    """Invalidate all cache for a user."""
    delete_cache(user_cache_key(user_id))
    return True


def invalidate_fpo_cache(fpo_id: int) -> bool:
    """Invalidate all cache for an FPO."""
    delete_cache(fpo_cache_key(fpo_id))
    return True


def invalidate_lookup_cache(category: str = None) -> bool:
    """
    Invalidate lookup cache for all active languages.
    Loops active languages from DB so adding Tamil/Hindi is automatic.
    """
    if category:
        try:
            from apps.database.models import Language
            lang_codes = Language.objects.filter(is_active=True).values_list('code', flat=True)
        except Exception:
            lang_codes = ['en', 'ml']
        for code in lang_codes:
            delete_cache(lookup_cache_key(category, code))
    else:
        delete_cache_pattern(cache_key_pattern('lookup'))
    return True


def invalidate_template_cache(code: str = None, channel: str = None) -> bool:
    """
    Invalidate notification template cache.

    Args:
        code: Specific template code or None for all
        channel: Specific channel or None for all
    """
    if code and channel:
        delete_cache(template_cache_key(code, channel))
    else:
        delete_cache_pattern(cache_key_pattern('template'))
    return True
