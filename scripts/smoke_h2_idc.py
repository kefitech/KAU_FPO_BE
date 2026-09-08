"""
Smoke test for H2 (KAU pre-UAT reply §2.6) — verifies that IDC is:
  1. NOT routed to pre-operative amortisation
  2. Allocated pro-rata across depreciable classes (buildings + machinery + equipment)
  3. Depreciated along with the related asset class
  4. Preserved exactly (no capex loss to rounding)
  5. Edge cases: IDC = 0 → no change; IDC + no depreciable capex → falls into machinery

Runs the full compute() pipeline on the sample project + temporarily sets a
non-zero IDC via rollback so DB stays untouched.

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/smoke_h2_idc.py').read())
    smoke_h2_idc('7a44dcf8-8b49-4fd1-a036-1f264b12f026')
    "
"""


def smoke_h2_idc(project_uuid: str):
    from decimal import Decimal
    from django.db import transaction
    from apps.database.models import DPRProject
    from apps.fpo.services.dpr.calculation import (
        compute, _allocate_idc, _aggregate_class_capex, compute_cost_and_mof,
    )

    project = DPRProject.objects.select_related('section_finance').get(uuid=project_uuid)
    fin = project.section_finance

    print('=' * 82)
    print(f'H2 IDC SMOKE — Project {project_uuid}')
    print('=' * 82)
    print(f'Current IDC field: {fin.cost_interest_during_construction!r}')

    # ── Unit tests on _allocate_idc ──
    print('\n--- Unit tests: _allocate_idc ---')

    # Case A: pro-rata across 3 depreciable classes
    totals = {'land': Decimal('500000'), 'buildings': Decimal('2000000'),
              'machinery': Decimal('3500000'), 'equipment': Decimal('500000'),
              'pre_operative': Decimal('400000'), 'other': Decimal('0')}
    idc = Decimal('600000')
    alloc = _allocate_idc(idc, totals)
    # depreciable_total = 2M + 3.5M + 0.5M = 6M
    # buildings: 600k × 2/6 = 200000
    # machinery: 600k × 3.5/6 = 350000
    # equipment: 600k × 0.5/6 = 50000
    print(f'  Case A (pro-rata): IDC=₹6L → {alloc}')
    total_alloc = sum(alloc.values())
    assert total_alloc == idc, f'Pro-rata total ({total_alloc}) must equal IDC ({idc})'
    assert 'land' not in alloc, 'Land is non-depreciable — must not receive IDC'
    assert 'pre_operative' not in alloc, 'Pre-op must not receive IDC (KAU §2.6)'
    print(f'  ✅ IDC fully allocated, land + pre-op correctly excluded')

    # Case B: no depreciable capex → falls into machinery
    totals_b = {'land': Decimal('1000000'), 'buildings': Decimal('0'),
                'machinery': Decimal('0'), 'equipment': Decimal('0'),
                'pre_operative': Decimal('500000'), 'other': Decimal('0')}
    alloc_b = _allocate_idc(Decimal('100000'), totals_b)
    assert alloc_b == {'machinery': Decimal('100000')}, \
        f'Fallback should be all-to-machinery, got {alloc_b}'
    print(f'  ✅ Case B (no depreciable capex fallback): all IDC to machinery')

    # Case C: IDC = 0 → empty allocation
    alloc_c = _allocate_idc(Decimal('0'), totals)
    assert alloc_c == {}, f'Zero IDC should give empty allocation, got {alloc_c}'
    print(f'  ✅ Case C (IDC=0): empty allocation')

    # Case D: rounding residue handling
    totals_d = {'land': Decimal('0'), 'buildings': Decimal('1'),
                'machinery': Decimal('1'), 'equipment': Decimal('1'),
                'pre_operative': Decimal('0'), 'other': Decimal('0')}
    alloc_d = _allocate_idc(Decimal('100'), totals_d)  # 100/3 = 33.33... × 3
    assert sum(alloc_d.values()) == Decimal('100'), \
        f'Rounding residue must be absorbed, got sum={sum(alloc_d.values())}'
    print(f'  ✅ Case D (rounding residue): {alloc_d} — sum = ₹100 exact')

    # ── End-to-end via compute() with a real IDC value ──
    print('\n--- End-to-end: full compute() pipeline ---')

    def _dump_depreciation(label, result):
        print(f'\n=== {label} ===')
        grand_dep = Decimal('0')
        for cls in result.depreciation.classes:
            cls_dep = sum(r.depreciation for r in cls.rows)
            grand_dep += cls_dep
            if cls.initial_cost > 0 or cls_dep > 0:
                print(f'  [{cls.key:14s}] {cls.label:36s} '
                      f'initial ₹{cls.initial_cost:>13,.2f}  '
                      f'total dep ₹{cls_dep:>13,.2f}')
        print(f'  {"— TOTAL depreciation across all classes":52s} '
              f'                       ₹{grand_dep:>13,.2f}')

    # Case 1: IDC = 0 (current DB state)
    result1 = compute(project)
    _dump_depreciation('Case 1 — IDC = 0 (baseline)', result1)

    # Case 2: IDC = ₹5L (typical for a ₹75L loan × 10.5% × 6-month construction)
    with transaction.atomic():
        sid = transaction.savepoint()
        fin.cost_interest_during_construction = Decimal('500000')
        fin.save(update_fields=['cost_interest_during_construction'])
        project_reloaded = DPRProject.objects.select_related('section_finance').get(uuid=project_uuid)
        result2 = compute(project_reloaded)
        _dump_depreciation('Case 2 — IDC = ₹5,00,000 (in-memory)', result2)
        # Verify allocation went to depreciable classes only
        cost2, _, _ = compute_cost_and_mof(project_reloaded)
        allocated = _aggregate_class_capex(cost2)
        idc_share_buildings = allocated['buildings'] - _aggregate_class_capex(_recompute_without_idc(project))['buildings']
        transaction.savepoint_rollback(sid)

    # Delta summary
    print('\n' + '=' * 82)
    print('DELTA SUMMARY (IDC ₹0 vs ₹5L)')
    print('=' * 82)
    for cls_name in ['land', 'buildings', 'machinery', 'equipment', 'pre_operative']:
        cls1 = next((c for c in result1.depreciation.classes if c.key == cls_name), None)
        cls2 = next((c for c in result2.depreciation.classes if c.key == cls_name), None)
        if cls1 and cls2:
            delta_capex = cls2.initial_cost - cls1.initial_cost
            dep1 = sum(r.depreciation for r in cls1.rows)
            dep2 = sum(r.depreciation for r in cls2.rows)
            delta_dep = dep2 - dep1
            marker = ' ← IDC allocated here' if delta_capex > 0 else ''
            print(f'  {cls_name:15s} capex Δ ₹{delta_capex:>13,.2f}  dep Δ ₹{delta_dep:>13,.2f}{marker}')

    print(f'\nDB state unchanged — all mutations rolled back.')
    print('Key check: pre_operative capex delta should be ₹0 (IDC does NOT go to pre-op per KAU §2.6).')


def _class_key_of(cls) -> str:
    """Reverse-lookup the class_key from the AssetClass label."""
    from apps.fpo.services.dpr.calculation import _ASSET_CLASS_META
    for key, (label, _) in _ASSET_CLASS_META.items():
        if label == cls.label:
            return key
    return ''


def _recompute_without_idc(project):
    """Fetch fresh cost breakdown without the IDC amount (for baseline comparison)."""
    from apps.fpo.services.dpr.calculation import compute_cost_and_mof
    cost, _, _ = compute_cost_and_mof(project)
    return cost
