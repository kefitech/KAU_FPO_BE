"""Smoke test — DPR §2.3.12 Technology Selection and Technical Feasibility."""

import json
from datetime import date
from django.contrib.auth.models import User
from django.test import Client
from rest_framework_simplejwt.tokens import RefreshToken

from apps.database.models import DPRProject, DPRTechnologyReason, DPRQualityStandard


def _tok(u): return str(RefreshToken.for_user(u).access_token)
def _hdr(u): return {'HTTP_AUTHORIZATION': f'Bearer {_tok(u)}'}
def _ok(l): print(f'  \033[32m✓\033[0m {l}')
def _bad(l, d=''): print(f'  \033[31m✗\033[0m {l}' + (f'\n      {d}' if d else ''))


def smoke_test():
    fpo_user = User.objects.filter(
        groups__name='fpo_manager', is_active=True, fpo__isnull=False,
    ).first()
    assert fpo_user

    reasons = list(DPRTechnologyReason.objects.filter(is_active=True).exclude(code='other')[:2])
    other_reason = DPRTechnologyReason.objects.get(code='other')
    certs = list(DPRQualityStandard.objects.filter(is_active=True)[:2])
    assert reasons and certs

    client = Client()
    failures = []

    def check(label, cond, detail=''):
        if cond: _ok(label)
        else: _bad(label, detail); failures.append(label)

    print('── §2.3.12 Technology smoke test ──')

    r = client.post('/api/fpo/dpr/projects/',
        data=json.dumps({'title': 'Technology Test'}),
        content_type='application/json', **_hdr(fpo_user))
    project_uuid = r.json()['data']['uuid']
    url = f'/api/fpo/dpr/projects/{project_uuid}/sections/technology/'

    r = client.get(url)
    check('unauth → 401', r.status_code == 401)

    r = client.get(url, **_hdr(fpo_user))
    check('GET → 200 (empty)', r.status_code == 200)
    check('  empty technologies', r.json()['data'].get('technologies') == [])

    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('empty → at_least_one_technology', 'at_least_one_technology' in errs)

    # PATCH one technology with mandatory fields + nested risks + M2Ms
    r = client.patch(url,
        data=json.dumps({
            'technologies': [{
                'order': 1,
                'name': 'Rice Milling Technology',
                'nature': 'Rubber-roll de-husking',
                'description': 'Modern rubber-roll dehusker with polisher.',
                'source': 'Indigenous',
                'technology_status': 'proven',
                'reasons': [r.id for r in reasons],
                'selection_justification': 'Best fit for Kerala scale of operation.',
                'process_description': 'Rice → cleaning → dehusking → polishing → grading → packaging',
                'process_type': 'batch',
                'automation_level': 'semi_auto',
                'quality_standards_applicable': True,
                'product_quality_standard': 'FSSAI grade 1',
                'certifications': [c.id for c in certs],
                'requires_skilled_operators': True,
                'requires_training': True,
                'upgradation_planned': False,
                'risks': [
                    {'risk_type': 'spare_parts', 'mitigation_measure': 'Local vendor tie-up'},
                    {'risk_type': 'high_maintenance', 'mitigation_measure': 'AMC with supplier'},
                ],
            }],
        }),
        content_type='application/json', **_hdr(fpo_user))
    check('PATCH 1 technology + 2 risks → 200', r.status_code == 200, f'{r.content[:400]}')
    techs = r.json()['data'].get('technologies', [])
    check(f'  1 technology saved', len(techs) == 1)
    if techs:
        t = techs[0]
        check(f'  2 reasons M2M ({len(t.get("reasons", []))})', len(t.get('reasons', [])) == 2)
        check(f'  2 certifications M2M ({len(t.get("certifications", []))})', len(t.get('certifications', [])) == 2)
        check(f'  2 nested risks ({len(t.get("risks", []))})', len(t.get('risks', [])) == 2)

    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    rr = r.json()['data']
    check('readiness → is_complete=True',
          rr['is_complete'] is True,
          f'errors: {rr["errors"]}')

    # Full-replace with 2 technologies
    r = client.patch(url,
        data=json.dumps({
            'technologies': [
                {
                    'order': 1, 'name': 'Tech A',
                    'source': 'Local',
                    'reasons': [reasons[0].id],
                    'process_description': 'Process A steps.',
                    'process_type': 'batch',
                    'automation_level': 'manual',
                    'requires_skilled_operators': False,
                    'requires_training': True,
                    'risks': [],
                },
                {
                    'order': 2, 'name': 'Tech B',
                    'source': 'Imported',
                    'reasons': [reasons[1].id],
                    'process_description': 'Process B steps.',
                    'process_type': 'continuous',
                    'automation_level': 'auto',
                    'requires_skilled_operators': True,
                    'requires_training': True,
                    'risks': [{'risk_type': 'breakdown', 'mitigation_measure': 'Spare unit backup'}],
                },
            ],
        }),
        content_type='application/json', **_hdr(fpo_user))
    d = r.json()['data']
    check(f'full-replace 2 techs → 200 ({len(d.get("technologies", []))})',
          r.status_code == 200 and len(d.get('technologies', [])) == 2)
    check('  tech1 name=Tech A', d['technologies'][0]['name'] == 'Tech A')
    check('  tech2 has 1 risk', len(d['technologies'][1]['risks']) == 1)

    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    check('readiness → is_complete=True (both techs valid)',
          r.json()['data']['is_complete'] is True,
          f'errors: {r.json()["data"]["errors"]}')

    # Validation — >150 word description
    long_desc = ' '.join(['word'] * 160)
    r = client.patch(url,
        data=json.dumps({
            'technologies': [{
                'name': 'Bad', 'source': 'x',
                'description': long_desc,
                'reasons': [reasons[0].id],
                'process_description': 'p',
                'process_type': 'batch',
                'automation_level': 'manual',
                'requires_skilled_operators': True,
                'requires_training': True,
            }],
        }),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('>150 word description → description_too_long', 'description_too_long' in errs)

    # Validation — risk with empty mitigation
    r = client.patch(url,
        data=json.dumps({
            'technologies': [{
                'name': 'Tech', 'source': 'x',
                'reasons': [reasons[0].id],
                'process_description': 'p', 'process_type': 'batch',
                'automation_level': 'manual',
                'requires_skilled_operators': True, 'requires_training': True,
                'risks': [{'risk_type': 'breakdown', 'mitigation_measure': ''}],
            }],
        }),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('empty mitigation → mitigation_required', 'mitigation_required' in errs)

    # Validation — upgradation planned + past year
    r = client.patch(url,
        data=json.dumps({
            'technologies': [{
                'name': 'Tech', 'source': 'x',
                'reasons': [reasons[0].id],
                'process_description': 'p', 'process_type': 'batch',
                'automation_level': 'manual',
                'requires_skilled_operators': True, 'requires_training': True,
                'upgradation_planned': True,
                'upgradation_year': 2020,
            }],
        }),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('upgradation past year → upgradation_year_future', 'upgradation_year_future' in errs)

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
