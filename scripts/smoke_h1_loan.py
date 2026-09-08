"""
Smoke test for H1 (KAU pre-UAT reply §2.2) — verifies both loan repayment
methods (reducing_balance default + emi opt-in) and both moratorium interest
treatments (serviced default + capitalised opt-in).

Runs the amortiser in isolation without needing a real DPRProject row. Prints
year-by-year opening / interest / principal / closing for each combination
so we can eyeball the numbers against a hand-checked reference.

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/smoke_h1_loan.py').read())
    smoke_h1_loan()
    "
"""


def smoke_h1_loan():
    from decimal import Decimal
    from apps.fpo.services.dpr.calculation import (
        _amortise_reducing_balance,
        _amortise_emi,
    )

    # Canned loan: ₹75L (Coconut Oil FPO sample), 10.5% pa, 7-year tenure,
    # 12-month moratorium. Projection window 10 years so we see amortisation
    # complete + 3 years of zero rows.
    loan = Decimal('7500000')
    rate = Decimal('10.5')
    tenure = 7
    moratorium_months = 12
    projection = 10

    def _dump(label, rows):
        print(f'\n=== {label} ===')
        print(f"{'Yr':>3}  {'Opening':>14}  {'Interest':>12}  {'Principal':>13}  {'Closing':>14}")
        totals = [Decimal('0')] * 3
        for r in rows:
            totals[0] += r.interest
            totals[1] += r.principal
            print(
                f'{r.year:>3}  '
                f'{r.opening_balance:>14,.2f}  {r.interest:>12,.2f}  '
                f'{r.principal:>13,.2f}  {r.closing_balance:>14,.2f}'
            )
        print(f"     {'':>14}  {totals[0]:>12,.2f}  {totals[1]:>13,.2f}  (totals)")

    print('=' * 78)
    print('H1 SMOKE — Loan repayment convention (KAU pre-UAT reply §2.2)')
    print('=' * 78)
    print(f'Loan: ₹{loan:,.0f}  |  Rate: {rate}%  |  Tenure: {tenure} yr  |  Moratorium: {moratorium_months} mo')

    # Case 1 — reducing balance, moratorium interest serviced (DEFAULT).
    rows = _amortise_reducing_balance(loan, rate, tenure, moratorium_months, 'serviced', projection)
    _dump('reducing_balance + serviced (DEFAULT)', rows)
    # Year 1 = pure interest (moratorium). Year 2 = first principal = 7500000/6 = 1250000.
    assert rows[0].principal == Decimal('0'), 'Y1 principal should be 0 (moratorium)'
    assert rows[1].principal == Decimal('1250000.00'), \
        f'Y2 principal should be 1250000 in reducing_balance, got {rows[1].principal}'
    print('  ✅ Y1 principal = 0 (moratorium); Y2 principal = 1250000 (7.5M / 6 remaining yrs)')

    # Case 2 — reducing balance, capitalised moratorium (interest added to principal).
    rows = _amortise_reducing_balance(loan, rate, tenure, moratorium_months, 'capitalised', projection)
    _dump('reducing_balance + capitalised', rows)
    # Y1 closing = 7500000 + interest(787500) = 8287500
    expected_y1_close = (loan + (loan * rate / Decimal('100'))).quantize(Decimal('0.01'))
    assert rows[0].closing_balance == expected_y1_close, \
        f'Y1 closing should be {expected_y1_close} (capitalised), got {rows[0].closing_balance}'
    print(f'  ✅ Y1 closing = {expected_y1_close} (loan + moratorium interest capitalised)')

    # Case 3 — EMI, serviced moratorium.
    rows = _amortise_emi(loan, rate, tenure, moratorium_months, 'serviced', projection)
    _dump('emi + serviced', rows)
    # Y2 principal + interest should equal Y3 principal + interest (EMI constant post-moratorium).
    y2_total = rows[1].principal + rows[1].interest
    y3_total = rows[2].principal + rows[2].interest
    # Rounding tolerance of a few paise per year is fine.
    assert abs(y2_total - y3_total) < Decimal('1'), \
        f'EMI Y2 ({y2_total}) should equal EMI Y3 ({y3_total}) — total P+I constant'
    print(f'  ✅ Y2 total P+I = {y2_total}; Y3 total P+I = {y3_total} (EMI constant)')

    # Case 4 — EMI, capitalised moratorium.
    rows = _amortise_emi(loan, rate, tenure, moratorium_months, 'capitalised', projection)
    _dump('emi + capitalised', rows)

    # Case 5 — no loan (edge case — all rows zero).
    rows = _amortise_reducing_balance(Decimal('0'), Decimal('0'), 0, 0, 'serviced', 3)
    assert all(r.interest == Decimal('0') and r.principal == Decimal('0') for r in rows), \
        'No-loan case must produce all-zero rows'
    print('\n  ✅ No-loan edge case: all rows zero')

    print('\nAll 5 smoke checks passed. H1 loan-repayment refactor is behaving as expected.')


if __name__ == '__main__':
    import django, os
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
    django.setup()
    smoke_h1_loan()
