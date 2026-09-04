"""Smoke test — DPR §2.3.9 Project Capacity and Production System."""

import json
from datetime import date
from django.contrib.auth.models import User
from django.test import Client
from rest_framework_simplejwt.tokens import RefreshToken

from apps.database.models import DPRProject, DPRCapacityUnit, DPRCapacityBasis


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
    basis = DPRCapacityBasis.objects.filter(is_active=True).first()
    assert unit and basis

    client = Client()
    failures = []

    def check(label, cond, detail=''):
        if cond: _ok(label)
        else: _bad(label, detail); failures.append(label)

    print('── §2.3.9 Project Capacity smoke test ──')

    r = client.post('/api/fpo/dpr/projects/',
        data=json.dumps({'title': 'Capacity Test'}),
        content_type='application/json', **_hdr(fpo_user))
    project_uuid = r.json()['data']['uuid']
    url = f'/api/fpo/dpr/projects/{project_uuid}/sections/capacity/'

    r = client.get(url)
    check('unauth → 401', r.status_code == 401)

    r = client.get(url, **_hdr(fpo_user))
    check('GET → 200 (empty)', r.status_code == 200)
    check('  peak_production_seasons is empty list',
          r.json()['data'].get('peak_production_seasons') == [])

    # Empty → many mandatory errors
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    for req in ['installed_capacity_positive', 'capacity_unit_required',
                'capacity_basis_required', 'process_description_required',
                'process_type_required', 'automation_required']:
        check(f'empty readiness → {req}', req in errs)

    # PATCH mandatory fields
    r = client.patch(url,
        data=json.dumps({
            'installed_capacity': '1000.000',
            'capacity_unit': unit.id,
            'capacity_basis': basis.id,
            'practical_operating_capacity': '850.000',
            'first_year_capacity_utilisation_pct': '65.00',
            'working_days_per_year': 300,
            'shifts_per_day': 2,
            'operating_hours_per_shift': '8.00',
            'operating_months_per_year': 12,
            'peak_production_seasons': ['nov', 'dec', 'jan'],
            'lean_production_seasons': ['jun', 'jul'],
            'process_description': 'Batch processing of rice through cleaning, sorting, drying, and packaging stages.',
            'process_type': 'batch',
            'automation_level': 'semi_auto',
        }),
        content_type='application/json', **_hdr(fpo_user))
    check('PATCH mandatory → 200', r.status_code == 200, f'{r.content[:400]}')
    d = r.json()['data']
    check('  installed_capacity saved', str(d.get('installed_capacity')) == '1000.000')
    check('  peak_production_seasons saved', d.get('peak_production_seasons') == ['nov', 'dec', 'jan'])

    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    check('readiness → is_complete=True',
          r.json()['data']['is_complete'] is True,
          f'errors: {r.json()["data"]["errors"]}')

    # Range validation — utilization > 100
    r = client.patch(url,
        data=json.dumps({'first_year_capacity_utilisation_pct': '150.00'}),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('utilization>100 → utilisation_range', 'utilisation_range' in errs)

    # Range validation — shifts > 3
    r = client.patch(url,
        data=json.dumps({'shifts_per_day': 5, 'first_year_capacity_utilisation_pct': '65.00'}),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('shifts>3 → shifts_range', 'shifts_range' in errs)

    # >150 words process description
    long_desc = ' '.join(['word'] * 160)
    r = client.patch(url,
        data=json.dumps({'shifts_per_day': 2, 'process_description': long_desc}),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('>150 words desc → process_description_too_long', 'process_description_too_long' in errs)

    # Restore good desc + turn on has_production_loss without pct → error
    r = client.patch(url,
        data=json.dumps({
            'process_description': 'Short desc.',
            'has_production_loss': True,
        }),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('has_production_loss=True w/o pct → loss_pct_required', 'loss_pct_required' in errs)

    # Fill loss info
    r = client.patch(url,
        data=json.dumps({
            'production_loss_pct': '5.00',
            'product_recovery_pct': '95.00',
            'loss_sources': ['processing', 'storage'],
        }),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    check('after filling losses → is_complete=True',
          r.json()['data']['is_complete'] is True,
          f'errors: {r.json()["data"]["errors"]}')

    # Future expansion — has flag but no year → error
    r = client.patch(url,
        data=json.dumps({'has_future_expansion': True}),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('has_future_expansion w/o year → expansion_year_required', 'expansion_year_required' in errs)

    # Fill expansion with past year → year_future error
    r = client.patch(url,
        data=json.dumps({
            'expected_year_of_expansion': 2020,
            'expansion_nature': 'capacity',
        }),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('past year → expansion_year_future', 'expansion_year_future' in errs)

    # Fix year
    r = client.patch(url,
        data=json.dumps({'expected_year_of_expansion': date.today().year + 2}),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    check('after fixing year → is_complete=True',
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
