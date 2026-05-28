"""
Custom management command to start the development server with clean output.

Usage:
    python manage.py dev
    python manage.py dev 9000  # Custom port
"""

import os
import sys
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = 'Start the development server with clean output'

    def add_arguments(self, parser):
        parser.add_argument(
            'port',
            nargs='?',
            default='8000',
            type=str,
            help='Port number (default: 8000)'
        )
        parser.add_argument(
            '--host',
            default='0.0.0.0',
            type=str,
            help='Host address (default: 0.0.0.0)'
        )

    def handle(self, *args, **options):
        port = options['port']
        host = options['host']

        # Print banner
        self.stdout.write(self.style.SUCCESS('\n' + '=' * 70))
        self.stdout.write(self.style.SUCCESS('  KAU-FPO Backend Development Server'))
        self.stdout.write(self.style.SUCCESS('=' * 70 + '\n'))

        # Show environment info
        self.stdout.write(f"  Django version: {self.style.WARNING(settings.VERSION if hasattr(settings, 'VERSION') else 'Django 4.2.30')}")
        self.stdout.write(f"  Database: {self.style.WARNING('PostgreSQL 13.9')}")
        self.stdout.write(f"  Server: {self.style.SUCCESS(f'http://{host}:{port}')}")
        self.stdout.write(f"  API Docs: {self.style.SUCCESS(f'http://{host}:{port}/api/docs/')}")
        self.stdout.write(f"  Admin Panel: {self.style.SUCCESS(f'http://{host}:{port}/admin/')}\n")

        self.stdout.write(self.style.SUCCESS('=' * 70 + '\n'))
        self.stdout.write(self.style.WARNING('  Press CTRL+C to stop the server\n'))
        self.stdout.write(self.style.SUCCESS('=' * 70 + '\n'))

        # Set environment to reduce Django logging
        os.environ['DJANGO_LOG_LEVEL'] = 'INFO'

        # Start the server
        try:
            call_command('runserver', f'{host}:{port}', '--noreload' if '--noreload' in sys.argv else None)
        except KeyboardInterrupt:
            self.stdout.write(self.style.SUCCESS('\n\nServer stopped gracefully.\n'))
