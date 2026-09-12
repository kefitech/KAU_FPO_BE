"""
LLM Gateway — provider-agnostic dispatcher for AI text generation.

Per KAU RCD reply B.5 + operational readiness (2026-09-03):
    Switching AI vendor (Anthropic → Google Gemini → OpenAI GPT) is a config
    change, not a code deploy. `AIServiceConfig.provider` picks the vendor;
    `AIServiceConfig.model_name` picks the exact model within that vendor.
    Everything else (KB retrieval, versioning, budget cap, audit) stays
    identical.

Public API:
    `call_llm(config, prompt, max_tokens=1500) -> LLMResponse`
        Blocking call. Returns text + token counts + cost. Raises
        `LLMError` on provider failures — caller handles gracefully.

    `LLMResponse` is a plain dataclass so callers don't couple to Django.

Provider status:
    - mock       : shipped, deterministic — used when no key is configured.
                    The `_call_mock` implementation is complete and used by
                    Phase 5's narrative service.
    - anthropic  : stub with a drop-in snippet in the function docstring.
                    Uncomment + `pip install anthropic` when KAU provides key.
    - openai     : stub with drop-in snippet. Uncomment + `pip install openai`.
    - google     : stub with drop-in snippet. Uncomment + `pip install
                    google-generativeai`.

Every stub raises `LLMError` today (rather than silently returning mock text)
so misconfiguration is loud, not silent. The dispatcher falls back to
mock ONLY when `provider='mock'` is explicitly set.

Pricing tables (USD per 1M tokens, as of 2026-09) live in this file so
regenerating cost tracking is a one-line edit when Anthropic / Google / OpenAI
revise their pricing pages.

Author: Athul Gopan (Kefi Tech Solutions)
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from apps.database.models import AIServiceConfig


class LLMError(Exception):
    """Provider call failed — includes provider + model in the message."""


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    provider: str
    model: str


# ─────────────────────────────────────────────────────────────────────────────
# Provider defaults + pricing
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_MODELS: dict[str, str] = {
    'anthropic': 'claude-sonnet-4-6',
    'openai':    'gpt-4o-mini',
    'google':    'gemini-3.6-flash',
    'mock':      'mock-narrative-v1',
}

# USD per 1M tokens (input, output). Update when providers change pricing.
# Keys are (provider, model) tuples so a service can pick a cheap model
# without triggering the wrong pricing formula.
PRICING_USD_PER_MTOKEN: dict[tuple[str, str], tuple[Decimal, Decimal]] = {
    # Anthropic Claude (as of 2026-09)
    ('anthropic', 'claude-sonnet-4-6'): (Decimal('3'),  Decimal('15')),
    ('anthropic', 'claude-opus-4-7'):   (Decimal('15'), Decimal('75')),
    ('anthropic', 'claude-haiku-4-5-20251001'): (Decimal('0.80'), Decimal('4')),
    # OpenAI GPT-4o family
    ('openai', 'gpt-4o'):       (Decimal('2.50'), Decimal('10')),
    ('openai', 'gpt-4o-mini'):  (Decimal('0.15'), Decimal('0.60')),
    # Google Gemini
    ('google', 'gemini-2.5-pro'):   (Decimal('1.25'), Decimal('10')),
    ('google', 'gemini-2.5-flash'): (Decimal('0.30'), Decimal('2.50')),
    ('google', 'gemini-3.6-flash'): (Decimal('0.30'), Decimal('2.50')),
    # Mock is free
    ('mock', 'mock-narrative-v1'): (Decimal('0'), Decimal('0')),
}


def _resolve_model(provider: str, requested: str) -> str:
    """Pick the effective model — explicit override or provider default."""
    if requested:
        return requested
    return DEFAULT_MODELS.get(provider, '')


def _compute_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> Decimal:
    """Compute USD cost. Unknown (provider, model) → 0 (logged but not billed)."""
    rates = PRICING_USD_PER_MTOKEN.get((provider, model))
    if not rates:
        return Decimal('0')
    in_rate, out_rate = rates
    return (
        Decimal(input_tokens) / Decimal('1000000') * in_rate
        + Decimal(output_tokens) / Decimal('1000000') * out_rate
    )


# ─────────────────────────────────────────────────────────────────────────────
# Dispatcher
# ─────────────────────────────────────────────────────────────────────────────

def call_llm(
    config: AIServiceConfig,
    prompt: str,
    max_tokens: int = 1500,
    system: Optional[str] = None,
) -> LLMResponse:
    """Dispatch to the configured LLM provider.

    Callers pass the AIServiceConfig for the feature they're generating for
    (typically fetched via `AIServiceConfig.objects.get(service='dpr_narratives')`).
    The provider is read off the config, so admin can swap it live without
    the caller knowing.

    Args:
        config: The service configuration row (holds provider + model + key).
        prompt: The user prompt / instruction.
        max_tokens: Maximum output tokens.
        system: Optional system message. Providers that don't support system
                messages get it prepended to the prompt.

    Returns:
        LLMResponse — text + token counts + computed cost + provenance.

    Raises:
        LLMError: on provider failures. Caller decides whether to fall back
                  or propagate to the user.
    """
    provider = config.provider or AIServiceConfig.Provider.MOCK
    model = _resolve_model(provider, config.model_name)

    if provider == AIServiceConfig.Provider.MOCK:
        return _call_mock(prompt, model)
    if provider == AIServiceConfig.Provider.ANTHROPIC:
        return _call_anthropic(config, prompt, model, max_tokens, system)
    if provider == AIServiceConfig.Provider.OPENAI:
        return _call_openai(config, prompt, model, max_tokens, system)
    if provider == AIServiceConfig.Provider.GOOGLE:
        return _call_google(config, prompt, model, max_tokens, system)

    raise LLMError(f'Unsupported provider: {provider}')


# ─────────────────────────────────────────────────────────────────────────────
# Mock — used by Phase 5 until a real key is configured
# ─────────────────────────────────────────────────────────────────────────────

def _call_mock(prompt: str, model: str) -> LLMResponse:
    """Deterministic placeholder — returns a hash-tagged echo of the prompt.

    Used when `provider='mock'`. The full narrative shape (chapter title +
    paragraphs + KB citations) is assembled by `narrative._generate_narrative_text`
    which owns the presentation. This gateway function just returns raw text
    so the mock stays symmetric with real provider calls.
    """
    seed = hashlib.sha256(prompt.encode()).hexdigest()[:8]
    text = f'[MOCK v{seed}] {prompt[:200]}…'
    input_tokens = len(prompt) // 4
    output_tokens = len(text) // 4
    return LLMResponse(
        text=text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=Decimal('0'),
        provider='mock',
        model=model,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Anthropic Claude
# ─────────────────────────────────────────────────────────────────────────────

def _call_anthropic(
    config: AIServiceConfig,
    prompt: str,
    model: str,
    max_tokens: int,
    system: Optional[str],
) -> LLMResponse:
    """Wire up when KAU provides an Anthropic API key.

    Drop-in implementation (uncomment + `pip install anthropic`):

        from anthropic import Anthropic, APIError
        key = config.get_api_key()
        if not key:
            raise LLMError('Anthropic API key not configured on AIServiceConfig')
        client = Anthropic(api_key=key)
        try:
            kwargs = {
                'model': model,
                'max_tokens': max_tokens,
                'messages': [{'role': 'user', 'content': prompt}],
            }
            if system:
                kwargs['system'] = system
            resp = client.messages.create(**kwargs)
        except APIError as e:
            raise LLMError(f'Anthropic API failure: {e}') from e
        text = resp.content[0].text
        input_tokens = resp.usage.input_tokens
        output_tokens = resp.usage.output_tokens
        return LLMResponse(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=_compute_cost('anthropic', model, input_tokens, output_tokens),
            provider='anthropic',
            model=model,
        )
    """
    raise LLMError(
        'Anthropic provider not yet wired. Configure API key in AIServiceConfig '
        'and uncomment the implementation in llm_gateway._call_anthropic.'
    )


# ─────────────────────────────────────────────────────────────────────────────
# OpenAI GPT
# ─────────────────────────────────────────────────────────────────────────────

def _call_openai(
    config: AIServiceConfig,
    prompt: str,
    model: str,
    max_tokens: int,
    system: Optional[str],
) -> LLMResponse:
    """Wire up when KAU provides an OpenAI API key.

    Drop-in implementation (uncomment + `pip install openai`):

        from openai import OpenAI, OpenAIError
        key = config.get_api_key()
        if not key:
            raise LLMError('OpenAI API key not configured on AIServiceConfig')
        client = OpenAI(api_key=key)
        messages = []
        if system:
            messages.append({'role': 'system', 'content': system})
        messages.append({'role': 'user', 'content': prompt})
        try:
            resp = client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                messages=messages,
            )
        except OpenAIError as e:
            raise LLMError(f'OpenAI API failure: {e}') from e
        text = resp.choices[0].message.content
        input_tokens = resp.usage.prompt_tokens
        output_tokens = resp.usage.completion_tokens
        return LLMResponse(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=_compute_cost('openai', model, input_tokens, output_tokens),
            provider='openai',
            model=model,
        )
    """
    raise LLMError(
        'OpenAI provider not yet wired. Configure API key in AIServiceConfig '
        'and uncomment the implementation in llm_gateway._call_openai.'
    )


# ─────────────────────────────────────────────────────────────────────────────
# Google Gemini
# ─────────────────────────────────────────────────────────────────────────────

def _call_google(
    config: AIServiceConfig,
    prompt: str,
    model: str,
    max_tokens: int,
    system: Optional[str],
) -> LLMResponse:
    import google.generativeai as genai
    from google.api_core.exceptions import GoogleAPIError

    key = config.get_api_key()
    if not key:
        raise LLMError('Google API key not configured on AIServiceConfig')
    genai.configure(api_key=key)
    gm = genai.GenerativeModel(
        model,
        system_instruction=system if system else None,
    )
    try:
        resp = gm.generate_content(
            prompt,
            generation_config={'max_output_tokens': max_tokens},
        )
    except GoogleAPIError as e:
        raise LLMError(f'Google Gemini API failure: {e}') from e
    text = resp.text
    usage = getattr(resp, 'usage_metadata', None)
    input_tokens = getattr(usage, 'prompt_token_count', 0) if usage else 0
    output_tokens = getattr(usage, 'candidates_token_count', 0) if usage else 0
    return LLMResponse(
        text=text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=_compute_cost('google', model, input_tokens, output_tokens),
        provider='google',
        model=model,
    )
