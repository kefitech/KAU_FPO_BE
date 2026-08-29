"""
Smoke test — DPR master data API (Phase 0.4 verification).

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/smoke_test_dpr_master.py').read())
    smoke_test()
    "

Covers:
  1. FPO read auth-gate (401 without auth)
  2. FPO read happy path (list rows, sorted)
  3. Component list (grouped-order override)
  4. Admin write (create, invalidates cache)
  5. Cache invalidation verified (read after write returns fresh count)
  6. i18n via X-Language: ml header
  7. Admin auth-gate (FPO user hitting admin endpoint = 403)
  8. Cleanup — delete the row we created
"""
import json
from django.test import Client
from django.contrib.auth.models import User
from rest_framework_simplejwt.tokens import RefreshToken
1
from apps.database.models import DPRFuelType, DPRComponent


def _token(user):
    return str(RefreshToken.for_user(user).access_token)


def _hdr(user, lang=None):
    h = {'HTTP_AUTHORIZATION': f'Bearer {_token(user)}'}
    if lang:
        h['HTTP_X_LANGUAGE'] = lang
    return h


def _passed(label):
    print(f'  \033[32m✓\033[0m {label}')


def _failed(label, detail=''):
    print(f'  \033[31m✗\033[0m {label}')
    if detail:
        print(f'      {detail}')


def smoke_test():
    fpo = User.objects.filter(groups__name='fpo_manager', is_active=True).first()
    admin = User.objects.filter(groups__name__in=['super_admin', 'sub_admin'], is_active=True).first()
    assert fpo and admin, 'Need at least one fpo_manager and one super/sub admin user'

    client = Client()
    failures = []

    def check(label, cond, detail=''):
        if cond:
            _passed(label)
        else:
            _failed(label, detail)
            failures.append(label)

    print('\n── Phase 0.4 smoke test ──')

    # 1. Auth gate — no token → 401
    r = client.get('/api/fpo/dpr/master/fuel-types/')
    check('unauth FPO read → 401', r.status_code == 401, f'got {r.status_code}')

    # 2. FPO read happy path
    r = client.get('/api/fpo/dpr/master/fuel-types/', **_hdr(fpo))
    body = r.json() if r.status_code == 200 else {}
    fuel_rows = body.get('data', [])
    check('FPO GET fuel-types → 200', r.status_code == 200, f'got {r.status_code}: {r.content[:200]}')
    check(f'  rows returned ({len(fuel_rows)})', len(fuel_rows) == 10, f'expected 10, got {len(fuel_rows)}')
    check('  row shape has code + label', bool(fuel_rows) and 'code' in fuel_rows[0] and 'label' in fuel_rows[0])
    # ordering
    orders = [r['order'] for r in fuel_rows]
    check('  sorted by (order, code)', orders == sorted(orders))

    # 3. Component grouped read
    r = client.get('/api/fpo/dpr/master/components/', **_hdr(fpo))
    body = r.json() if r.status_code == 200 else {}
    comp_rows = body.get('data', [])
    check(f'FPO GET components → 200 (40 rows)', r.status_code == 200 and len(comp_rows) == 40,
          f'status {r.status_code}, count {len(comp_rows)}')
    # first item should have `group` field
    check('  component row has group field', bool(comp_rows) and 'group' in comp_rows[0])

    # 4. Admin write — create a fuel type
    payload = {
        'code': '_smoke_test_fuel',
        'label_en': 'Smoke Test Fuel',
        'label_ml': 'സ്മോക്ക് ടെസ്റ്റ്',
        'order': 999,
        'is_active': True,
    }
    r = client.post(
        '/api/admin/dpr/master/fuel-types/',
        data=json.dumps(payload),
        content_type='application/json',
        **_hdr(admin),
    )
    check(f'admin POST fuel-type → 201', r.status_code == 201, f'got {r.status_code}: {r.content[:300]}')

    created_id = None
    if r.status_code == 201:
        created_id = r.json().get('data', {}).get('id')

    # 5. Cache invalidation — read after write returns 11 rows
    r = client.get('/api/fpo/dpr/master/fuel-types/', **_hdr(fpo))
    fresh = r.json().get('data', []) if r.status_code == 200 else []
    check(f'FPO re-GET returns fresh count (11)', len(fresh) == 11,
          f'got {len(fresh)} — cache not invalidated?')

    # 6. i18n — X-Language: ml → label = label_ml
    r = client.get('/api/fpo/dpr/master/fuel-types/', **_hdr(fpo, lang='ml'))
    ml_rows = r.json().get('data', []) if r.status_code == 200 else []
    smoke_ml = next((row for row in ml_rows if row['code'] == '_smoke_test_fuel'), None)
    check('X-Language: ml → label is Malayalam',
          smoke_ml is not None and smoke_ml['label'] == 'സ്മോക്ക് ടെസ്റ്റ്',
          f'got {smoke_ml}')

    # 7. Admin auth gate — FPO user hitting admin endpoint
    r = client.get('/api/admin/dpr/master/fuel-types/', **_hdr(fpo))
    check('FPO hitting admin endpoint → 403', r.status_code == 403, f'got {r.status_code}')

    # 8. Cleanup
    if created_id:
        r = client.delete(f'/api/admin/dpr/master/fuel-types/{created_id}/', **_hdr(admin))
        check('admin DELETE → 200', r.status_code == 200, f'got {r.status_code}')
        # Confirm removed
        r = client.get('/api/fpo/dpr/master/fuel-types/', **_hdr(fpo))
        final = r.json().get('data', []) if r.status_code == 200 else []
        check(f'FPO re-GET after delete → 10 rows again', len(final) == 10, f'got {len(final)}')

    print()
    if failures:
        print(f'\033[31m{len(failures)} failure(s):\033[0m')
        for f in failures:
            print(f'  - {f}')
    else:
        print('\033[32m✓ All checks passed.\033[0m')
    return not failures
