"""Smoke test — DPR §2.3.14 Building, Civil Works and Physical Infrastructure."""

import json
from django.contrib.auth.models import User
from django.test import Client
from rest_framework_simplejwt.tokens import RefreshToken

from apps.database.models import DPRProject, DPRBuildingType, DPRCivilCategory


def _tok(u): return str(RefreshToken.for_user(u).access_token)
def _hdr(u): return {'HTTP_AUTHORIZATION': f'Bearer {_tok(u)}'}
def _ok(l): print(f'  \033[32m✓\033[0m {l}')
def _bad(l, d=''): print(f'  \033[31m✗\033[0m {l}' + (f'\n      {d}' if d else ''))


def smoke_test():
    fpo_user = User.objects.filter(
        groups__name='fpo_manager', is_active=True, fpo__isnull=False,
    ).first()
    assert fpo_user

    b_type = DPRBuildingType.objects.filter(is_active=True).first()
    civil_cat = DPRCivilCategory.objects.filter(is_active=True).exclude(code='other').first()
    assert b_type and civil_cat

    client = Client()
    failures = []

    def check(label, cond, detail=''):
        if cond: _ok(label)
        else: _bad(label, detail); failures.append(label)

    print('── §2.3.14 Civil Works smoke test ──')

    r = client.post('/api/fpo/dpr/projects/',
        data=json.dumps({'title': 'Civil Test'}),
        content_type='application/json', **_hdr(fpo_user))
    project_uuid = r.json()['data']['uuid']
    url = f'/api/fpo/dpr/projects/{project_uuid}/sections/civil/'

    r = client.get(url)
    check('unauth → 401', r.status_code == 401)

    r = client.get(url, **_hdr(fpo_user))
    check('GET → 200 (empty)', r.status_code == 200)
    check('  empty lists', r.json()['data'].get('proposed_buildings') == [])

    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    check('empty → is_complete=True (no buildings entered = valid)',
          r.json()['data']['is_complete'] is True,
          f'errors: {r.json()["data"]["errors"]}')

    # PATCH with 2 existing + 1 proposed + 2 site dev items + cost data
    r = client.patch(url,
        data=json.dumps({
            'has_civil_cost_estimate': True,
            'cost_site_development': '250000.00',
            'cost_building_construction': '1500000.00',
            'cost_internal_roads': '100000.00',
            'basis_of_estimate': 'engineer',
            'has_future_expansion': False,
            'existing_buildings': [
                {
                    'order': 1, 'building_name': 'Old office',
                    'purpose': 'Administration',
                    'floor_area': '200.00', 'area_unit': 'sqm',
                    'present_condition': 'Good', 'ownership_status': 'fpo_owned',
                    'proposed_action': 'renovate', 'year_of_construction': 2010,
                    'num_floors': 1,
                },
                {
                    'order': 2, 'building_name': 'Store',
                    'floor_area': '100.00', 'area_unit': 'sqm',
                    'proposed_action': 'continue',
                    'ownership_status': 'fpo_owned',
                },
            ],
            'proposed_buildings': [
                {
                    'order': 1, 'building_type': b_type.id,
                    'purpose': 'Rice milling',
                    'floor_area': '500.00', 'area_unit': 'sqm',
                    'proposed_location_within_site': 'North-east corner',
                    'num_floors': 1,
                    'estimated_construction_cost': '1500000.00',
                    'estimated_completion_period': '6 months',
                },
            ],
            'site_development_items': [
                {
                    'order': 1, 'category': civil_cat.id,
                    'estimated_quantity': '500 m',
                    'estimated_cost': '75000.00',
                    'remarks': 'Perimeter fencing',
                },
            ],
        }),
        content_type='application/json', **_hdr(fpo_user))
    check('PATCH full → 200', r.status_code == 200, f'{r.content[:400]}')
    d = r.json()['data']
    check(f'  2 existing buildings ({len(d.get("existing_buildings", []))})', len(d.get('existing_buildings', [])) == 2)
    check(f'  1 proposed building ({len(d.get("proposed_buildings", []))})', len(d.get('proposed_buildings', [])) == 1)
    check(f'  1 site dev item ({len(d.get("site_development_items", []))})', len(d.get('site_development_items', [])) == 1)
    check('  cost_site_development saved', str(d.get('cost_site_development')) == '250000.00')

    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    check('readiness → is_complete=True',
          r.json()['data']['is_complete'] is True,
          f'errors: {r.json()["data"]["errors"]}')

    # Validation — existing building without name
    r = client.patch(url,
        data=json.dumps({
            'existing_buildings': [{'floor_area': '100', 'ownership_status': 'fpo_owned'}],
        }),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('existing bldg w/o name → name_required', 'name_required' in errs)

    # Proposed building with 0 floor area
    r = client.patch(url,
        data=json.dumps({
            'existing_buildings': [{'building_name': 'X', 'floor_area': '100', 'ownership_status': 'fpo_owned'}],
            'proposed_buildings': [{'building_type': b_type.id, 'floor_area': '0'}],
        }),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('proposed floor_area=0 → floor_area_positive', 'floor_area_positive' in errs)

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
