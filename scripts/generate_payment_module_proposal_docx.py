"""
Generate Payment Gateway & Subscription Module proposal DOCX.

Matches the KAU green styling used in generate_dpr_user_stories_docx.py —
KAU green title block, green section headers, KAU-green table headers with
pale-green alternating rows.

Source content:  Documents/Payment_Gateway_Module_Proposal.md
Output:          Documents/Payment_Gateway_Module_Proposal.docx

Run:
    source venv/bin/activate && python scripts/generate_payment_module_proposal_docx.py
"""

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

KAU_GREEN = '2e7d32'
KAU_PALE_GREEN = 'f1f8e9'
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
KAU_GREEN_RGB = RGBColor(0x2E, 0x7D, 0x32)
MUTED_RGB = RGBColor(0x55, 0x55, 0x55)


def _shade(cell, fill_hex):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:fill'), fill_hex)
    shd.set(qn('w:val'), 'clear')
    tc_pr.append(shd)


def _set_col_widths(table, widths_cm):
    for i, w in enumerate(widths_cm):
        for row in table.rows:
            row.cells[i].width = Cm(w)


def _run(paragraph, text, *, bold=False, italic=False, size=10, color=None):
    r = paragraph.add_run(text)
    r.bold = bold
    r.italic = italic
    r.font.size = Pt(size)
    if color is not None:
        r.font.color.rgb = color
    return r


def _section_header(doc, text, *, size=14):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(18)
    p.paragraph_format.space_after = Pt(6)
    _run(p, text, bold=True, size=size, color=KAU_GREEN_RGB)


def _subsection(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(4)
    _run(p, text, bold=True, size=12, color=KAU_GREEN_RGB)


def _para(doc, text, *, italic=False, size=10):
    p = doc.add_paragraph()
    _run(p, text, italic=italic, size=size)
    return p


def _bullet(doc, text):
    p = doc.add_paragraph(style='List Bullet')
    _run(p, text, size=10)
    return p


def _numbered(doc, text):
    p = doc.add_paragraph(style='List Number')
    _run(p, text, size=10)
    return p


def _divider(doc):
    p = doc.add_paragraph()
    _run(p, '─' * 60, color=MUTED_RGB, size=9)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER


def _add_table(doc, headers, rows, widths_cm=None):
    """Header row: KAU green fill + white bold text. Data rows: alt pale green."""
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.autofit = False
    if widths_cm:
        _set_col_widths(table, widths_cm)

    # Header row
    for i, text in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = ''
        p = cell.paragraphs[0]
        _run(p, text, bold=True, size=10, color=WHITE)
        _shade(cell, KAU_GREEN)
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    # Data rows
    for r_idx, row in enumerate(rows, start=1):
        fill = KAU_PALE_GREEN if r_idx % 2 == 1 else None
        for c_idx, value in enumerate(row):
            cell = table.rows[r_idx].cells[c_idx]
            cell.text = ''
            p = cell.paragraphs[0]
            _run(p, str(value), size=10)
            if fill:
                _shade(cell, fill)
            cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP

    doc.add_paragraph('')


def _title_block(doc):
    p = doc.add_paragraph()
    _run(p, 'KAU–FPO Linkage Platform', bold=True, size=18, color=KAU_GREEN_RGB)
    p = doc.add_paragraph()
    _run(p, 'Payment Gateway & Subscription Module — Proposal for KAU',
         bold=True, size=14, color=KAU_GREEN_RGB)
    p = doc.add_paragraph()
    _run(p, 'Kerala Agricultural University  ·  Communication Centre', size=10)
    p = doc.add_paragraph()
    _run(p, 'Prepared by: Athul Gopan · Kefi Tech Solutions  ·  17 September 2026',
         italic=True, size=10)
    doc.add_paragraph('')

    # Meta card as a small 2-col table
    meta = [
        ('Platform', 'KAU-FPO Linkage Programme'),
        ('Module status', 'Proposal — awaiting KAU sign-off before build begins'),
        ('Prepared by', 'Athul Gopan · Kefi Tech Solutions'),
        ('Date', '17 September 2026'),
    ]
    _add_table(doc, ['Field', 'Value'], meta, widths_cm=[4.5, 11.5])


def build_document(output_path):
    doc = Document()

    _title_block(doc)

    # 1
    _section_header(doc, '1. What KAU has asked for')
    _para(doc,
        'Introduce a paid-subscription tier on the platform so that access to premium '
        'features (DPR generation, AI narrative, expert consultations, etc.) is '
        'monetised. FPOs pay a recurring fee — monthly, quarterly or yearly — and '
        'revenue accrues to KAU (or its designated collection account).')
    _para(doc,
        'This proposal lists the features we intend to build so KAU can confirm the '
        'scope before development begins. Nothing is coded yet.', italic=True)

    # 2
    _section_header(doc, '2. Subscription plan structure')
    _subsection(doc, '2.1 Plan tiers (illustrative — KAU to decide final pricing)')
    _add_table(doc,
        ['Tier', 'Monthly ₹', 'Quarterly ₹', 'Yearly ₹', 'Included features'],
        [
            ['Free', '0', '0', '0',
             'Basic profile, browse schemes, up to 1 DPR (draft only), no AI'],
            ['Basic', '499', '1,299', '4,499',
             'Up to 3 DPRs per year, template narratives, expert directory read-only'],
            ['Premium', '999', '2,699', '8,999',
             'Unlimited DPRs, AI narrative generation, expert bookings, market linkage, GIS insights'],
            ['Institutional', 'Custom', '—', 'Custom',
             'Bulk seats for federations / KVKs / CBBOs, priority support, custom branding'],
        ],
        widths_cm=[2.6, 2.0, 2.2, 2.0, 7.2])
    for line in [
        'Plans are stored in the database as admin-editable rows — KAU can add / rename / re-price tiers without a code change.',
        'Feature-access matrix per plan is also admin-editable (checkbox grid: "which features does each tier unlock").',
        'Trial period (e.g. 14 days on Premium) configurable per plan.',
    ]:
        _bullet(doc, line)

    _subsection(doc, '2.2 Billing cycles')
    for line in [
        'Monthly, quarterly, yearly — chosen at checkout.',
        'Auto-renewal by default; FPO can turn off in Settings.',
        'Grace period after failed payment (default 7 days, admin-configurable) before the account is downgraded.',
    ]:
        _bullet(doc, line)

    # 3
    _section_header(doc, '3. Payment integration')
    _subsection(doc, '3.1 Recommended payment gateway')
    _para(doc,
        'Razorpay (industry standard for Indian SaaS, MSME-friendly, KAU IT familiar). '
        'Alternate options: Cashfree or PhonePe Business — comparable price and features.')

    _subsection(doc, '3.2 Supported payment methods')
    for line in [
        'UPI (BHIM, GPay, PhonePe, PayTM)',
        'Credit / Debit cards (Visa, MasterCard, RuPay)',
        'Net banking (all major Indian banks)',
        'Wallets (PayTM, MobiKwik, Amazon Pay)',
        'Auto-debit mandates (Razorpay Subscriptions / eNACH)',
    ]:
        _bullet(doc, line)

    _subsection(doc, '3.3 Payment flow')
    for line in [
        'FPO clicks "Upgrade to Premium" on the platform.',
        "Redirects to Razorpay checkout (hosted page — PCI-DSS compliance is Razorpay's problem, not KAU's).",
        'On success → webhook fires → subscription activated → confirmation SMS + email to FPO.',
        'On failure → error page with retry link, no charge.',
    ]:
        _bullet(doc, line)

    _subsection(doc, '3.4 Refunds')
    for line in [
        'Admin-initiated refund from the KAU admin panel (partial or full).',
        'Refund reason logged. Refund goes back to the original payment instrument via Razorpay.',
    ]:
        _bullet(doc, line)

    # 4
    _section_header(doc, '4. FPO-side features')
    for line in [
        'My Subscription page under Settings — shows current plan, next billing date, payment history, invoices.',
        'Upgrade / Downgrade — pro-rata credit applied when switching plans mid-cycle.',
        'Payment history — sortable table with date, amount, plan, invoice PDF download.',
        'Auto-renewal toggle — one click on/off.',
        'Renewal reminders — email + SMS at 7 / 3 / 1 day before due.',
        'Failed-payment recovery — reminder + retry link when a scheduled charge fails.',
        'Cancellation flow — with reason capture (optional short survey — helps KAU learn why FPOs churn).',
    ]:
        _bullet(doc, line)

    # 5
    _section_header(doc, '5. Access control — how paid features are gated')
    for line in [
        "Every premium feature checks the FPO's current plan before rendering.",
        'FPO on Free tier trying to open the DPR wizard beyond their quota → an "Upgrade to continue" modal with the pricing table.',
        'Usage counters (DPRs generated, AI narratives requested, expert bookings) shown on the dashboard.',
        'Hard limits are visual first (soft nudge), then blocking at the API level.',
    ]:
        _bullet(doc, line)

    # 6
    _section_header(doc, '6. Admin (KAU) features')
    _subsection(doc, '6.1 Subscription dashboard')
    for line in [
        'Total active subscriptions',
        'MRR (Monthly Recurring Revenue)',
        'ARR (Annual Recurring Revenue)',
        'Churn rate (last 30 / 90 days)',
        'Plan-wise distribution (pie chart)',
        'District-wise adoption (bar chart)',
        'Month-over-month growth trend',
    ]:
        _bullet(doc, line)

    _subsection(doc, '6.2 Per-FPO subscription view')
    for line in [
        'Complete payment history',
        'All invoices with download links',
        'Manual override — "Grant free subscription" for demo / promotional accounts',
        'Refund initiation',
        'Notes field for audit trail',
    ]:
        _bullet(doc, line)

    _subsection(doc, '6.3 Plan management CRUD')
    for line in [
        'Create / edit / deactivate plans without code',
        'Toggle features on/off per plan (checkbox grid)',
        'Set trial length, grace period, pricing per billing cycle',
        'Discount codes / coupons (percentage or fixed amount, expiry date, per-code usage cap)',
    ]:
        _bullet(doc, line)

    _subsection(doc, '6.4 Revenue reports')
    for line in [
        'Downloadable Excel / PDF (monthly / quarterly / YTD)',
        'Filterable by district, plan tier, payment method',
        'GST breakdown (for KAU accounting)',
    ]:
        _bullet(doc, line)

    _subsection(doc, '6.5 Refund & dispute management')
    for line in [
        'List of pending refund requests',
        'One-click approve / reject',
        'Reason tracked, refund receipt auto-emailed to FPO',
    ]:
        _bullet(doc, line)

    # 7
    _section_header(doc, '7. Compliance & invoicing')
    for line in [
        "GST-compliant invoices — auto-generated PDF with KAU's GSTIN, itemised, HSN/SAC codes.",
        'Numbered invoice series (KAU/DPR/2026-27/00001 …).',
        'TDS handling — configurable per plan for institutional buyers if needed.',
        'Accounting exports — Tally / SAP / QuickBooks-compatible CSV.',
        'KYC at signup — captured during FPO registration, no extra step at checkout.',
    ]:
        _bullet(doc, line)

    # 8
    _section_header(doc, '8. Notifications')
    _para(doc, 'Automatic email + SMS to the FPO on:')
    for line in [
        'Payment success',
        'Payment failure',
        'Renewal upcoming (7 / 3 / 1 day)',
        'Renewal successful',
        'Plan expiration / downgrade',
        'Refund initiated / completed',
        'Complimentary subscription granted',
    ]:
        _bullet(doc, line)
    _para(doc,
        'Templates admin-editable via the existing notification-templates module. '
        'Malayalam + English supported.', italic=True)

    # 9
    _section_header(doc, '9. Reporting for KAU leadership')
    _para(doc, 'Dashboard metrics KAU can pull at any time:')
    for line in [
        'Total revenue (day / week / month / quarter / year)',
        'Active subscriptions by plan',
        'New signups (funnel: free → paid)',
        'Churn — who cancelled, why, from which district',
        'ARPU (Average Revenue Per Unit)',
        'LTV (Lifetime Value estimate)',
        'Payment-method breakdown (UPI vs Cards vs Netbanking)',
        'District-wise adoption heatmap',
        'Overdue accounts (in grace period)',
    ]:
        _bullet(doc, line)
    _para(doc, 'All exportable to Excel / PDF.', italic=True)

    # 10
    _section_header(doc, '10. Optional advanced features (Phase 2)')
    _para(doc, 'Not committed for Phase 1 — flagged so KAU can prioritise:')
    for line in [
        'Discount codes / coupons — percentage or fixed off, per-code usage cap',
        'Referral program — reward FPOs who bring in new FPOs (₹ credit or free month)',
        'Wallet / prepaid credits — FPO adds ₹ to wallet, features draw from balance',
        'Bulk / federation licences — one CBBO buys 20 seats and distributes to its FPOs',
        'Custom pricing per FPO — for high-value institutional accounts',
        'Free access for select districts — configurable geographical carve-outs',
        'API access tier — for FPOs that want programmatic access to their DPR / market data',
        'Multiple currency support — INR only for Phase 1; add USD if KAU pursues NRI FPOs later',
    ]:
        _bullet(doc, line)

    # 11
    _section_header(doc, '11. What this replaces / what continues')
    for line in [
        'Currently free features stay free during the roll-out window (KAU-defined grace period).',
        "Existing FPOs get grandfathered into a plan of KAU's choice at launch — no forced upgrade.",
        'DPR PDFs already generated stay accessible even if the FPO downgrades later.',
    ]:
        _bullet(doc, line)

    # 12
    _section_header(doc, '12. Technical stack (for KAU IT reference)')
    for line in [
        'Payment gateway: Razorpay Subscriptions API (auto-debit mandates via eNACH)',
        'Backend: Django + Django REST Framework (same stack as the rest of the platform)',
        'Frontend: Next.js — new billing pages under /fpo/settings/subscription',
        'Notifications: existing MSG91 SMS + Gmail SMTP infrastructure',
        'Invoicing: WeasyPrint (same PDF engine we use for DPRs)',
        'Database: existing PostgreSQL — new tables for SubscriptionPlan, Subscription, Payment, Invoice, RefundRequest, Coupon',
    ]:
        _bullet(doc, line)
    _para(doc, 'No new infrastructure needed. Everything runs on the current AWS EC2 + RDS setup.', italic=True)

    # 13
    _section_header(doc, '13. Effort estimate (for KAU planning)')
    _para(doc,
        'End-to-end delivery of the production-ready subscription module: 10 days.')
    _para(doc,
        'Scope covered in the 10 days: plan model + Razorpay integration + FPO '
        'subscription page + feature gating + GST-compliant invoicing + admin '
        'revenue dashboard + email/SMS notifications + Malayalam translations + '
        'UAT with KAU and sandbox → production Razorpay switch.')
    _para(doc,
        'Timeline assumes KAU confirms scope in this document, provides Razorpay '
        'account credentials on day 1, and gives feedback within 1 working day at '
        'each review point.',
        italic=True)

    # 14
    _section_header(doc, '14. What KAU needs to decide before we start')
    _para(doc, 'Please respond with decisions on the following:')
    for line in [
        'Plan tiers — how many? Suggested names? Pricing per tier per billing cycle?',
        'Which features unlock at each tier? — checkbox against the DPR / AI / experts / market / GIS features.',
        'Trial period — days? Which tier(s) get a trial?',
        'Grace period — days between failed payment and account downgrade?',
        "Razorpay account — does KAU already have a merchant account, or should we register one on KAU's behalf?",
        'Revenue account — which KAU / KAU-designated bank account should Razorpay settle to?',
        'GSTIN + accounting details — for invoice generation.',
        'Existing FPOs — grandfather into which plan at launch (Free / Basic / Premium)?',
        'Refund policy — full / partial / no refunds? Time limit?',
        'Phase 2 features — which ones does KAU want in the initial commitment vs later?',
    ]:
        _numbered(doc, line)

    # 15
    _section_header(doc, '15. Reference documents')
    for line in [
        'Documents/DPR_Module_For_KAU_Review.docx — the DPR module we already delivered (pattern for how this next module will look and feel)',
        'Documents/KAU_DPR_Questionnaire_Spec.docx — sample of "one section per feature" documentation style KAU can expect once the payment module is built',
    ]:
        _bullet(doc, line)

    doc.add_paragraph('')
    _divider(doc)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _run(p,
        'Prepared by Athul Gopan · Kefi Tech Solutions for KAU-FPO Linkage Programme. '
        'This proposal is a scope-lock document — please review, redline and return '
        'a signed-off version before development starts.',
        italic=True, size=10, color=MUTED_RGB)

    doc.save(output_path)
    print(f'Wrote {output_path}')


if __name__ == '__main__':
    build_document('Documents/Payment_Gateway_Module_Proposal.docx')
