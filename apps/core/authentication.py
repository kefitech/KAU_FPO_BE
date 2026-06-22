"""
Custom Authentication Classes for KAU-FPO Platform
==================================================

Custom authentication backends that support cookie-based JWT tokens.

Classes:
- JWTCookieAuthentication: JWT authentication using HTTP-only cookies

Author: Athul Gopan
Created: 22-04-2026
"""

from typing import Optional, Tuple
from django.contrib.auth.models import User
from rest_framework.request import Request
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import Token
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from apps.core.utils.cookies import get_access_token_from_cookie


class JWTCookieAuthentication(JWTAuthentication):
    """
    Custom JWT authentication that reads tokens from HTTP-only cookies.

    This provides better security than Authorization header by:
    1. Storing tokens in HttpOnly cookies (prevents XSS attacks)
    2. Using SameSite cookie attribute (prevents CSRF attacks)
    3. Automatic token sending by browser (no manual header management)

    Fallback to Authorization header if cookie is not present.
    """

    def authenticate(self, request: Request) -> Optional[Tuple[User, Token]]:
        """
        Authenticate request using JWT token from cookie or header.

        Priority:
        1. Try cookie-based authentication
        2. Fall back to Authorization header (Swagger / Postman)

        If the cookie token is invalid or expired, we return None instead of
        raising — this allows AllowAny endpoints (like /login/) to still work
        even when the browser has a stale cookie sitting around.
        """
        raw_token = get_access_token_from_cookie(request)

        if raw_token:
            try:
                validated_token = super().get_validated_token(raw_token)
                return self.get_user(validated_token), validated_token
            except (InvalidToken, TokenError):
                # Stale/expired cookie — fall through to header auth
                pass

        # Fall back to Authorization header (used by Swagger / Postman)
        try:
            return super().authenticate(request)
        except (InvalidToken, TokenError, AuthenticationFailed):
            return None
