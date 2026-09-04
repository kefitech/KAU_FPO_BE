"""Smoke test — DPR §2.3.20 Environmental, Social and Sustainability Assessment."""

import json
from django.contrib.auth.models import User
from django.test import Client
from rest_framework_simplejwt.tokens import RefreshToken

from apps.database.models import DPRProject, DPREnvironmentalImpact, DPRClimateRisk


def _tok(u): return str(RefreshToken.for_user(u).access_token)
def _hdr(u): return {'HTTP_AUTHORIZATION': f'Bearer {_tok(u)}'}
def _ok(l): print(f'  \033[32m✓\033[0m {l}')
def _bad(l, d=''): print(f'  \033[31m✗\033[0m {l}' + (f'\n      {d}' if d else ''))


def smoke_test():
    fpo_user = User.objects.filter(
        groups__name='fpo_manager', is_active=True, fpo__isnull=False,
    ).first()
    assert fpo_user

    impacts = list(DPREnvironmentalImpact.objects.filter(is_active=True).exclude(code='other')[:2])
    other_impact = DPREnvironmentalImpact.objects.get(code='other')
    risks = list(DPRClimateRisk.objects.filter(is_active=True).exclude(code='other')[:2])

    client = Client()
    failures = []

    def check(label, cond, detail=''):
        if cond: _ok(label)
        else: _bad(label, detail); failures.append(label)

    print('── §2.3.20 ESS smoke test ──')

    r = client.post('/api/fpo/dpr/projects/',
        data=json.dumps({'title': 'ESS Test'}),
        content_type='application/json', **_hdr(fpo_user))
    project_uuid = r.json()['data']['uuid']
    url = f'/api/fpo/dpr/projects/{project_uuid}/sections/ess/'

    r = client.get(url)
    check('unauth → 401', r.status_code == 401)

    r = client.get(url, **_hdr(fpo_user))
    check('GET → 200 (empty)', r.status_code == 200)

    # Empty → is_complete (all fields advisory)
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    check('empty → is_complete=True',
          r.json()['data']['is_complete'] is True,
          f'errors: {r.json()["data"]["errors"]}')

    # PATCH full
    r = client.patch(url,
        data=json.dumps({
            'resources_used': ['electricity', 'water', 'raw_materials'],
            'conservation_measures': ['water_conservation', 'energy_conservation', 'solar_energy'],
            'annual_electricity_requirement': '50000 kWh',
            'annual_water_requirement': '2000 KL',
            'safety_measures': ['ppe', 'fire_safety', 'first_aid', 'safety_signage'],
            'farmers_benefited': 250,
            'direct_jobs_created': 15,
            'indirect_jobs_created': 40,
            'women_beneficiaries': 80,
            'youth_beneficiaries': 60,
            'small_marginal_farmers': 200,
            'expected_income_increase': '25% increase over 3 years',
            'sustainability_initiatives': ['renewable_energy', 'organic_production', 'water_reuse'],
            'environmental_impacts': [
                {'impact': impacts[0].id, 'estimated_quantity': '100 kg/day',
                 'source': 'Processing unit', 'existing_control_measure': 'Bag filter',
                 'proposed_mitigation_measure': 'Upgrade to cyclone separator'},
                {'impact': impacts[1].id, 'estimated_quantity': 'Moderate',
                 'proposed_mitigation_measure': 'Silencer installation'},
            ],
            'climate_risks': [
                {'risk': risks[0].id, 'expected_impact': 'Flooding risk in monsoon',
                 'proposed_mitigation_strategy': 'Elevated construction + drainage system'},
                {'risk': risks[1].id, 'expected_impact': 'Water scarcity in summer',
                 'proposed_mitigation_strategy': 'Rainwater harvesting + storage'},
            ],
        }),
        content_type='application/json', **_hdr(fpo_user))
    check('PATCH full → 200', r.status_code == 200, f'{r.content[:400]}')
    d = r.json()['data']
    check(f'  3 resources_used', len(d.get('resources_used', [])) == 3)
    check(f'  3 conservation_measures', len(d.get('conservation_measures', [])) == 3)
    check(f'  2 env impacts ({len(d.get("environmental_impacts", []))})', len(d.get('environmental_impacts', [])) == 2)
    check(f'  2 climate risks ({len(d.get("climate_risks", []))})', len(d.get('climate_risks', [])) == 2)
    check('  farmers_benefited=250', d.get('farmers_benefited') == 250)

    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    rr = r.json()['data']
    check('readiness → is_complete=True',
          rr['is_complete'] is True,
          f'errors: {rr["errors"]}')

    # "other" impact without text → error
    r = client.patch(url,
        data=json.dumps({
            'environmental_impacts': [{'impact': other_impact.id, 'impact_other': ''}],
        }),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('other impact w/o text → impact_other_required', 'impact_other_required' in errs)

    # Conservation "other" without text → error
    r = client.patch(url,
        data=json.dumps({
            'environmental_impacts': [{'impact': impacts[0].id}],
            'conservation_measures': ['other'],
            'conservation_other': '',
        }),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('conservation "other" w/o text → conservation_other_required', 'conservation_other_required' in errs)

    # Climate risk w/o mitigation → warning (not error)
    r = client.patch(url,
        data=json.dumps({
            'conservation_measures': ['water_conservation'],
            'climate_risks': [{'risk': risks[0].id}],
        }),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    rr = r.json()['data']
    check('climate risk w/o mitigation → warning (not error)',
          rr['is_complete'] is True and
          any(w['code'] == 'mitigation_recommended' for w in rr.get('warnings', [])))

    # Duplicate impact → 400
    r = client.patch(url,
        data=json.dumps({
            'environmental_impacts': [
                {'impact': impacts[0].id},
                {'impact': impacts[0].id},
            ],
        }),
        content_type='application/json', **_hdr(fpo_user))
    check('duplicate impact → 400', r.status_code == 400)

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
