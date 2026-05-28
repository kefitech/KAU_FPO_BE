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
KAU-FPO Backend - Settings Selector
===================================

Automatically selects the appropriate settings module based on the
DJANGO_ENV environment variable.

Environment Options:
    - development (default)
    - production

Usage:
    # Development (default):
    export DJANGO_ENV=development
    python manage.py runserver

    # Production:
    export DJANGO_ENV=production
    gunicorn config.wsgi:application

    # Or use DJANGO_SETTINGS_MODULE directly:
    export DJANGO_SETTINGS_MODULE=config.settings.production

Author:
    Athul Gopan
Created On:
    21-04-2026
"""

import os

# Get environment from DJANGO_ENV variable
# Defaults to 'development' if not set
environment = os.environ.get('DJANGO_ENV', 'development').lower()

# Import the appropriate settings
if environment == 'production':
    from .production import *
else:
    from .development import *
