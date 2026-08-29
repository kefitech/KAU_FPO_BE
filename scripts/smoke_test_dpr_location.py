"""Smoke test — DPR §2.3.6 Proposed Project Location."""

import json
from django.contrib.auth.models import User
from django.test import Client
from rest_framework_simplejwt.tokens import RefreshToken

from apps.database.models import DPRProject, DPRLandOwnershipType, DPRSiteStatus


def _tok(u): return str(RefreshToken.for_user(u).access_token)
def _hdr(u): return {'HTTP_AUTHORIZATION': f'Bearer {_tok(u)}'}
def _ok(l): print(f'  \033[32m✓\033[0m {l}')
def _bad(l, d=''): print(f'  \033[31m✗\033[0m {l}' + (f'\n      {d}' if d else ''))


def smoke_test():
    fpo_user = User.objects.filter(
        groups__name='fpo_manager', is_active=True, fpo__isnull=False,
    ).first()
    assert fpo_user

    ownership_options = list(DPRLandOwnershipType.objects.filter(is_active=True).exclude(code__contains='other')[:2])
    site_options = list(DPRSiteStatus.objects.filter(is_active=True).exclude(code__contains='other')[:2])
    assert len(ownership_options) >= 1 and len(site_options) >= 1

    client = Client()
    failures = []

    def check(label, cond, detail=''):
        if cond: _ok(label)
        else: _bad(label, detail); failures.append(label)

    print('── §2.3.6 Project Location smoke test ──')

    r = client.post('/api/fpo/dpr/projects/',
        data=json.dumps({'title': 'Location Test'}),
        content_type='application/json', **_hdr(fpo_user))
    project_uuid = r.json()['data']['uuid']
    url = f'/api/fpo/dpr/projects/{project_uuid}/sections/location/'

    r = client.get(url)
    check('unauth → 401', r.status_code == 401)

    r = client.get(url, **_hdr(fpo_user))
    check('GET → 200 (empty, state=Kerala default)', r.status_code == 200)
    check('  state defaults to Kerala', r.json()['data'].get('state') == 'Kerala')
    check('  empty land_ownership_types', r.json()['data'].get('land_ownership_types') == [])

    # Empty readiness → several errors (district, local body, ownership, site, address/gps)
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('empty readiness → district_required', 'district_required' in errs)
    check('empty readiness → local_body_required', 'local_body_required' in errs)
    check('empty readiness → land_ownership_required', 'land_ownership_required' in errs)
    check('empty readiness → site_status_required', 'site_status_required' in errs)
    check('empty readiness → address_or_gps_required', 'address_or_gps_required' in errs)

    # PATCH all mandatory
    r = client.patch(url,
        data=json.dumps({
            'district': 'Thrissur',
            'taluk': 'Thrissur',
            'block_panchayat': 'Ollukkara',
            'local_body_type': 'grama_panchayat',
            'local_body_name': 'Nadathara',
            'village': 'Vellanikkara',
            'ward_number': '5',
            'pin_code': '680654',
            'project_address': 'KAU Campus, Vellanikkara',
            'latitude': '10.5417000',
            'longitude': '76.2833000',
            'land_ownership_types': [o.id for o in ownership_options],
            'site_statuses': [s.id for s in site_options],
            'dist_nearest_main_road_km': '0.5',
            'dist_nearest_market_km': '3.0',
            'dist_nearest_collection_centre_km': '5.0',
            'road_connectivity': 'good',
            'has_broadband': True,
            'has_mobile_network': True,
        }),
        content_type='application/json', **_hdr(fpo_user))
    check('PATCH all mandatory → 200', r.status_code == 200, f'{r.content[:400]}')
    d = r.json()['data']
    check('  district saved', d.get('district') == 'Thrissur')
    check('  GPS coords saved',
          d.get('latitude') and d.get('longitude'))
    check(f'  M2M ownership ({len(d.get("land_ownership_types", []))})',
          len(d.get('land_ownership_types', [])) == len(ownership_options))
    check('  has_broadband=True', d.get('has_broadband') is True)

    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    rr = r.json()['data']
    check('readiness → is_complete=True',
          rr['is_complete'] is True, f'errors: {rr["errors"]}')

    # Test: address only (no GPS) is also valid
    r = client.patch(url,
        data=json.dumps({'latitude': None, 'longitude': None}),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    check('address only (no GPS) → still is_complete',
          r.json()['data']['is_complete'] is True)

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
