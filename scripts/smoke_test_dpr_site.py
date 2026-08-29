"""Smoke test — DPR §2.3.13 Land, Site Suitability and Infrastructure Readiness."""

import json
from django.contrib.auth.models import User
from django.test import Client
from rest_framework_simplejwt.tokens import RefreshToken

from apps.database.models import (
    DPRProject, DPRCapacityUnit, DPRLandOwnershipType,
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

    unit = DPRCapacityUnit.objects.filter(is_active=True).first()
    ownership = DPRLandOwnershipType.objects.filter(is_active=True).exclude(code__contains='other').first()

    client = Client()
    failures = []

    def check(label, cond, detail=''):
        if cond: _ok(label)
        else: _bad(label, detail); failures.append(label)

    print('── §2.3.13 Land & Site smoke test ──')

    r = client.post('/api/fpo/dpr/projects/',
        data=json.dumps({'title': 'Site Test'}),
        content_type='application/json', **_hdr(fpo_user))
    project_uuid = r.json()['data']['uuid']
    url = f'/api/fpo/dpr/projects/{project_uuid}/sections/site/'

    r = client.get(url)
    check('unauth → 401', r.status_code == 401)

    r = client.get(url, **_hdr(fpo_user))
    check('GET → 200 (empty)', r.status_code == 200)
    check('  empty parcels', r.json()['data'].get('parcels') == [])

    # Empty → several required errors
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('empty → at_least_one_parcel', 'at_least_one_parcel' in errs)
    check('empty → terrain_required', 'terrain_required' in errs)

    # Fill in section-level + 2 parcels + 1 infra + 1 constraint
    r = client.patch(url,
        data=json.dumps({
            'terrain': 'plain',
            'is_flood_prone': False,
            'water_available_year_round': True,
            'electricity_availability': 'available',
            'water_availability': 'available',
            'road_connectivity': 'good',
            'water_sources': ['borewell', 'panchayat_supply'],
            'has_broadband': True,
            'approvals_available': ['building_permit', 'panchayat_approval'],
            'has_future_expansion': False,
            'parcels': [
                {
                    'order': 1,
                    'total_land_available': '2.5000',
                    'land_proposed_for_project': '2.0000',
                    'unit': unit.id,
                    'village': 'Vellanikkara',
                    'taluk': 'Thrissur',
                    'district': 'Thrissur',
                    'ownership': ownership.id,
                    'survey_number': '123/1',
                    'present_land_use': 'Agricultural',
                },
                {
                    'order': 2,
                    'total_land_available': '1.0000',
                    'unit': unit.id,
                    'village': 'Nadathara',
                    'district': 'Thrissur',
                    'ownership': ownership.id,
                },
            ],
            'existing_infrastructure': [
                {
                    'order': 1,
                    'infrastructure_type': 'approach_road',
                    'condition': 'Good',
                    'approximate_area': '500.00',
                    'year_of_construction': 2015,
                    'renovation_required': False,
                },
            ],
            'constraints': [
                {
                    'constraint_type': 'water_scarcity',
                    'mitigation_measure': 'Rainwater harvesting + additional borewell',
                    'existing_situation': 'Water shortage in summer months',
                },
            ],
        }),
        content_type='application/json', **_hdr(fpo_user))
    check('PATCH full data → 200', r.status_code == 200, f'{r.content[:400]}')
    d = r.json()['data']
    check('  terrain=plain saved', d.get('terrain') == 'plain')
    check('  2 water_sources saved', d.get('water_sources') == ['borewell', 'panchayat_supply'])
    check('  2 approvals_available saved',
          set(d.get('approvals_available', [])) == {'building_permit', 'panchayat_approval'})
    check(f'  2 parcels saved ({len(d.get("parcels", []))})', len(d.get('parcels', [])) == 2)
    check(f'  1 infra saved ({len(d.get("existing_infrastructure", []))})', len(d.get('existing_infrastructure', [])) == 1)
    check(f'  1 constraint saved ({len(d.get("constraints", []))})', len(d.get('constraints', [])) == 1)

    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    rr = r.json()['data']
    check('readiness → is_complete=True',
          rr['is_complete'] is True,
          f'errors: {rr["errors"]}')

    # Full-replace parcels — 1 parcel with 0 area → validation error
    r = client.patch(url,
        data=json.dumps({
            'parcels': [{'total_land_available': '0', 'ownership': ownership.id, 'unit': unit.id}],
        }),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('area=0 → land_area_positive', 'land_area_positive' in errs)

    # Constraint with empty mitigation → error
    r = client.patch(url,
        data=json.dumps({
            'parcels': [{'total_land_available': '1.0', 'ownership': ownership.id, 'unit': unit.id}],
            'constraints': [{'constraint_type': 'flooding', 'mitigation_measure': ''}],
        }),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('empty mitigation → mitigation_required', 'mitigation_required' in errs)

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
