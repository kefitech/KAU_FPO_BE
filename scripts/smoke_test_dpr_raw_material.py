"""
Smoke test — DPR §2.3.10 Raw Material pilot (Phase 1).

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/smoke_test_dpr_raw_material.py').read())
    smoke_test()
    "

Covers:
  1. Auth gate  (401 unauth)
  2. Create DPR project (POST /projects/)
  3. List projects (GET /projects/)
  4. Get section — auto-created with empty child lists
  5. PATCH section — write Category C fields
  6. PATCH — add materials list with 2 rows including M2M quality_parameters
  7. PATCH — add packaging + consumables + risks
  8. Full re-GET — verify all writes round-trip
  9. Full-replace behaviour — send materials with 1 row, verify old rows deleted
 10. Readiness endpoint — validators return errors + warnings
 11. Clean up
"""
import json
from django.contrib.auth.models import User
from django.test import Client
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.models.generic import MasterLookup
from apps.database.models import (
    DPRProject, DPRSectionRawMaterial, DPRRawMaterial,
    DPRRawMaterialRisk, DPRPackagingMaterial, DPRConsumable,
    DPRCapacityUnit, DPRRawMaterialSource, DPRProcurementModel,
    DPRQualityParameter, DPRQualityStandard,
)


def _token(user):
    return str(RefreshToken.for_user(user).access_token)


def _hdr(user):
    return {'HTTP_AUTHORIZATION': f'Bearer {_token(user)}'}


def _ok(l):  print(f'  \033[32m✓\033[0m {l}')
def _bad(l, d=''): print(f'  \033[31m✗\033[0m {l}\n      {d}' if d else f'  \033[31m✗\033[0m {l}')


def smoke_test():
    # Find an FPO user
    from apps.database.models.fpo import FPOUserMembership
    fpo_user = User.objects.filter(groups__name='fpo_manager', is_active=True, fpo__isnull=False).first()
    if not fpo_user:
        # fallback: any user with primary FPO relation
        fpo_user = User.objects.filter(fpo__isnull=False, is_active=True).first()
    assert fpo_user and fpo_user.fpo, 'Need an fpo_manager with a linked FPO'
    fpo = fpo_user.fpo

    # Pick master data IDs (use first available of each)
    unit = DPRCapacityUnit.objects.filter(is_active=True).first()
    source = DPRRawMaterialSource.objects.filter(is_active=True).first()
    method = DPRProcurementModel.objects.filter(is_active=True).first()
    qp1, qp2 = DPRQualityParameter.objects.filter(is_active=True)[:2]
    qs = DPRQualityStandard.objects.filter(is_active=True).first()
    commodity = MasterLookup.objects.filter(category='commodity', is_active=True).first()

    assert all([unit, source, method, qp1, qp2, qs, commodity]), 'Master data missing'
    print(f'FPO: {fpo.name} (id={fpo.id})')
    print(f'Using unit={unit.code}, source={source.code}, method={method.code}, commodity={commodity.code}')

    client = Client()
    failures = []

    def check(label, cond, detail=''):
        if cond:
            _ok(label)
        else:
            _bad(label, detail)
            failures.append(label)

    print('\n── Phase 1 smoke test — DPR §2.3.10 Raw Material pilot ──')

    # 1. Auth gate
    r = client.get('/api/fpo/dpr/projects/')
    check('unauth GET projects → 401', r.status_code == 401, f'got {r.status_code}')

    # 2. Create project
    r = client.post(
        '/api/fpo/dpr/projects/',
        data=json.dumps({'title': 'Smoke Test DPR'}),
        content_type='application/json',
        **_hdr(fpo_user),
    )
    check('POST /projects/ → 201', r.status_code == 201, f'got {r.status_code}: {r.content[:200]}')
    project_uuid = r.json().get('data', {}).get('uuid') if r.status_code == 201 else None
    check('project has uuid', bool(project_uuid))

    # 3. List projects
    r = client.get('/api/fpo/dpr/projects/', **_hdr(fpo_user))
    check('GET /projects/ → 200', r.status_code == 200)
    projects = r.json().get('data', [])
    check(f'  our project in list (count={len(projects)})', any(p['uuid'] == project_uuid for p in projects))

    # 4. Get section (auto-created empty)
    section_url = f'/api/fpo/dpr/projects/{project_uuid}/sections/raw-material/'
    r = client.get(section_url, **_hdr(fpo_user))
    check('GET section → 200 (auto-created)', r.status_code == 200, f'{r.content[:300]}')
    section = r.json().get('data', {})
    check('  empty materials list', section.get('materials') == [])
    check('  empty risks list', section.get('risks') == [])
    check('  is_complete=False', section.get('is_complete') is False)

    # 5. PATCH section-level Category C
    r = client.patch(
        section_url,
        data=json.dumps({
            'procurement_model': method.id,
            'procurement_frequency': 'weekly',
            'collection_method': 'Farm-gate pickup',
            'transportation_arrangement': 'Own vehicles',
            'loading_cost': '250.00',
        }),
        content_type='application/json',
        **_hdr(fpo_user),
    )
    check('PATCH Cat C → 200', r.status_code == 200, f'{r.content[:400]}')
    body = r.json().get('data', {})
    check('  procurement_model saved', body.get('procurement_model') == method.id)
    check('  procurement_frequency saved', body.get('procurement_frequency') == 'weekly')
    check('  loading_cost saved', str(body.get('loading_cost')) == '250.00')

    # 6. PATCH with materials list (2 rows, M2M included)
    r = client.patch(
        section_url,
        data=json.dumps({
            'materials': [
                {
                    'order': 1,
                    'name': 'Rice Paddy',
                    'commodity': commodity.id,
                    'unit_of_purchase': unit.id,
                    'estimated_annual_requirement': '500.000',
                    'primary_source': source.id,
                    'procurement_method': method.id,
                    'estimated_qty_available_annual': '600.000',
                    'num_supplying_farmers': 25,
                    'num_supplying_villages': 5,
                    'available_months': ['jan', 'feb', 'mar'],
                    'available_throughout_year': False,
                    'peak_harvest_season': 'January to March',
                    'off_season_strategy': 'Buy from wholesale market',
                    'quality_standards_applicable': True,
                    'quality_standard': qs.id,
                    'quality_parameters': [qp1.id, qp2.id],
                    'current_purchase_price': '35.00',
                    'price_estimation_basis': 'market_survey',
                    'price_varies_seasonally': False,
                },
                {
                    'order': 2,
                    'name': 'Wheat',
                    'commodity': commodity.id,
                    'unit_of_purchase': unit.id,
                    'estimated_annual_requirement': '200.000',
                    'primary_source': source.id,
                    'procurement_method': method.id,
                    'estimated_qty_available_annual': '250.000',
                    'num_supplying_farmers': 10,
                    'num_supplying_villages': 3,
                    'available_months': ['nov', 'dec'],
                    'available_throughout_year': False,
                    'peak_harvest_season': 'Nov-Dec',
                    'off_season_strategy': 'Contract farming',
                    'quality_standards_applicable': False,
                    'current_purchase_price': '28.00',
                    'price_estimation_basis': 'recent_purchase',
                    'price_varies_seasonally': True,
                    'price_variation_range': 'moderate',
                    'peak_price_season': 'Feb-Apr',
                    'lowest_price_season': 'Nov-Dec',
                },
            ],
        }),
        content_type='application/json',
        **_hdr(fpo_user),
    )
    check('PATCH materials [2 rows] → 200', r.status_code == 200, f'{r.content[:500]}')
    materials = r.json().get('data', {}).get('materials', [])
    check(f'  2 materials returned (got {len(materials)})', len(materials) == 2)
    if materials:
        rice = next((m for m in materials if m['name'] == 'Rice Paddy'), None)
        check('  Rice Paddy row exists', rice is not None)
        if rice:
            check('  M2M quality_parameters (2 items)', len(rice.get('quality_parameters', [])) == 2)
            check('  available_months preserved', rice.get('available_months') == ['jan', 'feb', 'mar'])

    # 7. PATCH with packaging + consumables + risks
    r = client.patch(
        section_url,
        data=json.dumps({
            'packaging_materials': [
                {'order': 1, 'material_name': 'PP Bags', 'purpose': 'Primary packaging',
                 'unit': unit.id, 'estimated_annual_requirement': '10000.000', 'unit_cost': '2.50'},
            ],
            'consumables': [
                {'order': 1, 'name': 'Cleaning Chemicals', 'purpose': 'Sanitation',
                 'estimated_annual_requirement': '50.000', 'unit': unit.id, 'unit_cost': '150.00'},
            ],
            'risks': [
                {'risk_type': 'price_fluctuation', 'mitigation_strategy': 'Long-term contracts'},
                {'risk_type': 'climate_risk', 'mitigation_strategy': 'Diversify sourcing'},
            ],
        }),
        content_type='application/json',
        **_hdr(fpo_user),
    )
    check('PATCH packaging+consumables+risks → 200', r.status_code == 200, f'{r.content[:400]}')
    d = r.json().get('data', {})
    check(f'  1 packaging (got {len(d.get("packaging_materials", []))})', len(d.get('packaging_materials', [])) == 1)
    check(f'  1 consumable (got {len(d.get("consumables", []))})', len(d.get('consumables', [])) == 1)
    check(f'  2 risks (got {len(d.get("risks", []))})', len(d.get('risks', [])) == 2)
    # Absent keys → untouched
    check('  materials preserved (not in patch)', len(d.get('materials', [])) == 2)

    # 8. Full-replace behavior — send 1 material, other row should disappear
    r = client.patch(
        section_url,
        data=json.dumps({
            'materials': [
                {'order': 1, 'name': 'Only Rice', 'unit_of_purchase': unit.id,
                 'primary_source': source.id, 'procurement_method': method.id,
                 'estimated_annual_requirement': '100.000',
                 'estimated_qty_available_annual': '120.000',
                 'num_supplying_farmers': 5, 'num_supplying_villages': 2,
                 'available_months': ['jan'], 'available_throughout_year': False,
                 'peak_harvest_season': 'Jan', 'off_season_strategy': 'Buy elsewhere',
                 'current_purchase_price': '40.00', 'price_estimation_basis': 'other',
                 'price_estimation_basis_other': 'Direct farmer quote'},
            ],
        }),
        content_type='application/json',
        **_hdr(fpo_user),
    )
    check('PATCH full-replace materials → 200', r.status_code == 200, f'{r.content[:400]}')
    materials_after = r.json().get('data', {}).get('materials', [])
    check(f'  full-replace: 1 material only (got {len(materials_after)})', len(materials_after) == 1)
    check('  new name is "Only Rice"',
          bool(materials_after) and materials_after[0]['name'] == 'Only Rice')

    # 9. Readiness — should be complete now (all required fields present)
    r = client.get(f'{section_url}readiness/', **_hdr(fpo_user))
    check('GET readiness → 200', r.status_code == 200, f'{r.content[:300]}')
    readiness = r.json().get('data', {})
    errors = readiness.get('errors', [])
    warnings = readiness.get('warnings', [])
    check(f'  is_complete=True (errors={len(errors)})',
          readiness.get('is_complete') is True,
          f'errors: {[e["code"] for e in errors]}')
    print(f'    (warnings: {[w["code"] for w in warnings]})')

    # 10. Ownership isolation — other FPO user cannot see this project
    other = User.objects.filter(
        groups__name='fpo_manager', is_active=True, fpo__isnull=False,
    ).exclude(pk=fpo_user.pk).first()
    if other:
        r = client.get(f'/api/fpo/dpr/projects/{project_uuid}/', **_hdr(other))
        check('other FPO user → 404 on our project', r.status_code == 404, f'got {r.status_code}')
    else:
        print('  (skipped ownership isolation — only one FPO user in DB)')

    # 11. Cleanup — soft-delete project
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
