"""Smoke test — DPR §2.3.22 Risk Assessment and Mitigation Plan (FINAL SECTION)."""

import json
from django.contrib.auth.models import User
from django.test import Client
from rest_framework_simplejwt.tokens import RefreshToken

from apps.database.models import DPRProject


def _tok(u): return str(RefreshToken.for_user(u).access_token)
def _hdr(u): return {'HTTP_AUTHORIZATION': f'Bearer {_tok(u)}'}
def _ok(l): print(f'  \033[32m✓\033[0m {l}')
def _bad(l, d=''): print(f'  \033[31m✗\033[0m {l}' + (f'\n      {d}' if d else ''))


def smoke_test():
    fpo_user = User.objects.filter(
        groups__name='fpo_manager', is_active=True, fpo__isnull=False,
    ).first()
    assert fpo_user

    client = Client()
    failures = []

    def check(label, cond, detail=''):
        if cond: _ok(label)
        else: _bad(label, detail); failures.append(label)

    print('── §2.3.22 Risk Assessment smoke test (FINAL SECTION) ──')

    r = client.post('/api/fpo/dpr/projects/',
        data=json.dumps({'title': 'Risk Test'}),
        content_type='application/json', **_hdr(fpo_user))
    project_uuid = r.json()['data']['uuid']
    url = f'/api/fpo/dpr/projects/{project_uuid}/sections/risk/'

    r = client.get(url)
    check('unauth → 401', r.status_code == 401)

    r = client.get(url, **_hdr(fpo_user))
    check('GET → 200 (empty)', r.status_code == 200)
    check('  empty items', r.json()['data'].get('items') == [])

    # Empty → is_complete=True (all fields advisory) but with warning
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    rr = r.json()['data']
    check('empty → is_complete=True with warning',
          rr['is_complete'] is True and
          any(w['code'] == 'no_risks_identified' for w in rr.get('warnings', [])))

    # PATCH with risks across multiple categories
    r = client.patch(url,
        data=json.dumps({
            'items': [
                {
                    'order': 1, 'risk_category': 'production',
                    'risk_code': 'raw_material_unavailable',
                    'risk_description': 'Rice supply shortage during monsoon',
                    'mitigation_strategy': 'Long-term contracts with 5 farmers + buffer stock',
                    'responsible_person_or_agency': 'Procurement Manager',
                    'implementation_timeline': 'Q1 2027',
                    'expected_outcome': 'Uninterrupted supply throughout year',
                    'probability': 'medium', 'impact': 'high',
                    'existing_measures': 'Currently ad-hoc procurement',
                },
                {
                    'order': 2, 'risk_category': 'market',
                    'risk_code': 'price_fluctuation',
                    'risk_description': 'Rice price varies 30% seasonally',
                    'mitigation_strategy': 'Forward contracts + inventory hedging',
                    'probability': 'high', 'impact': 'medium',
                },
                {
                    'order': 3, 'risk_category': 'financial',
                    'risk_code': 'cost_escalation',
                    'risk_description': 'Diesel prices rising steadily',
                    'mitigation_strategy': 'Solar backup + energy efficiency measures',
                    'probability': 'medium', 'impact': 'medium',
                },
                {
                    'order': 4, 'risk_category': 'environmental',
                    'risk_code': 'flood',
                    'risk_description': 'Monsoon flooding risk',
                    'mitigation_strategy': 'Elevated construction + insurance',
                    'probability': 'medium', 'impact': 'high',
                },
                {
                    'order': 5, 'risk_category': 'regulatory',
                    'risk_code': 'delay_licences',
                    'risk_description': 'FSSAI licence renewal delays',
                    'mitigation_strategy': 'Apply 6 months in advance + track via dashboard',
                    'probability': 'low', 'impact': 'medium',
                },
            ],
        }),
        content_type='application/json', **_hdr(fpo_user))
    check('PATCH 5 risks → 200', r.status_code == 200, f'{r.content[:400]}')
    d = r.json()['data']
    check(f'  5 items saved ({len(d.get("items", []))})', len(d.get('items', [])) == 5)

    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    check('readiness → is_complete=True',
          r.json()['data']['is_complete'] is True,
          f'errors: {r.json()["data"]["errors"]}')

    # Risk without mitigation → error
    r = client.patch(url,
        data=json.dumps({
            'items': [
                {'risk_category': 'production', 'risk_code': 'machinery_breakdown',
                 'mitigation_strategy': ''},
            ],
        }),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('empty mitigation → mitigation_required', 'mitigation_required' in errs)

    # "Others" risk_code without specify text → error
    r = client.patch(url,
        data=json.dumps({
            'items': [
                {'risk_category': 'production', 'risk_code': 'other',
                 'mitigation_strategy': 'Some plan'},
            ],
        }),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('other risk w/o text → risk_other_required', 'risk_other_required' in errs)

    # Duplicate (category, code) → 400
    r = client.patch(url,
        data=json.dumps({
            'items': [
                {'risk_category': 'production', 'risk_code': 'power_failure',
                 'mitigation_strategy': 'A'},
                {'risk_category': 'production', 'risk_code': 'power_failure',
                 'mitigation_strategy': 'B'},
            ],
        }),
        content_type='application/json', **_hdr(fpo_user))
    check('duplicate (category, code) → 400', r.status_code == 400, f'got {r.status_code}')

    # Same code in DIFFERENT categories should be allowed
    r = client.patch(url,
        data=json.dumps({
            'items': [
                {'risk_category': 'production', 'risk_code': 'labour_shortage',
                 'mitigation_strategy': 'Local recruitment drive'},
                {'risk_category': 'institutional', 'risk_code': 'skilled_manpower_shortage',
                 'mitigation_strategy': 'Training partnerships'},
            ],
        }),
        content_type='application/json', **_hdr(fpo_user))
    check('same codes in different categories → 200',
          r.status_code == 200, f'got {r.status_code}: {r.content[:200]}')

    # Ownership isolation
    other = User.objects.filter(
        groups__name='fpo_manager', is_active=True, fpo__isnull=False,
    ).exclude(pk=fpo_user.pk).first()
    if other:
        r = client.get(url, **_hdr(other))
        check('other FPO → 404', r.status_code == 404)

    DPRProject.objects.filter(uuid=project_uuid).delete()
    check('cleanup', not DPRProject.objects.filter(uuid=project_uuid).exists())

    print()
    if failures:
        print(f'\033[31m{len(failures)} failures\033[0m')
        for f in failures: print(f'  - {f}')
        return False
    print('\033[32m✓ All checks passed.\033[0m')
    return True
