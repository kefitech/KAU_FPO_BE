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
Exception Handlers for KAU-FPO Platform
=======================================

Custom DRF exception handler that:
- Converts all exceptions to standard response format
- Handles custom exceptions
- Logs errors appropriately
- Returns bilingual messages when possible

Usage in settings.py:
    REST_FRAMEWORK = {
        'EXCEPTION_HANDLER': 'apps.core.exceptions.handlers.custom_exception_handler',
    }
Author:
    Athul Gopan

Created On:
    21-04-2026
"""

import logging

from django.core.exceptions import (
    ValidationError as DjangoValidationError,
    PermissionDenied as DjangoPermissionDenied,
    ObjectDoesNotExist,
)
from django.http import Http404
from rest_framework import status
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework.exceptions import (
    ValidationError as DRFValidationError,
    AuthenticationFailed,
    NotAuthenticated,
    PermissionDenied as DRFPermissionDenied,
    NotFound,
    MethodNotAllowed,
    Throttled,
)

from .base import BaseAPIException
from apps.core.services.translation import t
from apps.core.utils.helpers import get_client_ip

logger = logging.getLogger('exceptions')


def custom_exception_handler(exc, context):
    """
    Custom exception handler for DRF.

    Converts all exceptions to standard response format:
    {
        "status": "error",
        "message": "Human-readable message",
        "code": "error_code",
        "errors": {...}  # For validation errors
    }

    Args:
        exc: The exception instance
        context: Request context

    Returns:
        Response object
    """
    # Get request for language detection
    request = context.get('request')
    language = getattr(request, 'language', 'en') if request else 'en'

    # Call DRF's default exception handler first
    response = exception_handler(exc, context)

    # Handle our custom exceptions
    if isinstance(exc, BaseAPIException):
        return _handle_custom_exception(exc, context)

    # Handle Django's validation error
    if isinstance(exc, DjangoValidationError):
        return _handle_django_validation_error(exc, language)

    # Handle Django's permission denied
    if isinstance(exc, DjangoPermissionDenied):
        return _handle_permission_denied(language)

    # Handle object does not exist
    if isinstance(exc, ObjectDoesNotExist):
        return _handle_not_found(language)

    # Handle 404
    if isinstance(exc, Http404):
        return _handle_not_found(language)

    # If DRF handled it, convert to standard format
    if response is not None:
        return _convert_drf_response(exc, response, language)

    # Unhandled exception - log and return 500
    logger.exception(
        "Unhandled exception",
        extra={
            'exception_type': type(exc).__name__,
            'exception_message': str(exc),
            'path': request.path if request else 'unknown',
            'user': request.user.email if request and request.user.is_authenticated else 'anonymous',
            'ip': get_client_ip(request) if request else 'unknown',
        }
    )

    return Response(
        {
            "status": "error",
            "message": t('common.server_error', language),
            "code": "server_error",
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR
    )


def _handle_custom_exception(exc: BaseAPIException, context) -> Response:
    """Handle our custom BaseAPIException."""
    # Log error-level exceptions
    if exc.status_code >= 500:
        request = context.get('request')
        logger.error(
            f"Server error: {exc.message}",
            extra={
                'code': exc.code,
                'path': request.path if request else 'unknown',
            }
        )

    return Response(exc.to_dict(), status=exc.status_code)


def _handle_django_validation_error(exc: DjangoValidationError, language: str) -> Response:
    """Handle Django's ValidationError."""
    if hasattr(exc, 'message_dict'):
        errors = exc.message_dict
    elif hasattr(exc, 'messages'):
        errors = {'non_field_errors': exc.messages}
    else:
        errors = {'non_field_errors': [str(exc)]}

    return Response(
        {
            "status": "error",
            "message": t('common.bad_request', language),
            "code": "validation_error",
            "errors": errors,
        },
        status=status.HTTP_400_BAD_REQUEST
    )


def _handle_permission_denied(language: str) -> Response:
    """Handle permission denied."""
    return Response(
        {
            "status": "error",
            "message": t('common.permission_denied', language),
            "code": "permission_denied",
        },
        status=status.HTTP_403_FORBIDDEN
    )


def _handle_not_found(language: str) -> Response:
    """Handle not found."""
    return Response(
        {
            "status": "error",
            "message": t('common.not_found', language),
            "code": "not_found",
        },
        status=status.HTTP_404_NOT_FOUND
    )


def _convert_drf_response(exc, response: Response, language: str) -> Response:
    """Convert DRF's response to standard format."""
    data = response.data
    status_code = response.status_code

    # Determine error code and message
    if isinstance(exc, DRFValidationError):
        code = "validation_error"
        message = t('common.bad_request', language)
        errors = _normalize_errors(data)
        return Response(
            {
                "status": "error",
                "message": message,
                "code": code,
                "errors": errors,
            },
            status=status_code
        )

    elif isinstance(exc, (AuthenticationFailed, NotAuthenticated)):
        code = "authentication_failed"
        message = t('common.unauthorized', language)

    elif isinstance(exc, DRFPermissionDenied):
        code = "permission_denied"
        message = t('common.permission_denied', language)

    elif isinstance(exc, NotFound):
        code = "not_found"
        message = t('common.not_found', language)

    elif isinstance(exc, MethodNotAllowed):
        code = "method_not_allowed"
        message = f"Method '{exc.detail}' not allowed"

    elif isinstance(exc, Throttled):
        code = "rate_limit_exceeded"
        wait = exc.wait
        message = t('common.rate_limited', language, seconds=int(wait) if wait else 60)

    else:
        code = "error"
        message = str(data.get('detail', data)) if isinstance(data, dict) else str(data)

    return Response(
        {
            "status": "error",
            "message": message,
            "code": code,
        },
        status=status_code
    )


def _normalize_errors(data) -> dict:
    """
    Normalize validation errors to consistent format.

    DRF can return errors in different formats:
    - {"field": ["error1", "error2"]}
    - {"field": [{"message": "error", "code": "invalid"}]}
    - ["error1", "error2"]

    We normalize to: {"field": ["error1", "error2"]}
    """
    if isinstance(data, list):
        return {"non_field_errors": data}

    if isinstance(data, dict):
        normalized = {}
        for field, errors in data.items():
            if isinstance(errors, list):
                normalized[field] = [
                    e['message'] if isinstance(e, dict) and 'message' in e else str(e)
                    for e in errors
                ]
            else:
                normalized[field] = [str(errors)]
        return normalized

    return {"non_field_errors": [str(data)]}
