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
import re
from decimal import Decimal
from typing import Optional

from apps.database.models import AIServiceConfig, AIUsageLog
from apps.fpo.services.dpr.llm_gateway import LLMError, LLMResponse, call_llm


logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Prompt — grounded, concise, refuses off-context
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT_EN = """\
You are the KAU-FPO help assistant on the platform for Kerala's Farmer
Producer Organisations. Follow this decision tree for every USER QUESTION:

A) SMALL TALK / CASUAL CHATTER (greetings, "how are you", "thanks", jokes,
   compliments, "yo dude", "haii", one-word messages, emojis, non-English
   greetings, filler like "ok", "cool", "wow"):
   → Respond warmly in 1-2 sentences AS the KAU-FPO assistant. Never
     refuse. Optionally suggest what you can help with (registering an
     FPO, DPR wizard, market hub, tier assessment, etc.) so the user knows
     what to ask next.
   Examples:
     User: "haiii dudee" → "Hi there! I'm the KAU-FPO help assistant —
       ask me about registering your FPO, uploading documents, or the
       page you're on."
     User: "how r u" → "Doing great, thanks for asking! What can I help
       you with on the KAU-FPO platform today?"
     User: "thanks" → "You're welcome! Let me know if you need anything
       else."

B) A REAL FACTUAL QUESTION about the KAU-FPO platform, FPO registration,
   DPR wizard, tier assessment, marketplace, expert booking, KAU schemes,
   or any topic covered by the CONTEXT below:
   → Answer in 2-4 sentences using ONLY facts from the CONTEXT. Be
     concrete. DO NOT add inline citations like "[1]", "[2, 3]", or
     "(source: KB #4)" — the frontend already renders the sources
     separately, so inline markers just clutter the reply. Write the
     answer as clean flowing prose.

C) A REAL FACTUAL QUESTION that is genuinely off-topic (weather, recipes,
   personal finance, banking process outside KAU, celebrity gossip, math
   homework, politics, medical advice, generic tech questions):
   → Reply exactly: "That's not something I can help with here. Please
     rephrase your question, or contact KAU support at kau-fpo@kau.in."

PRONOUN + FOLLOW-UP HANDLING (very important):
- If a PREVIOUS CONVERSATION block is present, use it to resolve pronouns
  ("that", "this", "it", "the same") and elliptical follow-ups
  ("what about the fees?", "and after that?", "how long does it take?").
- Rewrite the user's short question in your head using the previous
  turn's topic, then answer case B/C on the rewritten form. Example:
    Previous user turn: "How do I register my FPO?"
    Current user turn:  "What documents will I need for that?"
    → Rewrite: "What documents will I need for FPO registration?" → CASE B.
- Only fall to case C ("not something I can help with") if the rewritten
  question is still genuinely off-topic (weather, recipes, etc.).

Hard rules for cases B and C:
- NEVER invent features, endpoints, phone numbers, or policies that are
  not in the CONTEXT.
- NEVER quote external sources or general internet knowledge as fact.

Tone: friendly, direct, non-technical. Sound human, not corporate.
"""

_SYSTEM_PROMPT_ML = """\
നിങ്ങൾ കേരള കാർഷിക സർവ്വകലാശാലയുടെ KAU-FPO സഹായി ആണ്. ഓരോ USER QUESTION-നും \
ഈ തീരുമാന-ഘട്ടങ്ങൾ പിന്തുടരുക (മറുപടി മലയാളത്തിൽ):

A) ചെറിയ സംഭാഷണം (ഹായ്, നമസ്കാരം, നന്ദി, ചെറിയ കുശലം, "hi", "hello", ജോക്കുകൾ):
   → 1-2 വാചകങ്ങളിൽ സൗഹാർദ്ദപരമായി മറുപടി പറയുക. നിരാകരിക്കരുത്. FPO രജിസ്ട്രേഷൻ, \
   DPR wizard, മാർക്കറ്റ് ഹബ്, tier assessment തുടങ്ങിയ വിഷയങ്ങളിൽ ചോദിക്കാം എന്ന് ക്ഷണിക്കുക.

B) KAU-FPO പ്ലാറ്റ്‌ഫോമിനെ, DPR-നെ, tier-നെ, മാർക്കറ്റ്-നെ, expert booking-നെ, KAU \
   സ്കീമുകളെ കുറിച്ചുള്ള യഥാർത്ഥ ചോദ്യം:
   → CONTEXT-ൽ നിന്നുള്ള വിവരം മാത്രം ഉപയോഗിച്ച് 2-4 വാചകങ്ങളിൽ മറുപടി പറയുക.

C) പ്ലാറ്റ്‌ഫോമുമായി ബന്ധമില്ലാത്ത ചോദ്യം (കാലാവസ്ഥ, പാചകം, ബാങ്കിംഗ്, മെഡിക്കൽ ഉപദേശം, \
   രാഷ്ട്രീയം):
   → കൃത്യമായി മറുപടി പറയുക: "ഇത് ഞാൻ സഹായിക്കാൻ കഴിയാത്ത ചോദ്യമാണ്. ചോദ്യം മറ്റൊരു \
   രീതിയിൽ ചോദിക്കുക, അല്ലെങ്കിൽ kau-fpo@kau.in-ൽ KAU സപ്പോർട്ടിനെ ബന്ധപ്പെടുക."

PRONOUN + FOLLOW-UP:
- PREVIOUS CONVERSATION block ഉണ്ടെങ്കിൽ, അതിനെ ഉപയോഗിച്ച് pronouns ("അത്", \
  "അതിന്", "അതെ", "that", "it") + ഹ്രസ്വ follow-up ചോദ്യങ്ങൾ (എത്ര സമയമെടുക്കും, \
  എന്ത് documents വേണം) മുൻ വിഷയത്തിലേക്ക് ബന്ധിപ്പിക്കുക. \
  മുൻ turn: "How do I register my FPO?" + ഇപ്പോൾ: "എന്ത് documents വേണം?" \
  → "FPO registration-നു എന്ത് documents വേണം?" എന്ന് വീണ്ടും എഴുതി CASE B ആയി കൈകാര്യം ചെയ്യുക.

നിയമങ്ങൾ:
- CONTEXT-ൽ ഇല്ലാത്ത feature-കൾ, endpoints, ഫോൺ നമ്പറുകൾ, നയങ്ങൾ കണ്ടുപിടിക്കരുത്.
- ബാഹ്യ ഉറവിടങ്ങൾ ഉദ്ധരിക്കരുത്.

ടോൺ: സൗഹാർദ്ദപരവും നേരിട്ടുള്ളതും ആയിരിക്കണം.
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
        'text':     _strip_inline_citations(response.text).strip(),
        'tokens':   response.input_tokens + response.output_tokens,
        'cost_inr': cost_inr,
        'provider': response.provider,
        'model':    response.model,
    }


# Defensive scrubber — even with the "no inline citations" prompt rule,
# Gemini sometimes still emits `[1]`, `[1, 3]`, `[KB #4]`, `(source: KB #2)`
# markers. Strip those before the reply reaches the widget so the prose
# looks clean. Sources are still delivered separately in the API payload.
_INLINE_CITE_RE = re.compile(
    r'\s*(?:'
    r'\[(?:KB\s*#?\d+|\d+(?:\s*,\s*\d+)*)\]'          # [1], [1, 2], [KB #4]
    r'|\((?:source|ref)[^)]*\)'                       # (source: KB #2)
    r')',
    re.IGNORECASE,
)


def _strip_inline_citations(text: str) -> str:
    """Remove `[N]`, `[N, M]`, `[KB #4]`, `(source: KB #2)` residuals."""
    cleaned = _INLINE_CITE_RE.sub('', text or '')
    # Collapse any doubled spaces the regex leaves behind.
    return re.sub(r'  +', ' ', cleaned)
