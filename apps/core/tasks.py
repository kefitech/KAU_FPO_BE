"""
Core Celery tasks — currently just the CMS auto-expiry sweeper.

Public CMS content (Announcement, QuickLink, NewsSource) carries an
optional `end_date`. KAU asked for links/news/announcements to disappear
from the public pages automatically after that date — this task flips
`is_active=False` so the existing `is_active=True` filters in the public
API hide them.

Wired into Celery Beat via config/celery.py as `core.expire_public_cms_content`.
Daily at 02:00 UTC. Safe to re-run (idempotent).
"""
import logging

from celery import shared_task
from django.core.cache import cache
from django.utils import timezone


logger = logging.getLogger(__name__)


@shared_task(name='core.expire_public_cms_content')
def expire_public_cms_content():
    """
    Deactivate CMS rows whose `end_date` has passed. Returns per-model
    counts for the Beat log.
    """
    from apps.database.models.cms import Announcement, NewsSource, QuickLink

    today = timezone.now().date()
    result = {}
    for model in (Announcement, QuickLink, NewsSource):
        count = model.objects.filter(
            is_active=True,
            end_date__isnull=False,
            end_date__lt=today,
        ).update(is_active=False)
        result[model.__name__] = count
        if count:
            logger.info(
                "expire_public_cms_content: deactivated %d %s(s) past end_date",
                count, model.__name__,
            )

    # Wipe the public CMS caches so expired items disappear on next request
    # instead of waiting out their 24h TTL.
    if any(result.values()):
        for pattern in (
            'public:announcements:*',
            'public:news-sources:*',
            'public:quick-links:*',
        ):
            try:
                cache.delete_pattern(pattern)
            except AttributeError:
                # LocMemCache in tests doesn't support delete_pattern.
                pass

    return result
