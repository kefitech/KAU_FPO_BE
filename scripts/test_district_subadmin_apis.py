"""
End-to-end API test for KAU suggestion #1 district-scoped sub-admin build.

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/test_district_subadmin_apis.py').read())
    run_all()
    "

Uses DRF's APIRequestFactory + force_authenticate — no live HTTP server needed.
Creates a controlled set of throwaway users and rolls everything back at the end.
"""

import io
from datetime import date, timedelta

from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType
from rest_framework.test import APIRequestFactory, force_authenticate

# Result collector — printed at the end.
_results = []


def _pass(label, expected, actual):
    ok = expected == actual
    _results.append((label, ok, f'expected {expected!r}, got {actual!r}'))
    icon = '✓' if ok else '✗'
    print(f'  {icon} {label}: {actual}')


def _assert(label, condition, detail=''):
    _results.append((label, bool(condition), detail))
    icon = '✓' if condition else '✗'
    suffix = f'  ({detail})' if detail else ''
    print(f'  {icon} {label}{suffix}')


def run_all():
    factory = APIRequestFactory()

    # ─── setup: users + groups + permissions ─────────────────────────────
    sa_g, _  = Group.objects.get_or_create(name='super_admin')
    sub_g, _ = Group.objects.get_or_create(name='sub_admin')
    ct = ContentType.objects.get(app_label='accounts', model='subadmin')

    def _mk(email, groups=(), perms=()):
        u, _ = User.objects.get_or_create(email=email, defaults={'username': email})
        for g in groups:
            u.groups.add(g)
        for p in perms:
            u.user_permissions.add(Permission.objects.get(codename=p, content_type=ct))
        return u

    print('\n' + '=' * 70)
    print('Setting up test users…')
    print('=' * 70)
    # Purge leftovers from any previous run — test is idempotent.
    _EMAILS_TO_CLEAN = [
        'test.sa@kau.in', 'test.sub.tsr@kau.in',
        'bulk1@kau.in', 'bulk2@kau.in', 'bulk4@kau.in', 'bulk5@kau.in', 'bad_email',
        'sub.dpr@kau.in', 'sub.nodpr@kau.in',
        'sub.schemes@kau.in', 'sub.other@kau.in',
    ]
    User.objects.filter(email__in=_EMAILS_TO_CLEAN).delete()
    print(f'  purged {len(_EMAILS_TO_CLEAN)} potential leftover accounts')

    super_admin = _mk('test.sa@kau.in', [sa_g])
    print('  super_admin created')

    # -----------------------------------------------------------------
    # 1. Sub-admin config API
    # -----------------------------------------------------------------
    print('\n--- 1. Sub-Admin Config API -----------------------------------')
    from apps.accounts.api.admin.subadmin_config import SubAdminConfigView

    r = factory.get('/api/admin/sub-admin-config/')
    force_authenticate(r, user=super_admin)
    resp = SubAdminConfigView.as_view()(r)
    _pass('GET config status', 200, resp.status_code)
    _pass('global_cap default', 30, resp.data['data']['global_cap'])

    r = factory.patch('/api/admin/sub-admin-config/', {
        'global_cap': 40, 'district_caps': {'TSR': 45, 'WYD': 15},
    }, format='json')
    force_authenticate(r, user=super_admin)
    resp = SubAdminConfigView.as_view()(r)
    _pass('PATCH config status', 200, resp.status_code)
    _pass('override TSR', 45, resp.data['data']['district_caps'].get('TSR'))

    from apps.core.services.subadmin_district import get_effective_cap
    _pass('effective cap TSR', 45, get_effective_cap('TSR'))
    _pass('effective cap PKD (fallback)', 40, get_effective_cap('PKD'))

    # -----------------------------------------------------------------
    # 2. Sub-admin create with district
    # -----------------------------------------------------------------
    print('\n--- 2. Sub-Admin Create (with district) -----------------------')
    from apps.accounts.api.sub_admins import SubAdminViewSet

    r = factory.post('/api/admin/sub-admins/', {
        'email': 'test.sub.tsr@kau.in', 'first_name': 'TSR', 'last_name': 'Admin',
        'phone': '9876500001', 'district': 'TSR',
        'permissions': ['can_approve_fpo', 'can_manage_schemes'],
    }, format='json')
    force_authenticate(r, user=super_admin)
    resp = SubAdminViewSet.as_view({'post': 'create'})(r)
    _pass('CREATE status', 201, resp.status_code)
    _pass('CREATE district', 'TSR', resp.data['data']['district'])
    _pass('CREATE permissions count', 2, len(resp.data['data']['permissions']))
    sub_tsr = User.objects.get(email='test.sub.tsr@kau.in')
    _assert('CREATE first-transfer audit row written',
            sub_tsr.district_transfers.count() == 1,
            f'transfer_count={sub_tsr.district_transfers.count()}')

    # -----------------------------------------------------------------
    # 3. Transfer district
    # -----------------------------------------------------------------
    print('\n--- 3. Transfer District --------------------------------------')
    r = factory.post(f'/api/admin/sub-admins/{sub_tsr.id}/transfer-district/', {
        'to_district': 'PKD', 'reason': 'reorg pilot',
    }, format='json')
    force_authenticate(r, user=super_admin)
    resp = SubAdminViewSet.as_view({'post': 'transfer_district'})(r, pk=sub_tsr.id)
    _pass('TRANSFER status', 200, resp.status_code)
    sub_tsr.refresh_from_db()
    _pass('TRANSFER district now', 'PKD', sub_tsr.district_assignment.district)
    _pass('TRANSFER audit row count', 2, sub_tsr.district_transfers.count())

    # Same-district transfer must fail
    r = factory.post(f'/api/admin/sub-admins/{sub_tsr.id}/transfer-district/', {
        'to_district': 'PKD',
    }, format='json')
    force_authenticate(r, user=super_admin)
    resp = SubAdminViewSet.as_view({'post': 'transfer_district'})(r, pk=sub_tsr.id)
    _pass('TRANSFER same district rejected', 400, resp.status_code)

    # -----------------------------------------------------------------
    # 4. District transfers history
    # -----------------------------------------------------------------
    print('\n--- 4. District Transfers History -----------------------------')
    r = factory.get(f'/api/admin/sub-admins/{sub_tsr.id}/district-transfers/')
    force_authenticate(r, user=super_admin)
    resp = SubAdminViewSet.as_view({'get': 'district_transfers'})(r, pk=sub_tsr.id)
    _pass('HISTORY status', 200, resp.status_code)
    _pass('HISTORY row count', 2, len(resp.data['data']))
    _pass('HISTORY latest is transfer', 'TSR', resp.data['data'][0]['from_district'])
    _pass('HISTORY latest reason', 'reorg pilot', resp.data['data'][0]['reason'])

    # -----------------------------------------------------------------
    # 5. District cap status
    # -----------------------------------------------------------------
    print('\n--- 5. District Cap Status ------------------------------------')
    r = factory.get('/api/admin/sub-admins/district-cap-status/')
    force_authenticate(r, user=super_admin)
    resp = SubAdminViewSet.as_view({'get': 'district_cap_status'})(r)
    _pass('CAP STATUS status', 200, resp.status_code)
    _pass('CAP STATUS PKD count ≥ 1', True, resp.data['data']['PKD']['count'] >= 1)
    _pass('CAP STATUS TSR cap 45',    45,   resp.data['data']['TSR']['cap'])
    _pass('CAP STATUS PKD cap 40',    40,   resp.data['data']['PKD']['cap'])

    # -----------------------------------------------------------------
    # 6. Bulk invite template download
    # -----------------------------------------------------------------
    print('\n--- 6. Bulk Invite Template -----------------------------------')
    r = factory.get('/api/admin/sub-admins/bulk-invite-template/')
    force_authenticate(r, user=super_admin)
    resp = SubAdminViewSet.as_view({'get': 'bulk_invite_template'})(r)
    _pass('TEMPLATE status', 200, resp.status_code)
    _pass('TEMPLATE content-type',
          'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          resp['Content-Type'])
    _assert('TEMPLATE has non-zero body',
            len(resp.content) > 500,
            f'{len(resp.content)} bytes')

    # -----------------------------------------------------------------
    # 7. Bulk invite (xlsx upload, in-memory)
    # -----------------------------------------------------------------
    print('\n--- 7. Bulk Invite ---------------------------------------------')
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(['first_name', 'last_name', 'email', 'phone', 'district', 'notification_channel'])
    ws.append(['B1', 'Test', 'bulk1@kau.in', '9876500002', 'IDK', 'email'])
    ws.append(['B2', 'Test', 'bulk2@kau.in', '9876500003', 'IDK', 'email'])
    ws.append(['B3', 'Test', 'bad_email',    '9876500004', 'IDK', 'email'])   # invalid email
    ws.append(['B4', 'Test', 'bulk4@kau.in', '9876500005', 'XXX', 'email'])   # bad district

    buf = io.BytesIO()
    wb.save(buf); buf.seek(0)

    from django.core.files.uploadedfile import SimpleUploadedFile
    upload = SimpleUploadedFile(
        'sub_admins.xlsx', buf.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    r = factory.post('/api/admin/sub-admins/bulk-invite/', {'file': upload}, format='multipart')
    force_authenticate(r, user=super_admin)
    resp = SubAdminViewSet.as_view({'post': 'bulk_invite'})(r)
    _pass('BULK status', 200, resp.status_code)
    _pass('BULK success', 2, resp.data['data']['success'])
    _pass('BULK failed', 2, resp.data['data']['failed'])
    _assert('BULK IDK count now 2',
            User.objects.filter(district_assignment__district='IDK').count() == 2,
            f"actual={User.objects.filter(district_assignment__district='IDK').count()}")

    # -----------------------------------------------------------------
    # 8. FPO scoping via scope_fpo_queryset
    # -----------------------------------------------------------------
    print('\n--- 8. FPO Scoping ---------------------------------------------')
    from apps.database.models import FPO
    from apps.core.permissions.fpo_scope import scope_fpo_queryset

    all_count = FPO.objects.filter(is_deleted=False).count()
    super_scoped = scope_fpo_queryset(FPO.objects.filter(is_deleted=False), super_admin).count()
    _pass('super sees all', all_count, super_scoped)

    # sub in PKD (post-transfer) sees only PKD FPOs
    pkd_count = FPO.objects.filter(district='PKD', is_deleted=False).count()
    sub_scoped = scope_fpo_queryset(FPO.objects.filter(is_deleted=False), sub_tsr).count()
    _pass('sub sees only PKD', pkd_count, sub_scoped)

    # -----------------------------------------------------------------
    # 9. Permission gate — DPR
    # -----------------------------------------------------------------
    print('\n--- 9. DPR Gate ------------------------------------------------')
    from apps.core.permissions.rbac import IsDPRAdmin

    sub_dpr = _mk('sub.dpr@kau.in', [sub_g], ['can_use_dpr_facilities'])
    sub_no_dpr = _mk('sub.nodpr@kau.in', [sub_g])

    class FakeView: pass
    checker = IsDPRAdmin()
    fake_req = factory.get('/'); force_authenticate(fake_req, user=super_admin)
    fake_req.user = super_admin  # DRF request wrapping
    _pass('DPR gate — super_admin', True, checker.has_permission(fake_req, FakeView()))
    fake_req.user = sub_dpr
    _pass('DPR gate — sub with perm', True, checker.has_permission(fake_req, FakeView()))
    fake_req.user = sub_no_dpr
    _pass('DPR gate — sub without perm', False, checker.has_permission(fake_req, FakeView()))

    # -----------------------------------------------------------------
    # 10. CBBO / Govt approve gate
    # -----------------------------------------------------------------
    print('\n--- 10. CBBO/Govt Approve Gate --------------------------------')
    from apps.core.permissions.rbac import require_sub_admin_perm
    _pass('CBBO gate — super',        True,  require_sub_admin_perm(super_admin, 'can_approve_cbbo_logins'))
    _pass('CBBO gate — sub no perm',  False, require_sub_admin_perm(sub_no_dpr,  'can_approve_cbbo_logins'))
    _pass('Govt gate — super',        True,  require_sub_admin_perm(super_admin, 'can_approve_govt_official_logins'))
    _pass('Govt gate — sub no perm',  False, require_sub_admin_perm(sub_no_dpr,  'can_approve_govt_official_logins'))

    # -----------------------------------------------------------------
    # 11. Scheme ownership rules
    # -----------------------------------------------------------------
    print('\n--- 11. Scheme Ownership Rules ---------------------------------')
    from apps.database.models import Scheme
    from apps.accounts.api.admin.schemes import SchemeListView, SchemeDetailView

    sub_schemes = _mk('sub.schemes@kau.in', [sub_g], ['can_manage_schemes'])

    # No perm → 403 create
    r = factory.post('/', {
        'name_en': 'Test A', 'administering_body': 'KAU', 'category': 'credit',
        'eligibility': 'FPOs', 'benefit_details': 'X', 'application_process': 'Y',
    }, format='json')
    force_authenticate(r, user=sub_no_dpr)
    resp = SchemeListView.as_view()(r)
    _pass('SCHEME create — no perm', 403, resp.status_code)

    # With perm → 201, created_by populated
    r = factory.post('/', {
        'name_en': 'Test Scheme B', 'administering_body': 'KAU', 'category': 'credit',
        'eligibility': 'FPOs', 'benefit_details': 'X', 'application_process': 'Y',
        'deadline': (date.today() - timedelta(days=10)).isoformat(),
    }, format='json')
    force_authenticate(r, user=sub_schemes)
    resp = SchemeListView.as_view()(r)
    _pass('SCHEME create — with perm', 201, resp.status_code)
    scheme_id = resp.data['data']['id']

    # Another sub tries to edit → 403
    another = _mk('sub.other@kau.in', [sub_g], ['can_manage_schemes'])
    r = factory.patch(f'/{scheme_id}/', {'name_en': 'Hijack'}, format='json')
    force_authenticate(r, user=another)
    resp = SchemeDetailView.as_view()(r, pk=scheme_id)
    _pass('SCHEME edit — other sub blocked', 403, resp.status_code)

    # Owner can edit
    r = factory.patch(f'/{scheme_id}/', {'name_en': 'Owner Edit'}, format='json')
    force_authenticate(r, user=sub_schemes)
    resp = SchemeDetailView.as_view()(r, pk=scheme_id)
    _pass('SCHEME edit — owner allowed', 200, resp.status_code)

    # Super admin can edit anyone's
    r = factory.patch(f'/{scheme_id}/', {'name_en': 'Super Edit'}, format='json')
    force_authenticate(r, user=super_admin)
    resp = SchemeDetailView.as_view()(r, pk=scheme_id)
    _pass('SCHEME edit — super bypasses', 200, resp.status_code)

    # -----------------------------------------------------------------
    # 12. Celery expiry task
    # -----------------------------------------------------------------
    print('\n--- 12. Celery expiry task -------------------------------------')
    from apps.accounts.tasks import expire_stale_schemes_and_trainings
    result = expire_stale_schemes_and_trainings()
    _pass('EXPIRY task ran (schemes deactivated ≥ 1)', True, result['schemes_expired'] >= 1)

    scheme = Scheme.objects.get(pk=scheme_id)
    _pass('EXPIRY scheme now inactive', False, scheme.is_active)

    # -----------------------------------------------------------------
    # 13. Cap enforcement — 30/30 → 31st blocked
    # -----------------------------------------------------------------
    print('\n--- 13. Cap enforcement (bulk-invite) --------------------------')
    # Lower IDK cap via config, then try to bulk-invite past it.
    r = factory.patch('/api/admin/sub-admin-config/', {'district_caps': {'IDK': 2}}, format='json')
    force_authenticate(r, user=super_admin)
    SubAdminConfigView.as_view()(r)

    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(['first_name', 'last_name', 'email', 'phone', 'district', 'notification_channel'])
    # 2 are already in IDK. Cap=2. So this one should fail.
    ws.append(['B5', 'Test', 'bulk5@kau.in', '9876500006', 'IDK', 'email'])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    upload = SimpleUploadedFile(
        'over.xlsx', buf.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    r = factory.post('/api/admin/sub-admins/bulk-invite/', {'file': upload}, format='multipart')
    force_authenticate(r, user=super_admin)
    resp = SubAdminViewSet.as_view({'post': 'bulk_invite'})(r)
    _pass('BULK cap-blocked failed', 1, resp.data['data']['failed'])
    _pass('BULK cap error mentions capacity', True,
          'capacity' in resp.data['data']['errors'][0]['reason'].lower())

    # -----------------------------------------------------------------
    # CLEANUP
    # -----------------------------------------------------------------
    print('\n=== Cleanup ==================================================')
    # Restore config
    r = factory.patch('/api/admin/sub-admin-config/', {
        'global_cap': 30, 'district_caps': {'TSR': None, 'WYD': None, 'IDK': None},
    }, format='json')
    force_authenticate(r, user=super_admin)
    SubAdminConfigView.as_view()(r)

    # Delete throwaway users + schemes
    for email in ['test.sa@kau.in', 'test.sub.tsr@kau.in', 'bulk1@kau.in', 'bulk2@kau.in',
                  'sub.dpr@kau.in', 'sub.nodpr@kau.in', 'sub.schemes@kau.in', 'sub.other@kau.in']:
        User.objects.filter(email=email).delete()
    Scheme.objects.filter(pk=scheme_id).delete()
    print('  test users + schemes cleaned up')

    # -----------------------------------------------------------------
    # RESULTS
    # -----------------------------------------------------------------
    total  = len(_results)
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = total - passed
    print('\n' + '=' * 70)
    print(f'RESULTS: {passed}/{total} passed  ({failed} failed)')
    print('=' * 70)
    if failed:
        print('\nFailures:')
        for label, ok, detail in _results:
            if not ok:
                print(f'  ✗ {label} — {detail}')
    return passed, failed
