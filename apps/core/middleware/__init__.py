"""
Middleware Module
=================

Custom middleware for the KAU-FPO Platform.

Available middleware:
- LanguageDetectionMiddleware: Detect user's preferred language
- RequestContextMiddleware: Add context to requests (IP, AJAX)
- CurrentRequestMiddleware: Store request in thread-local (for signals)
- AuditMiddleware: Log requests for audit
- RequestTimingMiddleware: Add timing headers

Usage in settings.py:
    MIDDLEWARE = [
        ...
        'apps.core.middleware.RequestContextMiddleware',
        'apps.core.middleware.LanguageDetectionMiddleware',
        'apps.core.middleware.CurrentRequestMiddleware',
        'apps.core.middleware.AuditMiddleware',
        ...
    ]
"""

from .locale import (
    LanguageDetectionMiddleware,
    RequestContextMiddleware,
)

from .audit import (
    CurrentRequestMiddleware,
    AuditMiddleware,
    RequestTimingMiddleware,
    get_current_request,
    get_current_user,
)

__all__ = [
    'LanguageDetectionMiddleware',
    'RequestContextMiddleware',
    'CurrentRequestMiddleware',
    'AuditMiddleware',
    'RequestTimingMiddleware',
    'get_current_request',
    'get_current_user',
]
