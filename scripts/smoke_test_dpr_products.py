"""Smoke test — DPR §2.3.5 Proposed Products and Services."""

import json
from django.contrib.auth.models import User
from django.test import Client
from rest_framework_simplejwt.tokens import RefreshToken

from apps.database.models import (
    DPRProject, DPRProductCategory, DPRProductType, DPRCapacityUnit,
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

    cat = DPRProductCategory.objects.filter(is_active=True).first()
    ptype = DPRProductType.objects.filter(code='finished').first()
    unit = DPRCapacityUnit.objects.filter(is_active=True).first()
    assert all([cat, ptype, unit])

    client = Client()
    failures = []

    def check(label, cond, detail=''):
        if cond: _ok(label)
        else: _bad(label, detail); failures.append(label)

    print('── §2.3.5 Products & Services smoke test ──')

    r = client.post('/api/fpo/dpr/projects/',
        data=json.dumps({'title': 'Products Test'}),
        content_type='application/json', **_hdr(fpo_user))
    project_uuid = r.json()['data']['uuid']
    url = f'/api/fpo/dpr/projects/{project_uuid}/sections/products/'

    r = client.get(url)
    check('unauth → 401', r.status_code == 401)

    r = client.get(url, **_hdr(fpo_user))
    check('GET → 200 (empty)', r.status_code == 200)
    check('  empty items', r.json()['data'].get('items') == [])

    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = r.json()['data']['errors']
    check('empty readiness → at_least_one_product',
          any(e['code'] == 'at_least_one_product' for e in errs))

    # PATCH with 2 valid items
    r = client.patch(url,
        data=json.dumps({
            'items': [
                {
                    'order': 1,
                    'name': 'Organic Basmati Rice',
                    'category': cat.id,
                    'primary_or_secondary': 'primary',
                    'product_type': ptype.id,
                    'unit_of_measurement': unit.id,
                    'annual_quantity': '5000.000',
                    'selling_unit': unit.id,
                    'selling_price_per_unit': '85.00',
                    'is_value_added': True,
                    'description': 'Premium quality organic basmati',
                },
                {
                    'order': 2,
                    'name': 'Bran Powder',
                    'category': cat.id,
                    'primary_or_secondary': 'secondary',
                    'product_type': ptype.id,
                    'unit_of_measurement': unit.id,
                    'annual_quantity': '500.000',
                    'selling_price_per_unit': '20.00',
                },
            ],
        }),
        content_type='application/json', **_hdr(fpo_user))
    check('PATCH 2 items → 200', r.status_code == 200, f'{r.content[:300]}')
    items = r.json()['data'].get('items', [])
    check(f'  2 items returned', len(items) == 2)
    basmati = next((i for i in items if i['name'] == 'Organic Basmati Rice'), None)
    check('  Basmati is primary + value-added',
          basmati is not None and basmati['primary_or_secondary'] == 'primary' and basmati['is_value_added'] is True)

    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    rr = r.json()['data']
    check('readiness → is_complete=True',
          rr['is_complete'] is True, f'errors: {rr["errors"]}')

    # Full-replace with 1 item
    r = client.patch(url,
        data=json.dumps({
            'items': [{
                'order': 1, 'name': 'Only Rice',
                'unit_of_measurement': unit.id,
                'annual_quantity': '100.000',
                'selling_price_per_unit': '50.00',
            }],
        }),
        content_type='application/json', **_hdr(fpo_user))
    items_after = r.json()['data'].get('items', [])
    check(f'  full-replace: 1 item only', len(items_after) == 1)
    check('  new name is "Only Rice"',
          bool(items_after) and items_after[0]['name'] == 'Only Rice')

    # Validation — 0 price
    r = client.patch(url,
        data=json.dumps({
            'items': [{
                'order': 1, 'name': 'Bad Item',
                'unit_of_measurement': unit.id,
                'annual_quantity': '100.000',
                'selling_price_per_unit': '0',
            }],
        }),
        content_type='application/json', **_hdr(fpo_user))
    r = client.get(f'{url}readiness/', **_hdr(fpo_user))
    errs = r.json()['data']['errors']
    check('price=0 → price_positive error',
          any(e['code'] == 'price_positive' for e in errs))

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
