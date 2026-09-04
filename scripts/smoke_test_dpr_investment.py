"""Smoke test — DPR §2.3.4 Proposed Project Investment."""

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

    print('── §2.3.4 Proposed Project Investment smoke test ──')

    r = client.post('/api/fpo/dpr/projects/',
        data=json.dumps({'title': 'Investment Test'}),
        content_type='application/json', **_hdr(fpo_user))
    project_uuid = r.json()['data']['uuid']
    url = f'/api/fpo/dpr/projects/{project_uuid}/sections/investment/'

    r = client.get(url)
    check('unauth → 401', r.status_code == 401)

    r = client.get(url, **_hdr(fpo_user))
    check('GET → 200 (empty)', r.status_code == 200)
    d = r.json()['data']
    check('  cost is null', d.get('estimated_project_cost') is None)
    check('  basis is blank', d.get('basis_of_estimate') == '')

    # 1. Empty section → readiness clean (conditional)
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    rr = r.json()['data']
    check('empty section → is_complete=True (conditional field)',
          rr['is_complete'] is True and rr['errors'] == [])

    # 2. Enter valid cost + basis
    r = client.patch(url,
        data=json.dumps({
            'estimated_project_cost': '1500000.00',
            'basis_of_estimate': 'consultant',
            'remarks': 'Prepared by external consultant, June 2026',
        }),
        content_type='application/json', **_hdr(fpo_user))
    check('PATCH valid cost + basis → 200', r.status_code == 200, f'{r.content[:200]}')
    d = r.json()['data']
    check('  cost saved', str(d.get('estimated_project_cost')) == '1500000.00')
    check('  basis saved', d.get('basis_of_estimate') == 'consultant')

    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    rr = r.json()['data']
    check('readiness clean → is_complete=True',
          rr['is_complete'] is True,
          f'errors: {rr["errors"]}')

    # 3. Cost with no basis → warning, but still complete
    r = client.patch(url,
        data=json.dumps({'basis_of_estimate': ''}),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    rr = r.json()['data']
    check('cost + no basis → warning "basis_recommended"',
          any(w['code'] == 'basis_recommended' for w in rr.get('warnings', [])))
    check('  still is_complete=True (warning, not error)', rr['is_complete'] is True)

    # 4. Cost = 0 → error
    r = client.patch(url,
        data=json.dumps({'estimated_project_cost': '0'}),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = r.json()['data']['errors']
    check('cost = 0 → error "cost_positive"',
          any(e['code'] == 'cost_positive' for e in errs))

    # 5. Ownership isolation
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
