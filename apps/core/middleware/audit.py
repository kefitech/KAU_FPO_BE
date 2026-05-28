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
Audit Middleware for KAU-FPO Platform
=====================================

Logs important requests for security and debugging.

Features:
- Logs sensitive operations (POST, PUT, DELETE)
- Captures request metadata (IP, user agent, path)
- Can be configured to log to database or file

Usage:
    Add to MIDDLEWARE in settings:
    'apps.core.middleware.audit.AuditMiddleware',

Author:
    Athul Gopan

Created On:
    21-04-2026
"""

import time
import logging
from threading import local

from django.conf import settings

logger = logging.getLogger('audit')

# Thread-local storage for request context
_request_local = local()


def get_current_request():
    """Get the current request from thread-local storage."""
    return getattr(_request_local, 'request', None)


def get_current_user():
    """Get the current user from thread-local storage."""
    request = get_current_request()
    if request and hasattr(request, 'user'):
        return request.user
    return None


class CurrentRequestMiddleware:
    """
    Middleware to store current request in thread-local storage.

    This allows access to request in model signals and other places
    where request object is not directly available.

    Usage:
        from apps.core.middleware.audit import get_current_request, get_current_user

        current_user = get_current_user()
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Store request in thread-local
        _request_local.request = request

        try:
            response = self.get_response(request)
        finally:
            # Clear thread-local
            _request_local.request = None

        return response


class AuditMiddleware:
    """
    Middleware to log requests for audit purposes.

    Logs:
    - All authenticated requests
    - All write operations (POST, PUT, PATCH, DELETE)
    - Failed authentication attempts (401)
    - Permission denied (403)

    Configuration (in settings.py):
        AUDIT_LOG_ENABLED = True
        AUDIT_LOG_METHODS = ['POST', 'PUT', 'PATCH', 'DELETE']
        AUDIT_LOG_EXCLUDE_PATHS = ['/api/health/', '/api/metrics/']
    """

    # Default methods to log
    LOG_METHODS = ['POST', 'PUT', 'PATCH', 'DELETE']

    # Paths to exclude from logging
    EXCLUDE_PATHS = [
        '/api/health/',
        '/api/healthcheck/',
        '/api/metrics/',
        '/admin/jsi18n/',
    ]

    def __init__(self, get_response):
        self.get_response = get_response
        self.enabled = getattr(settings, 'AUDIT_LOG_ENABLED', True)
        self.log_methods = getattr(settings, 'AUDIT_LOG_METHODS', self.LOG_METHODS)
        self.exclude_paths = getattr(settings, 'AUDIT_LOG_EXCLUDE_PATHS', self.EXCLUDE_PATHS)

    def __call__(self, request):
        if not self.enabled:
            return self.get_response(request)

        # Skip excluded paths
        if self._should_skip(request):
            return self.get_response(request)

        # Capture start time
        start_time = time.time()

        # Process request
        response = self.get_response(request)

        # Calculate duration
        duration_ms = (time.time() - start_time) * 1000

        # Log the request
        self._log_request(request, response, duration_ms)

        return response

    def _should_skip(self, request) -> bool:
        """Check if request should be skipped."""
        path = request.path

        # Skip excluded paths
        for exclude_path in self.exclude_paths:
            if path.startswith(exclude_path):
                return True

        return False

    def _should_log(self, request, response) -> bool:
        """Determine if request should be logged."""
        # Always log write operations
        if request.method in self.log_methods:
            return True

        # Always log authentication failures
        if response.status_code == 401:
            return True

        # Always log permission denied
        if response.status_code == 403:
            return True

        # Log authenticated requests (optional)
        if hasattr(request, 'user') and request.user.is_authenticated:
            return True

        return False

    def _log_request(self, request, response, duration_ms: float):
        """Log the request details."""
        if not self._should_log(request, response):
            return

        # Extract user info
        user_str = 'anonymous'
        user_id = None
        if hasattr(request, 'user') and request.user.is_authenticated:
            user_str = request.user.email
            user_id = request.user.id

        # Extract client info
        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get('User-Agent', '')[:200]

        # Build log entry
        log_data = {
            'user': user_str,
            'user_id': user_id,
            'method': request.method,
            'path': request.path,
            'status': response.status_code,
            'duration_ms': round(duration_ms, 2),
            'ip': client_ip,
            'user_agent': user_agent,
        }

        # Add query params for non-GET requests
        if request.method != 'GET' and request.GET:
            log_data['query_params'] = dict(request.GET)

        # Log level based on status code
        if response.status_code >= 500:
            logger.error("REQUEST", extra=log_data)
        elif response.status_code >= 400:
            logger.warning("REQUEST", extra=log_data)
        else:
            logger.info("REQUEST", extra=log_data)

    def _get_client_ip(self, request) -> str:
        """Extract client IP from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '')


class RequestTimingMiddleware:
    """
    Middleware to add timing information to responses.

    Adds X-Request-Time header with processing time in milliseconds.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start_time = time.time()

        response = self.get_response(request)

        duration_ms = (time.time() - start_time) * 1000
        response['X-Request-Time'] = f'{duration_ms:.2f}ms'

        return response
