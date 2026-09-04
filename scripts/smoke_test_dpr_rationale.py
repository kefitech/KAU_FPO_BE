"""Smoke test — DPR §2.3.7 Project Rationale."""

import json
from django.contrib.auth.models import User
from django.test import Client
from rest_framework_simplejwt.tokens import RefreshToken

from apps.database.models import DPRProject, DPRProjectRationale


def _tok(u): return str(RefreshToken.for_user(u).access_token)
def _hdr(u): return {'HTTP_AUTHORIZATION': f'Bearer {_tok(u)}'}
def _ok(l): print(f'  \033[32m✓\033[0m {l}')
def _bad(l, d=''): print(f'  \033[31m✗\033[0m {l}' + (f'\n      {d}' if d else ''))


def smoke_test():
    fpo_user = User.objects.filter(
        groups__name='fpo_manager', is_active=True, fpo__isnull=False,
    ).first()
    assert fpo_user

    reasons = list(DPRProjectRationale.objects.filter(is_active=True).exclude(code='other')[:3])
    other_reason = DPRProjectRationale.objects.filter(code='other').first()
    assert len(reasons) == 3 and other_reason

    client = Client()
    failures = []

    def check(label, cond, detail=''):
        if cond: _ok(label)
        else: _bad(label, detail); failures.append(label)

    print('── §2.3.7 Project Rationale smoke test ──')

    r = client.post('/api/fpo/dpr/projects/',
        data=json.dumps({'title': 'Rationale Test'}),
        content_type='application/json', **_hdr(fpo_user))
    project_uuid = r.json()['data']['uuid']
    url = f'/api/fpo/dpr/projects/{project_uuid}/sections/rationale/'

    r = client.get(url)
    check('unauth → 401', r.status_code == 401)

    r = client.get(url, **_hdr(fpo_user))
    check('GET → 200 (empty)', r.status_code == 200)
    check('  empty selections', r.json()['data'].get('selections') == [])

    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('empty readiness → at_least_one_rationale', 'at_least_one_rationale' in errs)

    # PATCH 3 selections with justifications
    r = client.patch(url,
        data=json.dumps({
            'selections': [
                {'rationale': reasons[0].id, 'justification': 'Reduces post-harvest losses by 25% based on FPO survey.'},
                {'rationale': reasons[1].id, 'justification': 'Direct market access improves farmer income by an estimated 30%.'},
                {'rationale': reasons[2].id, 'justification': 'Value addition of rice bran opens new revenue stream.'},
            ],
        }),
        content_type='application/json', **_hdr(fpo_user))
    check('PATCH 3 selections → 200', r.status_code == 200, f'{r.content[:400]}')
    sels = r.json()['data'].get('selections', [])
    check(f'  3 selections saved', len(sels) == 3)

    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    rr = r.json()['data']
    check('readiness → is_complete=True',
          rr['is_complete'] is True, f'errors: {rr["errors"]}')

    # Justification missing → error
    r = client.patch(url,
        data=json.dumps({
            'selections': [
                {'rationale': reasons[0].id, 'justification': ''},
            ],
        }),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('empty justification → justification_required', 'justification_required' in errs)

    # >100 words → error
    long_text = ' '.join(['word'] * 105)
    r = client.patch(url,
        data=json.dumps({
            'selections': [{'rationale': reasons[0].id, 'justification': long_text}],
        }),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('>100 words → justification_too_long', 'justification_too_long' in errs)

    # "other" without text → error
    r = client.patch(url,
        data=json.dumps({
            'selections': [
                {'rationale': reasons[0].id, 'justification': 'Good reason.'},
                {'rationale': other_reason.id, 'justification': 'Special reason.'},
            ],
            'rationale_other': '',
        }),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('other w/o text → rationale_other_required', 'rationale_other_required' in errs)

    # Fill "other" text → clean
    r = client.patch(url,
        data=json.dumps({'rationale_other': 'FPO-member community welfare drive'}),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    check('after filling rationale_other → is_complete=True',
          r.json()['data']['is_complete'] is True)

    # unique_together enforcement — same rationale twice in one PATCH → 400
    r = client.patch(url,
        data=json.dumps({
            'selections': [
                {'rationale': reasons[0].id, 'justification': 'A'},
                {'rationale': reasons[0].id, 'justification': 'B'},
            ],
        }),
        content_type='application/json', **_hdr(fpo_user))
    check('duplicate rationale in one PATCH → 400',
          r.status_code == 400, f'got {r.status_code}')

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
