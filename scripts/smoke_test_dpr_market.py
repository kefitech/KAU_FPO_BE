"""
Smoke test — DPR §2.3.11 Market Assessment.

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/smoke_test_dpr_market.py').read())
    smoke_test()
    "

Covers:
  1. Auth gate (401 unauth)
  2. Section auto-create on first GET
  3. Section-level fields PATCH (Cat B demand, Cat E pricing, Cat G branding)
  4. Section-level M2M promotional_activities round-trip
  5. Products PATCH (Cat A + H) with M2M customer_categories
  6. Buyers PATCH (Cat C)
  7. Channel selections PATCH (Cat D) with FK to master
  8. Competitors PATCH (Cat F)
  9. Risks PATCH (Cat I)
 10. Full-replace behavior — send products with 1 row, verify old rows deleted
 11. Absent-key preservation — send only buyers, verify products untouched
 12. Readiness endpoint returns is_complete=True after all mandatory fields set
 13. Ownership isolation (other FPO user → 404)
 14. Cleanup
"""

import json
from django.contrib.auth.models import User
from django.test import Client
from rest_framework_simplejwt.tokens import RefreshToken

from apps.database.models import (
    DPRProject, DPRSectionMarket, DPRMarketingProduct,
    DPRMarketingBuyer, DPRMarketingChannelSelection,
    DPRMarketingCompetitor, DPRMarketingRisk,
    DPRProductCategory, DPRProductType, DPRIntendedMarket,
    DPRCustomerCategory, DPRBuyerType, DPRMarketingChannel,
    DPRPromotionalActivity, DPRCapacityUnit,
)


def _token(user):
    return str(RefreshToken.for_user(user).access_token)


def _hdr(user):
    return {'HTTP_AUTHORIZATION': f'Bearer {_token(user)}'}


def _ok(l):  print(f'  \033[32m✓\033[0m {l}')
def _bad(l, d=''): print(f'  \033[31m✗\033[0m {l}\n      {d}' if d else f'  \033[31m✗\033[0m {l}')


def smoke_test():
    fpo_user = User.objects.filter(
        groups__name='fpo_manager', is_active=True, fpo__isnull=False,
    ).first()
    assert fpo_user and fpo_user.fpo, 'Need an fpo_manager with linked FPO'
    fpo = fpo_user.fpo

    # Master data picks
    prod_cat = DPRProductCategory.objects.filter(is_active=True).first()
    prod_type = DPRProductType.objects.filter(is_active=True).first()
    intended_mkt = DPRIntendedMarket.objects.filter(code='national').first() or DPRIntendedMarket.objects.first()
    cust_cats = list(DPRCustomerCategory.objects.filter(is_active=True)[:2])
    buyer_cat = DPRBuyerType.objects.filter(is_active=True).first()
    ch1 = DPRMarketingChannel.objects.filter(is_active=True).first()
    ch2 = DPRMarketingChannel.objects.filter(is_active=True)[1]
    promo_acts = list(DPRPromotionalActivity.objects.filter(is_active=True)[:2])
    unit = DPRCapacityUnit.objects.filter(is_active=True).first()

    assert all([prod_cat, prod_type, intended_mkt, cust_cats, buyer_cat, ch1, ch2, promo_acts, unit]), 'Master data missing'
    print(f'FPO: {fpo.name}')
    print(f'Master picks — cat={prod_cat.code}, type={prod_type.code}, market={intended_mkt.code}, channels={ch1.code}+{ch2.code}, unit={unit.code}')

    client = Client()
    failures = []

    def check(label, cond, detail=''):
        if cond:
            _ok(label)
        else:
            _bad(label, detail)
            failures.append(label)

    print('\n── §2.3.11 Market Assessment smoke test ──')

    # 0. Setup — create a fresh project
    r = client.post(
        '/api/fpo/dpr/projects/',
        data=json.dumps({'title': 'Market Test DPR'}),
        content_type='application/json',
        **_hdr(fpo_user),
    )
    project_uuid = r.json()['data']['uuid']
    section_url = f'/api/fpo/dpr/projects/{project_uuid}/sections/market/'

    # 1. Auth gate
    r = client.get(section_url)
    check('unauth GET section → 401', r.status_code == 401, f'got {r.status_code}')

    # 2. Section auto-create
    r = client.get(section_url, **_hdr(fpo_user))
    check('GET section → 200 (auto-created)', r.status_code == 200, f'{r.content[:300]}')
    body = r.json().get('data', {})
    check('  empty products list', body.get('products') == [])
    check('  empty channel_selections list', body.get('channel_selections') == [])
    check('  is_complete=False', body.get('is_complete') is False)

    # 3. PATCH Cat B (demand) + Cat E (pricing) + Cat G (branding)
    r = client.patch(
        section_url,
        data=json.dumps({
            'demand_exists': 'yes',
            'estimated_annual_demand': '10000.000',
            'demand_basis': 'market_survey',
            'expected_demand_growth_pct': '8.50',
            'has_existing_buyers': True,
            'pricing_basis': 'cost_plus',
            'expected_annual_price_increase_pct': '5.00',
            'credit_sales_pct': '40.00',
            'cash_sales_pct': '60.00',
            'has_competitors': 'yes',
            'is_branded': True,
            'brand_name': 'Kerala Green',
            'promotional_activities': [pa.id for pa in promo_acts],
            'website': 'https://example.com',
        }),
        content_type='application/json',
        **_hdr(fpo_user),
    )
    check('PATCH Cat B/E/G → 200', r.status_code == 200, f'{r.content[:400]}')
    d = r.json().get('data', {})
    check('  demand_exists=yes saved', d.get('demand_exists') == 'yes')
    check('  demand_basis saved', d.get('demand_basis') == 'market_survey')
    check('  pricing_basis saved', d.get('pricing_basis') == 'cost_plus')
    check('  is_branded=True saved', d.get('is_branded') is True)
    check('  brand_name saved', d.get('brand_name') == 'Kerala Green')
    check('  M2M promotional_activities (2 items)', len(d.get('promotional_activities', [])) == 2)

    # 4. PATCH products with 2 rows including M2M customer_categories
    r = client.patch(
        section_url,
        data=json.dumps({
            'products': [
                {
                    'order': 1,
                    'name': 'Organic Rice',
                    'product_category': prod_cat.id,
                    'product_type': prod_type.id,
                    'intended_market': intended_mkt.id,
                    'geographic_market': 'Kerala + Tamil Nadu',
                    'customer_categories': [c.id for c in cust_cats],
                    'proposed_selling_price': '50.00',
                    'unit_of_sale': unit.id,
                    'year1_qty': '1000.000',
                    'year2_qty': '1200.000',
                    'year3_qty': '1500.000',
                    'domestic_sales_pct': '80.00',
                    'export_sales_pct': '20.00',
                },
                {
                    'order': 2,
                    'name': 'Rice Bran (by-product)',
                    'product_category': prod_cat.id,
                    'product_type': prod_type.id,
                    'intended_market': intended_mkt.id,
                    'geographic_market': 'Local mills',
                    'customer_categories': [cust_cats[0].id],
                    'proposed_selling_price': '15.00',
                    'unit_of_sale': unit.id,
                    'year1_qty': '200.000',
                    'domestic_sales_pct': '100.00',
                },
            ],
        }),
        content_type='application/json',
        **_hdr(fpo_user),
    )
    check('PATCH products [2 rows] → 200', r.status_code == 200, f'{r.content[:400]}')
    products = r.json().get('data', {}).get('products', [])
    check(f'  2 products returned (got {len(products)})', len(products) == 2)
    rice = next((p for p in products if p['name'] == 'Organic Rice'), None)
    check('  Rice row has M2M customer_categories (2)',
          rice is not None and len(rice.get('customer_categories', [])) == 2)
    check('  year1_qty saved',
          rice is not None and str(rice.get('year1_qty')) == '1000.000')

    # 5. PATCH channels (Cat D)
    r = client.patch(
        section_url,
        data=json.dumps({
            'channel_selections': [
                {'channel': ch1.id, 'expected_share_pct': '60.00',
                 'existing_arrangement': 'Direct to wholesalers'},
                {'channel': ch2.id, 'expected_share_pct': '40.00'},
            ],
        }),
        content_type='application/json',
        **_hdr(fpo_user),
    )
    check('PATCH channel_selections → 200', r.status_code == 200, f'{r.content[:400]}')
    d = r.json().get('data', {})
    check(f'  2 channels saved (got {len(d.get("channel_selections", []))})',
          len(d.get('channel_selections', [])) == 2)
    check('  products preserved (not in patch)', len(d.get('products', [])) == 2)

    # 6. PATCH buyers + competitors + risks in one call
    r = client.patch(
        section_url,
        data=json.dumps({
            'buyers': [
                {'buyer_name': 'BigMart', 'buyer_category': buyer_cat.id,
                 'location': 'Kochi', 'purchase_frequency': 'weekly',
                 'num_buyers': 3, 'credit_period_days': 30},
            ],
            'competitors': [
                {'name': 'Rival FPO Co', 'competitor_type': 'regional',
                 'competitive_advantage': 'Organic certification + traceability'},
            ],
            'risks': [
                {'risk_type': 'price_fluctuation',
                 'mitigation_strategy': 'Forward contracts with 2 major buyers'},
                {'risk_type': 'quality_issues',
                 'mitigation_strategy': 'Third-party lab testing per batch'},
            ],
        }),
        content_type='application/json',
        **_hdr(fpo_user),
    )
    check('PATCH buyers+competitors+risks → 200', r.status_code == 200, f'{r.content[:400]}')
    d = r.json().get('data', {})
    check(f'  1 buyer (got {len(d.get("buyers", []))})', len(d.get('buyers', [])) == 1)
    check(f'  1 competitor (got {len(d.get("competitors", []))})', len(d.get('competitors', [])) == 1)
    check(f'  2 risks (got {len(d.get("risks", []))})', len(d.get('risks', [])) == 2)

    # 7. Full-replace behavior — send 1 product, verify other row deleted
    r = client.patch(
        section_url,
        data=json.dumps({
            'products': [{
                'order': 1, 'name': 'Only Rice',
                'product_category': prod_cat.id, 'product_type': prod_type.id,
                'intended_market': intended_mkt.id, 'geographic_market': 'X',
                'customer_categories': [cust_cats[0].id],
                'proposed_selling_price': '55.00', 'unit_of_sale': unit.id,
                'year1_qty': '500.000',
            }],
        }),
        content_type='application/json',
        **_hdr(fpo_user),
    )
    products_after = r.json().get('data', {}).get('products', [])
    check(f'  full-replace: 1 product only (got {len(products_after)})', len(products_after) == 1)
    check('  new name is "Only Rice"',
          bool(products_after) and products_after[0]['name'] == 'Only Rice')

    # 8. Readiness — all mandatory fields present, should be complete
    r = client.get(f'{section_url}readiness/', **_hdr(fpo_user))
    check('GET readiness → 200', r.status_code == 200)
    readiness = r.json().get('data', {})
    errors = readiness.get('errors', [])
    warnings = readiness.get('warnings', [])
    check(f'  is_complete=True (errors={len(errors)})',
          readiness.get('is_complete') is True,
          f'errors: {[e["code"] for e in errors]}')
    print(f'    (warnings: {[w["code"] for w in warnings]})')

    # 9. Ownership isolation
    other = User.objects.filter(
        groups__name='fpo_manager', is_active=True, fpo__isnull=False,
    ).exclude(pk=fpo_user.pk).first()
    if other:
        r = client.get(section_url, **_hdr(other))
        check('other FPO user → 404 on our project section', r.status_code == 404, f'got {r.status_code}')
    else:
        print('  (skipped isolation check — only one FPO user in DB)')

    # 10. Cleanup
    DPRProject.objects.filter(uuid=project_uuid).delete()
    check('cleanup — project deleted', not DPRProject.objects.filter(uuid=project_uuid).exists())

    print()
    if failures:
        print(f'\033[31m{len(failures)} failure(s):\033[0m')
        for f in failures:
            print(f'  - {f}')
        return False
    print('\033[32m✓ All checks passed.\033[0m')
    return True
