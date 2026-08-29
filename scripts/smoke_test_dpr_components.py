"""
Smoke test — DPR §2.3.2 Project Components.

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/smoke_test_dpr_components.py').read())
    smoke_test()
    "
"""

import json
from django.contrib.auth.models import User
from django.test import Client
from rest_framework_simplejwt.tokens import RefreshToken

from apps.database.models import DPRProject, DPRSectionComponents, DPRComponent


def _tok(u): return str(RefreshToken.for_user(u).access_token)
def _hdr(u): return {'HTTP_AUTHORIZATION': f'Bearer {_tok(u)}'}
def _ok(l): print(f'  \033[32m✓\033[0m {l}')
def _bad(l, d=''): print(f'  \033[31m✗\033[0m {l}' + (f'\n      {d}' if d else ''))


def smoke_test():
    fpo_user = User.objects.filter(
        groups__name='fpo_manager', is_active=True, fpo__isnull=False,
    ).first()
    assert fpo_user and fpo_user.fpo, 'Need an fpo_manager with linked FPO'

    # Pick 3 non-other components + 1 "other" component (with its group)
    non_other = list(DPRComponent.objects.filter(is_active=True).exclude(code__endswith='other')[:3])
    other_comp = DPRComponent.objects.filter(is_active=True, code='primary_prod_other').first()
    assert len(non_other) == 3 and other_comp, 'Master data missing'

    client = Client()
    failures = []

    def check(label, cond, detail=''):
        if cond: _ok(label)
        else: _bad(label, detail); failures.append(label)

    print('── §2.3.2 Project Components smoke test ──')

    # Setup — create project
    r = client.post('/api/fpo/dpr/projects/',
        data=json.dumps({'title': 'Components Test'}),
        content_type='application/json', **_hdr(fpo_user))
    project_uuid = r.json()['data']['uuid']
    url = f'/api/fpo/dpr/projects/{project_uuid}/sections/components/'

    # 1. Auth gate
    r = client.get(url)
    check('unauth → 401', r.status_code == 401)

    # 2. Auto-create empty
    r = client.get(url, **_hdr(fpo_user))
    check('GET → 200 (empty)', r.status_code == 200)
    check('  empty components', r.json()['data'].get('components') == [])

    # 3. Readiness on empty → error "at_least_one_component"
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    readiness = r.json()['data']
    check('empty section readiness → 1 error (at_least_one_component)',
          len(readiness['errors']) == 1 and readiness['errors'][0]['code'] == 'at_least_one_component',
          f'errors: {readiness["errors"]}')

    # 4. PATCH with 3 components (no "other")
    r = client.patch(url,
        data=json.dumps({'components': [c.id for c in non_other]}),
        content_type='application/json', **_hdr(fpo_user))
    check('PATCH 3 components → 200', r.status_code == 200, f'{r.content[:200]}')
    check(f'  3 components saved', len(r.json()['data'].get('components', [])) == 3)

    # 5. Readiness now → is_complete=True
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    check('readiness after PATCH → is_complete=True',
          r.json()['data']['is_complete'] is True,
          f'errors: {r.json()["data"]["errors"]}')

    # 6. PATCH with "_other" component but no specify text → validation error
    r = client.patch(url,
        data=json.dumps({'components': [c.id for c in non_other] + [other_comp.id]}),
        content_type='application/json', **_hdr(fpo_user))
    check('PATCH with _other component → 200', r.status_code == 200)
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = r.json()['data']['errors']
    check('readiness → error "other_specify_required"',
          any(e['code'] == 'other_specify_required' for e in errs),
          f'errors: {errs}')

    # 7. Fill in other_primary_production → readiness passes
    r = client.patch(url,
        data=json.dumps({'other_primary_production': 'Aquaponic tomato farming'}),
        content_type='application/json', **_hdr(fpo_user))
    check('PATCH other_primary_production text → 200', r.status_code == 200)
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    check('readiness now clean → is_complete=True',
          r.json()['data']['is_complete'] is True,
          f'errors: {r.json()["data"]["errors"]}')

    # 8. Absent-key preservation — PATCH only components, other_primary_production stays
    r = client.get(url, **_hdr(fpo_user))
    saved_other = r.json()['data'].get('other_primary_production')
    r = client.patch(url,
        data=json.dumps({'is_complete': True}),
        content_type='application/json', **_hdr(fpo_user))
    check('  other_primary_production preserved after unrelated PATCH',
          r.json()['data'].get('other_primary_production') == saved_other)

    # 9. Ownership isolation
    other = User.objects.filter(
        groups__name='fpo_manager', is_active=True, fpo__isnull=False,
    ).exclude(pk=fpo_user.pk).first()
    if other:
        r = client.get(url, **_hdr(other))
        check('other FPO user → 404', r.status_code == 404)

    # 10. Cleanup
    DPRProject.objects.filter(uuid=project_uuid).delete()
    check('cleanup', not DPRProject.objects.filter(uuid=project_uuid).exists())

    print()
    if failures:
        print(f'\033[31m{len(failures)} failures\033[0m')
        for f in failures: print(f'  - {f}')
        return False
    print('\033[32m✓ All checks passed.\033[0m')
    return True
