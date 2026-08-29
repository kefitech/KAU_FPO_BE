"""
Smoke test — DPR §2.3.3 Nature of Business.

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/smoke_test_dpr_nature_of_business.py').read())
    smoke_test()
    "
"""

import json
from django.contrib.auth.models import User
from django.test import Client
from rest_framework_simplejwt.tokens import RefreshToken

from apps.database.models import DPRProject, DPRNatureOfBusiness


def _tok(u): return str(RefreshToken.for_user(u).access_token)
def _hdr(u): return {'HTTP_AUTHORIZATION': f'Bearer {_tok(u)}'}
def _ok(l): print(f'  \033[32m✓\033[0m {l}')
def _bad(l, d=''): print(f'  \033[31m✗\033[0m {l}' + (f'\n      {d}' if d else ''))


def smoke_test():
    fpo_user = User.objects.filter(
        groups__name='fpo_manager', is_active=True, fpo__isnull=False,
    ).first()
    assert fpo_user

    non_other = list(DPRNatureOfBusiness.objects.filter(is_active=True).exclude(code='other')[:3])
    other_row = DPRNatureOfBusiness.objects.get(code='other')

    client = Client()
    failures = []

    def check(label, cond, detail=''):
        if cond: _ok(label)
        else: _bad(label, detail); failures.append(label)

    print('── §2.3.3 Nature of Business smoke test ──')

    r = client.post('/api/fpo/dpr/projects/',
        data=json.dumps({'title': 'NoB Test'}),
        content_type='application/json', **_hdr(fpo_user))
    project_uuid = r.json()['data']['uuid']
    url = f'/api/fpo/dpr/projects/{project_uuid}/sections/nature-of-business/'

    r = client.get(url)
    check('unauth → 401', r.status_code == 401)

    r = client.get(url, **_hdr(fpo_user))
    check('GET → 200 (empty)', r.status_code == 200)
    check('  empty natures', r.json()['data'].get('natures') == [])

    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = r.json()['data']['errors']
    check('empty readiness → at_least_one_nature',
          any(e['code'] == 'at_least_one_nature' for e in errs))

    r = client.patch(url,
        data=json.dumps({'natures': [n.id for n in non_other]}),
        content_type='application/json', **_hdr(fpo_user))
    check('PATCH 3 natures → 200', r.status_code == 200)
    check(f'  3 natures saved', len(r.json()['data'].get('natures', [])) == 3)

    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    check('readiness → is_complete=True',
          r.json()['data']['is_complete'] is True)

    # Add "other" without text → fail
    r = client.patch(url,
        data=json.dumps({'natures': [n.id for n in non_other] + [other_row.id]}),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = r.json()['data']['errors']
    check('add "other" without text → nature_other_required',
          any(e['code'] == 'nature_other_required' for e in errs))

    # Fill text → passes
    r = client.patch(url,
        data=json.dumps({'nature_other': 'Cooperative farming with training'}),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    check('after filling nature_other → is_complete=True',
          r.json()['data']['is_complete'] is True)

    # Absent-key preservation
    saved_text = r.json() and 'X'  # just to be sure
    r = client.get(url, **_hdr(fpo_user))
    check('  nature_other preserved',
          r.json()['data'].get('nature_other') == 'Cooperative farming with training')

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
