"""Smoke test — DPR §2.3.8 Current Status / Baseline."""

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

    print('── §2.3.8 Baseline smoke test ──')

    r = client.post('/api/fpo/dpr/projects/',
        data=json.dumps({'title': 'Baseline Test'}),
        content_type='application/json', **_hdr(fpo_user))
    project_uuid = r.json()['data']['uuid']
    url = f'/api/fpo/dpr/projects/{project_uuid}/sections/baseline/'

    r = client.get(url)
    check('unauth → 401', r.status_code == 401)

    r = client.get(url, **_hdr(fpo_user))
    check('GET → 200 (empty, currently_engaged=null)', r.status_code == 200)
    check('  currently_engaged is null', r.json()['data'].get('currently_engaged') is None)

    # Empty → status_required
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('empty readiness → status_required', 'status_required' in errs)

    # YES path — only status → missing products + capacity
    r = client.patch(url,
        data=json.dumps({'currently_engaged': True}),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('yes+empty → existing_products_required', 'existing_products_required' in errs)
    check('yes+empty → existing_capacity_required', 'existing_capacity_required' in errs)

    # YES full
    r = client.patch(url,
        data=json.dumps({
            'existing_products': 'Rice, wheat',
            'existing_installed_capacity': '500 tonnes / annum',
            'current_annual_turnover': '2500000.00',
            'num_employees': 12,
            'current_capacity_utilization_pct': '65.00',
            'existing_certifications': 'FSSAI',
        }),
        content_type='application/json', **_hdr(fpo_user))
    check('PATCH yes-path complete → 200', r.status_code == 200, f'{r.content[:200]}')
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    check('yes complete → is_complete=True',
          r.json()['data']['is_complete'] is True,
          f'errors: {r.json()["data"]["errors"]}')

    # Switch to NO path
    r = client.patch(url,
        data=json.dumps({'currently_engaged': False}),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('no+empty → reason_required', 'reason_required' in errs)

    # Fill reason
    r = client.patch(url,
        data=json.dumps({
            'reason_for_proposing': 'Diversify into value-added rice products',
            'previous_experience': 'Members have 10+ years farming experience',
            'proposed_implementation_approach': 'Set up 500kg/hr milling unit',
        }),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    check('no complete → is_complete=True',
          r.json()['data']['is_complete'] is True,
          f'errors: {r.json()["data"]["errors"]}')

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
