"""
Accounts App — Celery Tasks
============================
Location convention: apps/accounts/tasks.py
Author: Aleena LT
created: 2026-08-22
"""

import logging

from celery import shared_task
from django.core.cache import cache

from apps.database.models import Translation, TranslationCategory, Language
from apps.core.services.ai_translation import AITranslationService
from apps.core.services.translation import TranslationService

logger = logging.getLogger(__name__)


def lock_key(language_code: str) -> str:
    return f"auto_translate_lock:{language_code}"


@shared_task(bind=True)
def auto_translate_task(self, language_code: str, category_code: str | None = None):
    """
    Fetch all untranslated English strings for `language_code` (optionally
    scoped to `category_code`), translate them via Claude, and save as
    unverified Translation rows.

    Returns a summary dict, retrievable via:
        from celery.result import AsyncResult
        AsyncResult(task_id).result
    """
    try:
        language = Language.objects.get(code=language_code, is_active=True)
    except Language.DoesNotExist:
        cache.delete(lock_key(language_code))
        return {"error": f"Language '{language_code}' not found or inactive."}

    # Existing translations for this language — never overwrite
    existing_keys = set(
        Translation.objects.filter(language=language)
        .values_list("category__code", "key")
    )

    qs = Translation.objects.filter(language__code="en").select_related("category")
    if category_code:
        qs = qs.filter(category__code=category_code)

    # composite_key ("category.key") -> english value, kept unique across categories
    pending = {}
    category_lookup = {}
    for trans in qs:
        composite_key = f"{trans.category.code}.{trans.key}"
        if (trans.category.code, trans.key) in existing_keys:
            continue
        pending[composite_key] = trans.value
        category_lookup[composite_key] = trans.category

    skipped = len(existing_keys)

    if not pending:
        cache.delete(lock_key(language_code))
        return {"created": 0, "skipped": skipped, "failed": 0, "failed_keys": []}

    service = AITranslationService()
    translated, failed_keys = service.translate_all(pending, target_language=language.name)

    created_count = 0
    for composite_key, value in translated.items():
        category = category_lookup[composite_key]
        key = composite_key[len(category.code) + 1:]
        Translation.objects.create(
            category=category,
            key=key,
            language=language,
            value=value,
            is_verified=False,
        )
        created_count += 1

    cache.delete(lock_key(language_code))

    # New rows were created directly via ORM, bypassing whatever signal
    # normally invalidates the 24h Redis cache on admin edits. Invalidate
    # explicitly so t()/get_category() see the new strings immediately.
    if created_count:
        TranslationService.invalidate_cache(language=language_code)

    return {
        "created": created_count,
        "skipped": skipped,
        "failed": len(failed_keys),
        "failed_keys": failed_keys,
    }