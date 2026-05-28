"""
OpenAPI Schema Extensions for KAU-FPO Platform
================================================

Custom schema extensions for drf-spectacular to properly document
custom authentication classes in the OpenAPI/Swagger documentation.

Classes:
- JWTCookieAuthenticationScheme: Schema for cookie-based JWT authentication

Author: Athul Gopan
Created: 22-04-2026
"""

from drf_spectacular.extensions import OpenApiAuthenticationExtension


class JWTCookieAuthenticationScheme(OpenApiAuthenticationExtension):
    """
    OpenAPI authentication scheme for JWTCookieAuthentication.

    This extension tells drf-spectacular how to document the custom
    JWT cookie authentication in the OpenAPI schema.

    Supports both:
    1. Authorization header (Bearer token) - for API testing tools
    2. HTTP-only cookie (access_token) - for browser-based clients
    """

    target_class = 'apps.core.authentication.JWTCookieAuthentication'
    name = 'jwtCookieAuth'

    def get_security_definition(self, auto_schema):
        """
        Define the security scheme for OpenAPI documentation.

        Returns:
            dict: Security scheme definition with both Bearer token and cookie support
        """
        return {
            'type': 'http',
            'scheme': 'bearer',
            'bearerFormat': 'JWT',
            'description': (
                'JWT authentication using either:\n'
                '1. **Authorization header**: `Bearer <access_token>` (for API testing)\n'
                '2. **HTTP-only cookie**: `access_token=<token>` (for browser clients)\n\n'
                'The cookie-based approach is preferred for production as it provides '
                'better security against XSS attacks.'
            )
        }
