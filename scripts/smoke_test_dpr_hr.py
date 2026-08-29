"""Smoke test — DPR §2.3.17 Human Resources and Organisational Structure."""

import json
from django.contrib.auth.models import User
from django.test import Client
from rest_framework_simplejwt.tokens import RefreshToken

from apps.database.models import DPRProject, DPRTrainingArea


def _tok(u): return str(RefreshToken.for_user(u).access_token)
def _hdr(u): return {'HTTP_AUTHORIZATION': f'Bearer {_tok(u)}'}
def _ok(l): print(f'  \033[32m✓\033[0m {l}')
def _bad(l, d=''): print(f'  \033[31m✗\033[0m {l}' + (f'\n      {d}' if d else ''))


def smoke_test():
    fpo_user = User.objects.filter(
        groups__name='fpo_manager', is_active=True, fpo__isnull=False,
    ).first()
    assert fpo_user

    trainings = list(DPRTrainingArea.objects.filter(is_active=True).exclude(code='other')[:2])
    assert len(trainings) == 2

    client = Client()
    failures = []

    def check(label, cond, detail=''):
        if cond: _ok(label)
        else: _bad(label, detail); failures.append(label)

    print('── §2.3.17 HR smoke test ──')

    r = client.post('/api/fpo/dpr/projects/',
        data=json.dumps({'title': 'HR Test'}),
        content_type='application/json', **_hdr(fpo_user))
    project_uuid = r.json()['data']['uuid']
    url = f'/api/fpo/dpr/projects/{project_uuid}/sections/hr/'

    r = client.get(url)
    check('unauth → 401', r.status_code == 401)

    r = client.get(url, **_hdr(fpo_user))
    check('GET → 200 (empty)', r.status_code == 200)

    # Empty → management_model_required
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('empty → management_model_required', 'management_model_required' in errs)

    # PATCH full
    r = client.patch(url,
        data=json.dumps({
            'project_head': 'Ramesh Kumar',
            'operational_management_model': 'by_fpo',
            'reporting_authority': 'Board of Directors',
            'has_existing_employees': True,
            'existing_employees_total': 8,
            'existing_technical_staff': 3,
            'existing_administrative_staff': 2,
            'labour_availability': 'moderately',
            'primary_labour_source': 'local',
            'welfare_items': ['staff_room', 'toilets', 'drinking_water', 'safety_equipment'],
            'statutory_compliance': ['epf', 'esi', 'labour_registration'],
            'has_future_manpower_expansion': False,
            'employee_categories': [
                {
                    'order': 1, 'designation': 'Project Manager',
                    'nature_of_work': 'Overall management',
                    'number_required': 1, 'employment_type': 'permanent',
                    'monthly_salary': '50000.00', 'annual_salary': '600000.00',
                },
                {
                    'order': 2, 'designation': 'Operator',
                    'nature_of_work': 'Machine operation',
                    'number_required': 4, 'employment_type': 'permanent',
                    'monthly_salary': '18000.00', 'annual_salary': '216000.00',
                },
            ],
            'departments': [
                {'department': 'administration', 'num_persons': 3, 'annual_salary': '900000.00'},
                {'department': 'production', 'num_persons': 5, 'annual_salary': '1080000.00'},
            ],
            'training_requirements': [
                {'training_area': trainings[0].id, 'duration': '5 days',
                 'training_provider': 'KAU KVK', 'estimated_cost': '15000.00'},
                {'training_area': trainings[1].id, 'duration': '3 days',
                 'estimated_cost': '10000.00'},
            ],
        }),
        content_type='application/json', **_hdr(fpo_user))
    check('PATCH full → 200', r.status_code == 200, f'{r.content[:400]}')
    d = r.json()['data']
    check('  management_model saved', d.get('operational_management_model') == 'by_fpo')
    check(f'  2 employee_categories ({len(d.get("employee_categories", []))})', len(d.get('employee_categories', [])) == 2)
    check(f'  2 departments ({len(d.get("departments", []))})', len(d.get('departments', [])) == 2)
    check(f'  2 training_requirements ({len(d.get("training_requirements", []))})', len(d.get('training_requirements', [])) == 2)
    check(f'  4 welfare_items', len(d.get('welfare_items', [])) == 4)

    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    check('readiness → is_complete=True',
          r.json()['data']['is_complete'] is True,
          f'errors: {r.json()["data"]["errors"]}')

    # Employee with 0 count → error
    r = client.patch(url,
        data=json.dumps({
            'employee_categories': [
                {'designation': 'Bad', 'number_required': 0, 'employment_type': 'permanent'},
            ],
        }),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('number=0 → number_positive', 'number_positive' in errs)

    # Duplicate department → 400
    r = client.patch(url,
        data=json.dumps({
            'departments': [
                {'department': 'administration', 'num_persons': 1},
                {'department': 'administration', 'num_persons': 2},
            ],
        }),
        content_type='application/json', **_hdr(fpo_user))
    check('duplicate department → 400', r.status_code == 400)

    # Duplicate training area → 400
    r = client.patch(url,
        data=json.dumps({
            'training_requirements': [
                {'training_area': trainings[0].id},
                {'training_area': trainings[0].id},
            ],
        }),
        content_type='application/json', **_hdr(fpo_user))
    check('duplicate training_area → 400', r.status_code == 400)

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
