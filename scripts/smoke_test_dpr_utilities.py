"""Smoke test — DPR §2.3.16 Utilities and Support Services."""

import json
from django.contrib.auth.models import User
from django.test import Client
from rest_framework_simplejwt.tokens import RefreshToken

from apps.database.models import (
    DPRProject, DPRFuelType, DPRWasteType, DPRRenewableInitiative,
)


def _tok(u): return str(RefreshToken.for_user(u).access_token)
def _hdr(u): return {'HTTP_AUTHORIZATION': f'Bearer {_tok(u)}'}
def _ok(l): print(f'  \033[32m✓\033[0m {l}')
def _bad(l, d=''): print(f'  \033[31m✗\033[0m {l}' + (f'\n      {d}' if d else ''))


def smoke_test():
    fpo_user = User.objects.filter(
        groups__name='fpo_manager', is_active=True, fpo__isnull=False,
    ).first()
    assert fpo_user

    fuels = list(DPRFuelType.objects.filter(is_active=True).exclude(code='other')[:2])
    wastes = list(DPRWasteType.objects.filter(is_active=True).exclude(code='other')[:2])
    renewables = list(DPRRenewableInitiative.objects.filter(is_active=True).exclude(code='other')[:1])
    assert fuels and wastes and renewables

    client = Client()
    failures = []

    def check(label, cond, detail=''):
        if cond: _ok(label)
        else: _bad(label, detail); failures.append(label)

    print('── §2.3.16 Utilities smoke test ──')

    r = client.post('/api/fpo/dpr/projects/',
        data=json.dumps({'title': 'Utilities Test'}),
        content_type='application/json', **_hdr(fpo_user))
    project_uuid = r.json()['data']['uuid']
    url = f'/api/fpo/dpr/projects/{project_uuid}/sections/utilities/'

    r = client.get(url)
    check('unauth → 401', r.status_code == 401)

    r = client.get(url, **_hdr(fpo_user))
    check('GET → 200 (empty)', r.status_code == 200)
    check('  empty fuels', r.json()['data'].get('fuels') == [])

    # Empty is fine (all sub-sections conditional)
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    check('empty → is_complete=True',
          r.json()['data']['is_complete'] is True,
          f'errors: {r.json()["data"]["errors"]}')

    # Turn on electricity without supply type → error
    r = client.patch(url,
        data=json.dumps({'electricity_required': True}),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('electricity w/o supply → supply_type_required', 'supply_type_required' in errs)

    # PATCH full data
    r = client.patch(url,
        data=json.dumps({
            'electricity_required': True,
            'electricity_supply_type': 'three_phase',
            'backup_power_required': True,
            'connected_load_kw': '25.00',
            'dg_set_required': True,
            'water_required': True,
            'water_source': 'borewell',
            'water_available_year_round': True,
            'refrigeration_required': False,
            'generates_effluent': False,
            'communication_items': ['broadband_internet', 'wifi', 'cctv'],
            'fire_safety_items': ['fire_extinguishers', 'first_aid', 'ppe'],
            'fuels': [
                {'fuel': fuels[0].id, 'purpose': 'Boiler fuel', 'annual_consumption': '1000 L'},
                {'fuel': fuels[1].id, 'purpose': 'DG set', 'annual_consumption': '500 L'},
            ],
            'process_utilities': [
                {'utility_type': 'compressed_air', 'purpose': 'Packaging', 'capacity': '5 HP'},
                {'utility_type': 'steam', 'purpose': 'Boiler', 'source': 'in-house'},
            ],
            'wastes': [
                {'waste': wastes[0].id, 'disposal_method': 'Composting on-site', 'estimated_quantity': '20 kg/day'},
                {'waste': wastes[1].id, 'disposal_method': 'Third-party collection', 'estimated_quantity': '5 kg/day'},
            ],
            'renewable_initiatives': [
                {'initiative': renewables[0].id, 'capacity': '10 kW', 'estimated_cost': '500000.00', 'expected_annual_savings': '75000.00'},
            ],
        }),
        content_type='application/json', **_hdr(fpo_user))
    check('PATCH full → 200', r.status_code == 200, f'{r.content[:400]}')
    d = r.json()['data']
    check(f'  2 fuels ({len(d.get("fuels", []))})', len(d.get('fuels', [])) == 2)
    check(f'  2 process utils ({len(d.get("process_utilities", []))})', len(d.get('process_utilities', [])) == 2)
    check(f'  2 wastes ({len(d.get("wastes", []))})', len(d.get('wastes', [])) == 2)
    check(f'  1 renewable ({len(d.get("renewable_initiatives", []))})', len(d.get('renewable_initiatives', [])) == 1)
    check(f'  3 communication items', len(d.get('communication_items', [])) == 3)

    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    check('readiness → is_complete=True',
          r.json()['data']['is_complete'] is True,
          f'errors: {r.json()["data"]["errors"]}')

    # Duplicate fuel → 400 (dedup validator)
    r = client.patch(url,
        data=json.dumps({
            'fuels': [
                {'fuel': fuels[0].id, 'purpose': 'A'},
                {'fuel': fuels[0].id, 'purpose': 'B'},
            ],
        }),
        content_type='application/json', **_hdr(fpo_user))
    check('duplicate fuel → 400', r.status_code == 400, f'got {r.status_code}')

    # Duplicate process_utility → 400
    r = client.patch(url,
        data=json.dumps({
            'process_utilities': [
                {'utility_type': 'steam', 'purpose': 'A'},
                {'utility_type': 'steam', 'purpose': 'B'},
            ],
        }),
        content_type='application/json', **_hdr(fpo_user))
    check('duplicate process_utility → 400', r.status_code == 400, f'got {r.status_code}')

    # Empty disposal method → error
    r = client.patch(url,
        data=json.dumps({
            'wastes': [{'waste': wastes[0].id, 'disposal_method': ''}],
        }),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('empty disposal_method → disposal_method_required', 'disposal_method_required' in errs)

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
