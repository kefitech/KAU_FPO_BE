"""
Malayalam query translation for chatbot retrieval (2026-10-09).

The KB is English; Malayalam questions used Postgres `simple` config and
almost always retrieved nothing → generic refusal (12 tester questions).
Fix: translate the QUESTION to English first (one tiny Gemini call,
~₹0.02), search the KB with the translation, and let the normal answer
path reply in the user's language.

Fail-open: any error returns None and the caller keeps today's behaviour.
Every call is logged to AIUsageLog (service=chatbot, reference 'translate')
so the spend is visible and counted against the monthly cap.
"""

import logging
import re

logger = logging.getLogger(__name__)

MALAYALAM_RE = re.compile(r'[ഀ-ൿ]')

_PROMPT = (
    'Translate the following user question to English. Reply with ONLY '
    'the English translation, nothing else. Keep names, acronyms and '
    'platform terms (FPO, DPR, KAU, tier) as they are.\n\n'
    'Question: {q}'
)


def has_malayalam(text: str) -> bool:
    return bool(MALAYALAM_RE.search(text or ''))


def translate_query_to_english(text: str, user=None):
    """Return the English translation, or None on any failure/disabled."""
    try:
        from apps.database.models import AIServiceConfig, AIUsageLog
        from apps.fpo.services.dpr.llm_gateway import call_llm

        cfg = AIServiceConfig.objects.get(service=AIServiceConfig.Service.CHATBOT)
        if not cfg.is_enabled:
            return None
        resp = call_llm(cfg, _PROMPT.format(q=text.strip()[:500]), max_tokens=150)
        translated = (resp.text or '').strip().strip('"')
        if not translated or has_malayalam(translated):
            return None
        cost_inr = resp.cost_usd * cfg.usd_to_inr_rate
        AIUsageLog.objects.create(
            service=AIUsageLog.Service.CHATBOT,
            user=user if (user and getattr(user, 'is_authenticated', False)) else None,
            provider=resp.provider,
            model_used=resp.model,
            input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens,
            total_tokens=resp.input_tokens + resp.output_tokens,
            cost_usd=resp.cost_usd,
            cost_inr=cost_inr,
            success=True,
            reference_id='translate',
        )
        if resp.cost_usd > 0:
            cfg.record_usage(cost_inr=float(cost_inr),
                             tokens=resp.input_tokens + resp.output_tokens)
        return translated
    except Exception:  # noqa: BLE001 — translation must never break chat
        logger.warning('query translation failed', exc_info=True)
        return None
