"""
Cookie Utilities for KAU-FPO Platform
=====================================

Utilities for managing HTTP-only cookies for JWT token storage.

Features:
- Secure cookie settings (HttpOnly, Secure, SameSite)
- Access and refresh token cookie management
- CSRF-safe cookie operations

Author: Athul Gopan
Created: 22-04-2026
"""

from typing import Optional
from django.conf import settings
from django.http import HttpResponse
from rest_framework_simplejwt.tokens import RefreshToken


# Cookie names
ACCESS_TOKEN_COOKIE = 'access_token'
REFRESH_TOKEN_COOKIE = 'refresh_token'


def get_cookie_settings(is_access_token: bool = True) -> dict:
    """
    Get secure cookie settings.

    Args:
        is_access_token: True for access token, False for refresh token

    Returns:
        Dictionary of cookie settings
    """
    # Get token lifetime from JWT settings
    if is_access_token:
        max_age = int(settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'].total_seconds())
    else:
        max_age = int(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds())

    return {
        'max_age': max_age,
        'httponly': True,  # Prevents JavaScript access (XSS protection)
        'secure': not settings.DEBUG,  # HTTPS only in production
        'samesite': 'Lax',  # CSRF protection (Lax allows top-level navigation)
        'path': '/',
    }


def set_jwt_cookies(response: HttpResponse, refresh_token_obj) -> HttpResponse:
    """
    Set JWT access and refresh tokens as HTTP-only cookies.

    Args:
        response: HTTP response object
        refresh_token_obj: Already-generated RefreshToken instance

    Returns:
        Response with cookies set
    """
    access_token = str(refresh_token_obj.access_token)
    refresh_token = str(refresh_token_obj)

    # Set access token cookie
    access_settings = get_cookie_settings(is_access_token=True)
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=access_token,
        **access_settings
    )

    # Set refresh token cookie
    refresh_settings = get_cookie_settings(is_access_token=False)
    response.set_cookie(
        key=REFRESH_TOKEN_COOKIE,
        value=refresh_token,
        **refresh_settings
    )

    return response


def clear_jwt_cookies(response: HttpResponse) -> HttpResponse:
    """
    Clear JWT cookies on logout.

    Args:
        response: HTTP response object

    Returns:
        Response with cookies deleted
    """
    # delete_cookie() only accepts: path, domain, samesite
    # (httponly and secure are not needed for deletion)
    cookie_settings = {
        'path': '/',
        'samesite': 'Lax',
    }

    response.delete_cookie(ACCESS_TOKEN_COOKIE, **cookie_settings)
    response.delete_cookie(REFRESH_TOKEN_COOKIE, **cookie_settings)

    return response


def get_access_token_from_cookie(request) -> Optional[str]:
    """
    Extract access token from cookie.

    Args:
        request: HTTP request object

    Returns:
        Access token string or None
    """
    return request.COOKIES.get(ACCESS_TOKEN_COOKIE)


def get_refresh_token_from_cookie(request) -> Optional[str]:
    """
    Extract refresh token from cookie.

    Args:
        request: HTTP request object

    Returns:
        Refresh token string or None
    """
    return request.COOKIES.get(REFRESH_TOKEN_COOKIE)
