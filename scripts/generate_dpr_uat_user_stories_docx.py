"""
Generate the tester-facing UAT user stories DOCX for the KAU AI response
sprint (Phases 1-6 shipped 2026-09-19 → 2026-09-20).

Same KAU-green styling as scripts/generate_dpr_user_stories_docx.py — one
5-row table per story (US-ID | Title, Role, Story, Acceptance Criteria,
Priority | Status). Testers walk through them top-to-bottom.

Two modules covered here:
    Module A — Admin (super_admin)
    Module F — FPO (project owner filling the wizard)

Each story has a `traces` field pointing back to the specific KAU or
Kefitech doc reference the story validates — so a tester can tick items
against the two source documents:
    Documents/DPR-RESPONSE/AI.docx        (KAU review, 15 sections)
    Documents/DPR-RESPONSE/Kefitech.docx  (consolidated, 8 sections)

Output: Documents/DPR-RESPONSE/DPR-UAT-User-Stories.docx

Run:
    source venv/bin/activate && python scripts/generate_dpr_uat_user_stories_docx.py

Author: Athul Gopan (Kefi Tech Solutions)
"""
from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

KAU_GREEN = '2e7d32'
KAU_PALE_GREEN = 'f1f8e9'
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
KAU_GREEN_RGB = RGBColor(0x2E, 0x7D, 0x32)


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


def _add_story(doc, us_id, title, role, story, criteria, traces,
               priority='Medium', status='To Test'):
    """Append one story table matching the reference style."""
    table = doc.add_table(rows=6, cols=2)
    table.autofit = False
    _set_col_widths(table, [3.6, 12.0])

    # Row 0 — header (US-ID | Title)
    for i, text in enumerate([us_id, title]):
        cell = table.rows[0].cells[i]
        cell.text = ''
        p = cell.paragraphs[0]
        run = p.add_run(text)
        run.bold = True
        run.font.color.rgb = WHITE
        run.font.size = Pt(10)
        _shade(cell, KAU_GREEN)
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    rows_content = [
        ('Role',                role),
        ('Story',               story),
        ('Acceptance Criteria', criteria),
        ('Traces to',           traces),
        ('Priority / Status',   f'{priority}  |  {status}'),
    ]
    for r_idx, (label, value) in enumerate(rows_content, start=1):
        # Label cell
        lc = table.rows[r_idx].cells[0]
        lc.text = ''
        lr = lc.paragraphs[0].add_run(label)
        lr.bold = True
        lr.font.size = Pt(9)
        _shade(lc, KAU_PALE_GREEN)
        lc.vertical_alignment = WD_ALIGN_VERTICAL.TOP

        # Value cell — support multiline via \n
        vc = table.rows[r_idx].cells[1]
        vc.text = ''
        first = True
        for line in value.split('\n'):
            p = vc.paragraphs[0] if first else vc.add_paragraph()
            run = p.add_run(line)
            run.font.size = Pt(10)
            first = False
        vc.vertical_alignment = WD_ALIGN_VERTICAL.TOP

    doc.add_paragraph('')


def _add_section_header(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(18)
    p.paragraph_format.space_after = Pt(6)
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(16)
    run.font.color.rgb = KAU_GREEN_RGB


def _add_title_block(doc):
    for text, size, bold in [
        ('KAU–FPO Linkage Platform', 18, True),
        ('DPR — Post-review UAT User Stories', 14, True),
        ('Kerala Agricultural University  ·  Communication Centre', 10, False),
        ('Prepared by: Athul Gopan · Kefi Tech Solutions  ·  20 September 2026', 10, False),
    ]:
        p = doc.add_paragraph()
        run = p.add_run(text)
        run.bold = bold
        run.font.size = Pt(size)
        if bold and size >= 14:
            run.font.color.rgb = KAU_GREEN_RGB
    doc.add_paragraph('')


def _add_overview(doc):
    p = doc.add_paragraph()
    r = p.add_run(
        'This UAT script covers the changes shipped in response to two review '
        'documents received from KAU and Kefitech in September 2026:'
    )
    r.font.size = Pt(10)

    for line in [
        'Documents/DPR-RESPONSE/AI.docx — KAU review of the DPR AI narrative, 15 sections of feedback.',
        'Documents/DPR-RESPONSE/Kefitech.docx — Kefitech\'s consolidated requirements, 8 sections.',
    ]:
        p = doc.add_paragraph(style='List Bullet')
        r = p.add_run(line)
        r.font.size = Pt(10)

    p = doc.add_paragraph()
    r = p.add_run(
        'Two modules, run in either order. Every story has a "Traces to" '
        'row pointing at the exact section of the source document it '
        'validates, so testers can tick source items off the doc as they '
        'progress. Reference project across every story is the same '
        '"Coconut Oil Extraction — 500 L/day" DPR (uuid 7a44dcf8-8b49-4fd1-'
        'a036-1f264b12f026) used during development.'
    )
    r.font.size = Pt(10)
    r.italic = True

    p = doc.add_paragraph()
    r = p.add_run(
        'Setup: run both dev servers, log in as super_admin in one browser '
        'window (for Module A stories) and as the FPO owner in a second '
        'incognito window (for Module F stories).'
    )
    r.font.size = Pt(10)
    r.italic = True


# ─────────────────────────────────────────────────────────────────────────────
# Module A — Admin (super_admin)
# ─────────────────────────────────────────────────────────────────────────────

ADMIN_STORIES = [
    dict(
        us_id='US-A01', title='See DPR admin menu items in the sidebar',
        role='super_admin',
        story=(
            'As a super_admin, I want the DPR admin pages to appear in the '
            'sidebar without typing URLs, so that I can reach every DPR '
            'configuration surface from one place.'
        ),
        criteria=(
            '✓ Sidebar shows DPR Projects, DPR Config, DPR Master Data, '
            'DPR Applicability (L1), DPR Field Rules (L2), DPR Knowledge Base, '
            'DPR Risk Matrix — labels visible in English AND Malayalam.\n'
            '✓ All 7 items are grouped adjacent to each other.\n'
            '✓ Clicking each link navigates to the correct page without a 404.'
        ),
        traces='Menu seed sweep — previously only 2 of 7 DPR admin pages were '
               'reachable from the sidebar; the other 5 required typing the '
               'URL manually.',
        priority='High',
    ),
    dict(
        us_id='US-A02', title='Review AI content health per chapter on the admin viewer',
        role='super_admin',
        story=(
            'As an admin, I want an at-a-glance health card on the DPR '
            'oversight page that shows which of the 11 AI narrative '
            'chapters still need review, so that I can spot issues without '
            'opening each chapter.'
        ),
        criteria=(
            '✓ Navigate: DPR Projects → Coconut Oil project.\n'
            '✓ Top of content pane shows an "AI Content Health" card.\n'
            '✓ 11 rows, one per chapter. Each row has a colour dot: green '
            '(clean), red (needs_review — placeholder scrubber found hits), '
            'amber (consistency warnings), grey (no draft).\n'
            '✓ Rows with hits are clickable → expand inline to show:\n'
            '   • Raw placeholder tokens as code badges with counts.\n'
            '   • Consistency drift entries formatted as [metric]: expected X / found Y with the excerpt.'
        ),
        traces='AI.docx §3 (cross-chapter consistency) + §8 (final automated validation). '
               'Kefitech.docx §3 + §8.',
        priority='High',
    ),
    dict(
        us_id='US-A03', title='Manage Level 1 component × section applicability',
        role='super_admin',
        story=(
            'As a super_admin, I want to change whether a DPR section is '
            'Mandatory, Optional or Hidden for a given component selection, '
            'so that I can tune the wizard for real project shapes without a '
            'code deploy.'
        ),
        criteria=(
            '✓ Navigate: sidebar → DPR Applicability (L1).\n'
            '✓ Grid renders: components as rows × section keys as columns.\n'
            '✓ Each cell is a dropdown of M / O / H.\n'
            '✓ Changing a cell fires a toast on save.\n'
            '✓ Navigate to DPR Projects → any project → the "Applicability Preview" '
            'card at the top of the page reflects the new decision without a page reload.'
        ),
        traces='Existing infrastructure. Included in UAT to confirm nothing '
               'regressed from the menu-seed and admin-viewer additions.',
    ),
    dict(
        us_id='US-A04', title='Manage Level 2 field-level rules',
        role='super_admin',
        story=(
            'As an admin, I want a dedicated page to add / edit / delete '
            'Level 2 rules (field-level show/hide inside a section), so that '
            'I no longer need Kefi Tech to run a seed script every time KAU '
            'wants to reshape the wizard.'
        ),
        criteria=(
            '✓ Navigate: sidebar → DPR Field Rules (L2). Empty state shows '
            '"No field rules yet" if nothing was seeded.\n'
            '✓ Click "Add rule". Dialog opens.\n'
            '✓ Section — typeahead searchable dropdown with all 22 sections.\n'
            '✓ Field name — when the picked section is in the introspection '
            'map (finance, utilities, baseline, etc.), field name is a '
            'searchable dropdown of real Django model fields (88 finance '
            'fields, 38 utilities fields, etc.). Otherwise a free-text input.\n'
            '✓ Recipe = component_in → chip picker for required_components (chips '
            'with removable ×, search box to add).\n'
            '✓ Recipe = field_equals → trigger_field + trigger_value inputs.\n'
            '✓ Save. Rule appears grouped under its section header on the list.\n'
            '✓ Edit — reopens dialog pre-filled. Delete — confirm prompt, then removed.'
        ),
        traces='P6.7 — Level 2 rule admin UI was missing before today. '
               'Level 1 always had UI; Level 2 was seed-script only.',
        priority='High',
    ),
    dict(
        us_id='US-A05', title='Find existing field rules quickly',
        role='super_admin',
        story=(
            'As an admin managing a growing rule set, I want search + '
            'grouping on the field rules page, so that I can find a '
            'specific rule in a list of 50+ without scrolling.'
        ),
        criteria=(
            '✓ Top-of-page search box filters live against field_name, '
            'notes, and section key.\n'
            '✓ Filter — section (searchable dropdown of 22 sections + "All").\n'
            '✓ Filter — recipe (component_in / field_equals / All).\n'
            '✓ Result count reads "N of M rules" so admin knows how much '
            'the filter is hiding.\n'
            '✓ Rules render grouped under section headers (FINANCE, UTILITIES, '
            'etc.) with per-section counts.\n'
            '✓ Empty-state text differentiates "no rules yet" from "no rules '
            'match the current filters".'
        ),
        traces='Follow-up UX polish for the Level 2 admin page.',
    ),
    dict(
        us_id='US-A06', title='Tune KAU DPR platform defaults',
        role='super_admin',
        story=(
            'As a super_admin, I want to edit the 24 DPR platform defaults '
            '(discount rate, tax rate, depreciation, interest fallback, etc.) '
            'so that KAU can update the appraisal baseline without a code deploy.'
        ),
        criteria=(
            '✓ Navigate: sidebar → DPR Config.\n'
            '✓ 24 rows visible. Each editable inline with a type / bounds check.\n'
            '✓ "Modified from default" badge shows on changed rows.\n'
            '✓ "Reset to default" action per row works.\n'
            '✓ Change discount_rate_pct from 12 to 13. Regenerate the sample DPR '
            '→ Project-at-a-Glance §1 row 15 now reads "Net Present Value (13.00%*)" '
            'and NPV amount recalculates.\n'
            '✓ Reset the value back to 12 after test.'
        ),
        traces='AI.docx §Financial Analysis / Assumptions. Kefitech.docx §2.',
    ),
    dict(
        us_id='US-A07', title='Curate the Knowledge Base that grounds AI narrative',
        role='super_admin',
        story=(
            'As a super_admin, I want to add / deactivate / supersede '
            'Knowledge Base entries (KAU PoP, schemes, SOPs, statutory refs), '
            'so that AI-generated narrative continues to be grounded in the '
            'right sources as they evolve.'
        ),
        criteria=(
            '✓ Navigate: sidebar → DPR Knowledge Base.\n'
            '✓ List renders paginated + searchable + filterable by source type.\n'
            '✓ Click "Add entry" → dialog with source type / name / URL / '
            'version / title / content / language.\n'
            '✓ Save → entry appears in list.\n'
            '✓ Deactivate — soft-deletes; deactivated entries are no longer picked '
            'up by AI retrieval.\n'
            '✓ Supersede — points the old entry to a new one for audit; retrieval '
            'switches to the new one.'
        ),
        traces='AI.docx §5 (technical/market info source-based). Existing infra.',
    ),
    dict(
        us_id='US-A08', title='Configure the Risk Matrix',
        role='super_admin',
        story=(
            'As a super_admin, I want to configure the probability × impact '
            'risk matrix so that KAU can adjust the classification thresholds '
            'without code changes.'
        ),
        criteria=(
            '✓ Navigate: sidebar → DPR Risk Matrix.\n'
            '✓ Matrix table renders: probability (rows) × impact (columns).\n'
            '✓ Each cell dropdown: Low / Moderate / High.\n'
            '✓ Change any cell → toast confirms save.\n'
            '✓ Existing DPR project risk assessment reflects the new '
            'classification on next regeneration.'
        ),
        traces='AI.docx §Risk Assessment. Existing infra.',
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# Module F — FPO user (project owner)
# ─────────────────────────────────────────────────────────────────────────────

FPO_STORIES = [
    dict(
        us_id='US-F01', title='Fill Promoter Profile detail on the wizard',
        role='FPO primary user',
        story=(
            'As an FPO, I want to enter my CEO name, qualification, area '
            'covered, PSC composition, board meeting frequency, women '
            'shareholding and landholding pattern on §2.2 Identification, '
            'so that the AI narrative uses my actual values rather than '
            'placeholders like "[Name of the CEO]".'
        ),
        criteria=(
            '✓ Navigate: FPO portal → DPR → Coconut Oil project → §2.2 Identification.\n'
            '✓ Scroll to bottom of section. New "8. Promoter Profile detail" card '
            'is visible.\n'
            '✓ 6 scalar fields (CEO name/qualification/experience, board freq, '
            'area, women shareholding %) + 1 textarea (landholding pattern) + '
            'a repeatable list for PSC members.\n'
            '✓ Board meeting frequency renders as searchable dropdown with '
            'Monthly / Quarterly / Half-yearly / Annually.\n'
            '✓ Click "+ Add member" — new row with name / role / affiliation '
            'inputs. "Remove" deletes.\n'
            '✓ Autosave fires 5s after last keystroke — header status flips '
            'to "All changes saved".\n'
            '✓ Regenerate the Promoter Profile chapter (via AI Content page). '
            'The narrative quotes your CEO name / qualification / years in prose. '
            'Nothing reads "[Name of the CEO]".'
        ),
        traces='AI.docx §Promoter Profile para 35. Migration 0100 + FE §8 card.',
        priority='High',
    ),
    dict(
        us_id='US-F02', title='Grounded narrative — every number matches the calc engine',
        role='FPO primary user',
        story=(
            'As an FPO, I want every ₹ amount, %, and ratio in the AI '
            'narrative to match what the calc engine produces, so that I '
            'can trust the DPR to be internally consistent when I hand it '
            'to a banker.'
        ),
        criteria=(
            '✓ Navigate: FPO portal → DPR → Coconut Oil project → AI Content.\n'
            '✓ Open the Executive Summary chapter. Read through.\n'
            '✓ Every ₹ amount matches Project-at-a-Glance §1 in the PDF.\n'
            '✓ IRR / NPV / DSCR quoted in prose match the Financial Appraisal §10 numbers.\n'
            '✓ Debt:Equity in narrative reads as "2.00:1" (or similar ratio form), '
            'not as raw rupee amounts.\n'
            '✓ No text like "[X MT per day]", "[Rs. X Lakhs]", "[Name of the CEO]" '
            'or any other bracketed placeholder token anywhere in any chapter.\n'
            '✓ Where a value genuinely isn\'t available (e.g. IRR didn\'t converge), '
            'narrative reads "Not available" in flowing prose — never a '
            'bracketed placeholder.'
        ),
        traces='AI.docx §1 + §2 + §6. Kefitech.docx §1 + §2.',
        priority='High',
    ),
    dict(
        us_id='US-F03', title='See a "review required" banner when the AI left gaps',
        role='FPO primary user',
        story=(
            'As an FPO, I want to know which chapters had placeholders that '
            'were auto-replaced with "Not available", so that I know exactly '
            'which wizard fields to go fill before regenerating.'
        ),
        criteria=(
            '✓ Force a needs_review flag by regenerating a chapter for a project '
            'with material gaps (or ask admin to seed a test project).\n'
            '✓ Sidebar shows a rose dot next to the flagged chapter.\n'
            '✓ Chapter view shows a "Review required" banner at the top '
            'with the raw placeholder tokens listed (e.g. `[Name of the CEO] × 3`).\n'
            '✓ Fix the missing wizard field. Regenerate that chapter. Rose '
            'dot + banner clear.'
        ),
        traces='AI.docx §1 (no unresolved placeholders). P1.5 + P4.4 UI surfacing.',
        priority='High',
    ),
    dict(
        us_id='US-F04', title='Edit AI-generated text in place with autosave',
        role='FPO primary user',
        story=(
            'As an FPO, I want to tweak sentences in an AI-generated chapter '
            'without clicking Save every time, so that quick corrections feel '
            'natural.'
        ),
        criteria=(
            '✓ Open any chapter on AI Content page.\n'
            '✓ Click "Edit in place". Textarea appears with current text.\n'
            '✓ Edit a sentence.\n'
            '✓ Click outside the textarea (blur). Save fires automatically. '
            'Toast confirms.\n'
            '✓ Click "Save" button explicitly — also works, no double-save.\n'
            '✓ Reload the page. The edit persists.'
        ),
        traces='AI.docx (editable AI output theme). P4.3 autosave-on-blur.',
    ),
    dict(
        us_id='US-F05', title='See neutral bank-appraisal language in the DPR',
        role='FPO primary user',
        story=(
            'As an FPO who plans to submit this DPR to a bank, I want the '
            'narrative to read like a professional appraisal document, so '
            'that no reviewer dismisses it as marketing fluff.'
        ),
        criteria=(
            '✓ Read the AI Executive Summary, Financial Analysis, Conclusion.\n'
            '✓ No occurrences of "highly bankable", "state-of-the-art", '
            '"uniquely positioned", "transformative", "compelling", '
            '"exceptional", "unmatched", "extraordinary", "impressive", '
            '"outstanding", "lucrative".\n'
            '✓ The Conclusion does NOT recommend loan sanction, subsidy '
            'approval, or project approval. It presents the financial '
            'indicators and their supporting evidence and stops there.'
        ),
        traces='Kefitech.docx §7 (neutral bank-appraisal language). P6.4 HARD RULE 11 + '
               'rewritten Conclusion brief.',
        priority='High',
    ),
    dict(
        us_id='US-F06', title='See system-default rates cited transparently in prose',
        role='FPO primary user',
        story=(
            'As an FPO, I want the narrative to say when a rate is a '
            'KAU-configured platform default rather than a value I entered, '
            'so that the banker knows which numbers require project-level '
            'testing.'
        ),
        criteria=(
            '✓ Read the Financial Analysis chapter.\n'
            '✓ At least 3-5 prose citations naming provenance, e.g.:\n'
            '   • "at the platform\'s default 12% discount rate"\n'
            '   • "platform-default corporate tax rate of 25.17%"\n'
            '   • "system-default general inflation rate of 5%"\n'
            '   • "platform-configured baseline parameters, specifically 10%"\n'
            '✓ These prose citations remain even in Final PDF mode.'
        ),
        traces='AI.docx §6 (source traceability). Kefitech.docx §6. P2.1 provenance + '
               'HARD RULE 10.',
        priority='High',
    ),
    dict(
        us_id='US-F07', title='Debt:Equity renders as x.xx:1 on the PDF',
        role='FPO primary user',
        story=(
            'As an FPO, I want the debt-to-equity ratio on Project-at-a-'
            'Glance shown in banking convention (e.g. 2.00 : 1), not as '
            'raw rupee amounts.'
        ),
        criteria=(
            '✓ Open the generated PDF.\n'
            '✓ Locate §1 Project-at-a-Glance row 11 "Debt : Equity ratio".\n'
            '✓ Value reads "2.00 : 1" (or the appropriate ratio for your data).\n'
            '✓ Never reads as "₹ 75,00,000 : ₹ 37,50,000".\n'
            '✓ When promoter contribution is zero, reads "Not available" — no '
            'division by zero, no error.'
        ),
        traces='AI.docx §2 + §Project at a Glance. Kefitech.docx §2.',
        priority='High',
    ),
    dict(
        us_id='US-F08', title='Depreciation Schedule fits inside landscape A4',
        role='FPO primary user',
        story=(
            'As an FPO, I want the Depreciation Schedule table (14 columns: '
            'asset class + rate + initial cost + 10 years + net block) to '
            'render fully on the PDF, so that no column is clipped or '
            'unreadable.'
        ),
        criteria=(
            '✓ Open the generated PDF.\n'
            '✓ Locate §5 Depreciation Schedule (SLM).\n'
            '✓ Every column edge is visible inside the page margins.\n'
            '✓ Header labels shortened ("Y1 depreciation" → "Y1", "Net block Y10" → "Net Y10") but still readable.\n'
            '✓ Font is legible (not so tight it needs a magnifying glass).\n'
            '✓ Same denser layout applied to P&L §7, Cash Flow §8, Balance Sheet §9.'
        ),
        traces='AI.docx §Depreciation Schedule (table not fully visible). P4.1 dense-table CSS.',
    ),
    dict(
        us_id='US-F09', title='Cost breakdown donut has a readable legend',
        role='FPO primary user',
        story=(
            'As an FPO, I want the cost breakdown donut chart on §1 to have '
            'a clean, readable legend, so that the banker understands '
            'exactly what each slice represents without squinting.'
        ),
        criteria=(
            '✓ Open the generated PDF.\n'
            '✓ Locate the cost breakdown donut in §1 Project-at-a-Glance area.\n'
            '✓ Layout: donut on the left, legend panel on the right.\n'
            '✓ Legend rows read "<Label> — ₹ <indian_comma_amount> (<pct>%)".\n'
            '✓ No wedge-side label collisions.\n'
            '✓ In-wedge % appears only on slices ≥ 4% (small slices left unlabeled).'
        ),
        traces='AI.docx §Fixed Capital Investment (donut visibility improvement). P4.2.',
    ),
    dict(
        us_id='US-F10', title='See operating break-even in the Financial Appraisal chapter',
        role='FPO primary user',
        story=(
            'As an FPO, I want the DPR to show the standard operating '
            'break-even calculation (fixed cost / contribution → break-even '
            'sales and capacity utilisation), so that the banker sees a '
            'proper appraisal metric — not just cumulative-PAT year.'
        ),
        criteria=(
            '✓ Open the generated PDF.\n'
            '✓ Locate §10 Financial Appraisal.\n'
            '✓ Below the appraisal-ratios summary, a new "Operating Break-even (Y1 basis)" '
            'mini-table renders with 5 rows:\n'
            '   • Fixed cost (Y1)\n'
            '   • Variable cost (Y1)\n'
            '   • Contribution margin (%)\n'
            '   • Break-even sales (₹)\n'
            '   • Break-even capacity utilisation (%)\n'
            '✓ A small italic footnote lists what fixed vs variable costs include.\n'
            '✓ Numbers reconcile: contribution margin × break-even sales ≈ fixed cost.'
        ),
        traces='Kefitech.docx §2 (correct break-even methodology). P6.1.',
        priority='High',
    ),
    dict(
        us_id='US-F11', title='See Key Assumptions Used before Limitations',
        role='FPO primary user',
        story=(
            'As an FPO, I want the DPR to explicitly list every KAU-'
            'configured platform assumption used in the calculations, so '
            'that the banker can see which numbers are baseline assumptions '
            'to be tested during due diligence.'
        ),
        criteria=(
            '✓ Open the generated PDF (preview mode).\n'
            '✓ Locate "Key Assumptions Used" section, right before Limitations & Guidelines.\n'
            '✓ Preamble paragraph explains these are platform defaults.\n'
            '✓ Table has 3 columns: Assumption / Value / Source.\n'
            '✓ 8 rows: NPV discount rate, corporate tax rate, general inflation, '
            'loan interest fallback, buildings/machinery/equipment depreciation, '
            'project cost variance tolerance.\n'
            '✓ Source column reads "KAU DPR platform default" for every row.'
        ),
        traces='AI.docx §6 (source traceability). Kefitech.docx §6. P2.1.',
    ),
    dict(
        us_id='US-F12', title='Preview PDF has provenance markers; final PDF is clean',
        role='FPO primary user',
        story=(
            'As an FPO reviewing my draft, I want to see visual provenance '
            'markers (orange asterisks, Source column) on the PREVIEW PDF, '
            'but I want them hidden on the FINAL PDF sent to bankers — '
            'because the banker copy should look clean.'
        ),
        criteria=(
            '✓ Generate the DPR in PREVIEW mode. Locate §1 Project-at-a-Glance row 15. '
            'Value reads "Net Present Value (12.00%*)" — small orange asterisk after 12%.\n'
            '✓ Locate Key Assumptions Used table. It has 3 columns including Source.\n'
            '✓ Generate the DPR in FINAL mode. Same row 15 reads "Net Present Value (12.00%)" — no asterisk.\n'
            '✓ Key Assumptions Used table has 2 columns only (Assumption + Value); Source column hidden.\n'
            '✓ Prose citations in AI narrative ("at the platform\'s default 12% rate") STAY in both modes — that\'s the transparent-in-prose part KAU asked to keep.'
        ),
        traces='Kefitech.docx §6 (preview vs final visibility). P6.3.',
    ),
    dict(
        us_id='US-F13', title='Final PDF blocked when the DPR is incomplete',
        role='FPO primary user',
        story=(
            'As an FPO, I want the platform to refuse to generate a FINAL '
            'DPR if any chapter has unresolved placeholders, hard numeric '
            'mismatches, or major operational-chain gaps, so that I don\'t '
            'accidentally send a broken DPR to a bank.'
        ),
        criteria=(
            '✓ Attempt to generate a FINAL DPR on a project with a chapter '
            'that has needs_review=true (e.g. by seeding a fake placeholder hit).\n'
            '✓ The generate action fails cleanly.\n'
            '✓ Error surface lists exactly which chapters need attention, with a '
            'reason per chapter — e.g. "conclusion: 3 placeholder token(s) '
            'auto-replaced… regenerate after filling the missing wizard field(s)".\n'
            '✓ Preview generation of the SAME project still works.\n'
            '✓ Regenerate the flagged chapter after filling the missing wizard field. '
            'Final generation now succeeds.'
        ),
        traces='Kefitech.docx §8 (pre-final automated validation). P6.5.',
        priority='High',
    ),
    dict(
        us_id='US-F14', title='Cross-chapter numbers stay consistent',
        role='FPO primary user',
        story=(
            'As an FPO, I want the same financial number (project cost, '
            'DSCR, IRR, etc.) to read identically in every chapter that '
            'mentions it, so that no reviewer catches me quoting "1.27 '
            'crore" in one chapter and "1.26 crore" in another.'
        ),
        criteria=(
            '✓ Regenerate all 11 narrative chapters.\n'
            '✓ Search each chapter\'s prose for the ₹ project cost. Every '
            'occurrence reads the same figure.\n'
            '✓ Same test for DSCR (avg), IRR%, NPV.\n'
            '✓ If a chapter DID drift, the admin viewer\'s AI Content Health card '
            'flags it under "Numbers that don\'t match the calc engine" with the '
            'exact excerpt.'
        ),
        traces='AI.docx §3 (cross-section consistency). Kefitech.docx §3. P2.3 consistency check.',
        priority='High',
    ),
    dict(
        us_id='US-F15', title='DSCR average excludes moratorium years',
        role='FPO primary user',
        story=(
            'As an FPO with a loan moratorium, I want the "Average DSCR" '
            'reported on §10 to reflect years with real P+I service only, '
            'so that the reviewer isn\'t misled by a moratorium year\'s '
            'interest-only inflated DSCR.'
        ),
        criteria=(
            '✓ On a project with moratorium_years > 0, open §10 Financial Appraisal.\n'
            '✓ DSCR-by-year table shows a computed DSCR for the moratorium year(s).\n'
            '✓ The "Average DSCR" row above the table is an average of ONLY '
            'the post-moratorium years (principal > 0).\n'
            '✓ Minimum DSCR also excludes moratorium years.\n'
            '✓ AI Financial Analysis chapter uses the same avg/min in prose.'
        ),
        traces='Kefitech.docx §2 (DSCR methodology). P6.2.',
    ),
    dict(
        us_id='US-F16', title='Wizard sections respect the applicability rules the admin set',
        role='FPO primary user',
        story=(
            'As an FPO, I want the wizard sidebar to only show sections '
            'relevant to my project components, so that I don\'t waste time '
            'filling irrelevant sections.'
        ),
        criteria=(
            '✓ Open Coconut Oil project → §2.3.2 Project Components. Tick "processing_value_addition".\n'
            '✓ Sidebar reveals the sections marked Mandatory (M) and Optional (O) for that component; hides those marked Hidden (H).\n'
            '✓ Untick the component. Hidden sections return.\n'
            '✓ Applicability decisions match the Level 1 matrix admin set on /admin/dpr-applicability.\n'
            '✓ Level 2 field-level rules also apply — inside a section, individual fields hide/show based on component checks OR sibling-field values (see US-A04 for admin-side setup).'
        ),
        traces='Existing infra + P6.7 Level 2 admin ability.',
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# Doc builder
# ─────────────────────────────────────────────────────────────────────────────

def build_document(output_path):
    doc = Document()

    _add_title_block(doc)
    _add_overview(doc)

    _add_section_header(doc, 'Module A — Admin (super_admin)')
    p = doc.add_paragraph()
    r = p.add_run(
        'Test these as super_admin. Reference project uuid across every '
        'story: 7a44dcf8-8b49-4fd1-a036-1f264b12f026.'
    )
    r.italic = True
    r.font.size = Pt(10)
    r.font.color.rgb = KAU_GREEN_RGB
    doc.add_paragraph('')

    for s in ADMIN_STORIES:
        _add_story(doc, **s)

    _add_section_header(doc, 'Module F — FPO user (project owner)')
    p = doc.add_paragraph()
    r = p.add_run(
        'Test these as the FPO primary user who owns the Coconut Oil DPR. '
        'Log in via the FPO portal — separate incognito window from the '
        'admin one is fine.'
    )
    r.italic = True
    r.font.size = Pt(10)
    r.font.color.rgb = KAU_GREEN_RGB
    doc.add_paragraph('')

    for s in FPO_STORIES:
        _add_story(doc, **s)

    _add_section_header(doc, 'Test coverage snapshot')
    p = doc.add_paragraph()
    r = p.add_run(
        f'Total stories: {len(ADMIN_STORIES) + len(FPO_STORIES)}. '
        f'Admin: {len(ADMIN_STORIES)}. FPO: {len(FPO_STORIES)}. '
        'Every story is testable via UI clicks only — no shell required. '
        'For CI-side regression the hermetic unit test suite '
        '(apps/fpo/tests_narrative_grounding.py) has 41 tests running in '
        '~200 ms with zero DB and zero LLM calls.'
    )
    r.font.size = Pt(10)

    doc.save(output_path)
    print(f'Wrote {output_path}')
    print(f'  Module A (Admin): {len(ADMIN_STORIES)} stories')
    print(f'  Module F (FPO):   {len(FPO_STORIES)} stories')


if __name__ == '__main__':
    build_document('Documents/DPR-RESPONSE/DPR-UAT-User-Stories.docx')
