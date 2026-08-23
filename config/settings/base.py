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
KAU-FPO Backend - Base Settings
===============================

Common settings for all environments.
Environment-specific settings are in development.py and production.py.

Author:
    Athul Gopan
Created On:
    21-04-2026
"""

import os
from pathlib import Path
from datetime import timedelta
from decouple import config, Csv

# =============================================================================
# PATH CONFIGURATION
# =============================================================================

# Build paths inside the project like this: BASE_DIR / 'subdir'.
# BASE_DIR points to the project root (where manage.py is)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# =============================================================================
# CORE SETTINGS
# =============================================================================

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY', default='django-insecure-change-this-in-production')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=False, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())

# Site URL for email links, etc.
SITE_URL = config('SITE_URL', default='http://localhost:8000')
ML_SERVICE_URL = config('ML_SERVICE_URL', default='http://localhost:8001')
ML_MODELS_DIR = config('ML_MODELS_DIR', default=str(BASE_DIR.parent / 'ml_models'))
FRONTEND_URL = config('FRONTEND_URL', default='http://localhost:3000')

# =============================================================================
# APPLICATION DEFINITION
# =============================================================================

DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.gis',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'drf_spectacular',
    'django_filters',
]

LOCAL_APPS = [
    'apps.core.apps.CoreConfig',
    'apps.database.apps.DatabaseConfig',
    'apps.accounts.apps.AccountsConfig',
    'apps.fpo.apps.FpoConfig',
    'apps.notifications.apps.NotificationsConfig',
    'apps.experts.apps.ExpertsConfig',
    'apps.marketplace.apps.MarketplaceConfig',
    'apps.recommendations.apps.RecommendationsConfig',
    'apps.analytics.apps.AnalyticsConfig',
    'apps.gis_module.apps.GisModuleConfig',
    'apps.government.apps.GovernmentConfig',
    'apps.cbbo.apps.CbboConfig',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# =============================================================================
# MIDDLEWARE
# =============================================================================

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',  # CORS - must be before CommonMiddleware
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',  # i18n
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # Custom middleware
    'apps.core.middleware.RequestContextMiddleware',
    'apps.core.middleware.LanguageDetectionMiddleware',
    'apps.core.middleware.CurrentRequestMiddleware',
    'apps.core.middleware.AuditMiddleware',
]

ROOT_URLCONF = 'config.urls'

# =============================================================================
# TEMPLATES
# =============================================================================

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            BASE_DIR / 'templates',
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# =============================================================================
# DATABASE
# =============================================================================

DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': config('DB_NAME', default='kau_fpo'),
        'USER': config('DB_USER', default='postgres'),
        'PASSWORD': config('DB_PASSWORD', default='postgres'),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
        'CONN_MAX_AGE': 0,
        'OPTIONS': {
            'connect_timeout': 10,
        },
    }
}

# =============================================================================
# AUTHENTICATION
# =============================================================================

# Using Django's built-in User model with Groups for role-based access
# Roles (Groups): super_admin, admin, fpo_manager, government, cbbo, expert, viewer
# AUTH_USER_MODEL = 'auth.User'  # Default - no need to specify

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 8,
        },
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Password hashing (Argon2 is more secure than PBKDF2)
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
]

# =============================================================================
# INTERNATIONALIZATION
# =============================================================================

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Asia/Kolkata'

USE_I18N = True

USE_L10N = True

USE_TZ = True

# Supported languages
LANGUAGES = [
    ('en', 'English'),
    ('ml', 'Malayalam'),
]

LOCALE_PATHS = [
    BASE_DIR / 'locale',
]

# =============================================================================
# STATIC FILES (CSS, JavaScript, Images)
# =============================================================================

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

# =============================================================================
# MEDIA FILES (User uploads)
# =============================================================================

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# File upload settings
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # 5MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # 5MB

# =============================================================================
# DEFAULT PRIMARY KEY
# =============================================================================

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# =============================================================================
# DJANGO REST FRAMEWORK
# =============================================================================

REST_FRAMEWORK = {
    # Authentication (Cookie-based JWT)
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'apps.core.authentication.JWTCookieAuthentication',  # Custom cookie-based JWT auth
        'rest_framework_simplejwt.authentication.JWTAuthentication',  # Fallback for header-based
    ],

    # Permissions
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],

    # Pagination
    'DEFAULT_PAGINATION_CLASS': 'apps.core.utils.pagination.StandardPagination',
    'PAGE_SIZE': 20,

    # Filtering
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],

    # Throttling — disabled globally; per-view throttle_classes on sensitive endpoints only
    'DEFAULT_THROTTLE_CLASSES': [],
    'DEFAULT_THROTTLE_RATES': {
        'anon':              '100/hour',
        'user':              '1000/hour',
        'login':             '5/minute',
        'forgot_password':   '3/minute',
        'otp_verify':        '5/minute',
        'register':          '3/minute',
        'two_factor_login':  '5/minute',
        'two_factor_setup':  '10/minute',
        'disable_2fa_otp':   '3/minute',
    },

    # Renderers
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],

    # Parsers
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.MultiPartParser',
        'rest_framework.parsers.FormParser',
    ],

    # Schema
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',

    # Exception handling
    'EXCEPTION_HANDLER': 'apps.core.exceptions.handlers.custom_exception_handler',

    # Datetime format
    'DATETIME_FORMAT': '%Y-%m-%dT%H:%M:%S%z',
    'DATE_FORMAT': '%Y-%m-%d',
    'TIME_FORMAT': '%H:%M:%S',

    # Non-field errors key
    'NON_FIELD_ERRORS_KEY': 'non_field_errors',
}

# =============================================================================
# SIMPLE JWT
# =============================================================================

SIMPLE_JWT = {
    # Token lifetime
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=config('JWT_ACCESS_TOKEN_LIFETIME', default=60, cast=int)),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=config('JWT_REFRESH_TOKEN_LIFETIME', default=7, cast=int)),

    # Rotation & Blacklisting
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,

    # Algorithm
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,

    # Headers
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',

    # User settings
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',

    # Token types
    'TOKEN_TYPE_CLAIM': 'token_type',

    # Sliding tokens (disabled)
    'SLIDING_TOKEN_REFRESH_EXP_CLAIM': 'refresh_exp',
    'SLIDING_TOKEN_LIFETIME': timedelta(minutes=60),
    'SLIDING_TOKEN_REFRESH_LIFETIME': timedelta(days=7),
}

# =============================================================================
# CORS (Cookie-based authentication)
# =============================================================================

CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='http://localhost:3000,http://127.0.0.1:3000',
    cast=Csv()
)

# CRITICAL: Must be True for cookie-based JWT authentication
CORS_ALLOW_CREDENTIALS = True

CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    'x-language',  # Custom header for language
]

# Expose cookies + download headers to frontend
CORS_EXPOSE_HEADERS = ['Set-Cookie', 'Content-Disposition']

# =============================================================================
# CSRF PROTECTION (Cookie-based authentication)
# =============================================================================

# Set to False on testing servers that run HTTP (no TLS). Default: True in production, False in dev.
COOKIE_SECURE = config('COOKIE_SECURE', default=not DEBUG, cast=bool)

# CSRF settings for cookie-based JWT authentication
CSRF_COOKIE_HTTPONLY = False  # Frontend needs to read CSRF token
CSRF_COOKIE_SECURE = COOKIE_SECURE
CSRF_COOKIE_SAMESITE = 'Lax'  # CSRF protection
CSRF_COOKIE_NAME = 'csrftoken'
CSRF_HEADER_NAME = 'HTTP_X_CSRFTOKEN'

# Trusted origins for CSRF (same as CORS origins)
CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    default='http://localhost:3000,http://127.0.0.1:3000',
    cast=Csv()
)

# =============================================================================
# SESSION & COOKIE SECURITY
# =============================================================================

# Session cookie settings
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = COOKIE_SECURE
SESSION_COOKIE_SAMESITE = 'Lax'

# =============================================================================
# CACHING (Redis)
# =============================================================================

REDIS_URL = config('REDIS_URL', default='redis://localhost:6379/0')

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': REDIS_URL,
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            # Removed PARSER_CLASS - using default Python parser for better compatibility
            # HiredisParser only provides ~10% performance gain, not worth version conflicts
            'CONNECTION_POOL_KWARGS': {
                'max_connections': 50,
            },
            'SOCKET_CONNECT_TIMEOUT': 5,
            'SOCKET_TIMEOUT': 5,
        },
        'KEY_PREFIX': 'kau_fpo',
    }
}

# Cache key prefix for this application
CACHE_KEY_PREFIX = 'kau_fpo'

# Session using cache
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'

# =============================================================================
# CELERY
# =============================================================================

CELERY_BROKER_URL = config('CELERY_BROKER_URL', default=REDIS_URL)
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default=REDIS_URL)

CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60  # 25 minutes

# Retry settings
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True

# =============================================================================
# EMAIL
# =============================================================================

EMAIL_BACKEND = config(
    'EMAIL_BACKEND',
    default='django.core.mail.backends.console.EmailBackend'
)

EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')

DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@kau-fpo.in')
SERVER_EMAIL = config('SERVER_EMAIL', default='server@kau-fpo.in')

# Email provider for notifications service
EMAIL_PROVIDER = config('EMAIL_PROVIDER', default='smtp')  # 'smtp' or 'ses'

# Email template branding
EMAIL_COMPANY_NAME    = config('EMAIL_COMPANY_NAME',    default='KAU-FPO Platform')
EMAIL_COMPANY_ADDRESS = config('EMAIL_COMPANY_ADDRESS', default='Kerala Agricultural University, Thrissur - 680656, Kerala')
EMAIL_PRIMARY_COLOR   = config('EMAIL_PRIMARY_COLOR',   default='#2e7d32')

# =============================================================================
# SMS
# =============================================================================

SMS_PROVIDER = config('SMS_PROVIDER', default='console')  # 'console', 'msg91', 'sns'
SMS_API_KEY = config('SMS_API_KEY', default='')
SMS_SENDER_ID = config('SMS_SENDER_ID', default='KAUFPO')

# =============================================================================
# NOTIFICATIONS ENCRYPTION
# =============================================================================

NOTIFICATION_ENCRYPTION_KEY = config('NOTIFICATION_ENCRYPTION_KEY')

# =============================================================================
# AWS (S3 & SES)
# =============================================================================

AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID', default='')
AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY', default='')
AWS_REGION = config('AWS_REGION', default='ap-south-1')  # Mumbai

# S3 Storage
AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME', default='')
AWS_S3_CUSTOM_DOMAIN = config('AWS_S3_CUSTOM_DOMAIN', default='')
AWS_S3_OBJECT_PARAMETERS = {
    'CacheControl': 'max-age=86400',
}
AWS_DEFAULT_ACL = None
AWS_S3_FILE_OVERWRITE = False

# Use S3 for media files in production
USE_S3 = config('USE_S3', default=False, cast=bool)

if USE_S3:
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'

# =============================================================================
# DRF SPECTACULAR (API Documentation)
# =============================================================================

SPECTACULAR_SETTINGS = {
    'TITLE': 'KAU-FPO Platform API',
    'DESCRIPTION': (
        'AI-Based Digital Platform for KAU-FPO Linkage Programme\n\n'
        '## How to authenticate in Swagger\n'
        '> The app uses **HTTP-only cookies** in production (browser/mobile).\n'
        '> Swagger cannot access HttpOnly cookies, so use the Bearer token here instead.\n\n'
        '1. Call `POST /api/auth/login/` with your credentials\n'
        '2. Copy the **`access`** token from the response\n'
        '3. Click the **Authorize 🔒** button at the top right\n'
        '4. Paste the token and click **Authorize**\n'
        '5. All protected endpoints will now work'
    ),
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,

    # Contact info
    'CONTACT': {
        'name': 'KEFI Tech',
        'email': 'support@kefitech.com',
    },

    # Servers
    'SERVERS': [
        {'url': 'http://localhost:8000', 'description': 'Development'},
    ],

    # Schema
    'SCHEMA_PATH_PREFIX': '/api/',
    'COMPONENT_SPLIT_REQUEST': True,

    # Swagger UI settings
    'SWAGGER_UI_SETTINGS': {
        'deepLinking': True,
        'persistAuthorization': True,   # keeps the token after page refresh
        'displayOperationId': False,
        'defaultModelsExpandDepth': -1, # hide schemas section by default
    },

    # JWT security scheme — shows the Authorize 🔒 button in Swagger UI
    # NOTE: Swagger cannot read HttpOnly cookies (browser blocks JS access).
    # The app uses cookies in production, but JWTCookieAuthentication also
    # falls back to the Authorization header — so Swagger uses the header.
    'SECURITY': [{'bearerAuth': []}],
    'APPEND_COMPONENTS': {
        'securitySchemes': {
            'bearerAuth': {
                'type': 'http',
                'scheme': 'bearer',
                'bearerFormat': 'JWT',
            }
        }
    },
}

# =============================================================================
# LOGGING
# =============================================================================

LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,

    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {asctime} {message}',
            'style': '{',
        },
        'json': {
            'format': '{"level": "%(levelname)s", "time": "%(asctime)s", "module": "%(module)s", "message": "%(message)s"}',
        },
    },

    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        },
    },

    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'app.log',
            'maxBytes': 10 * 1024 * 1024,  # 10MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'error_file': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'error.log',
            'maxBytes': 10 * 1024 * 1024,  # 10MB
            'backupCount': 10,
            'formatter': 'verbose',
        },
        'audit_file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'audit.log',
            'maxBytes': 10 * 1024 * 1024,  # 10MB
            'backupCount': 30,
            'formatter': 'json',
        },
    },

    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': True,
        },
        'django.request': {
            'handlers': ['error_file'],
            'level': 'ERROR',
            'propagate': False,
        },
        'apps': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'audit': {
            'handlers': ['audit_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'exceptions': {
            'handlers': ['error_file', 'console'],
            'level': 'ERROR',
            'propagate': False,
        },
        'celery': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
    },

    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
}

# =============================================================================
# AUDIT LOGGING
# =============================================================================

AUDIT_LOG_ENABLED = True
AUDIT_LOG_METHODS = ['POST', 'PUT', 'PATCH', 'DELETE']
AUDIT_LOG_EXCLUDE_PATHS = [
    '/api/health/',
    '/api/healthcheck/',
    '/api/metrics/',
]

# =============================================================================
# APPLICATION SETTINGS
# =============================================================================

# FPO Settings
MIN_FPO_MEMBERS = 10
MIN_FPO_SHARE_CAPITAL = 100000  # Rs. 1 Lakh

# OTP Settings
OTP_EXPIRY_MINUTES = 10
OTP_MAX_ATTEMPTS = 5

# Account lockout
ACCOUNT_LOCKOUT_ATTEMPTS = 5
ACCOUNT_LOCKOUT_DURATION_MINUTES = 30

# Password reset token expiry
PASSWORD_RESET_TOKEN_EXPIRY_HOURS = 24

# Email verification token expiry
EMAIL_VERIFICATION_TOKEN_EXPIRY_HOURS = 48
