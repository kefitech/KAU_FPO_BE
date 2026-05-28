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
KAU-FPO Backend - Development Settings
======================================

Development-specific settings.
Inherits from base.py and overrides for local development.

Usage:
    export DJANGO_SETTINGS_MODULE=config.settings.development
    python manage.py runserver

Author:
    Athul Gopan
Created On:
    21-04-2026
"""

from .base import *

# =============================================================================
# DEBUG MODE
# =============================================================================

DEBUG = True

# =============================================================================
# ALLOWED HOSTS
# =============================================================================

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0', '*']

# =============================================================================
# DATABASE (Use SQLite for quick local setup, or PostgreSQL)
# =============================================================================

# Option 1: SQLite (simpler for quick testing)
# Uncomment if you don't have PostgreSQL installed
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.sqlite3',
#         'NAME': BASE_DIR / 'db.sqlite3',
#     }
# }

# Option 2: PostgreSQL (default - matches production)
# Uses settings from base.py (reads from .env)

# =============================================================================
# CACHING (Local Memory Cache for development)
# =============================================================================

# Use local memory cache if Redis not available
# Uncomment to switch from Redis to local memory
# CACHES = {
#     'default': {
#         'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
#         'LOCATION': 'unique-snowflake',
#     }
# }

# =============================================================================
# EMAIL (Console Backend for development)
# =============================================================================

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# =============================================================================
# SMS (Console logging for development)
# =============================================================================

SMS_PROVIDER = 'console'

# =============================================================================
# DJANGO DEBUG TOOLBAR
# =============================================================================

# Only install if django-debug-toolbar is installed
try:
    import debug_toolbar
    INSTALLED_APPS += ['debug_toolbar']
    MIDDLEWARE.insert(0, 'debug_toolbar.middleware.DebugToolbarMiddleware')

    # Debug toolbar settings
    DEBUG_TOOLBAR_CONFIG = {
        'SHOW_TOOLBAR_CALLBACK': lambda request: DEBUG,
        'INTERCEPT_REDIRECTS': False,
    }

    INTERNAL_IPS = [
        '127.0.0.1',
        'localhost',
    ]
except ImportError:
    pass

# =============================================================================
# REST FRAMEWORK DEVELOPMENT OVERRIDES
# =============================================================================

REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES'] = [
    'rest_framework.renderers.JSONRenderer',
    'rest_framework.renderers.BrowsableAPIRenderer',  # Enable browsable API
]

# Disable global throttling in development, but keep rates defined
# so per-view throttle_classes= don't crash with ImproperlyConfigured
REST_FRAMEWORK['DEFAULT_THROTTLE_CLASSES'] = []

# =============================================================================
# CORS (Allow all in development)
# =============================================================================

CORS_ALLOW_ALL_ORIGINS = True

# =============================================================================
# LOGGING (Clean output in development)
# =============================================================================

# Reduce noise from autoreloader
LOGGING['loggers']['django.utils.autoreload'] = {
    'level': 'INFO',
    'handlers': ['console'],
    'propagate': False,
}

LOGGING['loggers']['apps']['level'] = 'INFO'
LOGGING['loggers']['django']['level'] = 'INFO'
LOGGING['loggers']['django.db.backends'] = {
    'level': 'DEBUG' if config('LOG_SQL', default=False, cast=bool) else 'INFO',
    'handlers': ['console'],
    'propagate': False,
}

# Override root logger to be less verbose
LOGGING['root']['level'] = 'INFO'

# =============================================================================
# PASSWORD VALIDATION (Relaxed for development)
# =============================================================================

# Uncomment to disable password validation in development
# AUTH_PASSWORD_VALIDATORS = []

# =============================================================================
# SESSION (File-based session if Redis not available)
# =============================================================================

# Uncomment if Redis not available
# SESSION_ENGINE = 'django.contrib.sessions.backends.file'
# SESSION_FILE_PATH = BASE_DIR / 'sessions'

# =============================================================================
# CELERY (Eager mode for synchronous testing)
# =============================================================================

# Uncomment to run Celery tasks synchronously (without broker)
# CELERY_TASK_ALWAYS_EAGER = True
# CELERY_TASK_EAGER_PROPAGATES = True

# =============================================================================
# FILE STORAGE (Local for development)
# =============================================================================

USE_S3 = False
DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'

# =============================================================================
# API DOCUMENTATION
# =============================================================================

SPECTACULAR_SETTINGS['SERVERS'] = [
    {'url': 'http://localhost:8000', 'description': 'Development Server'},
]

# =============================================================================
# SECURITY (Relaxed for development)
# =============================================================================

SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# =============================================================================
# DEVELOPMENT HELPERS
# =============================================================================

# Show all SQL queries in console (set LOG_SQL=True in .env)
# Very verbose, use only when debugging queries

# Print emails to console
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Allow weak passwords in development (uncomment if needed)
# AUTH_PASSWORD_VALIDATORS = []
