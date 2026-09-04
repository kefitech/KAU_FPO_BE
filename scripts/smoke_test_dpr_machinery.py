"""Smoke test — DPR §2.3.15 Plant, Machinery and Equipment."""

import json
from django.contrib.auth.models import User
from django.test import Client
from rest_framework_simplejwt.tokens import RefreshToken

from apps.database.models import (
    DPRProject, DPRComponent, DPRMachineryCategory,
    DPRCapacityUnit, DPRSupportingAsset,
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

    comp = DPRComponent.objects.filter(is_active=True).exclude(code__endswith='_other').first()
    m_cat = DPRMachineryCategory.objects.filter(code='processing').first()
    unit = DPRCapacityUnit.objects.filter(is_active=True).first()
    sa = DPRSupportingAsset.objects.filter(is_active=True).first()

    client = Client()
    failures = []

    def check(label, cond, detail=''):
        if cond: _ok(label)
        else: _bad(label, detail); failures.append(label)

    print('── §2.3.15 Plant & Machinery smoke test ──')

    r = client.post('/api/fpo/dpr/projects/',
        data=json.dumps({'title': 'Machinery Test'}),
        content_type='application/json', **_hdr(fpo_user))
    project_uuid = r.json()['data']['uuid']
    url = f'/api/fpo/dpr/projects/{project_uuid}/sections/machinery/'

    r = client.get(url)
    check('unauth → 401', r.status_code == 401)

    r = client.get(url, **_hdr(fpo_user))
    check('GET → 200 (empty)', r.status_code == 200)
    check('  empty items', r.json()['data'].get('items') == [])

    # PATCH with 1 machinery item + 1 supporting asset + statutory approvals
    r = client.patch(url,
        data=json.dumps({
            'statutory_approvals': ['electrical_inspector', 'safety_cert'],
            'statutory_remarks': 'Pending final electrical inspector visit',
            'items': [{
                'order': 1, 'name': 'Rice Mill', 'purpose': 'Dehusking + polishing',
                'project_component': comp.id, 'machine_category': m_cat.id,
                'quantity_required': '1.000',
                'unit': unit.id,
                'manufacturer': 'ABC Industries', 'model_number': 'RM-500',
                'rated_capacity': '500.000', 'capacity_unit': unit.id,
                'power_source': 'Electric 3-phase', 'automation_level': 'semi_auto',
                'power_requirement': '10 kW', 'num_operators_required': 2,
                'installation_area_required': '30 sqm', 'foundation_required': True,
                'foundation_type': 'RCC platform',
                'unit_cost': '750000.00', 'basic_cost': '650000.00', 'gst': '117000.00',
                'transportation_charges': '15000.00', 'installation_charges': '25000.00',
                'supplier_identified': True, 'supplier_name': 'ABC Sales',
                'supplier_location': 'Coimbatore', 'delivery_period': '2 months',
                'warranty_period': '1 year', 'amc_required': True,
                'amc_cost': '25000.00', 'amc_duration': '1 year',
                'annual_maintenance_required': True,
                'spare_parts_availability': 'easily',
                'useful_life_years': 10, 'residual_value_pct': '10.00',
            }],
            'supporting_assets': [{
                'order': 1, 'asset': sa.id, 'quantity': '5.00',
                'purpose': 'Raw material transport', 'estimated_cost': '15000.00',
            }],
        }),
        content_type='application/json', **_hdr(fpo_user))
    check('PATCH complete → 200', r.status_code == 200, f'{r.content[:400]}')
    d = r.json()['data']
    check(f'  1 machinery item ({len(d.get("items", []))})', len(d.get('items', [])) == 1)
    check(f'  1 supporting asset ({len(d.get("supporting_assets", []))})', len(d.get('supporting_assets', [])) == 1)
    check(f'  2 statutory_approvals saved',
          set(d.get('statutory_approvals', [])) == {'electrical_inspector', 'safety_cert'})
    check('  unit_cost saved', str(d['items'][0].get('unit_cost')) == '750000.00')

    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    rr = r.json()['data']
    check('readiness → is_complete=True',
          rr['is_complete'] is True,
          f'errors: {rr["errors"]}')

    # Validation — item without project_component → error
    r = client.patch(url,
        data=json.dumps({
            'items': [{'name': 'Bad', 'quantity_required': '1'}],
        }),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('missing component → component_required', 'component_required' in errs)

    # Rated capacity without unit → error
    r = client.patch(url,
        data=json.dumps({
            'items': [{
                'name': 'X', 'quantity_required': '1', 'project_component': comp.id,
                'rated_capacity': '100',
            }],
        }),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('capacity w/o unit → capacity_unit_required', 'capacity_unit_required' in errs)

    # Zero quantity → error
    r = client.patch(url,
        data=json.dumps({
            'items': [{'name': 'X', 'quantity_required': '0', 'project_component': comp.id}],
        }),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('quantity=0 → quantity_positive', 'quantity_positive' in errs)

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
