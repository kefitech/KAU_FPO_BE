"""
██╗  ██╗███████╗███████╗██╗    ████████╗███████╗ ██████╗██╗  ██╗
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
KAU-FPO Backend - Production Settings
=====================================

Production-specific settings.
Inherits from base.py and adds security hardening.

IMPORTANT:
    - Never set DEBUG = True
    - Always use environment variables for secrets
    - Review all security settings before deployment

Usage:
    export DJANGO_SETTINGS_MODULE=config.settings.production
    gunicorn config.wsgi:application

Author:
    Athul Gopan
Created On:
    21-04-2026
"""

from .base import *

# =============================================================================
# DEBUG MODE (Never True in production!)
# =============================================================================

DEBUG = False

# =============================================================================
# ALLOWED HOSTS (Must be explicitly set)
# =============================================================================

# Read from environment variable
# Example: ALLOWED_HOSTS=api.kau-fpo.in,www.kau-fpo.in
ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=Csv())

# =============================================================================
# SECURITY SETTINGS
# =============================================================================

# HTTPS settings
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=True, cast=bool)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# HSTS (HTTP Strict Transport Security)
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Cookie security
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7  # 1 week
SESSION_COOKIE_SAMESITE = 'Lax'

CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    default='',
    cast=Csv()
)

# Content security
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'DENY'

# =============================================================================
# DATABASE (Production PostgreSQL)
# =============================================================================

DATABASES['default']['OPTIONS'] = {
    'connect_timeout': 10,
    'options': '-c statement_timeout=30000',  # 30 second query timeout
}

# =============================================================================
# CACHING (Redis - required in production)
# =============================================================================

# Redis is required in production
# CACHES configuration is inherited from base.py

# Session using Redis cache
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'

# =============================================================================
# EMAIL (Production SMTP or SES)
# =============================================================================

EMAIL_BACKEND = config(
    'EMAIL_BACKEND',
    default='django.core.mail.backends.smtp.EmailBackend'
)

# For AWS SES, use:
# EMAIL_BACKEND = 'django_ses.SESBackend'

# =============================================================================
# FILE STORAGE (S3 in production)
# =============================================================================

USE_S3 = config('USE_S3', default=True, cast=bool)

if USE_S3:
    # S3 storage for media files
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'

    # Optional: Use CloudFront CDN
    AWS_S3_CUSTOM_DOMAIN = config('AWS_S3_CUSTOM_DOMAIN', default='')

# =============================================================================
# STATIC FILES (WhiteNoise)
# =============================================================================

# Insert WhiteNoise middleware after SecurityMiddleware
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')

# WhiteNoise settings
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# =============================================================================
# REST FRAMEWORK PRODUCTION OVERRIDES
# =============================================================================

# Only JSON renderer in production (no browsable API)
REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES'] = [
    'rest_framework.renderers.JSONRenderer',
]

# Stricter throttling for production
REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] = {
    'anon':              '50/hour',
    'user':              '500/hour',
    'login':             '5/minute',
    'forgot_password':   '3/minute',
    'otp_verify':        '5/minute',
    'register':          '3/minute',
    'two_factor_login':  '5/minute',
    'two_factor_setup':  '10/minute',
    'disable_2fa_otp':   '3/minute',
}

# =============================================================================
# CORS (Strict in production)
# =============================================================================

CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    cast=Csv()
)

# =============================================================================
# LOGGING (Production logging)
# =============================================================================

# More concise logging in production
LOGGING['handlers']['console']['formatter'] = 'json'

# Add Sentry for error tracking (optional)
SENTRY_DSN = config('SENTRY_DSN', default='')

if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.redis import RedisIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            DjangoIntegration(),
            CeleryIntegration(),
            RedisIntegration(),
        ],
        environment=config('ENVIRONMENT', default='production'),
        traces_sample_rate=config('SENTRY_TRACES_SAMPLE_RATE', default=0.1, cast=float),
        send_default_pii=False,  # Don't send PII
    )

# =============================================================================
# API DOCUMENTATION
# =============================================================================

# Update servers for production
SPECTACULAR_SETTINGS['SERVERS'] = [
    {'url': config('API_URL', default='https://api.kau-fpo.in'), 'description': 'Production'},
]

# Optionally disable docs in production
SPECTACULAR_SETTINGS['SERVE_INCLUDE_SCHEMA'] = config('SERVE_API_DOCS', default=False, cast=bool)

# =============================================================================
# CELERY PRODUCTION SETTINGS
# =============================================================================

# Ensure tasks are properly acknowledged
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True

# Concurrency limits
CELERY_WORKER_CONCURRENCY = config('CELERY_CONCURRENCY', default=4, cast=int)
CELERY_WORKER_PREFETCH_MULTIPLIER = 2

# =============================================================================
# ADMINS (For error emails)
# =============================================================================

ADMINS = [
    ('Admin', config('ADMIN_EMAIL', default='admin@kau-fpo.in')),
]

MANAGERS = ADMINS

# =============================================================================
# HEALTH CHECK
# =============================================================================

try:
    import health_check
    INSTALLED_APPS += [
        'health_check',
        'health_check.db',
        'health_check.cache',
        'health_check.storage',
    ]
except ImportError:
    pass

# =============================================================================
# PERFORMANCE OPTIMIZATIONS
# =============================================================================

# Data upload limits
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB

