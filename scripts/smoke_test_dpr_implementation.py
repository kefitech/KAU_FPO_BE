"""Smoke test — DPR §2.3.21 Project Implementation Plan."""

import json
from django.contrib.auth.models import User
from django.test import Client
from rest_framework_simplejwt.tokens import RefreshToken

from apps.database.models import DPRProject


def _tok(u): return str(RefreshToken.for_user(u).access_token)
def _hdr(u): return {'HTTP_AUTHORIZATION': f'Bearer {_tok(u)}'}
def _ok(l): print(f'  \033[32m✓\033[0m {l}')
def _bad(l, d=''): print(f'  \033[31m✗\033[0m {l}' + (f'\n      {d}' if d else ''))


def smoke_test():
    fpo_user = User.objects.filter(
        groups__name='fpo_manager', is_active=True, fpo__isnull=False,
    ).first()
    assert fpo_user

    client = Client()
    failures = []

    def check(label, cond, detail=''):
        if cond: _ok(label)
        else: _bad(label, detail); failures.append(label)

    print('── §2.3.21 Implementation Plan smoke test ──')

    r = client.post('/api/fpo/dpr/projects/',
        data=json.dumps({'title': 'Implementation Test'}),
        content_type='application/json', **_hdr(fpo_user))
    project_uuid = r.json()['data']['uuid']
    url = f'/api/fpo/dpr/projects/{project_uuid}/sections/implementation/'

    r = client.get(url)
    check('unauth → 401', r.status_code == 401)

    r = client.get(url, **_hdr(fpo_user))
    check('GET → 200 (empty)', r.status_code == 200)

    # Empty → procurement + monitoring required
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('empty → procurement_method_required', 'procurement_method_required' in errs)
    check('empty → monitoring_frequency_required', 'monitoring_frequency_required' in errs)

    # PATCH full
    r = client.patch(url,
        data=json.dumps({
            'procurement_method': 'tender',
            'tender_required': True,
            'num_quotations_proposed': 3,
            'supplier_finalisation_method': 'L1 (Lowest bid)',
            'expected_procurement_period': '2 months',
            'responsibility_agencies': ['fpo_board', 'ceo', 'project_manager'],
            'responsibility_remarks': 'CEO owns overall execution; Project Manager reports weekly',
            'monitoring_frequency': 'monthly',
            'monitoring_authority': 'Board of Directors',
            'reporting_mechanism': 'Monthly written report + quarterly board meeting',
            'corrective_action_process': 'Escalate to board within 15 days if variance > 20%',
            'activities': [
                {'order': 1, 'activity_name': 'Land Development',
                 'proposed_start_date': '2026-09-01',
                 'proposed_completion_date': '2026-10-15',
                 'estimated_duration': '45 days',
                 'responsible_person_or_agency': 'Local contractor'},
                {'order': 2, 'activity_name': 'Civil Construction',
                 'proposed_start_date': '2026-10-16',
                 'proposed_completion_date': '2027-03-31',
                 'estimated_duration': '5 months',
                 'responsible_person_or_agency': 'Construction contractor'},
                {'order': 3, 'activity_name': 'Machinery Procurement',
                 'proposed_start_date': '2027-01-01',
                 'proposed_completion_date': '2027-03-31',
                 'responsible_person_or_agency': 'Project Manager'},
            ],
            'milestones': [
                {'order': 1, 'milestone_type': 'financial_closure',
                 'expected_date': '2026-08-31'},
                {'order': 2, 'milestone_type': 'civil_completion',
                 'expected_date': '2027-03-31'},
                {'order': 3, 'milestone_type': 'commercial_production',
                 'expected_date': '2027-06-01'},
            ],
        }),
        content_type='application/json', **_hdr(fpo_user))
    check('PATCH full → 200', r.status_code == 200, f'{r.content[:400]}')
    d = r.json()['data']
    check('  procurement_method saved', d.get('procurement_method') == 'tender')
    check(f'  3 activities ({len(d.get("activities", []))})', len(d.get('activities', [])) == 3)
    check(f'  3 milestones ({len(d.get("milestones", []))})', len(d.get('milestones', [])) == 3)
    check(f'  3 responsibility_agencies', len(d.get('responsibility_agencies', [])) == 3)

    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    check('readiness → is_complete=True',
          r.json()['data']['is_complete'] is True,
          f'errors: {r.json()["data"]["errors"]}')

    # Activity without name → error
    r = client.patch(url,
        data=json.dumps({
            'activities': [{'proposed_start_date': '2026-09-01'}],
        }),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('activity w/o name → activity_name_required', 'activity_name_required' in errs)

    # Start > completion → error
    r = client.patch(url,
        data=json.dumps({
            'activities': [{
                'activity_name': 'Bad activity',
                'proposed_start_date': '2027-01-01',
                'proposed_completion_date': '2026-06-01',
            }],
        }),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('start > completion → start_before_completion', 'start_before_completion' in errs)

    # Milestone "other" without text → error
    r = client.patch(url,
        data=json.dumps({
            'activities': [{'activity_name': 'X'}],
            'milestones': [{'milestone_type': 'other'}],
        }),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('milestone other w/o text → milestone_other_required', 'milestone_other_required' in errs)

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
