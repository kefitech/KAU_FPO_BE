"""
Tests for AI Business Plan generation (apps/recommendations/business_plan.py).

DB-free: the LLM gateway, AIServiceConfig and persistence are mocked so the
suite runs without Postgres / a Gemini key.

    python manage.py test apps.recommendations.tests_business_plan
"""
import json
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from apps.fpo.services.dpr.llm_gateway import LLMError, LLMResponse
from apps.recommendations import business_plan as bp


def _ctx(**overrides):
    ctx = {
        'fpo_name': 'Wayanad Coffee FPO',
        'primary_commodities': [{'code': 'COFFEE', 'name': 'Coffee'}],
        'secondary_commodities': [{'code': 'PEPPER', 'name': 'Black Pepper'}],
        'district_display': 'Wayanad',
        'block_display': 'Mananthavady',
        'village_town': 'Thrissilery',
        'pincode': '670646',
        'agro_climatic_zone': 'High Range Zone',
        'soil': None,
        'total_members': 420,
        'female_members': 150,
        'current_tier': 'B',
        'annual_turnover': None,
    }
    ctx.update(overrides)
    return ctx


def _valid_plan_json(**overrides):
    plan = {
        'title': 'Coffee value chain plan',
        'executive_summary': 'Aggregate and process coffee.',
        'commodity_focus': [{'commodity': 'Coffee', 'role': 'primary', 'opportunity': 'Roasting'}],
        'location_advantages': 'Wayanad highlands.',
        'business_activities': [{'name': 'Aggregation', 'description': 'Collective procurement'}],
        'market_strategy': {'target_markets': ['Kochi'], 'channels': ['Retail'], 'branding': 'Wayanad Gold'},
        'operations_plan': 'Hub and spoke.',
        'financial_outline': {'estimated_investment': '₹15-20 lakhs', 'working_capital': '₹5 lakhs',
                              'revenue_streams': ['Roasted coffee'], 'funding_sources': ['SFAC']},
        'risks': [{'risk': 'Price volatility', 'mitigation': 'Forward contracts'}],
        'action_plan': [{'period': '0-6 months', 'activities': ['Set up collection centres']}],
        'key_recommendations': ['Register a brand'],
    }
    plan.update(overrides)
    return json.dumps(plan)


class ParsePlanTests(unittest.TestCase):
    def test_parses_valid_json(self):
        plan = bp.parse_plan(_valid_plan_json())
        self.assertEqual(plan['title'], 'Coffee value chain plan')
        self.assertEqual(plan['risks'][0]['risk'], 'Price volatility')

    def test_strips_code_fences(self):
        plan = bp.parse_plan('```json\n' + _valid_plan_json() + '\n```')
        self.assertEqual(plan['executive_summary'], 'Aggregate and process coffee.')

    def test_extracts_object_wrapped_in_prose(self):
        plan = bp.parse_plan('Here is the plan:\n' + _valid_plan_json() + '\nThanks!')
        self.assertTrue(plan['action_plan'])

    def test_mistyped_optional_sections_are_defaulted(self):
        plan = bp.parse_plan(_valid_plan_json(risks='none', market_strategy=None, title=5))
        self.assertEqual(plan['risks'], [])
        self.assertEqual(plan['market_strategy'], {})
        self.assertEqual(plan['title'], '')

    def test_missing_required_section_raises(self):
        with self.assertRaises(ValueError):
            bp.parse_plan(_valid_plan_json(executive_summary=''))

    def test_non_json_raises(self):
        with self.assertRaises(ValueError):
            bp.parse_plan('I cannot help with that.')

    def test_json_array_raises(self):
        with self.assertRaises(ValueError):
            bp.parse_plan('[1, 2, 3]')


class BuildPromptTests(unittest.TestCase):
    def test_includes_commodities_and_location(self):
        prompt = bp.build_prompt(_ctx(), 'en')
        self.assertIn('Primary commodities: Coffee', prompt)
        self.assertIn('Secondary commodities: Black Pepper', prompt)
        self.assertIn('Thrissilery, Mananthavady, Wayanad, Kerala', prompt)
        self.assertIn('Agro-climatic zone: High Range Zone', prompt)
        self.assertIn('Soil: Not available', prompt)
        self.assertIn('"key_recommendations"', prompt)

    def test_malayalam_rule(self):
        self.assertIn('Malayalam', bp.build_prompt(_ctx(), 'ml'))
        self.assertNotIn('Malayalam', bp.build_prompt(_ctx(), 'en'))

    def test_no_secondary_commodities(self):
        prompt = bp.build_prompt(_ctx(secondary_commodities=[]), 'en')
        self.assertIn('Secondary commodities: None', prompt)


class IsOutdatedTests(unittest.TestCase):
    def _fpo(self, **kw):
        base = dict(primary_commodities=['COFFEE'], secondary_commodities=['PEPPER'],
                    district='WYD', block_taluk='MNT')
        base.update(kw)
        return SimpleNamespace(**base)

    def _plan(self):
        return SimpleNamespace(input_snapshot={
            'primary_commodity_codes': ['COFFEE'], 'secondary_commodity_codes': ['PEPPER'],
            'district': 'WYD', 'block_taluk': 'MNT',
        })

    def test_unchanged(self):
        self.assertFalse(bp.is_outdated(self._plan(), self._fpo()))

    def test_commodity_changed(self):
        self.assertTrue(bp.is_outdated(self._plan(), self._fpo(primary_commodities=['COFFEE', 'TEA'])))

    def test_location_changed(self):
        self.assertTrue(bp.is_outdated(self._plan(), self._fpo(block_taluk='SBY')))


class GenerateBusinessPlanTests(unittest.TestCase):
    def setUp(self):
        self.fpo = SimpleNamespace(pk=7, primary_commodities=['COFFEE'])
        self.user = SimpleNamespace(pk=1)
        self.cfg = SimpleNamespace(
            is_enabled=True, monthly_cap_inr=Decimal('0'), current_month_cost_inr=Decimal('0'),
            provider='google', model_name='gemini-2.5-flash', usd_to_inr_rate=Decimal('84'),
            record_usage=mock.Mock(),
        )
        patches = [
            mock.patch.object(bp.AIServiceConfig.objects, 'get_or_create', return_value=(self.cfg, False)),
            mock.patch.object(bp, 'build_plan_context', return_value=_ctx()),
            mock.patch.object(bp.AIUsageLog.objects, 'create'),
            mock.patch.object(bp.BusinessPlan.objects, 'update_or_create',
                              side_effect=lambda defaults, **kw: (SimpleNamespace(**kw, **defaults), True)),
        ]
        self.mocks = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)
        self.usage_create = self.mocks[2]

    def _response(self, text, provider='google'):
        return LLMResponse(text=text, input_tokens=1000, output_tokens=3000,
                           cost_usd=Decimal('0.01'), provider=provider, model='gemini-2.5-flash')

    def test_success_persists_plan_and_records_usage(self):
        with mock.patch.object(bp, 'call_llm', return_value=self._response(_valid_plan_json())) as call:
            plan = bp.generate_business_plan(self.fpo, self.user, 'ml')
        self.assertEqual(call.call_args.kwargs['response_mime_type'], 'application/json')
        self.assertEqual(plan.language, 'ml')
        self.assertEqual(plan.content['title'], 'Coffee value chain plan')
        self.assertTrue(self.usage_create.call_args.kwargs['success'])
        self.cfg.record_usage.assert_called_once()

    def test_unknown_language_falls_back_to_english(self):
        with mock.patch.object(bp, 'call_llm', return_value=self._response(_valid_plan_json())):
            plan = bp.generate_business_plan(self.fpo, self.user, 'ta')
        self.assertEqual(plan.language, 'en')

    def test_no_primary_commodity(self):
        self.fpo.primary_commodities = []
        with self.assertRaises(bp.BusinessPlanError) as ctx:
            bp.generate_business_plan(self.fpo, self.user, 'en')
        self.assertEqual(ctx.exception.code, bp.BusinessPlanError.NO_COMMODITY)

    def test_disabled_service(self):
        self.cfg.is_enabled = False
        with self.assertRaises(bp.BusinessPlanError) as ctx:
            bp.generate_business_plan(self.fpo, self.user, 'en')
        self.assertEqual(ctx.exception.code, bp.BusinessPlanError.SERVICE_UNAVAILABLE)

    def test_budget_cap_reached(self):
        self.cfg.monthly_cap_inr = Decimal('100')
        self.cfg.current_month_cost_inr = Decimal('100')
        with mock.patch.object(bp, 'call_llm') as call:
            with self.assertRaises(bp.BusinessPlanError) as ctx:
                bp.generate_business_plan(self.fpo, self.user, 'en')
        call.assert_not_called()
        self.assertEqual(ctx.exception.code, bp.BusinessPlanError.SERVICE_UNAVAILABLE)

    def test_llm_error_logs_failure(self):
        with mock.patch.object(bp, 'call_llm', side_effect=LLMError('boom')):
            with self.assertRaises(bp.BusinessPlanError) as ctx:
                bp.generate_business_plan(self.fpo, self.user, 'en')
        self.assertEqual(ctx.exception.code, bp.BusinessPlanError.GENERATION_FAILED)
        self.assertFalse(self.usage_create.call_args.kwargs['success'])

    def test_unparseable_output_logs_failure_and_bills(self):
        with mock.patch.object(bp, 'call_llm', return_value=self._response('not json')):
            with self.assertRaises(bp.BusinessPlanError) as ctx:
                bp.generate_business_plan(self.fpo, self.user, 'en')
        self.assertEqual(ctx.exception.code, bp.BusinessPlanError.GENERATION_FAILED)
        self.assertFalse(self.usage_create.call_args.kwargs['success'])
        self.cfg.record_usage.assert_called_once()

    def test_mock_provider_returns_stub_plan(self):
        with mock.patch.object(bp, 'call_llm', return_value=self._response('{"mock": true}', provider='mock')):
            plan = bp.generate_business_plan(self.fpo, self.user, 'en')
        self.assertIn('[MOCK]', plan.content['title'])
        self.assertTrue(plan.content['action_plan'])


class GeminiRetryTests(unittest.TestCase):
    """llm_gateway._call_google retries transient Gemini errors (e.g. 503 high demand)."""

    def setUp(self):
        from google.genai import errors as genai_errors
        from apps.fpo.services.dpr import llm_gateway

        self.gateway = llm_gateway
        self.overloaded = genai_errors.APIError(
            503, {'error': {'code': 503, 'message': 'high demand', 'status': 'UNAVAILABLE'}},
        )
        self.bad_request = genai_errors.APIError(
            400, {'error': {'code': 400, 'message': 'bad', 'status': 'INVALID_ARGUMENT'}},
        )
        self.ok = SimpleNamespace(text='{"ok": true}', usage_metadata=SimpleNamespace(
            prompt_token_count=10, candidates_token_count=20, thoughts_token_count=0,
        ))
        self.cfg = SimpleNamespace(provider='google', model_name='gemini-2.5-flash', get_api_key=lambda: 'k')
        sleep = mock.patch.object(llm_gateway.time, 'sleep')
        self.sleep = sleep.start()
        self.addCleanup(sleep.stop)

    def _call(self, side_effect, **kw):
        with mock.patch('google.genai.Client') as client_cls:
            client_cls.return_value.models.generate_content.side_effect = side_effect
            result = self.gateway.call_llm(self.cfg, 'p', **kw)
            return result, client_cls.return_value.models.generate_content.call_count

    def test_retries_then_succeeds(self):
        result, calls = self._call([self.overloaded, self.overloaded, self.ok], max_retries=2)
        self.assertEqual(result.text, '{"ok": true}')
        self.assertEqual(calls, 3)
        self.assertEqual([c.args[0] for c in self.sleep.call_args_list], [2, 4])

    def test_gives_up_after_max_retries(self):
        with self.assertRaises(LLMError):
            self._call([self.overloaded] * 3, max_retries=2)
        self.assertEqual(self.sleep.call_count, 2)

    def test_no_retry_by_default(self):
        with self.assertRaises(LLMError):
            self._call([self.overloaded, self.ok])
        self.sleep.assert_not_called()

    def test_client_errors_are_not_retried(self):
        with self.assertRaises(LLMError):
            self._call([self.bad_request, self.ok], max_retries=2)
        self.sleep.assert_not_called()
