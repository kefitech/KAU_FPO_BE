"""
Generate Phase 2 User Stories DOCX.

Matches the style of docs/KAU-FPO-User-Stories.docx (Phase 1) — KAU green
title, section headers in green bold, 5-row-per-story tables.

This file is the collab surface for every Phase 2 module. Right now only
Module 1 (DPR) is populated — other developers append their modules below
using the same US-XYY id convention (US-M01..US-M?? for Marketplace, etc.).

Output: docs/KAU-FPO-Phase2-User-Stories.docx

Run:
    source venv/bin/activate && python scripts/generate_dpr_user_stories_docx.py

Author (Module 1 / DPR): Athul Gopan kefi tech solutions
"""

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

KAU_GREEN = 'FF2E7D32'.lower()[2:]  # 2e7d32
KAU_PALE_GREEN = 'FFF1F8E9'.lower()[2:]  # f1f8e9
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
KAU_GREEN_RGB = RGBColor(0x2E, 0x7D, 0x32)


def _shade(cell, fill_hex):
    """Set cell background fill (hex without #)."""
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:fill'), fill_hex)
    shd.set(qn('w:val'), 'clear')
    tc_pr.append(shd)


def _set_col_widths(table, widths_cm):
    """Force column widths (cm). widths_cm is a list matching column count."""
    for i, w in enumerate(widths_cm):
        for row in table.rows:
            row.cells[i].width = Cm(w)


def _add_story(doc, us_id, title, role, story, criteria, priority='Medium', status='To Test'):
    """Append one 5-row story table matching the reference style."""
    table = doc.add_table(rows=5, cols=2)
    table.autofit = False
    _set_col_widths(table, [3.6, 12.0])

    # --- Row 0: header (US-ID | Title) — KAU green fill, white bold text
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

    # --- Rows 1-4: label | value pairs
    rows_content = [
        ('Role',                  role),
        ('Story',                 story),
        ('Acceptance Criteria',   criteria),
        ('Priority / Status',     f'{priority}  |  {status}'),
    ]
    for r_idx, (label, value) in enumerate(rows_content, start=1):
        # Label cell
        label_cell = table.rows[r_idx].cells[0]
        label_cell.text = ''
        lp = label_cell.paragraphs[0]
        lr = lp.add_run(label)
        lr.bold = True
        lr.font.size = Pt(9)
        _shade(label_cell, KAU_PALE_GREEN)
        label_cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP

        # Value cell — value may contain "\n" to make multi-line acceptance lists
        value_cell = table.rows[r_idx].cells[1]
        value_cell.text = ''
        first = True
        for line in value.split('\n'):
            p = value_cell.paragraphs[0] if first else value_cell.add_paragraph()
            run = p.add_run(line)
            run.font.size = Pt(10)
            first = False
        value_cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP

    # spacing paragraph after each story
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
        ('Phase 2 — User Stories & Test Scenarios', 14, True),
        ('Kerala Agricultural University  ·  Communication Centre', 10, False),
        ('Prepared by: Kefi Tech Solutions  ·  August 2026', 10, False),
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
        'This document is the acceptance-testing script for every Phase 2 module. '
        'Each module is written by its owning developer and appended below as a '
        'new "Module X — Name" section. Testers walk through the stories top to '
        'bottom; the same persona (Wayanad Spice Growers FPC, turmeric processing '
        'project) is used across modules wherever a shared FPO scenario is needed.'
    )
    r.font.size = Pt(10)
    doc.add_paragraph('')
    p = doc.add_paragraph()
    r = p.add_run(
        'Module status — Module 1 (DPR, Athul), Module 2 (Marketplace, Arunima), '
        'Module 3 (AI Recommendations, Aravind), Module 5 (GIS, Aravind) and '
        'Module 8 (Auto-Translate, Aleena) are populated below. Modules 4 (Chat), '
        '6 (Analytics) and 7 (CBBO Portal) will be appended by their respective owners.'
    )
    r.italic = True
    r.font.size = Pt(10)
    doc.add_paragraph('')
    p = doc.add_paragraph()
    r = p.add_run(
        'Test login (existing FPO user): anjitha.contact+pokemon@gmail.com / Test@1234. '
        'Reference scenario used across DPR stories: Wayanad Spice Growers FPC — '
        'turmeric processing + packaging unit at Sultan Bathery, ₹95 lakh project '
        '(40% promoter · 45% bank loan · 15% NABARD grant), 250 member farmers.'
    )
    r.italic = True
    r.font.size = Pt(10)


def _add_placeholder_module(doc, module_num, module_name, hint):
    _add_section_header(doc, f'Module {module_num} — {module_name}')
    p = doc.add_paragraph()
    r = p.add_run(
        f'(placeholder — owner: TBD. This section will be populated by the {module_name} '
        f'module owner using the same 5-row story-table format. {hint})'
    )
    r.italic = True
    r.font.size = Pt(10)
    r.font.color.rgb = RGBColor(0x70, 0x70, 0x70)
    doc.add_paragraph('')


# ─────────────────────────────────────────────────────────────────────────────
# DPR user-story catalogue
# ─────────────────────────────────────────────────────────────────────────────

FPO_STORIES = [
    dict(
        us_id='US-D01', title='Create a new DPR project',
        role='FPO primary user',
        story=(
            'As an FPO primary user, I want to create a new DPR project by giving it a title, '
            'so that I can start filling out the 22-step wizard for a new business initiative.'
        ),
        criteria=(
            '✓ "New DPR Project" button visible on /fpo/dpr\n'
            '✓ Dialog accepts a title and creates the project on submit\n'
            '✓ On success the user is redirected to the wizard shell (/fpo/dpr/<uuid>/)\n'
            '✓ The new project appears in the FPO projects list with status "Draft"'
        ),
        priority='High',
    ),
    dict(
        us_id='US-D02', title='List my DPR projects',
        role='FPO user',
        story=(
            'As an FPO user, I want to see the list of DPR projects my FPO has created, '
            'so that I can resume working on any project or check its status.'
        ),
        criteria=(
            '✓ /fpo/dpr shows a table of all DPR projects owned by my FPO\n'
            '✓ Table columns: Title, Status, Created, Updated\n'
            '✓ Clicking a row opens the wizard at the last-visited section\n'
            '✓ Deleted / other FPOs’ projects are not visible'
        ),
    ),
    dict(
        us_id='US-D03', title='Fill §2.2 Project Identification',
        role='FPO user',
        story=(
            'As an FPO user, I want to fill Project Identification (title, type, description, '
            'primary + secondary commodities, objectives, outcomes), so that my DPR has a valid header.'
        ),
        criteria=(
            '✓ 7 fields per §2.2 spec are present and required (except secondary commodities)\n'
            '✓ Brief description enforces min 50 characters; readiness shows current length\n'
            '✓ Commodity dropdown lists all 83 rows including the 20 Kerala additions\n'
            '✓ Multi-select checkboxes save immediately; "Other" free-text captured\n'
            '✓ When all 7 required fields are filled the readiness panel turns green'
        ),
        priority='High',
    ),
    dict(
        us_id='US-D04', title='Fill Project Components (§2.3.2)',
        role='FPO user',
        story=(
            'As an FPO user, I want to select the components proposed under the project '
            '(processing, branding, cold storage, etc.), so that the DPR reflects my project scope.'
        ),
        criteria=(
            '✓ All active DPR components appear as checkboxes\n'
            '✓ Multi-select works; "Other" produces an inline text field\n'
            '✓ Component group headings visible (Processing, Storage, etc.)\n'
            '✓ Readiness turns green after at least one component is selected'
        ),
    ),
    dict(
        us_id='US-D05', title='Fill Nature of Business, Investment, Products',
        role='FPO user',
        story=(
            'As an FPO user, I want to enter Nature of Business, Proposed Investment amounts, '
            'and my Product/Service catalogue, so that the financial + product foundation is set.'
        ),
        criteria=(
            '✓ Nature is a single-select dropdown from master data\n'
            '✓ Investment fields accept ₹ amounts with 2-decimal precision\n'
            '✓ Products opens a modal with a wide layout (max-w-5xl) for a comfortable form\n'
            '✓ Added products appear in the table immediately after Save (useWatch subscription)\n'
            '✓ Nested modal allows edit + delete of existing products'
        ),
    ),
    dict(
        us_id='US-D06', title='Pick project location on the map',
        role='FPO user',
        story=(
            'As an FPO user, I want to pin my project location on an interactive Kerala map, '
            'so that GPS coordinates are captured without me typing lat/long manually.'
        ),
        criteria=(
            '✓ Leaflet map loads centred on Kerala\n'
            '✓ Clicking the map places a pin and populates latitude + longitude fields\n'
            '✓ Pincode search, "Use my location" (GPS), and drag-to-adjust all work\n'
            '✓ State, district, block, local body form fields save independently'
        ),
    ),
    dict(
        us_id='US-D07', title='Fill Baseline — Yes/No conditional branch',
        role='FPO user',
        story=(
            'As an FPO user, I want the Baseline section to show the correct sub-form '
            'depending on whether I select "Yes — existing enterprise" or "No — new venture".'
        ),
        criteria=(
            '✓ Radio choice reveals the matching sub-form (Yes → 8 fields, No → 5 fields)\n'
            '✓ Toggling the radio triggers an immediate save; readiness re-runs at once\n'
            '✓ The other branch’s errors are cleared once branch changes\n'
            '✓ "Existing products" + "Existing installed capacity" show inline red errors when empty on the Yes branch'
        ),
    ),
    dict(
        us_id='US-D08', title='Fill Capacity & Production',
        role='FPO user',
        story=(
            'As an FPO user, I want to enter production capacity, working schedule, process '
            'description with word count, and future expansion, so that the DPR captures how I produce.'
        ),
        criteria=(
            '✓ Process description shows live word + character count\n'
            '✓ Peak / lean season months toggle visually as chips\n'
            '✓ Production loss + future expansion checkboxes reveal their conditional sub-forms\n'
            '✓ Backend readiness errors highlight the offending field label in red'
        ),
    ),
    dict(
        us_id='US-D09', title='Fill Raw Material with deep nested modal',
        role='FPO user',
        story=(
            'As an FPO user, I want to add each raw material via a wide modal covering source, '
            'availability calendar, quality standards, and price basis, so that supply is fully documented.'
        ),
        criteria=(
            '✓ Modal opens wide (max-w-5xl) with clear section separators\n'
            '✓ Commodity dropdown uses the shared MasterLookup source\n'
            '✓ Selecting "Others (Specify)" reveals the free-text specifier\n'
            '✓ Availability months + quality parameters are multi-select checkboxes\n'
            '✓ Saved row appears in the parent table immediately'
        ),
    ),
    dict(
        us_id='US-D10', title='Fill Market Assessment with live channel balancing',
        role='FPO user',
        story=(
            'As an FPO user, I want the Market Assessment card to show a running total of '
            'my channel share percentages, so that I can balance them to exactly 100% without guessing.'
        ),
        criteria=(
            '✓ D. Marketing Channels card title shows "Total: xx.xx%"\n'
            '✓ Amber warning when total ≠ 100 (± 1)\n'
            '✓ Balance auto-clears the moment I bring the sum to 100%\n'
            '✓ All 5 nested lists (Products, Buyers, Channels, Competitors, Risks) persist rows after save'
        ),
    ),
    dict(
        us_id='US-D11', title='Fill Technology Selection with inner risks',
        role='FPO user',
        story=(
            'As an FPO user, I want to add each proposed technology and its own inline risks + '
            'mitigations, so that technical feasibility is captured together with residual risk.'
        ),
        criteria=(
            '✓ Technology modal groups fields into logical panels (A. Details, B. Reasons, C. Process, etc.)\n'
            '✓ "Add risk" button inside the modal appends an inline mini-form\n'
            '✓ Risks are saved as part of the parent technology row'
        ),
    ),
    dict(
        us_id='US-D12', title='Fill Land & Site with multi-parcel + utilities',
        role='FPO user',
        story=(
            'As an FPO user, I want to add multiple land parcels, describe utilities, and '
            'declare statutory approvals, so that site suitability is fully documented.'
        ),
        criteria=(
            '✓ Multi-parcel table with ownership dropdown; "Others" reveals specifier\n'
            '✓ Distance-to-market fields accept km with 2-decimal precision\n'
            '✓ Water source + statutory approvals are multi-select checkbox groups\n'
            '✓ "Future expansion" checkbox toggles its own sub-form'
        ),
    ),
    dict(
        us_id='US-D13', title='Fill Civil Works & Plant & Machinery',
        role='FPO user',
        story=(
            'As an FPO user, I want to add proposed buildings + site development items + '
            'machinery line items with unit costs, so that capex breakdown is itemised.'
        ),
        criteria=(
            '✓ Civil: existing + proposed buildings + site development are separate lists\n'
            '✓ Machinery: item name, quantity, unit cost, supporting assets all captured\n'
            '✓ Cost estimate section allows "Basis of estimate" with "Others" specifier'
        ),
    ),
    dict(
        us_id='US-D14', title='Fill Utilities across 4 conditional sub-cards',
        role='FPO user',
        story=(
            'As an FPO user, I want each utility (electricity, water, refrigeration, effluent) '
            'to expand only if I check "required", so that I don’t see irrelevant fields.'
        ),
        criteria=(
            '✓ 4 conditional cards (Electricity, Water, Refrigeration, Effluent) hide/show correctly\n'
            '✓ Fuel + Waste + Renewable Energy nested lists persist rows after save\n'
            '✓ Communication + Fire safety are multi-select checkbox groups\n'
            '✓ "Water source = Others" reveals the specifier input'
        ),
    ),
    dict(
        us_id='US-D15', title='Fill Human Resources with employee categories',
        role='FPO user',
        story=(
            'As an FPO user, I want to add employee designations, department-wise staffing, '
            'training requirements, and statutory compliance, so that HR planning is complete.'
        ),
        criteria=(
            '✓ 3 nested lists (Employee categories, Departments, Training requirements) work\n'
            '✓ Existing employee sub-form toggles under "FPO has existing employees" checkbox\n'
            '✓ Future manpower expansion is conditional\n'
            '✓ Welfare + Statutory compliance are multi-select checkbox groups with "Others" specifier'
        ),
    ),
    dict(
        us_id='US-D16', title='Fill Finance with live Cost vs MoF balance badge',
        role='FPO user',
        story=(
            'As an FPO user, I want a live badge that shows whether my Means of Finance total '
            'equals my Project Cost total, so that I can balance the two sides in real time.'
        ),
        criteria=(
            '✓ Project Cost card shows "Total: ₹x,xx,xxx" that updates as I type\n'
            '✓ MoF card shows two totals + a Balanced ✓ / MoF short by ₹x / MoF over by ₹x badge\n'
            '✓ Badge is green when the two match (within ₹1) and amber otherwise\n'
            '✓ Loan + subsidy + operational-history sub-forms are all conditional\n'
            '✓ Revenue assumptions nested list persists rows after save'
        ),
        priority='High',
    ),
    dict(
        us_id='US-D17', title='Fill Compliance, ESS, Implementation, Risk',
        role='FPO user',
        story=(
            'As an FPO user, I want to complete the remaining sections (Statutory Compliance, '
            'Environment & Sustainability, Implementation Plan, Risk Assessment) via consistent nested-list UIs, '
            'so that finishing the wizard feels predictable.'
        ),
        criteria=(
            '✓ Compliance items list, pending-legal-issues Yes/No conditional both work\n'
            '✓ ESS: 6 nested lists (resources, conservation, safety, sustainability, impacts, climate risks)\n'
            '✓ Implementation: activities, milestones, agencies + procurement method + monitoring frequency\n'
            '✓ Risk: 6 category cards; a section-top banner shows the list-level warning when no risks are added'
        ),
    ),
    dict(
        us_id='US-D18', title='Save vs Autosave vs Discard',
        role='FPO user',
        story=(
            'As an FPO user, I want three save behaviours: explicit Save (immediate), autosave '
            '(5 s after last change), and Discard (revert to last saved), so that I never lose data or accidentally overwrite.'
        ),
        criteria=(
            '✓ Sticky footer shows a Save + Discard button and a status indicator (Saved / Unsaved / Saving / Failed)\n'
            '✓ Autosave fires 5 s after the last keystroke on any field\n'
            '✓ Save button flushes immediately, bypassing the 5 s debounce\n'
            '✓ Discard resets the form to the last-saved server state and cancels the pending autosave\n'
            '✓ Status label updates ("just now", "3 s ago", …) as time passes'
        ),
    ),
    dict(
        us_id='US-D19', title='Inline field-level error highlighting',
        role='FPO user',
        story=(
            'As an FPO user, I want backend readiness errors to appear right under the field '
            'that caused them, so that I do not need to hunt through the bottom panel to find the problem.'
        ),
        criteria=(
            '✓ Failed fields get a red label + a red inline message ("X is required.")\n'
            '✓ Warnings show in amber under the field\n'
            '✓ List-level errors (e.g. "At least one X must be added") render on the NestedListCard header\n'
            '✓ Errors clear on the next successful save that fixes the problem'
        ),
    ),
    dict(
        us_id='US-D20', title='Load a partially-filled DPR without losing state',
        role='FPO user',
        story=(
            'As an FPO user, I want to close the browser and reopen the wizard later and see all '
            'my previously saved data (dropdowns, checkboxes, nested rows), so that my work never disappears.'
        ),
        criteria=(
            '✓ On reload, every field reflects the value stored on the server\n'
            '✓ Multi-select checkboxes / dropdowns / arrays hydrate reliably (useWatch subscriptions)\n'
            '✓ Conditional branches (Yes/No radios, "required" checkboxes) show the correct sub-form on reload'
        ),
        priority='High',
    ),
    dict(
        us_id='US-D21', title='See sidebar completion dots update in real time',
        role='FPO user',
        story=(
            'As an FPO user, I want each sidebar section to show a coloured dot indicating '
            'completeness, so that I know at a glance which sections still need attention.'
        ),
        criteria=(
            '✓ Empty section: grey dot\n'
            '✓ Section with backend errors: red dot\n'
            '✓ Section with warnings only: amber dot\n'
            '✓ Section complete, no errors, no warnings: green dot\n'
            '✓ Dot updates immediately after each save'
        ),
    ),
    dict(
        us_id='US-D22', title='Fill objectives / outcomes with "Other" free-text',
        role='FPO user',
        story=(
            'As an FPO user, I want to type in an "Other" objective / outcome when the standard '
            'checkbox list does not cover my case, so that the DPR captures my exact intent.'
        ),
        criteria=(
            '✓ project_objectives_other and expected_outcomes_other fields accept any string ≤ 500 chars\n'
            '✓ Backend readiness accepts the "other" text as satisfying the "at least one" requirement'
        ),
    ),
    dict(
        us_id='US-D23', title='See a "no risks identified" warning banner',
        role='FPO user',
        story=(
            'As an FPO user, I want a visible amber banner when the risk section has no entries, '
            'so that I remember to add risks across all 6 categories before generation.'
        ),
        criteria=(
            '✓ Banner text matches the backend validator message ("No risks identified …")\n'
            '✓ Banner disappears once at least one risk is added\n'
            '✓ Sidebar risk-section dot goes amber (warning), not red (error)'
        ),
    ),
    dict(
        us_id='US-D24', title='Fully-completed DPR shows all-green readiness',
        role='FPO user',
        story=(
            'As an FPO user, I want to see all 22 sidebar sections with green dots after '
            'completing the walkthrough, so that I know my DPR is ready for downstream generation.'
        ),
        criteria=(
            '✓ All 22 sections report is_complete: true, errors: 0\n'
            '✓ (Optional) risk warning may still show if no risks were added\n'
            '✓ No blocking issues anywhere in the wizard'
        ),
        priority='High',
    ),
]

MARKETPLACE_STORIES = [
    dict(
        us_id='US-M01', title='Create a product listing',
        role='FPO user',
        story=(
            'As an FPO user, I want to create a new product listing capturing name (EN + ML), '
            'commodity type, quantity, unit, price, quality certification, and availability dates, '
            'so that buyers can discover our produce with all the information they need.'
        ),
        criteria=(
            '✓ Form captures: name_en, name_ml, commodity, quantity, unit, price, quality_certification, availability_from, availability_to\n'
            '✓ New listing is created with status = draft by default\n'
            '✓ Commodity dropdown sources from the shared MasterLookup (category=commodity)\n'
            '✓ Quantity + price validate as positive numbers with sensible max limits\n'
            '✓ Availability dates enforce from ≤ to'
        ),
        priority='High',
    ),
    dict(
        us_id='US-M02', title='Publish a listing when ready',
        role='FPO user',
        story=(
            'As an FPO user, I want to publish my draft listing when it’s ready, so that it becomes '
            'visible to buyers per its public/private setting.'
        ),
        criteria=(
            '✓ Publish action transitions the listing from draft → active\n'
            '✓ Only listings in draft status can be published (attempting on active/sold returns 400)\n'
            '✓ Once active, the listing appears on the Market Hub (if public) or the internal FPO listing (if private)'
        ),
        priority='High',
    ),
    dict(
        us_id='US-M03', title='Edit a listing while draft or active',
        role='FPO user',
        story=(
            'As an FPO user, I want to edit my listing while it’s still a draft or currently active, '
            'so that I can update quantity, price, or availability as conditions change.'
        ),
        criteria=(
            '✓ Editable fields: name (EN + ML), quantity, unit, price, quality_certification, availability dates, visibility\n'
            '✓ Edits allowed only while status is draft or active\n'
            '✓ Editing an active listing keeps its status = active (does not revert to draft)\n'
            '✓ Sold listings are read-only (no edit form shown)'
        ),
    ),
    dict(
        us_id='US-M04', title='Mark a listing as sold',
        role='FPO user',
        story=(
            'As an FPO user, I want to mark my active listing as sold when the produce has been '
            'bought, so that it stops appearing on the Market Hub as available.'
        ),
        criteria=(
            '✓ Only listings with status = active can be marked sold (attempts on draft/sold return 400)\n'
            '✓ Once sold, the listing is read-only — cannot be edited or deleted\n'
            '✓ Sold listing remains in the FPO’s history but is filtered out of the public Market Hub'
        ),
        priority='High',
    ),
    dict(
        us_id='US-M05', title='Delete a draft listing',
        role='FPO user',
        story=(
            'As an FPO user, I want to delete a listing while it’s still a draft, so that I can '
            'discard experimental entries without cluttering my dashboard.'
        ),
        criteria=(
            '✓ Delete is allowed only when status = draft\n'
            '✓ Deleting a published (active) or sold listing returns 400 with a clear message\n'
            '✓ Prevents the "listing disappeared" scenario where a buyer had already seen an active listing'
        ),
    ),
    dict(
        us_id='US-M06', title='Control listing visibility (public vs private)',
        role='FPO user',
        story=(
            'As an FPO user, I want to choose whether a listing is visible on the public Market Hub '
            'or kept private within the platform, so that I can pilot pricing or restrict certain '
            'produce to closed-circle buyers.'
        ),
        criteria=(
            '✓ Each listing has a visibility flag: public | private\n'
            '✓ Public listings appear on the Market Hub page (no login required to browse)\n'
            '✓ Private listings are visible only to authenticated platform users\n'
            '✓ Flag can be toggled while the listing is draft or active'
        ),
    ),
    dict(
        us_id='US-M07', title='Only approved FPOs can list',
        role='FPO user whose registration is pending',
        story=(
            'As an FPO whose registration is not yet approved, when I attempt to create a product '
            'listing the system should reject me, so that unapproved FPOs cannot pollute the Market Hub.'
        ),
        criteria=(
            '✓ Create-listing endpoint returns 403 when the caller’s FPO.status is not "approved"\n'
            '✓ Clear error message: "Your FPO registration must be approved before listing products"\n'
            '✓ Business rule is enforced server-side (not just hidden in UI)'
        ),
        priority='High',
    ),
    dict(
        us_id='US-M08', title='State-machine transitions are enforced',
        role='platform',
        story=(
            'As the platform, I want product-listing state transitions to be strictly enforced, so '
            'that no invalid moves (e.g. publishing a sold listing, deleting an active one) are possible.'
        ),
        criteria=(
            '✓ Allowed transitions: draft → active (publish), active → sold (mark_sold), draft → deleted (delete)\n'
            '✓ Any other transition returns HTTP 400 with a descriptive error\n'
            '✓ Server enforces the state machine — not the client'
        ),
    ),
]


GIS_STORIES = [
    dict(
        us_id='US-G01', title='Browse the 14 Kerala districts',
        role='FPO user or admin',
        story=(
            'As a platform user, I want to browse the list of Kerala districts served by the platform, '
            'so that I can see which regions are supported.'
        ),
        criteria=(
            '✓ GET /api/gis/districts/ returns all 14 real Kerala districts with codes + names\n'
            '✓ GET /api/gis/districts/{code}/ returns detail for a single district\n'
            '✓ District list is used as a filter across admin dashboards (FPOs, DPRs, etc.)'
        ),
    ),
    dict(
        us_id='US-G02', title='Browse agro-climatic zones',
        role='FPO user or admin',
        story=(
            'As a platform user, I want to browse Kerala’s agro-climatic zones with their recommended '
            'crops + soil types, so that I understand what my region is suited for.'
        ),
        criteria=(
            '✓ GET /api/gis/zones/ returns all seeded zones with name, boundary, recommended crops, soil type\n'
            '✓ GET /api/gis/zones/{code}/ returns detail for one zone\n'
            '✓ 5 placeholder zones seeded (real names, crops, soil types)'
        ),
    ),
    dict(
        us_id='US-G03', title='Auto-detect zone from GPS coordinates',
        role='FPO user',
        story=(
            'As an FPO user, I want the platform to auto-detect which agro-climatic zone my project '
            'falls in based on my registered coordinates, so that I don’t have to pick it manually.'
        ),
        criteria=(
            '✓ POST /api/gis/detect-zone/ accepts { latitude, longitude } and returns the matching zone\n'
            '✓ Detection uses spatial containment against seeded zone polygons\n'
            '✓ Returns a clear error if the coordinates fall outside all seeded zones'
        ),
    ),
    dict(
        us_id='US-G04', title='See my FPO location + detected zone',
        role='FPO user',
        story=(
            'As an FPO user, I want a single endpoint that returns my FPO’s registered coordinates + '
            'the detected zone, so that the frontend can render location context in one call.'
        ),
        criteria=(
            '✓ GET /api/gis/fpo-location/ returns { latitude, longitude, zone_code, zone_name, district }\n'
            '✓ Zone auto-populates from the FPO’s coordinates via FPOZoneAssignment cache\n'
            '✓ Response is fast (cached), no repeat spatial computation per request'
        ),
        priority='High',
    ),
    dict(
        us_id='US-G05', title='Draw my farm cultivation boundary on a map',
        role='FPO user',
        story=(
            'As an FPO user, I want to click on a Leaflet map to draw the actual boundary of my '
            'cultivation area, so that we capture the real farm shape (not just a single point).'
        ),
        criteria=(
            '✓ CultivationAreaMap component lets me click to add polygon vertices\n'
            '✓ POST /api/gis/cultivation-area/me/ persists the polygon\n'
            '✓ Server computes area in hectares from the polygon and returns it in the response\n'
            '✓ GET /api/gis/cultivation-area/me/ returns my saved polygon on reload\n'
            '✓ DELETE removes the polygon; UI resets to click-to-draw mode\n'
            '✓ Zone + soil + weather panels update to reflect the newly drawn plot'
        ),
        priority='High',
    ),
    dict(
        us_id='US-G06', title='View live weather at my location',
        role='FPO user',
        story=(
            'As an FPO user, I want to see current weather conditions (temperature, humidity, '
            'rainfall) at my project location, so that I can plan field work.'
        ),
        criteria=(
            '✓ GET /api/gis/weather/me/ returns cached weather from FPOWeatherSnapshot\n'
            '✓ WeatherCard displays temperature, humidity, rainfall\n'
            '✓ Card auto-refreshes when the drawn cultivation area changes\n'
            '✓ Live data comes from OpenWeatherMap (integration verified)'
        ),
    ),
    dict(
        us_id='US-G07', title='Refresh weather on demand',
        role='FPO user',
        story=(
            'As an FPO user, I want to manually refresh the weather reading, so that I can force a '
            'fresh fetch when the cached snapshot feels stale.'
        ),
        criteria=(
            '✓ POST /api/gis/weather/me/refresh/ calls OpenWeatherMap now and updates the snapshot\n'
            '✓ WeatherCard shows a spinner during refresh and updates on completion\n'
            '✓ Rate limiting protects against abuse (endpoint-level throttle)'
        ),
        priority='Low',
    ),
    dict(
        us_id='US-G08', title='Weather falls back gracefully when API is down',
        role='FPO user',
        story=(
            'As an FPO user, I want to still see a plausible weather estimate when OpenWeatherMap is '
            'unavailable, so that the dashboard never breaks.'
        ),
        criteria=(
            '✓ On upstream failure, a season/zone-based estimate is returned instead of an error\n'
            '✓ Simulated response is flagged clearly (is_simulated: true)\n'
            '✓ WeatherCard shows a small "estimated" badge when is_simulated is true'
        ),
    ),
    dict(
        us_id='US-G09', title='Admin — Configure OpenWeatherMap credentials',
        role='super admin',
        story=(
            'As a super admin, I want to configure the OpenWeatherMap API key through the admin '
            'dashboard, so that I don’t need a code deploy to rotate credentials.'
        ),
        criteria=(
            '✓ Key stored encrypted via existing ExternalAPISettings (same system as PAN/GSTIN/CIN)\n'
            '✓ Test connectivity action verifies the key against a probe endpoint\n'
            '✓ Rotating the key takes effect on the next weather call without server restart'
        ),
    ),
]


RECOMMENDATIONS_STORIES = [
    dict(
        us_id='US-R01', title='Request a crop recommendation',
        role='FPO user',
        story=(
            'As an FPO user, I want to request an AI-driven crop recommendation, so that I can see '
            'which crops the model suggests for my zone, soil, season, and existing commodity profile.'
        ),
        criteria=(
            '✓ POST /api/recommendations/me/request/ returns instantly (async)\n'
            '✓ CropRecommendation row is created with status=pending, then processing, then completed\n'
            '✓ Recommendation logic actually scores crops (zone + soil + season + FPO commodities)\n'
            '✓ Ranking is NOT a static per-zone list — different inputs yield different orderings'
        ),
        priority='High',
    ),
    dict(
        us_id='US-R02', title='See a "generating…" state while background task runs',
        role='FPO user',
        story=(
            'As an FPO user, I want the recommendation UI to show clear "generating…" progress after '
            'I request, so that I understand the result is coming without needing to guess when.'
        ),
        criteria=(
            '✓ CropRecommendationDisplay renders a spinner + explanatory text while status is pending/processing\n'
            '✓ UI auto-polls or subscribes and switches to the result panel once status=completed\n'
            '✓ If status=failed, the UI shows a "retry" action with the error reason'
        ),
    ),
    dict(
        us_id='US-R03', title='View my latest crop recommendation',
        role='FPO user',
        story=(
            'As an FPO user, I want to retrieve my most recent completed recommendation without '
            're-running the model, so that repeat visits feel instant.'
        ),
        criteria=(
            '✓ GET /api/recommendations/me/ returns the cached most-recent CropRecommendation\n'
            '✓ Response includes the model version used and the input snapshot for traceability\n'
            '✓ If no completed recommendation exists yet, response is a friendly empty state'
        ),
    ),
    dict(
        us_id='US-R04', title='Get notified when a recommendation is ready',
        role='FPO user',
        story=(
            'As an FPO user, I want an email + in-app notification the moment my recommendation is '
            'ready, so that I don’t have to keep the page open.'
        ),
        criteria=(
            '✓ On task completion, a notification is queued via the existing notification pipeline\n'
            '✓ Email + in-app inbox entry both delivered\n'
            '✓ Notification includes a deep-link back to the recommendation'
        ),
    ),
    dict(
        us_id='US-R05', title='Submit 1-5 star feedback + comment',
        role='FPO user',
        story=(
            'As an FPO user, I want to rate the recommendation 1-5 and leave a comment, so that '
            'KAU can improve the model based on ground truth.'
        ),
        criteria=(
            '✓ POST /api/recommendations/me/feedback/ accepts rating (int 1-5) + comment (text)\n'
            '✓ UI renders a star-picker + a free-text field\n'
            '✓ Once submitted, the feedback is disabled/read-only for that recommendation'
        ),
    ),
    dict(
        us_id='US-R06', title='New AI Recommendations page with 3 tabs',
        role='FPO user',
        story=(
            'As an FPO user, I want a single AI Recommendations page with tabs for Crop Recommendation, '
            'Business Plan Guidance, and DPR Generation, so that I can see all AI-assisted features in one place.'
        ),
        criteria=(
            '✓ /fpo/recommendations page renders three tabs\n'
            '✓ Crop Recommendation tab is fully functional today\n'
            '✓ Business Plan Guidance + DPR Generation tabs render "Coming soon" placeholders (Phase 4 dependency)'
        ),
    ),
    dict(
        us_id='US-R07', title='Admin — List ML model versions',
        role='super admin or sub admin',
        story=(
            'As an admin, I want to see every registered ML model version with pagination + status, '
            'so that I know which model is currently active.'
        ),
        criteria=(
            '✓ GET /api/admin/ml-models/ returns paginated list\n'
            '✓ Row shows version, uploaded_at, is_active, size, uploaded_by\n'
            '✓ Active model version clearly highlighted in the UI'
        ),
    ),
    dict(
        us_id='US-R08', title='Admin — Register / upload a new model version',
        role='super admin',
        story=(
            'As a super admin, I want to upload and register a new model version through the admin UI, '
            'so that I don’t need a code deploy to ship an improved model.'
        ),
        criteria=(
            '✓ POST /api/admin/ml-models/ accepts model artefact + metadata\n'
            '✓ New version appears in the list as inactive by default (does not disrupt live serving)\n'
            '✓ Failed uploads (bad checksum, wrong format) return a clear error'
        ),
        priority='High',
    ),
    dict(
        us_id='US-R09', title='Admin — Activate an ML model version',
        role='super admin',
        story=(
            'As a super admin, I want to click "activate" on a model version and have the FastAPI '
            'service pick it up, so that switching models is a single click.'
        ),
        criteria=(
            '✓ POST /api/admin/ml-models/{id}/activate/ marks the version as active\n'
            '✓ Django notifies the FastAPI recommendation service directly to reload\n'
            '✓ Any previously active model is deactivated in the same transaction\n'
            '✓ Subsequent recommendations use the newly activated version'
        ),
        priority='High',
    ),
    dict(
        us_id='US-R10', title='Admin — Review FPO feedback by model version',
        role='super admin or sub admin',
        story=(
            'As an admin, I want to browse FPO feedback filtered by the model version that produced the '
            'recommendation, so that I can compare model performance across versions.'
        ),
        criteria=(
            '✓ GET /api/admin/recommendations/feedback/ paginated with filter ?model_version=\n'
            '✓ Row shows FPO, rating, comment, model version, recommendation id\n'
            '✓ Aggregate summary (avg rating per model version) visible at the top of the page'
        ),
    ),
]


AUTO_TRANSLATE_STORIES = [
    dict(
        us_id='US-150', title='Trigger Auto-Translate for a Language',
        role='super admin',
        story=(
            'As a super admin, I want to trigger auto-translation for a language, so that I '
            'can populate hundreds of translation strings in minutes instead of manually preparing '
            'an Excel upload.'
        ),
        criteria=(
            '✓ POST /api/admin/translations/auto-translate/ accepts language_code and an optional category_code\n'
            '✓ Omitting category_code translates all categories\n'
            '✓ English strings for the selected scope are sent to Claude in batches of 50 keys\n'
            '✓ System prompt instructs an agricultural domain, Kerala government context, and formal register\n'
            '✓ Response returns a summary: { created, skipped, failed, failed_keys }\n'
            '✓ Only super_admin can call this endpoint'
        ),
        priority='High',
    ),
    dict(
        us_id='US-151', title='Re-running Auto-Translate Does Not Duplicate Work',
        role='super admin',
        story=(
            'As a super admin, I want re-running auto-translate to skip strings that are already '
            'translated, so that I don’t waste API calls or overwrite existing translations by accident.'
        ),
        criteria=(
            '✓ Keys that already have a translation in the target language are skipped, not overwritten\n'
            '✓ Running the same language + category twice returns created: 0 and skipped: N on the second run\n'
            '✓ No duplicate Translation rows are created for the same key + language'
        ),
        priority='High',
    ),
    dict(
        us_id='US-152', title='Auto-Translated Strings Require Review Before Going Live',
        role='super admin',
        story=(
            'As a super admin, I want every auto-translated string saved as unverified, so that '
            'incorrect or awkward machine translations don’t reach FPO users before I’ve reviewed them.'
        ),
        criteria=(
            '✓ Every Translation row created by auto-translate has is_verified=False\n'
            '✓ Unverified strings are visibly flagged as such in the admin translations list\n'
            '✓ POST /api/admin/translations/{id}/verify/ marks a string as verified (is_verified becomes True)\n'
            '✓ Verification is a distinct, deliberate admin action — it does not happen automatically'
        ),
        priority='High',
    ),
    dict(
        us_id='US-153', title='Restrict Auto-Translate to Super Admin Only',
        role='sub admin',
        story=(
            'As a sub admin, I should not be able to trigger auto-translation, so that only super '
            'admins control when and how AI-generated content is added to the platform’s language data.'
        ),
        criteria=(
            '✓ Sub-admin call to POST /api/admin/translations/auto-translate/ returns HTTP 403\n'
            '✓ No Translation rows are created as a result of a sub-admin’s attempt\n'
            '✓ Super admin remains the only role that can trigger this endpoint'
        ),
        priority='High',
    ),
    dict(
        us_id='US-154', title='Clear Error for an Invalid or Inactive Language',
        role='super admin',
        story=(
            'As a super admin, I want a clear error if I try to auto-translate into a language that '
            'doesn’t exist or isn’t active, so that I don’t get a confusing failure with no explanation.'
        ),
        criteria=(
            '✓ Auto-translate with a non-existent language code (e.g. xx) returns HTTP 400 with a clear error message\n'
            '✓ The target language must exist and be active in the Language table before translating\n'
            '✓ No partial Translation rows are created when the request is rejected for an invalid language'
        ),
        priority='Medium',
    ),
    dict(
        us_id='US-155', title='Failed Translations Are Reported for Manual Retry',
        role='super admin',
        story=(
            'As a super admin, I want to see which specific keys failed to translate, so that I can '
            'retry just those instead of re-running the whole batch.'
        ),
        criteria=(
            '✓ Keys that fail (e.g. Claude API timeout) are counted in failed and listed by key in failed_keys\n'
            '✓ Successful keys in the same batch are still saved even if other keys in that batch fail\n'
            '✓ Failed keys are not silently dropped — they remain untranslated and available for a manual retry'
        ),
        priority='Medium',
    ),
    dict(
        us_id='US-156', title='Auto-Translated Strings Appear via the Public Translations Endpoint',
        role='FPO user / any platform user',
        story=(
            'As a platform user, I want newly auto-translated strings to be retrievable through the '
            'public translations endpoint, so that the new language becomes usable on the platform '
            'once translations exist.'
        ),
        criteria=(
            '✓ GET /api/translations/public/?lang=hi returns Hindi strings after an auto-translate run\n'
            '✓ Response includes the keys translated in that run'
        ),
        priority='Medium',
    ),
]


ADMIN_STORIES = [
    dict(
        us_id='US-D25', title='Admin — Filter list of every FPO’s DPR projects',
        role='super_admin or sub_admin',
        story=(
            'As an admin, I want to see all DPR projects across every FPO with filters by status, '
            'district, and search-by-name/title, so that I can quickly locate a project I need to review.'
        ),
        criteria=(
            '✓ /admin/dpr/projects shows a paginated table\n'
            '✓ Filters: Status (Draft / In Progress / Submitted / Generated), District (Kerala 14), Search\n'
            '✓ Table columns: FPO name, DPR title, District, Tier, Status (colored badge), Updated\n'
            '✓ Each row has a "View" button that opens the detail viewer\n'
            '✓ Endpoint returns 403 for fpo_manager (permission enforced)'
        ),
        priority='High',
    ),
    dict(
        us_id='US-D26', title='Admin — View any DPR project read-only',
        role='super_admin or sub_admin',
        story=(
            'As an admin, I want to open one DPR project and see every section’s data in a '
            'read-only viewer, so that I can review the FPO’s submission without accidentally editing it.'
        ),
        criteria=(
            '✓ Header card shows FPO name, application_id, district, tier, office email + phone\n'
            '✓ Sidebar lists all 22 sections with completion dots (green / amber / red / grey)\n'
            '✓ Right pane renders the selected section’s data:\n'
            '   • Primitives → 2-column key-value grid\n'
            '   • Arrays of objects → table\n'
            '   • Arrays of strings → chips\n'
            '✓ Read-only — no edit / save controls'
        ),
    ),
    dict(
        us_id='US-D27', title='Admin — See backend readiness per section',
        role='admin',
        story=(
            'As an admin, I want the read-only viewer to show the backend readiness errors + '
            'warnings for each section, so that I can flag issues back to the FPO if needed.'
        ),
        criteria=(
            '✓ For each section: an error / warning / all-clear panel appears above the data\n'
            '✓ Field names accompany each message ("<field> — <message>")\n'
            '✓ Sidebar dot colour matches the readiness state'
        ),
    ),
    dict(
        us_id='US-D28', title='Admin — Manage DPR master data (33 categories)',
        role='super_admin or sub_admin',
        story=(
            'As an admin, I want CRUD access to the 33 DPR master categories '
            '(fuel types, project components, buyer types, etc.), so that I can maintain the dropdowns '
            'FPOs see in the wizard without a code deploy.'
        ),
        criteria=(
            '✓ /admin/dpr/master-data lists all 33 categories grouped logically\n'
            '✓ For each: add, edit, activate / deactivate, reorder\n'
            '✓ Bilingual labels (label_en + label_ml) editable per row\n'
            '✓ Change is reflected in FPO wizard within cache TTL (< 24 h; can be manually cleared)'
        ),
    ),
    dict(
        us_id='US-D29', title='Admin — Placeholder pages for Financial Assumptions + AI Services',
        role='admin',
        story=(
            'As an admin, I want /admin/dpr-config and /admin/ai-services to render clear '
            '"Coming in Phase 4" pages instead of 404-ing, so that the sidebar links are honest and I '
            'know what is coming.'
        ),
        criteria=(
            '✓ Both routes return HTTP 200 and render a placeholder page\n'
            '✓ Page lists the planned assumption groups / services\n'
            '✓ Page cites the KAU RCD items blocking each\n'
            '✓ "Back to DPR" navigation works'
        ),
        priority='Low',
    ),
    dict(
        us_id='US-D30', title='Admin — Search filter respects district code',
        role='admin',
        story=(
            'As an admin, I want the district filter on the DPR projects list to accept the '
            'Kerala 3-letter district code (e.g. TRS, WYD), so that URLs are shareable and typed filters work.'
        ),
        criteria=(
            '✓ ?district=WYD narrows the list to Wayanad FPOs\n'
            '✓ Case-insensitive on the query string\n'
            '✓ Combined with ?status= + ?search= without conflict\n'
            '✓ Pagination preserves the filter across pages'
        ),
        priority='Low',
    ),
]


def build_document(output_path):
    doc = Document()
    _add_title_block(doc)
    _add_overview(doc)

    # Module 1 — DPR (this file's owner)
    _add_section_header(doc, 'Module 1 — DPR (Detailed Project Report)')
    _p = doc.add_paragraph()
    _r = _p.add_run('Developed by Athul Gopan · Kefi Tech Solutions')
    _r.italic = True
    _r.font.size = Pt(10)
    _r.font.color.rgb = KAU_GREEN_RGB
    doc.add_paragraph('')

    # ── Scope block: what works · what to test · what we need from KAU ──
    _p = doc.add_paragraph()
    _r = _p.add_run('What works today')
    _r.bold = True
    _r.font.size = Pt(11)
    _r.font.color.rgb = KAU_GREEN_RGB
    for line in [
        '✓ FPO wizard — all 22 steps (§2.2 + §2.3.2 through §2.3.22) with save + autosave + discard',
        '✓ Backend readiness validators for every section, feeding inline field-level errors + warnings',
        '✓ Hybrid save model — explicit Save button (immediate) plus 5-second autosave safety net',
        '✓ Nested-list modals (Products, Raw Material, Market channels, Machinery, HR, Risk, etc.)',
        '✓ Live totals — MoF ↔ Project Cost balance badge, Marketing channels % running sum',
        '✓ Kerala Leaflet map for Project Location (click-to-pin, GPS, pincode + Nominatim search)',
        '✓ Admin list of every FPO’s DPR projects with status / district / search filters',
        '✓ Admin read-only detail viewer with per-section readiness dots and generic data renderer',
        '✓ Admin CRUD for the 33 DPR master categories (dropdowns editable without a code deploy)',
        '✓ 83 commodities in MasterLookup (63 KAU baseline + 20 Kerala-specific additions)',
    ]:
        pp = doc.add_paragraph()
        rr = pp.add_run(line)
        rr.font.size = Pt(10)
    doc.add_paragraph('')

    _p = doc.add_paragraph()
    _r = _p.add_run('What needs to be tested')
    _r.bold = True
    _r.font.size = Pt(11)
    _r.font.color.rgb = KAU_GREEN_RGB
    _p = doc.add_paragraph()
    _r = _p.add_run(
        'The 30 stories below (US-D01 to US-D30) drive the full acceptance suite. '
        'Walking them top to bottom exercises: every wizard section, every save/discard flow, '
        'every conditional branch, every inline error, every live totals badge, admin oversight '
        'list + detail, backend readiness endpoints, and the master data CRUD. Successful pass = '
        'all 22 sidebar sections green in FPO view AND same 22 green in admin view.'
    )
    _r.font.size = Pt(10)
    doc.add_paragraph('')

    _p = doc.add_paragraph()
    _r = _p.add_run('What we need from KAU (blocking) — Phase 3 / 4 / 6 work paused')
    _r.bold = True
    _r.font.size = Pt(11)
    _r.font.color.rgb = KAU_GREEN_RGB
    _p = doc.add_paragraph()
    _r = _p.add_run(
        'All 25 questions were sent as Documents/KAU_FPO_DPR_RCD_KefiTech_v1.0.docx. Until those '
        'answers arrive, the following DPR capabilities cannot be built:'
    )
    _r.font.size = Pt(10)
    for line in [
        '• Dynamic questionnaire — which sections auto-show / hide based on selected components (blocks Phase 3, RCD item A.1)',
        '• Financial calc engine — P&L, IRR, NPV, DSCR, break-even, sensitivity analysis (blocks Phase 4, RCD items A.3 + B.4 + B.6 + B.9)',
        '• AI narrative sections — 17 Claude-generated chapters for the DPR (blocks Phase 4, RCD items A.2 + B.5)',
        '• DPR PDF template — bank-ready Word / PDF output (blocks Phase 6, depends on Phase 4 outputs + RCD item B.7)',
        '• Component master list finalisation — 20 Kerala commodities are provisional pending RCD item B.2',
    ]:
        pp = doc.add_paragraph()
        rr = pp.add_run(line)
        rr.font.size = Pt(10)
    _p = doc.add_paragraph()
    _r = _p.add_run(
        'Successful pass of the stories below therefore represents 100% of the currently buildable '
        'DPR scope. Phase 3 / 4 / 6 work resumes the moment KAU RCD answers land.'
    )
    _r.italic = True
    _r.font.size = Pt(10)
    doc.add_paragraph('')

    _add_section_header(doc, '1.1 FPO Wizard (22 steps)')
    for s in FPO_STORIES:
        _add_story(doc, **s)
    _add_section_header(doc, '1.2 Admin Oversight + Master Data')
    for s in ADMIN_STORIES:
        _add_story(doc, **s)

    # Module 8 — Auto-Translate (Admin Translation Automation, Aleena)
    _add_section_header(doc, 'Module 8 — Auto-Translate (Admin Translation Automation)')
    _p = doc.add_paragraph()
    _r = _p.add_run('Developed by Aleena · Kefi Tech Solutions')
    _r.italic = True
    _r.font.size = Pt(10)
    _r.font.color.rgb = KAU_GREEN_RGB
    doc.add_paragraph('')
    for s in AUTO_TRANSLATE_STORIES:
        _add_story(doc, **s)

    # Modules 2-7 — populated where owners have delivered, placeholders otherwise

    # Module 2 — Marketplace (Arunima)
    _add_section_header(doc, 'Module 2 — Marketplace (Product Listings)')
    _p = doc.add_paragraph()
    _r = _p.add_run('Developed by Arunima · Kefi Tech Solutions')
    _r.italic = True
    _r.font.size = Pt(10)
    _r.font.color.rgb = KAU_GREEN_RGB
    doc.add_paragraph('')
    for s in MARKETPLACE_STORIES:
        _add_story(doc, **s)

    # Module 3 — AI Recommendations (Aravind)
    _add_section_header(doc, 'Module 3 — AI Recommendations')
    _p = doc.add_paragraph()
    _r = _p.add_run('Developed by Aravind · Kefi Tech Solutions')
    _r.italic = True
    _r.font.size = Pt(10)
    _r.font.color.rgb = KAU_GREEN_RGB
    doc.add_paragraph('')
    for s in RECOMMENDATIONS_STORIES:
        _add_story(doc, **s)
    _add_placeholder_module(doc, 4, 'Chat / Chatbot',
        'Suggested id prefix: US-C01, US-C02, …')

    # Module 5 — GIS (Aravind)
    _add_section_header(doc, 'Module 5 — GIS (Agro-Climatic Zones + Cultivation Area + Weather)')
    _p = doc.add_paragraph()
    _r = _p.add_run('Developed by Aravind · Kefi Tech Solutions')
    _r.italic = True
    _r.font.size = Pt(10)
    _r.font.color.rgb = KAU_GREEN_RGB
    doc.add_paragraph('')
    for s in GIS_STORIES:
        _add_story(doc, **s)
    _add_placeholder_module(doc, 6, 'Analytics',
        'Suggested id prefix: US-A01, US-A02, …')
    _add_placeholder_module(doc, 7, 'CBBO Portal',
        'Suggested id prefix: US-B01, US-B02, …')

    doc.save(output_path)
    print(f'Wrote {output_path}')
    print(f'  Module 1 (DPR — Athul):                       {len(FPO_STORIES)} FPO + {len(ADMIN_STORIES)} admin = {len(FPO_STORIES) + len(ADMIN_STORIES)} stories')
    print(f'  Module 2 (Marketplace — Arunima):             {len(MARKETPLACE_STORIES)} stories')
    print(f'  Module 3 (AI Recommendations — Aravind):      {len(RECOMMENDATIONS_STORIES)} stories')
    print(f'  Module 5 (GIS — Aravind):                     {len(GIS_STORIES)} stories')
    print(f'  Module 8 (Auto-Translate — Aleena):           {len(AUTO_TRANSLATE_STORIES)} stories')
    print('  Modules 4 / 6 / 7: placeholders (other developers to fill in)')


if __name__ == '__main__':
    # Remove any stale prior generation before writing
    import os
    for stale in ('docs/KAU-FPO-DPR-User-Stories.docx',):
        if os.path.exists(stale):
            os.remove(stale)
            print(f'Removed stale {stale}')
    build_document('docs/KAU-FPO-Phase2-User-Stories.docx')
