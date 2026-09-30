"""
AI Business Plan generation — FPO "Business Plan Guidance" tab.

Builds a short, structured business plan for the logged-in FPO, grounded in
its primary / secondary commodities (FPO.primary_commodities /
secondary_commodities — MasterLookup 'commodity' codes) and its registered
location (district, block, village, pincode + the agro-climatic zone and
soil region resolved from its coordinates).

Same wiring as DPR narratives (apps/fpo/services/dpr/narrative.py):
    AIServiceConfig(service='business_plan')  → provider / model / key / budget
    llm_gateway.call_llm(...)                  → Gemini (google-genai) or mock
    AIUsageLog + cfg.record_usage()            → admin usage + monthly cap
Generation is synchronous (like DPR `/generate/`); the result is cached in
BusinessPlan, one row per FPO per language.
"""
from __future__ import annotations

import json
import logging
import re
from decimal import Decimal

from django.utils import timezone

from apps.core.models.generic import MasterLookup
from apps.database.models import AIServiceConfig, AIUsageLog, BusinessPlan
from apps.fpo.services.dpr.llm_gateway import LLMError, LLMResponse, call_llm
from apps.recommendations.services import get_current_financial_year

logger = logging.getLogger(__name__)

# ~1000-1500 words of JSON; Malayalam needs roughly 2-3x the tokens of English.
MAX_OUTPUT_TOKENS = 6000


class BusinessPlanError(Exception):
    """Generation failed. `code` is mapped to an HTTP status + message by the API layer."""

    NO_COMMODITY = 'no_commodity'
    SERVICE_UNAVAILABLE = 'service_unavailable'
    GENERATION_FAILED = 'generation_failed'

    def __init__(self, code: str, detail: str = ''):
        super().__init__(detail or code)
        self.code = code


def normalise_language(lang: str | None) -> str:
    return BusinessPlan.Language.MALAYALAM if lang == 'ml' else BusinessPlan.Language.ENGLISH


# ─────────────────────────────────────────────────────────────────────────────
# FPO profile / context
# ─────────────────────────────────────────────────────────────────────────────

# Read MasterLookup directly rather than via LookupService: the cached
# service only returns ACTIVE items, but an FPO's saved commodity / block
# may point at a lookup an admin has since deactivated — we still want its
# real name (same approach as apps/fpo/api/serializers.py).

def _commodities(codes, lang: str) -> list[dict]:
    codes = list(codes or [])
    lookups = {
        m.code: m for m in MasterLookup.objects.filter(category='commodity', code__in=codes)
    }
    return [
        {'code': code, 'name': lookups[code].get_name(lang) if code in lookups else code}
        for code in codes
    ]


def _block_name(fpo, lang: str) -> str:
    if not fpo.block_taluk:
        return ''
    lookup = MasterLookup.objects.filter(category='block', code=fpo.block_taluk).first()
    return lookup.get_name(lang) if lookup else fpo.block_taluk


def build_profile(fpo, lang: str = 'en') -> dict:
    """What the plan is based on — shown on the tab before/after generation."""
    return {
        'fpo_name': fpo.name_ml if lang == 'ml' and fpo.name_ml else fpo.name,
        'primary_commodities': _commodities(fpo.primary_commodities, lang),
        'secondary_commodities': _commodities(fpo.secondary_commodities, lang),
        'district': fpo.district,
        'district_display': fpo.get_district_display() if fpo.district else '',
        'block_taluk': fpo.block_taluk,
        'block_display': _block_name(fpo, lang),
        'village_town': fpo.village_town,
        'address': ', '.join(p for p in [fpo.address_line1, fpo.address_line2] if p),
        'pincode': fpo.pincode,
    }


def build_plan_context(fpo) -> dict:
    """Facts fed to the LLM (always English names) — stored as input_snapshot."""
    from apps.gis_module.services import resolve_fpo_soil_region, resolve_fpo_zone

    ctx = build_profile(fpo, 'en')
    ctx['primary_commodity_codes'] = list(fpo.primary_commodities or [])
    ctx['secondary_commodity_codes'] = list(fpo.secondary_commodities or [])

    # Spatial lookups are best-effort — a missing pin or GIS layer shouldn't
    # block plan generation, the prompt just says "Not available".
    try:
        zone = resolve_fpo_zone(fpo)
        ctx['agro_climatic_zone'] = zone.name_en if zone else None
    except Exception:
        logger.exception('business_plan: zone lookup failed for FPO %s', fpo.pk)
        ctx['agro_climatic_zone'] = None
    try:
        soil = resolve_fpo_soil_region(fpo)
        ctx['soil'] = f'{soil.name_en} ({soil.soil_type})' if soil else None
    except Exception:
        logger.exception('business_plan: soil lookup failed for FPO %s', fpo.pk)
        ctx['soil'] = None

    ctx['total_members'] = fpo.total_members
    ctx['female_members'] = fpo.female_members
    ctx['current_tier'] = fpo.current_tier
    ctx['annual_turnover'] = str(fpo.annual_turnover) if fpo.annual_turnover is not None else None
    return ctx


def is_outdated(plan: BusinessPlan, fpo) -> bool:
    """True when the FPO's commodities or location changed since the plan was generated."""
    snap = plan.input_snapshot or {}
    return (
        snap.get('primary_commodity_codes') != list(fpo.primary_commodities or [])
        or snap.get('secondary_commodity_codes') != list(fpo.secondary_commodities or [])
        or snap.get('district') != fpo.district
        or snap.get('block_taluk') != fpo.block_taluk
    )


# ─────────────────────────────────────────────────────────────────────────────
# Prompt
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM = (
    'You are an agri-business advisor to Farmer Producer Organisations (FPOs) in Kerala, India, '
    'working with Kerala Agricultural University. You write concise, practical business plans '
    'that an FPO board can act on. You respond with a single JSON object only — no markdown, '
    'no commentary.'
)

_OUTPUT_SCHEMA = """{
  "title": string,
  "executive_summary": string (80-120 words),
  "commodity_focus": [{"commodity": string, "role": "primary" | "secondary", "opportunity": string}],
  "location_advantages": string,
  "business_activities": [{"name": string, "description": string}],
  "market_strategy": {"target_markets": [string], "channels": [string], "branding": string},
  "operations_plan": string,
  "financial_outline": {
    "estimated_investment": string,
    "working_capital": string,
    "revenue_streams": [string],
    "funding_sources": [string]
  },
  "risks": [{"risk": string, "mitigation": string}],
  "action_plan": [{"period": string, "activities": [string]}],
  "key_recommendations": [string]
}"""

REQUIRED_KEYS = ('executive_summary', 'business_activities', 'action_plan')


def _fact(value) -> str:
    return str(value) if value not in (None, '', []) else 'Not available'


def _names(items: list[dict]) -> str:
    return ', '.join(i['name'] for i in items) or 'None'


def build_prompt(ctx: dict, lang: str) -> str:
    location = ', '.join(p for p in [
        ctx.get('village_town'), ctx.get('block_display'), ctx.get('district_display'), 'Kerala',
    ] if p)
    language_rule = (
        'Write every string value in Malayalam (മലയാളം). Keep the JSON keys in English exactly as '
        'given. Commodity and scheme names may stay in English where that is the common usage.'
        if lang == 'ml' else
        'Write every string value in clear, simple English.'
    )
    return f"""Prepare a small business plan for the FPO below.

FACTS
- FPO name: {_fact(ctx.get('fpo_name'))}
- Primary commodities: {_names(ctx.get('primary_commodities', []))}
- Secondary commodities: {_names(ctx.get('secondary_commodities', []))}
- Location: {_fact(location)} (PIN {_fact(ctx.get('pincode'))})
- Agro-climatic zone: {_fact(ctx.get('agro_climatic_zone'))}
- Soil: {_fact(ctx.get('soil'))}
- Members: {_fact(ctx.get('total_members'))} (women: {_fact(ctx.get('female_members'))})
- Current tier: {_fact(ctx.get('current_tier'))}
- Annual turnover (INR): {_fact(ctx.get('annual_turnover'))}

RULES
1. Build the plan around the primary commodities; use the secondary commodities for diversification,
   off-season income or bundled products.
2. Use the location: nearby markets, district strengths, climate/soil fit, logistics.
3. Suggest realistic value addition, aggregation, processing and marketing activities for a Kerala FPO
   of this size.
4. Funding sources should be real Indian / Kerala schemes where relevant (e.g. NABARD, SFAC equity grant
   and credit guarantee, PMFME, Agriculture Infrastructure Fund, Kerala Agriculture Department / VFPCK).
5. Give money as indicative ranges in ₹ lakhs. Never invent exact figures presented as facts, and never
   output placeholders like [X] or "TBD".
6. Keep it concise: 1000-1500 words in total. 3-5 items per list; action_plan should cover
   "0-6 months", "6-12 months" and "Year 2-3".
7. {language_rule}

Return ONLY a JSON object matching this schema:
{_OUTPUT_SCHEMA}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Parsing
# ─────────────────────────────────────────────────────────────────────────────

_FENCE_RE = re.compile(r'^```(?:json)?\s*|\s*```$', re.IGNORECASE)

# Expected type per key — anything missing / mistyped is replaced with the
# default so the frontend can rely on the shape.
_SHAPE = {
    'title': str,
    'executive_summary': str,
    'commodity_focus': list,
    'location_advantages': str,
    'business_activities': list,
    'market_strategy': dict,
    'operations_plan': str,
    'financial_outline': dict,
    'risks': list,
    'action_plan': list,
    'key_recommendations': list,
}


def parse_plan(text: str) -> dict:
    """Parse + normalise the LLM output. Raises ValueError when unusable."""
    cleaned = _FENCE_RE.sub('', (text or '').strip())
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Some models wrap the object in prose despite JSON mode.
        start, end = cleaned.find('{'), cleaned.rfind('}')
        if start == -1 or end <= start:
            raise ValueError('LLM output is not JSON')
        data = json.loads(cleaned[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError('LLM output is not a JSON object')

    plan = {key: data.get(key) if isinstance(data.get(key), typ) else typ() for key, typ in _SHAPE.items()}
    missing = [k for k in REQUIRED_KEYS if not plan[k]]
    if missing:
        raise ValueError(f'LLM output missing required sections: {", ".join(missing)}')
    return plan


def _mock_plan(ctx: dict) -> dict:
    """Deterministic plan for provider='mock' so the tab works without a key."""
    primary = _names(ctx.get('primary_commodities', []))
    return {
        'title': f'[MOCK] Business plan — {primary}',
        'executive_summary': (
            f'[MOCK] Placeholder plan for {ctx.get("fpo_name")} built around {primary} in '
            f'{ctx.get("district_display") or "Kerala"}. Configure the business_plan AI service '
            'with a Google Gemini key to generate a real plan.'
        ),
        'commodity_focus': [
            {'commodity': c['name'], 'role': 'primary', 'opportunity': '[MOCK] Aggregation and value addition.'}
            for c in ctx.get('primary_commodities', [])
        ] + [
            {'commodity': c['name'], 'role': 'secondary', 'opportunity': '[MOCK] Diversification.'}
            for c in ctx.get('secondary_commodities', [])
        ],
        'location_advantages': '[MOCK] Location advantages.',
        'business_activities': [{'name': '[MOCK] Collective aggregation', 'description': '[MOCK]'}],
        'market_strategy': {'target_markets': ['[MOCK]'], 'channels': ['[MOCK]'], 'branding': '[MOCK]'},
        'operations_plan': '[MOCK] Operations plan.',
        'financial_outline': {
            'estimated_investment': '[MOCK]', 'working_capital': '[MOCK]',
            'revenue_streams': ['[MOCK]'], 'funding_sources': ['[MOCK]'],
        },
        'risks': [{'risk': '[MOCK]', 'mitigation': '[MOCK]'}],
        'action_plan': [{'period': '0-6 months', 'activities': ['[MOCK]']}],
        'key_recommendations': ['[MOCK]'],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Generation
# ─────────────────────────────────────────────────────────────────────────────

def _log_failure(cfg, fpo, user, error: str, response: LLMResponse | None = None):
    AIUsageLog.objects.create(
        service=AIUsageLog.Service.BUSINESS_PLAN,
        fpo=fpo,
        user=user,
        provider=response.provider if response else cfg.provider,
        model_used=(response.model if response else cfg.model_name) or 'unknown',
        input_tokens=response.input_tokens if response else 0,
        output_tokens=response.output_tokens if response else 0,
        total_tokens=(response.input_tokens + response.output_tokens) if response else 0,
        cost_usd=response.cost_usd if response else Decimal('0'),
        cost_inr=(response.cost_usd * cfg.usd_to_inr_rate) if response else Decimal('0'),
        success=False,
        error_message=error[:500],
        reference_id=str(fpo.pk),
    )


def generate_business_plan(fpo, user, lang: str = 'en') -> BusinessPlan:
    """Generate (or regenerate) the FPO's business plan in `lang`. Raises BusinessPlanError."""
    lang = normalise_language(lang)

    if not fpo.primary_commodities:
        raise BusinessPlanError(BusinessPlanError.NO_COMMODITY)

    cfg, _ = AIServiceConfig.objects.get_or_create(service=AIServiceConfig.Service.BUSINESS_PLAN)
    if not cfg.is_enabled:
        raise BusinessPlanError(BusinessPlanError.SERVICE_UNAVAILABLE, 'business_plan service disabled')
    if cfg.monthly_cap_inr and cfg.current_month_cost_inr >= cfg.monthly_cap_inr:
        raise BusinessPlanError(BusinessPlanError.SERVICE_UNAVAILABLE, 'monthly budget cap reached')

    ctx = build_plan_context(fpo)
    prompt = build_prompt(ctx, lang)

    try:
        response = call_llm(
            cfg, prompt, max_tokens=MAX_OUTPUT_TOKENS, system=_SYSTEM,
            response_mime_type='application/json', max_retries=2,
        )
    except LLMError as e:
        _log_failure(cfg, fpo, user, str(e))
        logger.warning('business_plan: LLM call failed for FPO %s: %s', fpo.pk, e)
        raise BusinessPlanError(BusinessPlanError.GENERATION_FAILED, str(e)) from e

    try:
        content = _mock_plan(ctx) if response.provider == 'mock' else parse_plan(response.text)
    except ValueError as e:
        # The tokens were still spent — log them and count them against the cap.
        _log_failure(cfg, fpo, user, f'Unparseable output: {e}', response)
        if response.cost_usd > 0:
            cfg.record_usage(
                cost_inr=float(response.cost_usd * cfg.usd_to_inr_rate),
                tokens=response.input_tokens + response.output_tokens,
            )
        logger.warning('business_plan: unparseable LLM output for FPO %s: %s', fpo.pk, e)
        raise BusinessPlanError(BusinessPlanError.GENERATION_FAILED, str(e)) from e

    cost_inr = response.cost_usd * cfg.usd_to_inr_rate
    AIUsageLog.objects.create(
        service=AIUsageLog.Service.BUSINESS_PLAN,
        fpo=fpo,
        user=user,
        provider=response.provider,
        model_used=response.model,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        total_tokens=response.input_tokens + response.output_tokens,
        cost_usd=response.cost_usd,
        cost_inr=cost_inr,
        success=True,
        reference_id=str(fpo.pk),
    )
    if response.cost_usd > 0:
        cfg.record_usage(
            cost_inr=float(cost_inr),
            tokens=response.input_tokens + response.output_tokens,
        )

    plan, _ = BusinessPlan.objects.update_or_create(
        fpo=fpo,
        language=lang,
        defaults={
            'financial_year': get_current_financial_year(),
            'input_snapshot': ctx,
            'content': content,
            'provider': response.provider,
            'model_used': response.model,
            'generated_at': timezone.now(),
            'generated_by': user,
        },
    )
    return plan
