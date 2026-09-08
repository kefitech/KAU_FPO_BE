"""
FPO App — Celery Tasks
========================
Location convention: apps/fpo/tasks.py (matches apps/recommendations/tasks.py,
apps/accounts/tasks.py, apps/notifications/tasks.py).

generate_marketing_strategy_task is currently a SKELETON — it proves the
async status flow (pending -> generating -> ready/failed) end to end
without calling Claude yet. Real generation (grounding data + the Claude
call + PDF/S3) is the next step, scoped separately from these endpoints.
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    name='fpo.generate_marketing_strategy',
)
def generate_marketing_strategy_task(self, strategy_id):
    """
    Args:
        strategy_id: MarketingStrategy.pk

    TODO (next step, not part of this endpoints pass):
      - Fetch grounding data (buyer matches, comparable listing prices —
        see apps.marketplace.services once written)
      - Call Claude via a service in apps.core.services
      - WeasyPrint -> PDF -> S3, set file_url
      - Notify FPO via apps.notifications.services.send_notification
    """
    from apps.database.models import MarketingStrategy

    try:
        strategy = MarketingStrategy.objects.get(pk=strategy_id)
    except MarketingStrategy.DoesNotExist:
        logger.error('generate_marketing_strategy_task: strategy %s not found', strategy_id)
        return

    strategy.status = MarketingStrategy.Status.GENERATING
    strategy.save(update_fields=['status'])

    # Placeholder — real generation not wired in yet.
    strategy.content = {}
    strategy.status = MarketingStrategy.Status.READY
    strategy.save(update_fields=['content', 'status'])

    return strategy.id