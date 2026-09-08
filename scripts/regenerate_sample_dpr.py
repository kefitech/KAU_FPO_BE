"""
Regenerate a sample DPR PDF after H1 (loan repayment) + H2 (IDC) changes.

Produces two variants for KAU maths review:
  1. DEFAULT convention (reducing_balance + IDC=0) — same as the sample we
     shared pre-reply, but on the current code.
  2. WITH H2 ILLUSTRATED — user enters IDC = ₹5L to show it lands in the
     depreciable asset base pro-rata (not in pre-op amortisation).

Output files go to Documents/ so we can attach them to the KAU follow-up.
DB is not mutated — variant 2 uses transaction.savepoint rollback.

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/regenerate_sample_dpr.py').read())
    regenerate_sample_dpr('7a44dcf8-8b49-4fd1-a036-1f264b12f026')
    "
"""

import os
from decimal import Decimal


def regenerate_sample_dpr(project_uuid: str):
    from django.db import transaction
    from apps.database.models import DPRProject
    from apps.fpo.services.dpr.pdf import save_pdf_to_disk

    project = DPRProject.objects.select_related('section_finance').get(uuid=project_uuid)
    fin = project.section_finance

    out_dir = '/home/athul_dasp/Desktop/AGRI-THRISSUR/kau-fpo-backend/Documents'
    os.makedirs(out_dir, exist_ok=True)

    # ── Variant 1: DEFAULT (current DB state) ──
    path1 = os.path.join(out_dir, 'dpr_sample_v2_H1_reducing_balance.pdf')
    save_pdf_to_disk(project, output_path=path1)
    size1 = os.path.getsize(path1)
    print(f'✅ Variant 1 (H1 default — reducing_balance, IDC=0):')
    print(f'   {path1}  ({size1 / 1024:.1f} KB)')
    print(f'   Loan {fin.loan_amount:,.0f} @ {fin.rate_of_interest_pct}% × '
          f'{fin.repayment_period_years}yr, moratorium {fin.moratorium_period_months}mo, '
          f'method={fin.repayment_method}')

    # ── Variant 2: WITH IDC ₹5L (H2 illustrated) ──
    with transaction.atomic():
        sid = transaction.savepoint()
        fin.cost_interest_during_construction = Decimal('500000')
        fin.save(update_fields=['cost_interest_during_construction'])
        # Re-fetch so the compute pipeline sees the updated value.
        project_reloaded = DPRProject.objects.select_related('section_finance').get(uuid=project_uuid)
        path2 = os.path.join(out_dir, 'dpr_sample_v2_H2_idc_capitalised.pdf')
        save_pdf_to_disk(project_reloaded, output_path=path2)
        size2 = os.path.getsize(path2)
        print(f'✅ Variant 2 (H2 illustrated — IDC ₹5,00,000 pro-rata to depreciable base):')
        print(f'   {path2}  ({size2 / 1024:.1f} KB)')
        print(f'   Same loan + IDC ₹5L allocated across buildings/machinery/equipment')
        transaction.savepoint_rollback(sid)

    # ── Variant 3: EMI opt-in (H1 alternative) — show KAU the EMI schedule ──
    with transaction.atomic():
        sid = transaction.savepoint()
        fin.repayment_method = 'emi'
        fin.save(update_fields=['repayment_method'])
        project_reloaded = DPRProject.objects.select_related('section_finance').get(uuid=project_uuid)
        path3 = os.path.join(out_dir, 'dpr_sample_v2_H1_emi_alternative.pdf')
        save_pdf_to_disk(project_reloaded, output_path=path3)
        size3 = os.path.getsize(path3)
        print(f'✅ Variant 3 (H1 opt-in — EMI schedule):')
        print(f'   {path3}  ({size3 / 1024:.1f} KB)')
        print(f'   Same loan, repayment_method=emi (per-project opt-in)')
        transaction.savepoint_rollback(sid)

    print()
    print('DB state unchanged — variants 2 + 3 mutations rolled back.')
    print('Attach these 3 PDFs to the KAU follow-up email as second-round review artefacts.')
