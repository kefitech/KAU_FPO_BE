"""Smoke test — DPR §2.3.18 Financial Information and Means of Finance."""

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

    print('── §2.3.18 Finance smoke test ──')

    r = client.post('/api/fpo/dpr/projects/',
        data=json.dumps({'title': 'Finance Test'}),
        content_type='application/json', **_hdr(fpo_user))
    project_uuid = r.json()['data']['uuid']
    url = f'/api/fpo/dpr/projects/{project_uuid}/sections/finance/'

    r = client.get(url)
    check('unauth → 401', r.status_code == 401)

    r = client.get(url, **_hdr(fpo_user))
    check('GET → 200 (empty)', r.status_code == 200)

    # Empty → at least one revenue required
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('empty → at_least_one_revenue', 'at_least_one_revenue' in errs)

    # Basic cost + MoF + revenue
    r = client.patch(url,
        data=json.dumps({
            'cost_civil_works': '1500000.00',
            'cost_plant_machinery': '2000000.00',
            'cost_preliminary_expenses': '100000.00',
            'cost_margin_for_working_capital': '400000.00',
            'mof_promoters_contribution': '1000000.00',
            'mof_bank_term_loan': '2500000.00',
            'mof_government_subsidy': '500000.00',
            'wc_raw_materials': '300000.00',
            'wc_labour_salaries': '800000.00',
            'op_raw_material': '1500000.00',
            'op_salaries_wages': '900000.00',
            'op_electricity': '150000.00',
            'loan_proposed': True,
            'loan_amount': '2500000.00',
            'loan_type': 'term_loan',
            'lending_institution': 'NABARD',
            'rate_of_interest_pct': '10.50',
            'repayment_period_years': 7,
            'moratorium_period_months': 6,
            'repayment_frequency': 'quarterly',
            'subsidy_proposed': True,
            'subsidy_scheme_name': 'FPO Formation Scheme',
            'expected_subsidy_amount': '500000.00',
            'subsidy_application_status': 'applied',
            'is_operational': False,
            'inflation_rate_pct': '6.00',
            'salary_escalation_pct': '5.00',
            'revenue_assumptions': [
                {'order': 1, 'product_name': 'Organic Rice',
                 'year1_sales_quantity': '5000.000',
                 'expected_selling_price': '85.00',
                 'annual_sales_revenue': '425000.00',
                 'expected_annual_growth_rate_pct': '8.00'},
                {'order': 2, 'product_name': 'Bran Powder',
                 'year1_sales_quantity': '500.000',
                 'expected_selling_price': '20.00',
                 'annual_sales_revenue': '10000.00'},
            ],
        }),
        content_type='application/json', **_hdr(fpo_user))
    check('PATCH full → 200', r.status_code == 200, f'{r.content[:400]}')
    d = r.json()['data']
    check('  cost_civil_works saved', str(d.get('cost_civil_works')) == '1500000.00')
    check('  loan_proposed=True', d.get('loan_proposed') is True)
    check(f'  2 revenue assumptions ({len(d.get("revenue_assumptions", []))})', len(d.get('revenue_assumptions', [])) == 2)

    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    rr = r.json()['data']
    check('readiness → is_complete=True',
          rr['is_complete'] is True,
          f'errors: {rr["errors"]}')

    # Cost/MoF mismatch → warning
    warnings = rr.get('warnings', [])
    # Total cost = 4000000, Total MoF = 4000000 → aligned, no warning here
    # Let's test by breaking it
    r = client.patch(url,
        data=json.dumps({'mof_bank_term_loan': '1000000.00'}),  # now MoF < cost
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    warnings = [w['code'] for w in r.json()['data'].get('warnings', [])]
    check('MoF < cost → mof_cost_mismatch warning', 'mof_cost_mismatch' in warnings)

    # Loan without amount → error
    r = client.patch(url,
        data=json.dumps({'loan_proposed': True, 'loan_amount': None}),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('loan_proposed w/o amount → loan_amount_required', 'loan_amount_required' in errs)

    # Loan > total cost → error
    r = client.patch(url,
        data=json.dumps({'loan_amount': '99999999.00'}),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('loan > cost → loan_exceeds_cost', 'loan_exceeds_cost' in errs)

    # Subsidy without scheme → error
    r = client.patch(url,
        data=json.dumps({
            'loan_amount': '2500000.00',
            'mof_bank_term_loan': '2500000.00',
            'subsidy_proposed': True, 'subsidy_scheme_name': '',
        }),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('subsidy w/o scheme → scheme_name_required', 'scheme_name_required' in errs)

    # Operational + no turnover → error
    r = client.patch(url,
        data=json.dumps({
            'subsidy_scheme_name': 'X',
            'is_operational': True, 'latest_annual_turnover': None,
        }),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = [e['code'] for e in r.json()['data']['errors']]
    check('operational w/o turnover → turnover_required', 'turnover_required' in errs)

    # Test year history with duplicate FY → 400
    r = client.patch(url,
        data=json.dumps({
            'is_operational': True, 'latest_annual_turnover': '2000000.00',
            'year_history': [
                {'financial_year': '2023-24', 'annual_turnover': '1800000.00'},
                {'financial_year': '2023-24', 'annual_turnover': '1900000.00'},
            ],
        }),
        content_type='application/json', **_hdr(fpo_user))
    check('duplicate financial_year → 400', r.status_code == 400)

    # Valid year history
    r = client.patch(url,
        data=json.dumps({
            'year_history': [
                {'financial_year': '2022-23', 'annual_turnover': '1500000.00', 'net_profit': '150000.00'},
                {'financial_year': '2023-24', 'annual_turnover': '1800000.00', 'net_profit': '200000.00'},
                {'financial_year': '2024-25', 'annual_turnover': '2000000.00', 'net_profit': '250000.00'},
            ],
        }),
        content_type='application/json', **_hdr(fpo_user))
    check('PATCH 3 year history → 200', r.status_code == 200)
    check(f'  3 year history rows', len(r.json()['data'].get('year_history', [])) == 3)

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
