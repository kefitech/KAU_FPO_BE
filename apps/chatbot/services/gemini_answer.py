"""
Chatbot — Gemini-backed grounded answer generator.

Reuses the shared LLM gateway (apps.fpo.services.dpr.llm_gateway) so the
chatbot benefits from the same provider abstraction, budget cap enforcement,
usage logging, and API key management as the DPR narrative feature.

Contract:
    generate_answer(question, entries, user, lang) -> {answer, tokens, cost_inr, provider, model}

Returns None if:
    - AIServiceConfig for chatbot is disabled
    - Budget cap for the month has been hit (config.is_over_cap())
    - API call raised LLMError (already logged to AIUsageLog on our side)

The API view (apps.chatbot.api.message.ChatMessageView) falls back to the
extractive QA (chatbot_service on port 8002) whenever this returns None,
so the chatbot keeps working through outages / budget exhaustion.

Grounded prompt: instructs Gemini to answer only from the provided KB
context. Off-context questions get a polite refusal — no hallucination.

Author: Athul Gopan (Kefi Tech Solutions)
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

from apps.database.models import AIServiceConfig, AIUsageLog
from apps.fpo.services.dpr.llm_gateway import LLMError, LLMResponse, call_llm


logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Prompt — grounded, concise, refuses off-context
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT_EN = """\
You are the KAU-FPO help assistant. Your job is to answer the user's
question using ONLY the CONTEXT below. Follow these rules strictly:

1. If the answer is in the CONTEXT, respond in 2-4 sentences. Be concrete.
2. If the CONTEXT doesn't cover the question, reply exactly:
   "That's not something I can help with here. Please rephrase your \
question, or contact KAU support at kau-fpo@kau.in."
3. NEVER invent features, endpoints, phone numbers, or policies not in \
   the CONTEXT.
4. NEVER quote external sources or general internet knowledge.
5. Keep the tone friendly, direct, non-technical.
"""

_SYSTEM_PROMPT_ML = """\
You are the KAU-FPO help assistant. Reply in Malayalam. Use ONLY the \
CONTEXT below. Follow these rules strictly:

1. If the answer is in the CONTEXT, reply in Malayalam in 2-4 sentences.
2. If not in CONTEXT, reply:
   "ഇത് ഞാൻ സഹായിക്കാൻ കഴിയാത്ത ചോദ്യമാണ്. ചോദ്യം മറ്റൊരു രീതിയിൽ ചോദിക്കുക, \
അല്ലെങ്കിൽ kau-fpo@kau.in-ൽ KAU സപ്പോർട്ടിനെ ബന്ധപ്പെടുക."
3. NEVER invent features not in CONTEXT.
4. NEVER quote external sources.
"""


def _build_prompt(
    question: str,
    entries: list,
    current_path: str,
    prior_turns: list | None = None,
) -> str:
    """Assemble the user prompt with retrieved KB context.

    The KB entries were pre-filtered by audience in the caller, so this
    context is safe to include for the user's role.

    `prior_turns` — last N exchanges from the same ChatConversation, oldest
    first. Included so Gemini can handle "yes, and what about X?"
    follow-ups. Passed as a "PREVIOUS CONVERSATION" block above the
    current question; the grounded system prompt still forces answers to
    stay within the CONTEXT.
    """
    context_lines = []
    for i, e in enumerate(entries, 1):
        context_lines.append(f'[{i}] {e.topic}\n{e.body_en}')
    context = '\n\n'.join(context_lines) or '(no relevant entries found)'

    page_hint = f'The user is currently on the page: {current_path}\n' if current_path else ''

    history_block = ''
    if prior_turns:
        history_lines = []
        for turn in prior_turns:
            speaker = 'User' if turn['role'] == 'user' else 'Assistant'
            history_lines.append(f'{speaker}: {turn["content"]}')
        history_block = 'PREVIOUS CONVERSATION:\n' + '\n'.join(history_lines) + '\n\n'

    return (
        f'{page_hint}'
        f'{history_block}'
        f'USER QUESTION: {question}\n\n'
        f'CONTEXT:\n{context}\n\n'
        f'Reply:'
    )


# ─────────────────────────────────────────────────────────────────────────────
# Public entrypoint
# ─────────────────────────────────────────────────────────────────────────────

def generate_answer(
    question: str,
    entries: list,
    user=None,
    current_path: str = '',
    lang: str = 'en',
    prior_turns: list | None = None,
) -> Optional[dict]:
    """Try to answer via Gemini using the retrieved KB context.

    Returns:
        {'text': str, 'tokens': int, 'cost_inr': Decimal,
         'provider': str, 'model': str} on success
        None if disabled / over budget / API error (caller falls back)
    """
    try:
        cfg = AIServiceConfig.objects.get(service=AIServiceConfig.Service.CHATBOT)
    except AIServiceConfig.DoesNotExist:
        logger.info('chatbot: AIServiceConfig row not found — falling back to extractive')
        return None

    if not cfg.is_enabled:
        return None

    # Budget cap — if this service has already spent its monthly allowance,
    # skip the Gemini call and let the caller use the extractive fallback.
    if cfg.monthly_cap_inr and cfg.current_month_cost_inr >= cfg.monthly_cap_inr:
        logger.info('chatbot: monthly budget cap reached — falling back to extractive')
        return None

    system = _SYSTEM_PROMPT_ML if lang == 'ml' else _SYSTEM_PROMPT_EN
    prompt = _build_prompt(question, entries, current_path, prior_turns)

    try:
        # 500 tokens is plenty for a 2-4 sentence chatbot reply and keeps
        # cost per call very low.
        response: LLMResponse = call_llm(cfg, prompt, max_tokens=500, system=system)
    except LLMError as e:
        # Log the failure to AIUsageLog + return None so caller uses the
        # extractive fallback. No exception propagated — chatbot keeps working.
        AIUsageLog.objects.create(
            service=AIUsageLog.Service.CHATBOT,
            user=user if user and user.is_authenticated else None,
            provider=cfg.provider,
            model_used=cfg.model_name or 'unknown',
            input_tokens=0, output_tokens=0, total_tokens=0,
            cost_usd=Decimal('0'), cost_inr=Decimal('0'),
            success=False,
            error_message=str(e)[:500],
        )
        logger.warning('chatbot: LLM call failed, falling back to extractive: %s', e)
        return None

    # Success — log usage + apply spend against the monthly cap.
    cost_inr = response.cost_usd * cfg.usd_to_inr_rate
    AIUsageLog.objects.create(
        service=AIUsageLog.Service.CHATBOT,
        user=user if user and user.is_authenticated else None,
        provider=response.provider,
        model_used=response.model,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        total_tokens=response.input_tokens + response.output_tokens,
        cost_usd=response.cost_usd,
        cost_inr=cost_inr,
        success=True,
    )
    if response.cost_usd > 0:
        cfg.record_usage(
            cost_inr=float(cost_inr),
            tokens=response.input_tokens + response.output_tokens,
        )

    return {
        'text':     response.text.strip(),
        'tokens':   response.input_tokens + response.output_tokens,
        'cost_inr': cost_inr,
        'provider': response.provider,
        'model':    response.model,
    }
