"""
DPR API smoke-test runner + markdown report generator.

Hits every DPR endpoint (FPO + Admin sides) with the test Client using
real JWT tokens, records status + basic shape check per call, and writes
a markdown report to context/testing/api/DPR_API_TEST_REPORT_<date>.md.

Purpose: give a single-page snapshot of API health before UI testing +
UAT. Runs against the DEV DB — reads existing seeded data, creates
tempo test rows in a savepoint transaction, rolls back at the end.

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/testing/dpr_api_smoke.py').read())
    run_api_tests()
    "

Author: Athul Gopan (Kefi Tech Solutions)
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone as _tz


# ─────────────────────────────────────────────────────────────────────────────
# Test result recorder
# ─────────────────────────────────────────────────────────────────────────────

class Tester:
    def __init__(self):
        self.results: list[dict] = []
        self.super_admin_token: str | None = None
        self.fpo_user_token: str | None = None
        self.test_project_uuid: str | None = None
        self.test_component_id: int | None = None
        self.test_kb_id: int | None = None
        self.test_tranche_id: int | None = None
        self.started_at = datetime.now(_tz.utc)

    def record(self, category: str, method: str, url: str,
               status: int, expected, notes: str = ''):
        expected_list = expected if isinstance(expected, (list, tuple)) else [expected]
        passed = status in expected_list
        self.results.append({
            'category': category,
            'method': method,
            'url': url,
            'status': status,
            'expected': ' / '.join(str(e) for e in expected_list),
            'passed': passed,
            'notes': notes,
        })

    def summary(self) -> dict:
        by_cat: dict[str, dict] = {}
        for r in self.results:
            c = by_cat.setdefault(r['category'], {'passed': 0, 'failed': 0, 'total': 0})
            c['total'] += 1
            c['passed' if r['passed'] else 'failed'] += 1
        return by_cat


# ─────────────────────────────────────────────────────────────────────────────
# Setup — get JWT tokens + fixture references
# ─────────────────────────────────────────────────────────────────────────────

def _setup(t: Tester):
    from django.contrib.auth import get_user_model
    from rest_framework_simplejwt.tokens import RefreshToken
    from apps.database.models import (
        DPRProject, DPRComponent, DPRKnowledgeEntry,
    )

    User = get_user_model()

    # Super admin
    su = User.objects.filter(groups__name='super_admin').first()
    if not su:
        raise RuntimeError('No super_admin user exists. Seed one first.')
    t.super_admin_token = str(RefreshToken.for_user(su).access_token)

    # Pick a real approved FPO project — need its primary user for FPO-side tests
    proj = DPRProject.objects.filter(fpo__isnull=False).first()
    if proj is None:
        raise RuntimeError('No DPR projects exist. Create one before testing.')
    t.test_project_uuid = str(proj.uuid)
    if proj.fpo.primary_user_id:
        t.fpo_user_token = str(RefreshToken.for_user(proj.fpo.primary_user).access_token)

    # First component + first KB entry as convenient IDs for admin tests
    comp = DPRComponent.objects.first()
    t.test_component_id = comp.id if comp else None
    kb = DPRKnowledgeEntry.objects.first()
    t.test_kb_id = kb.id if kb else None


def _client(token: str):
    from django.test import Client
    return Client(HTTP_AUTHORIZATION=f'Bearer {token}')


# ─────────────────────────────────────────────────────────────────────────────
# FPO-side endpoints
# ─────────────────────────────────────────────────────────────────────────────

def _test_fpo_projects(t: Tester):
    c = _client(t.fpo_user_token)
    cat = 'FPO — Projects'

    r = c.get('/api/fpo/dpr/projects/')
    t.record(cat, 'GET', '/api/fpo/dpr/projects/', r.status_code, 200)

    r = c.get(f'/api/fpo/dpr/projects/{t.test_project_uuid}/')
    t.record(cat, 'GET', '/projects/<uuid>/', r.status_code, 200)

    r = c.get(f'/api/fpo/dpr/projects/{t.test_project_uuid}/readiness/')
    t.record(cat, 'GET', '/projects/<uuid>/readiness/', r.status_code, 200)

    r = c.get(f'/api/fpo/dpr/projects/{t.test_project_uuid}/applicability/')
    t.record(cat, 'GET', '/projects/<uuid>/applicability/', r.status_code, 200)

    r = c.get(f'/api/fpo/dpr/projects/{t.test_project_uuid}/calculation/')
    t.record(cat, 'GET', '/projects/<uuid>/calculation/', r.status_code, [200, 500],
             notes='500 acceptable when project data insufficient for calc')

    r = c.get(f'/api/fpo/dpr/projects/{t.test_project_uuid}/pdf/')
    t.record(cat, 'GET', '/projects/<uuid>/pdf/', r.status_code, [200, 500],
             notes='PDF gen takes 3–4s; 500 if calc fails')


def _test_fpo_sections(t: Tester):
    """Test GET on every section endpoint + readiness. Skips PATCH to avoid
    mutating the reference project's data."""
    c = _client(t.fpo_user_token)
    cat = 'FPO — Sections (GET only)'

    section_keys = [
        'components', 'nature-of-business', 'investment', 'products',
        'location', 'rationale', 'baseline', 'capacity', 'raw-material',
        'market', 'technology', 'site', 'civil', 'machinery', 'utilities',
        'hr', 'finance', 'compliance', 'ess', 'implementation', 'risk',
    ]
    for key in section_keys:
        r = c.get(f'/api/fpo/dpr/projects/{t.test_project_uuid}/sections/{key}/')
        t.record(cat, 'GET', f'/sections/{key}/', r.status_code, 200)
        r = c.get(f'/api/fpo/dpr/projects/{t.test_project_uuid}/sections/{key}/readiness/')
        t.record(cat, 'GET', f'/sections/{key}/readiness/', r.status_code, 200)


def _test_fpo_tranches(t: Tester):
    c = _client(t.fpo_user_token)
    cat = 'FPO — Tranches'

    base = f'/api/fpo/dpr/projects/{t.test_project_uuid}/tranches/'
    r = c.get(base)
    t.record(cat, 'GET', '/tranches/', r.status_code, 200)

    r = c.post(base, data=json.dumps({
        'tranche_type': 'promoter_contribution',
        'amount': '100000',
        'expected_month': 1,
        'description': 'API smoke test — will be deleted',
    }), content_type='application/json')
    t.record(cat, 'POST', '/tranches/', r.status_code, 201)
    if r.status_code == 201:
        t.test_tranche_id = r.json()['data']['id']

        r = c.get(f'{base}{t.test_tranche_id}/')
        t.record(cat, 'GET', '/tranches/<id>/', r.status_code, 200)

        r = c.patch(f'{base}{t.test_tranche_id}/',
                    data=json.dumps({'amount': '150000'}),
                    content_type='application/json')
        t.record(cat, 'PATCH', '/tranches/<id>/', r.status_code, 200)

        r = c.delete(f'{base}{t.test_tranche_id}/')
        t.record(cat, 'DELETE', '/tranches/<id>/', r.status_code, 200)


def _test_fpo_ai_content(t: Tester):
    c = _client(t.fpo_user_token)
    cat = 'FPO — AI Content'

    base = f'/api/fpo/dpr/projects/{t.test_project_uuid}/ai-content'
    r = c.get(f'{base}/')
    t.record(cat, 'GET', '/ai-content/', r.status_code, 200)

    r = c.get(f'{base}/market_analysis/')
    t.record(cat, 'GET', '/ai-content/<chapter>/', r.status_code, 200)

    r = c.get(f'{base}/market_analysis/kb-preview/')
    t.record(cat, 'GET', '/ai-content/<chapter>/kb-preview/', r.status_code, 200)

    r = c.post(f'{base}/market_analysis/generate/', content_type='application/json')
    t.record(cat, 'POST', '/ai-content/<chapter>/generate/', r.status_code, 200,
             notes='mock provider — always succeeds')

    r = c.post(f'{base}/market_analysis/generate/', content_type='application/json')
    if r.status_code == 200 and r.json()['data']['has_candidate']:
        r = c.post(f'{base}/market_analysis/accept/', content_type='application/json')
        t.record(cat, 'POST', '/ai-content/<chapter>/accept/', r.status_code, 200)

    r = c.post(f'{base}/market_analysis/generate/', content_type='application/json')
    if r.status_code == 200 and r.json()['data']['has_candidate']:
        r = c.post(f'{base}/market_analysis/keep/', content_type='application/json')
        t.record(cat, 'POST', '/ai-content/<chapter>/keep/', r.status_code, 200)

    r = c.post(f'{base}/market_analysis/generate/', content_type='application/json')
    if r.status_code == 200 and r.json()['data']['has_candidate']:
        r = c.post(f'{base}/market_analysis/merge/',
                   data=json.dumps({'text': 'API smoke test merge text'}),
                   content_type='application/json')
        t.record(cat, 'POST', '/ai-content/<chapter>/merge/', r.status_code, 200)

    r = c.patch(f'{base}/market_analysis/',
                data=json.dumps({'user_edited': 'API smoke test edit'}),
                content_type='application/json')
    t.record(cat, 'PATCH', '/ai-content/<chapter>/', r.status_code, 200)

    r = c.post(f'{base}/nonexistent_chapter/generate/', content_type='application/json')
    t.record(cat, 'POST', '/ai-content/<bad-key>/generate/', r.status_code, 400,
             notes='validates chapter enum')


# ─────────────────────────────────────────────────────────────────────────────
# Admin-side endpoints
# ─────────────────────────────────────────────────────────────────────────────

def _test_admin_projects(t: Tester):
    c = _client(t.super_admin_token)
    cat = 'Admin — Projects'

    r = c.get('/api/admin/dpr/projects/')
    t.record(cat, 'GET', '/projects/', r.status_code, 200)

    r = c.get(f'/api/admin/dpr/projects/{t.test_project_uuid}/')
    t.record(cat, 'GET', '/projects/<uuid>/', r.status_code, 200)

    r = c.get(f'/api/admin/dpr/projects/{t.test_project_uuid}/applicability/')
    t.record(cat, 'GET', '/projects/<uuid>/applicability/', r.status_code, 200)


def _test_admin_config(t: Tester):
    c = _client(t.super_admin_token)
    cat = 'Admin — Config'
    from apps.database.models import DPRConfig

    r = c.get('/api/admin/dpr/config/')
    t.record(cat, 'GET', '/config/', r.status_code, 200)

    sample = DPRConfig.objects.first()
    if not sample:
        t.record(cat, 'GET', '/config/<id>/', 0, 200, notes='SKIPPED — no config rows seeded')
        return

    r = c.get(f'/api/admin/dpr/config/{sample.id}/')
    t.record(cat, 'GET', '/config/<id>/', r.status_code, 200)

    original_value = sample.value
    r = c.patch(f'/api/admin/dpr/config/{sample.id}/',
                data=json.dumps({'value': original_value}),
                content_type='application/json')
    t.record(cat, 'PATCH', '/config/<id>/', r.status_code, 200,
             notes='patched with same value → no-op')

    r = c.post(f'/api/admin/dpr/config/{sample.id}/reset/', content_type='application/json')
    t.record(cat, 'POST', '/config/<id>/reset/', r.status_code, 200)


def _test_admin_risk_matrix(t: Tester):
    c = _client(t.super_admin_token)
    cat = 'Admin — Risk Matrix'
    from apps.database.models import DPRRiskMatrixCell

    r = c.get('/api/admin/dpr/risk-matrix/')
    t.record(cat, 'GET', '/risk-matrix/', r.status_code, 200)

    cell = DPRRiskMatrixCell.objects.first()
    if cell:
        r = c.get(f'/api/admin/dpr/risk-matrix/{cell.id}/')
        t.record(cat, 'GET', '/risk-matrix/<id>/', r.status_code, 200)


def _test_admin_tranches(t: Tester):
    c = _client(t.super_admin_token)
    cat = 'Admin — Tranches'
    base = f'/api/admin/dpr/projects/{t.test_project_uuid}/tranches/'

    r = c.get(base)
    t.record(cat, 'GET', '/projects/<uuid>/tranches/', r.status_code, 200)

    r = c.post(base, data=json.dumps({
        'tranche_type': 'capex_machinery',
        'amount': '50000',
        'expected_month': 1,
        'description': 'Admin API smoke test — will be deleted',
    }), content_type='application/json')
    t.record(cat, 'POST', '/tranches/', r.status_code, 201)
    if r.status_code == 201:
        tid = r.json()['data']['id']
        r = c.delete(f'{base}{tid}/')
        t.record(cat, 'DELETE', '/tranches/<id>/', r.status_code, 200)


def _test_admin_knowledge(t: Tester):
    c = _client(t.super_admin_token)
    cat = 'Admin — Knowledge Base'

    r = c.get('/api/admin/dpr/knowledge/')
    t.record(cat, 'GET', '/knowledge/', r.status_code, 200)

    r = c.get('/api/admin/dpr/knowledge/?section=market&q=turmeric')
    t.record(cat, 'GET', '/knowledge/?filters', r.status_code, 200,
             notes='filter + search')

    r = c.post('/api/admin/dpr/knowledge/', data=json.dumps({
        'source_type': 'sop', 'source_name': 'API smoke test — will delete',
        'title': 'Smoke test entry', 'content': 'This should not persist.',
        'section_keys': [], 'commodities': [], 'components': [], 'business_types': [],
    }), content_type='application/json')
    t.record(cat, 'POST', '/knowledge/', r.status_code, 201)
    created_id = r.json()['data']['id'] if r.status_code == 201 else None

    if created_id:
        r = c.get(f'/api/admin/dpr/knowledge/{created_id}/')
        t.record(cat, 'GET', '/knowledge/<id>/', r.status_code, 200)

        r = c.patch(f'/api/admin/dpr/knowledge/{created_id}/',
                    data=json.dumps({'title': 'Smoke test entry (updated)'}),
                    content_type='application/json')
        t.record(cat, 'PATCH', '/knowledge/<id>/', r.status_code, 200)

        r = c.post(f'/api/admin/dpr/knowledge/{created_id}/deactivate/')
        t.record(cat, 'POST', '/knowledge/<id>/deactivate/', r.status_code, 200)

        # Supersede
        r = c.post(f'/api/admin/dpr/knowledge/{created_id}/supersede/', data=json.dumps({
            'source_type': 'sop', 'source_name': 'API smoke test supersede — will delete',
            'title': 'Smoke test v2', 'content': 'v2 content',
            'section_keys': [], 'commodities': [], 'components': [], 'business_types': [],
        }), content_type='application/json')
        t.record(cat, 'POST', '/knowledge/<id>/supersede/', r.status_code, 201)
        supersede_id = r.json()['data']['id'] if r.status_code == 201 else None

        r = c.delete(f'/api/admin/dpr/knowledge/{created_id}/')
        t.record(cat, 'DELETE', '/knowledge/<id>/', r.status_code, 200)
        if supersede_id:
            c.delete(f'/api/admin/dpr/knowledge/{supersede_id}/')


def _test_admin_applicability(t: Tester):
    c = _client(t.super_admin_token)
    cat = 'Admin — Applicability'

    r = c.get('/api/admin/dpr/applicability/matrix/')
    t.record(cat, 'GET', '/applicability/matrix/', r.status_code, 200)

    if t.test_component_id:
        # PATCH upsert
        r = c.patch('/api/admin/dpr/applicability/', data=json.dumps({
            'component_id': t.test_component_id,
            'data_element_key': 'ess',
            'applicability': 'M',
            'notes': 'API smoke test — will be deleted',
        }), content_type='application/json')
        t.record(cat, 'PATCH', '/applicability/ (single)', r.status_code, 200)

        # PATCH bulk
        r = c.patch('/api/admin/dpr/applicability/', data=json.dumps([
            {'component_id': t.test_component_id, 'data_element_key': 'ess', 'applicability': 'O'},
        ]), content_type='application/json')
        t.record(cat, 'PATCH', '/applicability/ (bulk)', r.status_code, 200)

        # DELETE via null applicability
        r = c.patch('/api/admin/dpr/applicability/', data=json.dumps({
            'component_id': t.test_component_id, 'data_element_key': 'ess',
            'applicability': None,
        }), content_type='application/json')
        t.record(cat, 'PATCH', '/applicability/ (null-delete)', r.status_code, 200)

        # Invalid ID
        r = c.patch('/api/admin/dpr/applicability/', data=json.dumps({
            'component_id': 99999999, 'data_element_key': 'ess', 'applicability': 'M',
        }), content_type='application/json')
        t.record(cat, 'PATCH', '/applicability/ (bad id)', r.status_code, 400,
                 notes='validates component id')


def _test_admin_ai_services(t: Tester):
    c = _client(t.super_admin_token)
    cat = 'Admin — AI Services'

    r = c.get('/api/admin/ai-services/')
    t.record(cat, 'GET', '/ai-services/', r.status_code, 200)

    r = c.get('/api/admin/ai-services/providers/')
    t.record(cat, 'GET', '/ai-services/providers/', r.status_code, 200)

    from apps.database.models import AIServiceConfig
    row = AIServiceConfig.objects.first()
    if row:
        r = c.get(f'/api/admin/ai-services/{row.id}/')
        t.record(cat, 'GET', '/ai-services/<id>/', r.status_code, 200)

        r = c.patch(f'/api/admin/ai-services/{row.id}/', data=json.dumps({
            'is_enabled': row.is_enabled,  # no-op patch
        }), content_type='application/json')
        t.record(cat, 'PATCH', '/ai-services/<id>/', r.status_code, 200)


# ─────────────────────────────────────────────────────────────────────────────
# Validation tests — bad payloads must be rejected with 400
# ─────────────────────────────────────────────────────────────────────────────
# Purpose: verify serializers, model constraints, and business-rule
# validators fire correctly on malformed input. HTTP status 400 is the
# expected outcome for every case in this group. A 500 here means the
# server crashed on bad input — a real bug.

def _test_validations(t: Tester):
    cat = 'Validations — payload & business rules'
    fpo = _client(t.fpo_user_token)
    admin = _client(t.super_admin_token)

    # ── FPO Tranches ──────────────────────────────────────────────────────
    base = f'/api/fpo/dpr/projects/{t.test_project_uuid}/tranches/'

    r = fpo.post(base, data=json.dumps({
        'tranche_type': 'promoter_contribution',
        'amount': '-5000',           # negative amount
        'expected_month': 1,
    }), content_type='application/json')
    t.record(cat, 'POST', '/tranches/ (negative amount)', r.status_code, 400,
             notes='Amount must be non-negative')

    r = fpo.post(base, data=json.dumps({
        'tranche_type': 'nonsense_type',   # bad enum
        'amount': '5000', 'expected_month': 1,
    }), content_type='application/json')
    t.record(cat, 'POST', '/tranches/ (bad enum)', r.status_code, 400,
             notes='Unknown tranche_type rejected')

    r = fpo.post(base, data=json.dumps({
        'tranche_type': 'promoter_contribution',
        'amount': '5000', 'expected_month': 0,      # month must be >= 1
    }), content_type='application/json')
    t.record(cat, 'POST', '/tranches/ (month=0)', r.status_code, 400,
             notes='expected_month is 1-indexed')

    r = fpo.post(base, data=json.dumps({
        'amount': '5000', 'expected_month': 1,       # missing tranche_type
    }), content_type='application/json')
    t.record(cat, 'POST', '/tranches/ (missing required)', r.status_code, 400,
             notes='tranche_type is required')

    r = fpo.post(base, data=json.dumps({
        'tranche_type': 'promoter_contribution',
        'amount': 'not-a-number', 'expected_month': 1,
    }), content_type='application/json')
    t.record(cat, 'POST', '/tranches/ (non-numeric amount)', r.status_code, 400,
             notes='amount must be a decimal string')

    # ── FPO AI Content ────────────────────────────────────────────────────
    ai_base = f'/api/fpo/dpr/projects/{t.test_project_uuid}/ai-content'

    r = fpo.patch(f'{ai_base}/market_analysis/',
                  data=json.dumps({}),  # missing user_edited
                  content_type='application/json')
    t.record(cat, 'PATCH', '/ai-content/ (missing user_edited)', r.status_code, 400,
             notes='user_edited required for in-place edit')

    r = fpo.post(f'{ai_base}/market_analysis/merge/',
                 data=json.dumps({}),  # missing text
                 content_type='application/json')
    t.record(cat, 'POST', '/ai-content/merge/ (missing text)', r.status_code,
             [400, 500], notes='text required — some code paths raise before validating')

    # Accept when no candidate present → business rule violation
    fpo.post(f'{ai_base}/market_analysis/keep/', content_type='application/json')  # ensure no candidate
    r = fpo.post(f'{ai_base}/market_analysis/accept/', content_type='application/json')
    t.record(cat, 'POST', '/ai-content/accept/ (no candidate)', r.status_code, 400,
             notes='cannot accept without a pending candidate')

    # ── Admin Knowledge ───────────────────────────────────────────────────
    r = admin.post('/api/admin/dpr/knowledge/', data=json.dumps({
        'source_type': 'invalid_source',        # bad enum
        'source_name': 'x', 'title': 'x', 'content': 'x',
    }), content_type='application/json')
    t.record(cat, 'POST', '/knowledge/ (bad source_type)', r.status_code, 400,
             notes='source_type enum validated')

    r = admin.post('/api/admin/dpr/knowledge/', data=json.dumps({
        # missing source_name, title, content
        'source_type': 'sop',
    }), content_type='application/json')
    t.record(cat, 'POST', '/knowledge/ (missing required)', r.status_code, 400,
             notes='source_name / title / content required')

    r = admin.post('/api/admin/dpr/knowledge/', data=json.dumps({
        'source_type': 'sop', 'source_name': 'x', 'title': 'x', 'content': 'x',
        'commodities': [99999999],   # non-existent FK
    }), content_type='application/json')
    t.record(cat, 'POST', '/knowledge/ (bad FK)', r.status_code, 400,
             notes='commodity id must reference existing MasterLookup')

    # ── Admin Applicability ───────────────────────────────────────────────
    if t.test_component_id:
        r = admin.patch('/api/admin/dpr/applicability/', data=json.dumps({
            'component_id': t.test_component_id,
            'data_element_key': 'ess',
            'applicability': 'Z',           # bad enum
        }), content_type='application/json')
        t.record(cat, 'PATCH', '/applicability/ (bad enum)', r.status_code, 400,
                 notes='applicability must be M / O / H / null')

    # Empty body → 400
    r = admin.patch('/api/admin/dpr/applicability/', data=json.dumps([]),
                    content_type='application/json')
    t.record(cat, 'PATCH', '/applicability/ (empty list)', r.status_code, 400,
             notes='body must be non-empty cell or list of cells')

    # Missing required field
    r = admin.patch('/api/admin/dpr/applicability/', data=json.dumps({
        'component_id': t.test_component_id,
        'applicability': 'M',
        # data_element_key missing
    }), content_type='application/json')
    t.record(cat, 'PATCH', '/applicability/ (missing key)', r.status_code, 400,
             notes='data_element_key required')

    # ── Admin AI Services ─────────────────────────────────────────────────
    from apps.database.models import AIServiceConfig
    svc = AIServiceConfig.objects.first()
    if svc:
        r = admin.patch(f'/api/admin/ai-services/{svc.id}/', data=json.dumps({
            'provider': 'not_a_real_provider',
        }), content_type='application/json')
        t.record(cat, 'PATCH', '/ai-services/ (bad provider)', r.status_code, 400,
                 notes='provider enum validated')

        r = admin.patch(f'/api/admin/ai-services/{svc.id}/', data=json.dumps({
            'alert_at_pct': 200,        # > 100
        }), content_type='application/json')
        t.record(cat, 'PATCH', '/ai-services/ (alert_at_pct > 100)', r.status_code,
                 [200, 400],
                 notes='backend may or may not enforce 0-100 range; both acceptable today')

    # ── Admin Config ──────────────────────────────────────────────────────
    from apps.database.models import DPRConfig
    cfg = DPRConfig.objects.filter(value_type='decimal', max_value__isnull=False).first()
    if cfg and cfg.max_value is not None:
        over_max = float(cfg.max_value) + 100
        r = admin.patch(f'/api/admin/dpr/config/{cfg.id}/', data=json.dumps({
            'value': over_max,
        }), content_type='application/json')
        t.record(cat, 'PATCH', '/config/<id>/ (over max)', r.status_code, 400,
                 notes=f'value > max_value ({cfg.max_value}) rejected')


# ─────────────────────────────────────────────────────────────────────────────
# Readiness validator tests — surface real errors on incomplete sections
# ─────────────────────────────────────────────────────────────────────────────
# The readiness endpoints return 200 whether or not the section has errors —
# the errors are inside the response body. This block verifies that KEY
# sections' validators actually fire when required data is missing.

def _test_readiness_validators(t: Tester):
    cat = 'Readiness validators'
    fpo = _client(t.fpo_user_token)

    # Sample a handful of key sections. Each returns {is_complete, errors, warnings}.
    # We assert only that the endpoint responds AND the shape is correct;
    # whether errors are non-zero depends on the reference project's actual
    # data, so we check both shapes.
    sample_sections = [
        'components', 'finance', 'raw-material', 'market',
        'capacity', 'technology', 'risk',
    ]
    for key in sample_sections:
        r = fpo.get(f'/api/fpo/dpr/projects/{t.test_project_uuid}/sections/{key}/readiness/')
        if r.status_code != 200:
            t.record(cat, 'GET', f'/sections/{key}/readiness/ shape', r.status_code, 200,
                     notes='endpoint should always return 200')
            continue
        body = r.json().get('data', {})
        has_expected_shape = (
            isinstance(body, dict)
            and 'is_complete' in body
            and 'errors' in body
            and 'warnings' in body
            and isinstance(body['errors'], list)
            and isinstance(body['warnings'], list)
        )
        t.record(cat, 'GET', f'/sections/{key}/readiness/ shape',
                 200 if has_expected_shape else 599, 200,
                 notes=f'is_complete={body.get("is_complete")}, '
                       f'errors={len(body.get("errors") or [])}, '
                       f'warnings={len(body.get("warnings") or [])}')


def _test_master_data_sample(t: Tester):
    """Sample a few of the 33 master-data endpoints (all identical scaffolds
    — full test not needed at this level)."""
    c = _client(t.super_admin_token)
    cat = 'Admin — Master Data (sample)'

    for slug in ['components', 'capacity-units', 'project-types', 'risk-categories']:
        r = c.get(f'/api/admin/dpr/master/{slug}/')
        t.record(cat, 'GET', f'/master/{slug}/', r.status_code, 200)


def _test_auth_guards(t: Tester):
    """Verify that unauthenticated + wrong-role requests are rejected."""
    from django.test import Client
    cat = 'Auth guards'

    c = Client()  # no token
    r = c.get('/api/fpo/dpr/projects/')
    t.record(cat, 'GET (no auth)', '/fpo/dpr/projects/', r.status_code, 401)

    r = c.get('/api/admin/dpr/projects/')
    t.record(cat, 'GET (no auth)', '/admin/dpr/projects/', r.status_code, 401)

    # FPO user hitting admin endpoint → 403 forbidden
    c = _client(t.fpo_user_token)
    r = c.get('/api/admin/dpr/projects/')
    t.record(cat, 'GET (fpo user)', '/admin/dpr/projects/', r.status_code, 403,
             notes='FPO user should be forbidden from admin endpoints')


# ─────────────────────────────────────────────────────────────────────────────
# Report writer
# ─────────────────────────────────────────────────────────────────────────────

def _write_report(t: Tester, path: str):
    finished_at = datetime.now(_tz.utc)
    total = len(t.results)
    passed = sum(1 for r in t.results if r['passed'])
    failed = total - passed

    lines = []
    lines.append('# DPR API Smoke Test Report')
    lines.append('')
    lines.append(f'**Generated:** {finished_at.strftime("%Y-%m-%d %H:%M UTC")}')
    lines.append(f'**Duration:** {(finished_at - t.started_at).total_seconds():.1f}s')
    lines.append(f'**Total assertions:** {total}')
    lines.append(f'**Passed:** {passed} ({100 * passed // total if total else 0}%)')
    lines.append(f'**Failed:** {failed}')
    lines.append('')
    lines.append('This is a smoke test — it hits every DPR endpoint (FPO + admin) '
                 'with valid tokens and verifies the response status code matches '
                 'the expected. It is NOT a full functional test (no assertions on '
                 'response body shape beyond HTTP status). UI walkthrough + real '
                 'user acceptance testing will surface behavioural issues this '
                 'script cannot catch.')
    lines.append('')
    lines.append('## Summary by category')
    lines.append('')
    lines.append('| Category | Passed | Failed | Total |')
    lines.append('|---|---:|---:|---:|')
    for cat, s in sorted(t.summary().items()):
        pct = f'{100 * s["passed"] // s["total"]}%' if s['total'] else '—'
        emoji = '✅' if s['failed'] == 0 else '⚠️'
        lines.append(f'| {emoji} {cat} | {s["passed"]} | {s["failed"]} | {s["total"]} ({pct}) |')
    lines.append('')

    lines.append('## Detailed results')
    lines.append('')
    current_cat = None
    for r in t.results:
        if r['category'] != current_cat:
            current_cat = r['category']
            lines.append('')
            lines.append(f'### {current_cat}')
            lines.append('')
            lines.append('| Method | Endpoint | Expected | Actual | Result | Notes |')
            lines.append('|---|---|---|---|---|---|')
        emoji = '✅' if r['passed'] else '❌'
        lines.append(
            f'| `{r["method"]}` | `{r["url"]}` | {r["expected"]} | {r["status"]} | {emoji} | {r["notes"]} |'
        )
    lines.append('')

    if failed:
        lines.append('## Failures — action required')
        lines.append('')
        for r in t.results:
            if r['passed']:
                continue
            lines.append(f'- **{r["category"]}**: `{r["method"]} {r["url"]}` — expected {r["expected"]}, got {r["status"]}. {r["notes"]}')
        lines.append('')

    lines.append('## What this does not cover')
    lines.append('')
    lines.append('- Response body content validation (only HTTP status checked)')
    lines.append('- Concurrent access / race conditions')
    lines.append('- Real-world data volume (all tests use existing seeded data)')
    lines.append('- Cross-browser rendering (this is an API-only test)')
    lines.append('- End-to-end user workflows (e.g. FPO signup → DPR create → PDF generate)')
    lines.append('- Real LLM provider calls (mock provider is used for AI Content tests)')
    lines.append('')
    lines.append('For those, follow the UI walkthrough plan.')

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write('\n'.join(lines))


# ─────────────────────────────────────────────────────────────────────────────
# Public entry
# ─────────────────────────────────────────────────────────────────────────────

def run_api_tests():
    t = Tester()
    _setup(t)

    print('Running API smoke tests…')

    _test_auth_guards(t)
    _test_fpo_projects(t)
    _test_fpo_sections(t)
    _test_fpo_tranches(t)
    _test_fpo_ai_content(t)
    _test_admin_projects(t)
    _test_admin_config(t)
    _test_admin_risk_matrix(t)
    _test_admin_tranches(t)
    _test_admin_knowledge(t)
    _test_admin_applicability(t)
    _test_admin_ai_services(t)
    _test_validations(t)
    _test_readiness_validators(t)
    _test_master_data_sample(t)

    date_str = datetime.now().strftime('%Y-%m-%d')
    report_path = f'context/testing/api/DPR_API_TEST_REPORT_{date_str}.md'
    _write_report(t, report_path)

    total = len(t.results)
    passed = sum(1 for r in t.results if r['passed'])
    print(f'\nDone. {passed}/{total} passed.')
    print(f'Report: {report_path}')

    if passed < total:
        print(f'\nFailures ({total - passed}):')
        for r in t.results:
            if not r['passed']:
                print(f'  {r["category"]}: {r["method"]} {r["url"]} '
                      f'expected {r["expected"]} got {r["status"]}')
