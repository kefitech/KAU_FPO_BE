"""
Claude API service wrapper for the chatbot.

Uses the project's real AI service infrastructure:
  - AIServiceConfig (apps.database.models.ai_config) -- per-service on/off
    toggle, encrypted API key, monthly Rupee budget cap, auto-disable.
  - AIUsageLog (apps.database.models.ai_config) -- one row per Claude API
    call, used by the admin usage/cost dashboard.

Task #14 (skeleton scope): if the chatbot service isn't configured, has no
API key, or has been disabled (manually or via budget auto-disable), this
returns a graceful mock reply instead of erroring -- the rest of the chat
flow works end-to-end without needing a real key yet.
"""
import logging
from decimal import Decimal

import anthropic

from apps.database.models.ai_config import AIServiceConfig, AIUsageLog

logger = logging.getLogger(__name__)

SERVICE_NAME = AIServiceConfig.Service.CHATBOT  # "chatbot"
DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024

# ASSUMPTION -- VERIFY BEFORE RELYING ON COST FIGURES:
# these are placeholder USD-per-million-token rates for cost_usd/cost_inr
# calculations. Confirm the real current rate for whatever model string
# DEFAULT_MODEL resolves to at console.anthropic.com / docs.claude.com
# before trusting the currency numbers on the admin usage dashboard.
PRICE_PER_MILLION_INPUT_TOKENS_USD = Decimal("3.00")
PRICE_PER_MILLION_OUTPUT_TOKENS_USD = Decimal("15.00")

KERALA_AG_CONTEXT = (
    "Kerala agricultural context: major crops include rice (paddy), "
    "coconut, rubber, pepper, cardamom, banana, and vegetables. Cropping "
    "follows the monsoon calendar (Kharif: Jun-Sep, Rabi: Oct-Jan, "
    "Zaid/summer: Feb-May). Farmer Producer Organizations (FPOs) operate "
    "under Kerala state and central schemes for input subsidy, market "
    "linkage, and value addition."
)


class ChatServiceUnavailable(Exception):
    """Raised when the chatbot IS configured/enabled but the live API call itself fails."""


MOCK_NOT_CONFIGURED_TEXT = (
    "AI service not yet configured. An administrator needs to add the "
    "Claude API key before I can answer real questions -- for now this is "
    "a placeholder reply so the rest of the chat flow can be built and "
    "tested."
)

MOCK_DISABLED_TEXT = (
    "The AI assistant is currently turned off by an administrator "
    "(this can also happen automatically if the monthly usage budget was "
    "reached). Please try again later."
)


def get_chatbot_config():
    return AIServiceConfig.objects.filter(service=SERVICE_NAME).first()


def is_claude_configured() -> bool:
    config = get_chatbot_config()
    return bool(config and config.is_enabled and config.get_api_key())


def get_user_fpo(user):
    """
    Resolve the FPO for either a primary user (FPO.primary_user OneToOne,
    reachable as user.fpo) or a secondary user (FPOUserMembership,
    reachable as user.fpo_membership.fpo). Returns None if neither exists.
    """
    fpo = getattr(user, "fpo", None)
    if fpo is not None:
        return fpo
    membership = getattr(user, "fpo_membership", None)
    return getattr(membership, "fpo", None) if membership else None


def build_system_prompt(user, language: str) -> str:
    """
    Build the system prompt with FPO profile context injected.
    Business rule #6: no PII -- only public profile fields (district,
    commodities, tier, status), never name/phone/PAN/GSTIN/bank details.
    """
    fpo = get_user_fpo(user)

    district = getattr(fpo, "district", "unknown")
    commodities = ", ".join(getattr(fpo, "primary_commodities", []) or []) or "unspecified"
    tier = getattr(fpo, "tier", "") or "not assessed"
    status = getattr(fpo, "status", "unspecified")

    active_schemes = _get_relevant_schemes(fpo)

    lang_label = "Malayalam" if language == "ml" else "English"

    return (
        "You are an agricultural assistant for Kerala FPOs (Farmer "
        "Producer Organizations). Respond only in "
        f"{lang_label}.\n"
        f"FPO context: district={district}, commodities=[{commodities}], "
        f"tier={tier}, status={status}.\n"
        f"Relevant schemes: [{active_schemes}].\n"
        f"{KERALA_AG_CONTEXT}\n"
        "Help with crop guidance, scheme eligibility, platform navigation, "
        "and registration questions. Keep answers practical and concise."
    )


def _get_relevant_schemes(fpo) -> str:
    """
    ASSUMPTION: there's a Scheme model with an `is_active` flag. Your
    __init__.py confirms `Scheme` exists at apps.database.models.schemes
    (plural) -- adjust the import below if the field names differ.
    """
    try:
        from apps.database.models.schemes import Scheme

        qs = Scheme.objects.filter(is_active=True)
        names = list(qs.values_list("name_en", flat=True)[:5])
        return ", ".join(names) if names else "none configured"
    except Exception:  # noqa: BLE001 -- scheme lookup is best-effort context
        return "none configured"


def _calculate_cost(input_tokens: int, output_tokens: int, usd_to_inr_rate):
    cost_usd = (
        Decimal(input_tokens) / Decimal(1_000_000) * PRICE_PER_MILLION_INPUT_TOKENS_USD
        + Decimal(output_tokens) / Decimal(1_000_000) * PRICE_PER_MILLION_OUTPUT_TOKENS_USD
    )
    cost_inr = cost_usd * Decimal(usd_to_inr_rate)
    return cost_usd, cost_inr


def get_assistant_reply(user, language: str, conversation_history: list, message: str, reference_id: str = "") -> dict:
    """
    Entry point used by the view.

    Returns a dict: {content, claude_model, tokens_used}. If Claude isn't
    configured/enabled, returns a mock reply (task #14).
    """
    config = get_chatbot_config()

    if config is None or not config.get_api_key():
        return {
            "content": MOCK_NOT_CONFIGURED_TEXT,
            "claude_model": "mock",
            "tokens_used": 0,
        }

    if not config.is_enabled:
        return {
            "content": MOCK_DISABLED_TEXT,
            "claude_model": "mock",
            "tokens_used": 0,
        }

    return _call_claude(user, language, conversation_history, message, config, reference_id)


def _call_claude(user, language: str, conversation_history: list, message: str, config, reference_id: str) -> dict:
    """
    Real Claude API call -- only reached once an admin has configured and
    enabled the chatbot service. On success, records usage against
    AIServiceConfig (running totals + auto-disable) and creates an
    AIUsageLog row. On failure, logs the failed attempt and raises
    ChatServiceUnavailable (business rule #7 -> view returns 503).
    """
    api_key = config.get_api_key()
    system_prompt = build_system_prompt(user, language)

    messages = [
        {"role": m["role"], "content": m["content"]}
        for m in conversation_history
        if m["role"] in ("user", "assistant")
    ]
    messages.append({"role": "user", "content": message})

    client = anthropic.Anthropic(api_key=api_key)
    fpo = get_user_fpo(user)

    try:
        response = client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            messages=messages,
        )
    except anthropic.APIError as exc:
        logger.error("Claude API call failed: %s", exc)
        AIUsageLog.objects.create(
            service=SERVICE_NAME,
            fpo=fpo,
            user=user,
            model_used=DEFAULT_MODEL,
            success=False,
            error_message=str(exc),
            reference_id=reference_id,
        )
        raise ChatServiceUnavailable("Claude API is currently unavailable.") from exc

    text_parts = [block.text for block in response.content if block.type == "text"]
    content = "\n".join(text_parts).strip()

    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    total_tokens = input_tokens + output_tokens

    cost_usd, cost_inr = _calculate_cost(input_tokens, output_tokens, config.usd_to_inr_rate)

    AIUsageLog.objects.create(
        service=SERVICE_NAME,
        fpo=fpo,
        user=user,
        model_used=response.model or DEFAULT_MODEL,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cost_usd=cost_usd,
        cost_inr=cost_inr,
        success=True,
        reference_id=reference_id,
    )
    # Updates AIServiceConfig running totals; auto-disables if budget cap hit.
    config.record_usage(cost_inr=float(cost_inr), tokens=total_tokens)

    return {
        "content": content,
        "claude_model": response.model or DEFAULT_MODEL,
        "tokens_used": total_tokens,
    }