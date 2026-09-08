"""
Generate the M/O/H applicability matrix Excel template for KAU (per pre-UAT
reply §3.1 + covering email dated 2026-09-09).

Structure:
  * Sheet 1 — "M-O-H Matrix" — 40 components (rows) × 22 sections (columns)
    - Cells pre-filled with 'O' (Optional = current default)
    - Cells with a seeded rule pre-filled with that rule's value (currently
      only 2: Cold Storage + Custom Hiring Centre → 'H' for raw-material)
    - Data validation on each cell: only 'M' / 'O' / 'H' accepted
    - Colour-coded conditional formatting: green M, blue O, red H
    - Frozen header row + component-code column so scroll doesn't lose orientation
  * Sheet 2 — "Instructions" — one-page primer:
    - What M / O / H mean
    - When each fires (Level-1 applicability engine reads from the FPO's
      selected project components)
    - How KAU should mark cells + return the file (or edit live at
      /admin/dpr-applicability)
    - Note that any cell KAU leaves blank stays as the current default (O)

Kefi Tech sends this to KAU as a starter; KAU populates progressively
during UAT — no need to complete the full matrix before UAT kickoff.

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/generate_moh_matrix_template.py').read())
    generate_moh_matrix_template()
    "

Output:
    Documents/KAU_FPO_DPR_MoH_Matrix_Template_v1.xlsx
"""

import os


def generate_moh_matrix_template():
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.formatting.rule import CellIsRule
    from apps.database.models.dpr.applicability import DPRComponentApplicability
    from apps.database.models import DPRComponent
    from apps.fpo.services.dpr.rule_engine import ALL_SECTION_KEYS

    # ── Pull components + seeded rules ──
    components = list(
        DPRComponent.objects
        .filter(is_active=True)
        .order_by('group', 'order', 'code')
    )
    seeded = {}  # (component_code, section_key) → 'M'/'O'/'H'
    for r in DPRComponentApplicability.objects.select_related('component'):
        seeded[(r.component.code, r.data_element_key)] = r.applicability

    # Human labels for section keys (title-case + underscore→space)
    def _section_label(key: str) -> str:
        # Handle a few section-specific renderings
        pretty = {
            'hr':  'HR',
            'ess': 'ESS (Env / Social / Sustainability)',
            'nature-of-business':  'Nature of Business',
            'raw-material':        'Raw Material',
        }
        return pretty.get(key, key.replace('-', ' ').replace('_', ' ').title())

    # Human labels for component groups
    _group_labels = {
        'primary_production':        'A. Primary Production',
        'processing_value_addition': 'B. Processing & Value Addition',
        'storage_post_harvest':      'C. Storage & Post-Harvest',
        'marketing_business_dev':    'D. Marketing & Business Development',
        'service_enterprises':       'E. Service-Based Enterprises',
        'supporting_infrastructure': 'F. Supporting Infrastructure',
    }
    _group_order = list(_group_labels.keys())
    components.sort(key=lambda c: (_group_order.index(c.group) if c.group in _group_order else 99, c.order, c.code))

    # ── Workbook ──
    wb = Workbook()
    ws = wb.active
    ws.title = 'M-O-H Matrix'

    # Brand colours
    header_fill = PatternFill('solid', fgColor='1F3864')  # KAU navy
    header_font = Font(bold=True, color='FFFFFF', size=10, name='Calibri')
    group_fill  = PatternFill('solid', fgColor='E86C1A')  # KAU orange
    group_font  = Font(bold=True, color='FFFFFF', size=11, name='Calibri')
    body_font   = Font(size=10, name='Calibri')
    thin_border = Border(
        left=Side('thin', color='D9D9D9'),
        right=Side('thin', color='D9D9D9'),
        top=Side('thin', color='D9D9D9'),
        bottom=Side('thin', color='D9D9D9'),
    )

    # ── Header row ──
    ws.cell(row=1, column=1, value='Component Code').fill = header_fill
    ws.cell(row=1, column=1).font = header_font
    ws.cell(row=1, column=2, value='Component Name').fill = header_fill
    ws.cell(row=1, column=2).font = header_font
    for i, sec in enumerate(ALL_SECTION_KEYS, start=3):
        cell = ws.cell(row=1, column=i, value=_section_label(sec))
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True, text_rotation=45)
        cell.border = thin_border

    ws.cell(row=1, column=1).alignment = Alignment(vertical='center', wrap_text=True)
    ws.cell(row=1, column=2).alignment = Alignment(vertical='center', wrap_text=True)

    # ── Body rows: components grouped + group separator rows ──
    row_idx = 2
    prev_group = None
    for comp in components:
        # Group header row
        if comp.group != prev_group:
            group_label = _group_labels.get(comp.group, comp.group)
            ws.merge_cells(start_row=row_idx, start_column=1,
                           end_row=row_idx, end_column=2 + len(ALL_SECTION_KEYS))
            gcell = ws.cell(row=row_idx, column=1, value=group_label)
            gcell.fill = group_fill
            gcell.font = group_font
            gcell.alignment = Alignment(horizontal='left', vertical='center', indent=1)
            ws.row_dimensions[row_idx].height = 22
            row_idx += 1
            prev_group = comp.group

        # Component row
        code_cell = ws.cell(row=row_idx, column=1, value=comp.code)
        code_cell.font = Font(bold=True, size=9, name='Calibri', color='595959')
        code_cell.border = thin_border
        name_cell = ws.cell(row=row_idx, column=2, value=comp.label_en)
        name_cell.font = body_font
        name_cell.border = thin_border

        for i, sec in enumerate(ALL_SECTION_KEYS, start=3):
            value = seeded.get((comp.code, sec), 'O')  # 'O' = default (Optional)
            c = ws.cell(row=row_idx, column=i, value=value)
            c.alignment = Alignment(horizontal='center', vertical='center')
            c.font = Font(size=10, bold=(value != 'O'), name='Calibri')
            c.border = thin_border

        row_idx += 1

    last_data_row = row_idx - 1

    # ── Data validation on the M/O/H cells ──
    dv = DataValidation(
        type='list',
        formula1='"M,O,H"',
        allow_blank=False,
        showErrorMessage=True,
        errorTitle='Invalid value',
        error='Please enter M (Mandatory), O (Optional), or H (Hidden).',
        promptTitle='M/O/H applicability',
        prompt='M = section is mandatory for this component\n'
               'O = section is optional (shown but not required) — default\n'
               'H = section is hidden for this component',
    )
    dv.add(f'C2:{get_column_letter(2 + len(ALL_SECTION_KEYS))}{last_data_row}')
    ws.add_data_validation(dv)

    # ── Conditional formatting: colour-code M / O / H ──
    matrix_range = f'C2:{get_column_letter(2 + len(ALL_SECTION_KEYS))}{last_data_row}'
    ws.conditional_formatting.add(
        matrix_range,
        CellIsRule(operator='equal', formula=['"M"'],
                   fill=PatternFill('solid', fgColor='C6EFCE'),  # green
                   font=Font(bold=True, color='006100', name='Calibri', size=10)),
    )
    ws.conditional_formatting.add(
        matrix_range,
        CellIsRule(operator='equal', formula=['"H"'],
                   fill=PatternFill('solid', fgColor='FFC7CE'),  # red
                   font=Font(bold=True, color='9C0006', name='Calibri', size=10)),
    )
    # 'O' stays default (no highlight) — keeps the sheet readable

    # ── Column widths + freeze ──
    ws.column_dimensions['A'].width = 32
    ws.column_dimensions['B'].width = 38
    for i in range(3, 3 + len(ALL_SECTION_KEYS)):
        ws.column_dimensions[get_column_letter(i)].width = 12
    ws.row_dimensions[1].height = 90
    ws.freeze_panes = 'C2'

    # ── Sheet 2: Instructions ──
    inst = wb.create_sheet('Instructions')
    inst_rows = [
        ('KAU-FPO DPR Applicability Matrix — Instructions', True),
        ('Prepared by Kefi Tech per KAU pre-UAT reply §3.1 (2026-09-08)', False),
        ('', False),
        ('WHAT THIS SHEET DOES', True),
        ('The DPR module\'s Dynamic Questionnaire engine uses this matrix to decide which sections '
         'each FPO project sees. For every project component the FPO selects on §2.2 Identification, '
         'the engine looks up this matrix to determine each of the 22 sections\' visibility.', False),
        ('', False),
        ('THREE POSSIBLE VALUES PER CELL', True),
        ('M (Mandatory)  — section is required for this component; blocks DPR submission if empty.', False),
        ('O (Optional)   — section is shown but not required. This is the DEFAULT — leave cells as O '
         'unless there is a clear rule.', False),
        ('H (Hidden)     — section is not shown at all for this component. Use for sections that are '
         'genuinely inapplicable (e.g. "Raw Material" is hidden for Cold Storage projects since a '
         'cold storage doesn\'t process a raw material — it just stores end-product).', False),
        ('', False),
        ('HOW MULTIPLE COMPONENTS COMBINE', True),
        ('An FPO can select multiple components (e.g. Cold Storage + Warehouse). When components '
         'disagree on a section, the ENGINE picks the STRICTEST value in this order: M beats O, and '
         'O beats H. So a section is hidden only when ALL selected components mark it H.', False),
        ('', False),
        ('HOW TO POPULATE THIS SHEET', True),
        ('1. Cells are already pre-filled with the current defaults (mostly O, with two H rules '
         'currently seeded: Cold Storage + Custom Hiring Centre both hide Raw Material).', False),
        ('2. Change any cell to M, O, or H using the dropdown (data validation is applied).', False),
        ('3. You do NOT need to complete the entire matrix before UAT — populate progressively for '
         'the components you are most interested in first. Any cell left as O stays as the '
         'current default.', False),
        ('4. Save + return this file to Kefi Tech, OR edit rules live at '
         'http://<server>/admin/dpr-applicability (Level-1 matrix is fully editable there).', False),
        ('', False),
        ('DPR SECTIONS (columns) — QUICK REFERENCE', True),
        ('identification    §2.2 — Project identification (always shown, never optional)', False),
        ('components        §2.3.1 — FPO picks project components (always shown, never optional)', False),
        ('nature-of-business §2.3.2 — Nature of business', False),
        ('investment        §2.3.4 — Proposed investment (top-line estimate)', False),
        ('products          §2.3.5 — Products & services', False),
        ('location          §2.3.6 — Project location + parcels', False),
        ('rationale         §2.3.7 — Project rationale', False),
        ('baseline          §2.3.8 — Baseline / current state', False),
        ('capacity          §2.3.11 — Production capacity', False),
        ('raw-material      §2.3.9 — Raw material sourcing', False),
        ('market            §2.3.10 — Market analysis', False),
        ('technology        §2.3.12 — Technology selection', False),
        ('site              §2.3.13 — Land + site suitability', False),
        ('civil             §2.3.14 — Buildings + civil works', False),
        ('machinery         §2.3.15 — Plant + machinery + equipment', False),
        ('utilities         §2.3.16 — Utilities + support services', False),
        ('hr                §2.3.17 — Human resources', False),
        ('finance           §2.3.18 — Financial info + means of finance', False),
        ('compliance        §2.3.19 — Statutory approvals + licences', False),
        ('ess               §2.3.20 — Environmental + social + sustainability', False),
        ('implementation    §2.3.21 — Implementation plan', False),
        ('risk              §2.3.22 — Risk assessment + mitigation', False),
        ('', False),
        ('QUESTIONS?', True),
        ('Athul Gopan  |  Kefi Tech Solutions  |  athul.gopan@kefitech.com', False),
    ]
    for i, (text, is_header) in enumerate(inst_rows, start=1):
        cell = inst.cell(row=i, column=1, value=text)
        if is_header:
            cell.font = Font(bold=True, size=12, color='1F3864', name='Calibri')
        else:
            cell.font = Font(size=10, name='Calibri')
        cell.alignment = Alignment(wrap_text=True, vertical='top')

    inst.column_dimensions['A'].width = 120

    # ── Save ──
    out_dir = '/home/athul_dasp/Desktop/AGRI-THRISSUR/kau-fpo-backend/Documents'
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, 'KAU_FPO_DPR_MoH_Matrix_Template_v1.xlsx')
    wb.save(out_path)

    size = os.path.getsize(out_path)
    print(f'✅ Generated M/O/H matrix template')
    print(f'   Path      : {out_path}')
    print(f'   Size      : {size / 1024:.1f} KB')
    print(f'   Rows      : {len(components)} components (grouped in 6 categories)')
    print(f'   Columns   : {len(ALL_SECTION_KEYS)} DPR sections')
    print(f'   Total cells: {len(components) * len(ALL_SECTION_KEYS):,} '
          f'(2 pre-filled H rules, rest default O)')
    print(f'   Attach this file to the KAU reply email alongside the 3 sample PDFs.')
