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
Celery Configuration for KAU-FPO Platform
=========================================

Celery is used for:
- Async email notifications
- Async SMS notifications
- Scheduled tasks (reports, cleanup)
- Background processing (PDF generation, data exports)

Usage:
    # Start worker:
    celery -A config worker -l info

    # Start beat (scheduler):
    celery -A config beat -l info

    # Start worker with beat:
    celery -A config worker -B -l info

    # Monitor (Flower):
    celery -A config flower

Author:
    Athul Gopan
Created On:
    21-04-2026
"""

import os
from celery import Celery
from celery.schedules import crontab

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Create Celery app
app = Celery('kau_fpo')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()


# =============================================================================
# CELERY BEAT SCHEDULE (Periodic Tasks)
# =============================================================================

app.conf.beat_schedule = {
    # Cleanup expired tokens every day at 2 AM
    'cleanup-expired-tokens': {
        'task': 'apps.accounts.tasks.cleanup_expired_tokens',
        'schedule': crontab(hour=2, minute=0),
    },

    # Send pending notification reminders every hour
    'send-notification-reminders': {
        'task': 'apps.notifications.tasks.send_pending_reminders',
        'schedule': crontab(minute=0),  # Every hour
    },

    # Generate daily reports at 6 AM
    'generate-daily-reports': {
        'task': 'apps.analytics.tasks.generate_daily_report',
        'schedule': crontab(hour=6, minute=0),
    },

    # Cleanup old audit logs monthly (keep 1 year)
    'cleanup-old-audit-logs': {
        'task': 'apps.core.tasks.cleanup_old_audit_logs',
        'schedule': crontab(day_of_month=1, hour=3, minute=0),
    },

    # Sync FPO data with external systems (if applicable)
    'sync-external-data': {
        'task': 'apps.fpo.tasks.sync_external_data',
        'schedule': crontab(hour='*/6'),  # Every 6 hours
    },

    # Clear expired cache entries
    'clear-expired-cache': {
        'task': 'apps.core.tasks.clear_expired_cache',
        'schedule': crontab(hour=4, minute=30),
    },
    #------------------------------------------------------------------------------
    #Arunima  
    #22/08/2026
    #P2-11 Marketplace — mark products past available_until as expired
    #expire_products will genuinely run automatically every day at 00:30, without anyone needing to trigger it manually.

    'expire-products-daily': {
        'task': 'apps.marketplace.tasks.expire_products',
        'schedule': crontab(hour=17, minute=35),  # 00:30 daily
    },
 
    # P2-11 Marketplace — score newly active products against buyer requirements
    'run-buyer-seller-matching-daily': {
        'task': 'apps.marketplace.tasks.run_buyer_seller_matching',
        'schedule': crontab(hour=1, minute=0),  # 01:00 daily, after expiry runs
    },

    #-------------------------------------------------------------------------------

}

# =============================================================================
# TASK ROUTING (Optional - for different queues)
# =============================================================================

app.conf.task_routes = {
    # High priority: email/SMS notifications
    'apps.notifications.tasks.*': {'queue': 'notifications'},

    # Low priority: reports and analytics
    'apps.analytics.tasks.*': {'queue': 'reports'},

    # Default queue for everything else
    '*': {'queue': 'default'},
}

# =============================================================================
# TASK SETTINGS
# =============================================================================

app.conf.task_default_queue = 'default'
app.conf.task_default_exchange = 'default'
app.conf.task_default_routing_key = 'default'

# Retry settings
app.conf.task_annotations = {
    '*': {
        'rate_limit': '100/s',
    },
    'apps.notifications.tasks.send_email': {
        'rate_limit': '50/m',  # 50 emails per minute
        'max_retries': 3,
    },
    'apps.notifications.tasks.send_sms': {
        'rate_limit': '30/m',  # 30 SMS per minute
        'max_retries': 3,
    },
}


# =============================================================================
# DEBUG TASK
# =============================================================================

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task to test Celery is working."""
    print(f'Request: {self.request!r}')
