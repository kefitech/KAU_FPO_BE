"""
End-to-end smoke for H1 — runs the full compute() pipeline on a real
DPRProject and compares reducing_balance vs EMI across:
  * interest schedule (year-by-year)
  * total interest paid
  * DSCR pattern
  * IRR
  * final ending cash

Uses django.db.transaction.atomic + rollback so the DB stays untouched.

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/smoke_h1_end_to_end.py').read())
    smoke_h1_end_to_end('7a44dcf8-8b49-4fd1-a036-1f264b12f026')
    "
"""


def smoke_h1_end_to_end(project_uuid: str):
    from decimal import Decimal
    from django.db import transaction
    from apps.database.models import DPRProject, DPRConfig
    from apps.fpo.services.dpr.calculation import compute

    project = DPRProject.objects.select_related('section_finance').get(uuid=project_uuid)
    fin = project.section_finance

    print('=' * 82)
    print(f'H1 END-TO-END SMOKE — Project {project_uuid}')
    print('=' * 82)
    print(f'Loan: ₹{fin.loan_amount:,.0f}  |  Rate: {fin.rate_of_interest_pct}%  |  '
          f'Tenure: {fin.repayment_period_years} yr  |  '
          f'Moratorium: {fin.moratorium_period_months} mo')
    print(f'Current DB repayment_method: {fin.repayment_method!r}')
    treatment = DPRConfig.get_str('moratorium_interest_treatment', 'serviced')
    print(f'DPRConfig moratorium_interest_treatment: {treatment!r}')

    def _dump_schedule(label, result):
        print(f'\n--- {label} ---')
        print(f'  method            : {result.interest_schedule.repayment_method}')
        print(f'  moratorium treat. : {result.interest_schedule.moratorium_interest_treatment}')
        print(f'  loan amount       : ₹{result.interest_schedule.loan_amount:,.2f}')
        print(f'  tenure years      : {result.interest_schedule.tenure_years}')
        print(f'  moratorium months : {result.interest_schedule.moratorium_months}')
        total_interest = sum(r.interest for r in result.interest_schedule.rows)
        total_principal = sum(r.principal for r in result.interest_schedule.rows)
        print(f'  total interest    : ₹{total_interest:,.2f}')
        print(f'  total principal   : ₹{total_principal:,.2f}')
        print(f'  Y1-Y7 P + I profile:')
        for r in result.interest_schedule.rows[:8]:
            total = r.interest + r.principal
            print(f'    Yr {r.year:>2}: interest ₹{r.interest:>12,.2f}  '
                  f'principal ₹{r.principal:>13,.2f}  total ₹{total:>13,.2f}')
        # DSCR / IRR / ending cash
        if getattr(result, 'financial_appraisal', None):
            fa = result.financial_appraisal
            print(f'  Overall DSCR      : {fa.dscr_overall}')
            print(f'  IRR               : {fa.irr_pct}')
            print(f'  NPV               : ₹{fa.npv:,.2f}')
        # Ending cash from last-year row
        if getattr(result, 'cash_flow', None) and result.cash_flow.rows:
            last = result.cash_flow.rows[-1]
            print(f'  Y{last.year} ending cash  : ₹{last.closing_cash:,.2f}')

    # --- CASE 1 : Current settings (reducing_balance default) ---
    result1 = compute(project)
    _dump_schedule('Case 1 — reducing_balance (current DB setting)', result1)

    # --- CASE 2 : Flip to EMI (temporarily, rolled back) ---
    with transaction.atomic():
        sid = transaction.savepoint()
        fin.repayment_method = 'emi'
        fin.save(update_fields=['repayment_method'])
        # Fresh query so the compute pipeline sees the updated value
        project_reloaded = DPRProject.objects.select_related('section_finance').get(uuid=project_uuid)
        result2 = compute(project_reloaded)
        _dump_schedule('Case 2 — EMI (in-memory only, rolled back)', result2)
        transaction.savepoint_rollback(sid)

    # --- CASE 3 : Flip DPRConfig moratorium to capitalised (rolled back) ---
    with transaction.atomic():
        sid = transaction.savepoint()
        cfg = DPRConfig.get('moratorium_interest_treatment')
        if cfg:
            original_value = cfg.value
            cfg.value = 'capitalised'
            cfg.save(update_fields=['value'])
        project_reloaded = DPRProject.objects.select_related('section_finance').get(uuid=project_uuid)
        result3 = compute(project_reloaded)
        _dump_schedule('Case 3 — reducing_balance + moratorium interest CAPITALISED', result3)
        if cfg:
            cfg.value = original_value  # will get rolled back anyway
        transaction.savepoint_rollback(sid)

    # --- DELTA SUMMARY ---
    print('\n' + '=' * 82)
    print('DELTA SUMMARY')
    print('=' * 82)
    t1 = sum(r.interest for r in result1.interest_schedule.rows)
    t2 = sum(r.interest for r in result2.interest_schedule.rows)
    t3 = sum(r.interest for r in result3.interest_schedule.rows)
    print(f'  Reducing balance (default)          → total interest ₹{t1:>12,.2f}')
    print(f'  EMI                                 → total interest ₹{t2:>12,.2f}  (Δ ₹{t2 - t1:+,.2f})')
    print(f'  Reducing balance + capitalised      → total interest ₹{t3:>12,.2f}  (Δ ₹{t3 - t1:+,.2f})')
    print('\nDB state unchanged — all mutations rolled back.')
    print('If DSCR / IRR / NPV differ across cases and the numbers look sensible,')
    print('the H1 refactor is landing correctly in the full compute() pipeline.')
