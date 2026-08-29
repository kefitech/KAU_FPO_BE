"""Smoke test — DPR §2.3.19 Statutory Approvals, Licences and Regulatory Compliance."""

import json
from django.contrib.auth.models import User
from django.test import Client
from rest_framework_simplejwt.tokens import RefreshToken

from apps.database.models import DPRProject, DPRStatutoryRegistration


def _tok(u): return str(RefreshToken.for_user(u).access_token)
def _hdr(u): return {'HTTP_AUTHORIZATION': f'Bearer {_tok(u)}'}
def _ok(l): print(f'  \033[32m✓\033[0m {l}')
def _bad(l, d=''): print(f'  \033[31m✗\033[0m {l}' + (f'\n      {d}' if d else ''))


def smoke_test():
    fpo_user = User.objects.filter(
        groups__name='fpo_manager', is_active=True, fpo__isnull=False,
    ).first()
    assert fpo_user

    fpo_reg = DPRStatutoryRegistration.objects.get(code='fpo_registration')
    pan_reg = DPRStatutoryRegistration.objects.get(code='pan')
    gst_reg = DPRStatutoryRegistration.objects.get(code='gst')
    fssai_reg = DPRStatutoryRegistration.objects.filter(code='fssai').first()

    client = Client()
    failures = []

    def check(label, cond, detail=''):
        if cond: _ok(label)
        else: _bad(label, detail); failures.append(label)

    print('── §2.3.19 Compliance smoke test ──')

    r = client.post('/api/fpo/dpr/projects/',
        data=json.dumps({'title': 'Compliance Test'}),
        content_type='application/json', **_hdr(fpo_user))
    project_uuid = r.json()['data']['uuid']
    url = f'/api/fpo/dpr/projects/{project_uuid}/sections/compliance/'

    r = client.get(url)
    check('unauth → 401', r.status_code == 401)

    r = client.get(url, **_hdr(fpo_user))
    check('GET → 200 (empty)', r.status_code == 200)

    # Empty → fpo_registration_required
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('empty → fpo_registration_required', 'fpo_registration_required' in errs)

    # PATCH with FPO reg + a few items
    r = client.patch(url,
        data=json.dumps({
            'items': [
                {'order': 1, 'registration': fpo_reg.id, 'status': 'available',
                 'issuing_authority': 'Registrar of Companies', 'remarks': 'Since 2022'},
                {'order': 2, 'registration': pan_reg.id, 'status': 'available'},
                {'order': 3, 'registration': gst_reg.id, 'status': 'available'},
                {'order': 4, 'registration': fssai_reg.id, 'status': 'proposed_to_obtain',
                 'issuing_authority': 'FSSAI Kerala',
                 'expected_date_of_approval': '2026-12-31'},
                {'order': 5, 'custom_name': 'Local NGO clearance', 'status': 'proposed_to_obtain',
                 'issuing_authority': 'Vellanikkara Panchayat'},
            ],
            'has_pending_legal_issues': False,
        }),
        content_type='application/json', **_hdr(fpo_user))
    check('PATCH 5 items → 200', r.status_code == 200, f'{r.content[:400]}')
    d = r.json()['data']
    check(f'  5 items saved ({len(d.get("items", []))})', len(d.get('items', [])) == 5)
    # Verify custom_name case
    custom = next((i for i in d['items'] if i.get('custom_name') == 'Local NGO clearance'), None)
    check('  custom_name item exists (no FK)',
          custom is not None and custom.get('registration') is None)

    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    check('readiness → is_complete=True',
          r.json()['data']['is_complete'] is True,
          f'errors: {r.json()["data"]["errors"]}')

    # Test — item without registration AND without custom_name → error
    r = client.patch(url,
        data=json.dumps({
            'items': [
                {'registration': fpo_reg.id, 'status': 'available'},
                {'status': 'available'},  # no registration + no custom_name
            ],
        }),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('item w/o registration + custom → name_required', 'name_required' in errs)

    # Item without status → error
    r = client.patch(url,
        data=json.dumps({
            'items': [
                {'registration': fpo_reg.id, 'status': 'available'},
                {'registration': pan_reg.id},  # no status
            ],
        }),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('item w/o status → status_required', 'status_required' in errs)

    # Pending legal issues without nature/impact → error
    r = client.patch(url,
        data=json.dumps({
            'items': [{'registration': fpo_reg.id, 'status': 'available'}],
            'has_pending_legal_issues': True,
        }),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('pending legal w/o nature → nature_required', 'nature_required' in errs)
    check('pending legal w/o impact → impact_required', 'impact_required' in errs)

    # Fill legal issue → clean
    r = client.patch(url,
        data=json.dumps({
            'nature_of_case': 'Land title dispute with neighbouring plot',
            'possible_impact': 'May delay building permit by 3 months',
            'present_status': 'Under mediation',
        }),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    check('legal filled → is_complete=True',
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
