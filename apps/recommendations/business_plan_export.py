"""
Business plan export — PDF + Word downloads of an FPO's AI business plan.

Same look as the DPR report (apps/fpo/templates/dpr/report.html and
apps/fpo/services/dpr/docx.py): KAU navy + orange, FPO-first cover page,
boxed disclaimer, navy-header tables, page header/footer.

Public entry points:
    * render_business_plan_pdf(plan)  -> bytes   (WeasyPrint)
    * render_business_plan_docx(plan) -> bytes   (python-docx)
    * build_filename(plan, ext)       -> str

The document is written in the plan's own language (one BusinessPlan row per
FPO per language), so headings come from LABELS, not the request language.
"""
from __future__ import annotations

import io

from django.template.loader import render_to_string
from django.utils import timezone

from apps.recommendations.business_plan import build_profile

# Section headings and fixed text, per plan language. Headings match the
# fpo_recommendations.bp_* UI translations so the download reads like the tab.
LABELS = {
    'en': {
        'doc_title': 'Business Plan',
        'subtitle': 'Prepared under the KAU-FPO Linkage Programme',
        'farmer_producer_org': 'Farmer Producer Organisation',
        'kerala': 'Kerala',
        'financial_year': 'Financial year',
        'generated_on': 'Generated',
        'primary_commodities': 'Primary commodities',
        'secondary_commodities': 'Secondary commodities',
        'location': 'Location',
        'attribution': 'Prepared using the Kerala Agricultural University FPO platform',
        'ai_label': 'AI-generated guidance · KAU platform',
        'disclaimer_title': 'Disclaimer',
        'disclaimer': (
            'This business plan was generated with AI on the Kerala Agricultural University (KAU) '
            'FPO platform from the FPO\'s registered commodities and location. It is guidance only — '
            'figures are indicative and KAU has not approved, certified or endorsed its contents. '
            'Validate it with your board, KAU experts and a detailed project report before investing.'
        ),
        'page': 'Page',
        'of': 'of',
        'executive_summary': 'Executive Summary',
        'commodity_focus': 'Commodity Focus',
        'commodity': 'Commodity',
        'role': 'Role',
        'opportunity': 'Opportunity',
        'role_primary': 'Primary',
        'role_secondary': 'Secondary',
        'location_advantages': 'Location Advantages',
        'business_activities': 'Business Activities',
        'activity': 'Activity',
        'description': 'Description',
        'market_strategy': 'Market Strategy',
        'target_markets': 'Target markets',
        'channels': 'Sales channels',
        'branding': 'Branding',
        'operations_plan': 'Operations Plan',
        'financial_outline': 'Financial Outline',
        'estimated_investment': 'Estimated investment',
        'working_capital': 'Working capital',
        'revenue_streams': 'Revenue streams',
        'funding_sources': 'Funding sources & schemes',
        'risks': 'Risks & Mitigation',
        'risk': 'Risk',
        'mitigation': 'Mitigation',
        'action_plan': 'Action Plan',
        'period': 'Period',
        'activities': 'Activities',
        'key_recommendations': 'Key Recommendations',
    },
    'ml': {
        'doc_title': 'ബിസിനസ് പ്ലാൻ',
        'subtitle': 'KAU-FPO ലിങ്കേജ് പ്രോഗ്രാമിന് കീഴിൽ തയ്യാറാക്കിയത്',
        'farmer_producer_org': 'കർഷക ഉത്പാദക സംഘടന',
        'kerala': 'കേരളം',
        'financial_year': 'സാമ്പത്തിക വർഷം',
        'generated_on': 'തയ്യാറാക്കിയത്',
        'primary_commodities': 'പ്രാഥമിക ഉൽപ്പന്നങ്ങൾ',
        'secondary_commodities': 'ദ്വിതീയ ഉൽപ്പന്നങ്ങൾ',
        'location': 'സ്ഥലം',
        'attribution': 'കേരള കാർഷിക സർവകലാശാല FPO പ്ലാറ്റ്ഫോം ഉപയോഗിച്ച് തയ്യാറാക്കിയത്',
        'ai_label': 'AI തയ്യാറാക്കിയ മാർഗ്ഗനിർദ്ദേശം · KAU പ്ലാറ്റ്ഫോം',
        'disclaimer_title': 'നിരാകരണം',
        'disclaimer': (
            'FPO-യുടെ രജിസ്റ്റർ ചെയ്ത ഉൽപ്പന്നങ്ങളുടെയും സ്ഥലത്തിന്റെയും അടിസ്ഥാനത്തിൽ കേരള കാർഷിക '
            'സർവകലാശാലയുടെ (KAU) FPO പ്ലാറ്റ്ഫോമിൽ AI ഉപയോഗിച്ച് തയ്യാറാക്കിയതാണ് ഈ ബിസിനസ് പ്ലാൻ. '
            'ഇത് മാർഗ്ഗനിർദ്ദേശം മാത്രമാണ് — തുകകൾ സൂചകം മാത്രം; ഇതിലെ ഉള്ളടക്കം KAU അംഗീകരിക്കുകയോ '
            'സാക്ഷ്യപ്പെടുത്തുകയോ ചെയ്തിട്ടില്ല. നിക്ഷേപിക്കുന്നതിന് മുമ്പ് നിങ്ങളുടെ ബോർഡ്, KAU വിദഗ്ധർ, '
            'വിശദമായ പദ്ധതി റിപ്പോർട്ട് എന്നിവ ഉപയോഗിച്ച് പരിശോധിക്കുക.'
        ),
        'page': 'പേജ്',
        'of': '/',
        'executive_summary': 'സംഗ്രഹം',
        'commodity_focus': 'ഉൽപ്പന്ന ശ്രദ്ധ',
        'commodity': 'ഉൽപ്പന്നം',
        'role': 'തരം',
        'opportunity': 'അവസരം',
        'role_primary': 'പ്രാഥമികം',
        'role_secondary': 'ദ്വിതീയം',
        'location_advantages': 'സ്ഥലത്തിന്റെ അനുകൂല ഘടകങ്ങൾ',
        'business_activities': 'ബിസിനസ് പ്രവർത്തനങ്ങൾ',
        'activity': 'പ്രവർത്തനം',
        'description': 'വിവരണം',
        'market_strategy': 'വിപണന തന്ത്രം',
        'target_markets': 'ലക്ഷ്യ വിപണികൾ',
        'channels': 'വിൽപ്പന മാർഗ്ഗങ്ങൾ',
        'branding': 'ബ്രാൻഡിംഗ്',
        'operations_plan': 'പ്രവർത്തന പദ്ധതി',
        'financial_outline': 'സാമ്പത്തിക രൂപരേഖ',
        'estimated_investment': 'കണക്കാക്കിയ നിക്ഷേപം',
        'working_capital': 'പ്രവർത്തന മൂലധനം',
        'revenue_streams': 'വരുമാന സ്രോതസ്സുകൾ',
        'funding_sources': 'ധനസഹായ സ്രോതസ്സുകളും പദ്ധതികളും',
        'risks': 'അപകടസാധ്യതകളും പരിഹാരങ്ങളും',
        'risk': 'അപകടസാധ്യത',
        'mitigation': 'പരിഹാരം',
        'action_plan': 'കർമ്മ പദ്ധതി',
        'period': 'കാലയളവ്',
        'activities': 'പ്രവർത്തനങ്ങൾ',
        'key_recommendations': 'പ്രധാന ശുപാർശകൾ',
    },
}


def _labels(plan) -> dict:
    return LABELS['ml' if plan.language == 'ml' else 'en']


def _sections(content: dict) -> list[str]:
    """Section keys that have content, in document order — numbered 1..n."""
    market = content.get('market_strategy') or {}
    finance = content.get('financial_outline') or {}
    present = {
        'executive_summary':   bool(content.get('executive_summary')),
        'commodity_focus':     bool(content.get('commodity_focus')),
        'location_advantages': bool(content.get('location_advantages')),
        'business_activities': bool(content.get('business_activities')),
        'market_strategy':     any(market.get(k) for k in ('target_markets', 'channels', 'branding')),
        'operations_plan':     bool(content.get('operations_plan')),
        'financial_outline':   any(finance.get(k) for k in (
            'estimated_investment', 'working_capital', 'revenue_streams', 'funding_sources')),
        'risks':               bool(content.get('risks')),
        'action_plan':         bool(content.get('action_plan')),
        'key_recommendations': bool(content.get('key_recommendations')),
    }
    return [key for key, has in present.items() if has]


def build_context(plan) -> dict:
    """Everything both renderers need, in the plan's language."""
    lang = 'ml' if plan.language == 'ml' else 'en'
    labels = _labels(plan)
    profile = build_profile(plan.fpo, lang)
    content = plan.content or {}
    sections = _sections(content)
    generated = timezone.localtime(plan.generated_at) if plan.generated_at else timezone.localtime()

    location = ', '.join(p for p in [
        profile['village_town'], profile['block_display'], profile['district_display'], profile['pincode'],
    ] if p)
    district = profile['district_display']

    return {
        'lang': lang,
        'L': labels,
        'plan': plan,
        'fpo_name': profile['fpo_name'] or '—',
        'fpo_location': f"{district}, {labels['kerala']}" if district else labels['farmer_producer_org'],
        'title': content.get('title') or labels['doc_title'],
        'c': content,
        'sections': sections,
        # {'executive_summary': 1, ...} — heading numbers that skip empty sections
        'num': {key: i for i, key in enumerate(sections, start=1)},
        'generated_at': generated.strftime('%d %b %Y'),
        'primary_commodities': ', '.join(c['name'] for c in profile['primary_commodities']),
        'secondary_commodities': ', '.join(c['name'] for c in profile['secondary_commodities']),
        'location': location,
    }


def build_filename(plan, ext: str) -> str:
    raw = (plan.fpo.name or 'fpo').strip()
    slug = ''.join(ch if ch.isalnum() else '_' for ch in raw)[:40].strip('_') or 'fpo'
    return f'Business_Plan_{slug}_{plan.language}.{ext}'


# ─────────────────────────────────────────────────────────────────────────────
# PDF
# ─────────────────────────────────────────────────────────────────────────────

def render_business_plan_pdf(plan) -> bytes:
    from weasyprint import HTML  # deferred — heavy dependency

    html = render_to_string('recommendations/business_plan_report.html', build_context(plan))
    return HTML(string=html).write_pdf()


# ─────────────────────────────────────────────────────────────────────────────
# Word
# ─────────────────────────────────────────────────────────────────────────────

# Word draws Malayalam with the "complex script" font slot, which the default
# template leaves unset — so set it. Same font as the PDF; where it isn't
# installed (e.g. Word on Windows) the app substitutes its own Malayalam font.
_MALAYALAM_FONT = 'Noto Sans Malayalam'


def _set_malayalam_font(doc) -> None:
    from docx.oxml.ns import qn

    for style in doc.styles:
        if style.type != 1:  # paragraph + character styles only
            continue
        r_pr = style.element.get_or_add_rPr()
        fonts = r_pr.find(qn('w:rFonts'))
        if fonts is None:
            fonts = r_pr.makeelement(qn('w:rFonts'), {})
            r_pr.insert(0, fonts)
        fonts.set(qn('w:cs'), _MALAYALAM_FONT)
        fonts.attrib.pop(qn('w:cstheme'), None)


def _mirror_complex_script(doc) -> None:
    """
    Word keeps separate size / bold / italic for complex-script text (Malayalam),
    and python-docx only sets the Latin ones — copy them across so Malayalam
    headings aren't drawn at body size.
    """
    from docx.oxml.ns import qn

    parts = [doc.element] + [s.footer._element for s in doc.sections] + [doc.styles.element]
    for part in parts:
        for r_pr in part.iter(qn('w:rPr')):
            for latin, cs in (('w:sz', 'w:szCs'), ('w:b', 'w:bCs'), ('w:i', 'w:iCs')):
                src = r_pr.find(qn(latin))
                if src is None or r_pr.find(qn(cs)) is not None:
                    continue
                dst = r_pr.makeelement(qn(cs), dict(src.attrib))
                src.addnext(dst)

def render_business_plan_docx(plan) -> bytes:
    from docx import Document
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Inches, Pt, RGBColor

    # Same palette + cell helpers as the DPR Word export
    from apps.fpo.services.dpr.docx import (
        _KAU_NAVY, _KAU_ORANGE, _add_heading, _set_cell_border, _set_cell_shading,
    )

    ctx = build_context(plan)
    L, c = ctx['L'], ctx['c']
    grey = RGBColor(0x66, 0x66, 0x66)

    doc = Document()
    normal = doc.styles['Normal']
    normal.font.name = 'Calibri'
    normal.font.size = Pt(11)
    if ctx['lang'] == 'ml':
        _set_malayalam_font(doc)

    def para(text, *, size=None, color=None, bold=False, italic=False,
             align=None, space_after=None):
        p = doc.add_paragraph()
        if align is not None:
            p.alignment = align
        run = p.add_run(text)
        run.bold, run.italic = bold, italic
        if size:
            run.font.size = Pt(size)
        if color is not None:
            run.font.color.rgb = color
        if space_after is not None:
            p.paragraph_format.space_after = Pt(space_after)
        return p

    def bullets(items):
        for item in items or []:
            doc.add_paragraph(str(item), style='List Bullet')

    def sub_label(text):
        para(text, bold=True, color=_KAU_NAVY, size=10.5, space_after=2)

    def heading(key):
        _add_heading(doc, f"{ctx['num'][key]}. {L[key]}", level=1)

    def grid(header, rows, widths):
        """Navy-header table with light borders — the DPR table look."""
        table = doc.add_table(rows=1 + len(rows), cols=len(header))
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = False
        for i, w in enumerate(widths):  # grid widths — LibreOffice ignores per-cell ones
            table.columns[i].width = Inches(w)
        for i, text in enumerate(header):
            cell = table.rows[0].cells[i]
            cell.width = Inches(widths[i])
            cell.text = ''
            run = cell.paragraphs[0].add_run(text)
            run.bold = True
            run.font.size = Pt(10)
            run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            _set_cell_shading(cell, '1F3864')
            _set_cell_border(cell, color='CCCCCC')
        for r, values in enumerate(rows, start=1):
            for i, value in enumerate(values):
                cell = table.rows[r].cells[i]
                cell.width = Inches(widths[i])
                cell.text = ''
                if isinstance(value, list):
                    for j, item in enumerate(value):
                        p = cell.paragraphs[0] if j == 0 else cell.add_paragraph()
                        p.add_run(f'• {item}').font.size = Pt(10)
                else:
                    run = cell.paragraphs[0].add_run(str(value or ''))
                    run.font.size = Pt(10)
                    run.bold = i == 0
                _set_cell_border(cell, color='CCCCCC')
        doc.add_paragraph()

    # ── Cover (mirrors the DPR cover) ──
    center = WD_ALIGN_PARAGRAPH.CENTER
    para(ctx['fpo_name'], size=22, color=_KAU_NAVY, bold=True, align=center, space_after=4)
    para(ctx['fpo_location'], size=12, color=grey, italic=True, align=center, space_after=14)
    para(L['doc_title'], size=32, color=_KAU_NAVY, bold=True, align=center, space_after=6)
    para(L['subtitle'], size=13, color=RGBColor(0x44, 0x44, 0x44), align=center, space_after=20)
    para(ctx['title'], size=15, color=_KAU_ORANGE, bold=True, align=center, space_after=16)

    meta = [
        (L['financial_year'], plan.financial_year),
        (L['generated_on'], ctx['generated_at']),
        (L['primary_commodities'], ctx['primary_commodities']),
        (L['secondary_commodities'], ctx['secondary_commodities']),
        (L['location'], ctx['location']),
    ]
    meta = [(k, v) for k, v in meta if v]
    meta_table = doc.add_table(rows=len(meta), cols=2)
    meta_table.autofit = False
    meta_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    meta_table.columns[0].width, meta_table.columns[1].width = Inches(1.9), Inches(2.8)
    for i, (label, value) in enumerate(meta):
        cell_l, cell_v = meta_table.rows[i].cells
        cell_l.width, cell_v.width = Inches(1.9), Inches(2.8)
        cell_l.text = cell_v.text = ''
        run_l = cell_l.paragraphs[0].add_run(f'{label}:')
        run_l.bold = True
        run_l.font.color.rgb = _KAU_NAVY
        run_l.font.size = Pt(10.5)
        cell_v.paragraphs[0].add_run(str(value)).font.size = Pt(10.5)
        for cell in (cell_l, cell_v):
            _set_cell_border(cell, color='DDDDDD')
            _set_cell_shading(cell, 'FAFAFA')

    para(L['attribution'], size=9, color=RGBColor(0x99, 0x99, 0x99), italic=True, align=center, space_after=10)

    disc_table = doc.add_table(rows=1, cols=1)
    disc_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    disc_cell = disc_table.rows[0].cells[0]
    disc_cell.width = Inches(6.0)
    disc_cell.text = ''
    run_t = disc_cell.paragraphs[0].add_run(L['disclaimer_title'].upper())
    run_t.bold = True
    run_t.font.size = Pt(8)
    run_t.font.color.rgb = RGBColor(0x9A, 0x34, 0x12)
    run_b = disc_cell.add_paragraph().add_run(L['disclaimer'])
    run_b.font.size = Pt(8.5)
    run_b.font.color.rgb = RGBColor(0x78, 0x35, 0x0F)
    _set_cell_border(disc_cell, color='E86C1A', size_pt=1.0)
    _set_cell_shading(disc_cell, 'FFF7ED')
    doc.add_page_break()

    # ── Sections ──
    para(L['ai_label'].upper(), size=8, color=_KAU_ORANGE, bold=True, space_after=4)
    market = c.get('market_strategy') or {}
    finance = c.get('financial_outline') or {}
    role = {'primary': L['role_primary'], 'secondary': L['role_secondary']}

    for key in ctx['sections']:
        heading(key)
        if key in ('executive_summary', 'location_advantages', 'operations_plan'):
            para(c[key])
        elif key == 'commodity_focus':
            grid([L['commodity'], L['role'], L['opportunity']],
                 [(f.get('commodity'), role.get(f.get('role'), f.get('role')), f.get('opportunity'))
                  for f in c['commodity_focus']],
                 [1.6, 1.0, 3.9])
        elif key == 'business_activities':
            grid([L['activity'], L['description']],
                 [(a.get('name'), a.get('description')) for a in c['business_activities']],
                 [2.0, 4.5])
        elif key == 'market_strategy':
            if market.get('target_markets'):
                sub_label(L['target_markets'])
                bullets(market['target_markets'])
            if market.get('channels'):
                sub_label(L['channels'])
                bullets(market['channels'])
            if market.get('branding'):
                sub_label(L['branding'])
                para(market['branding'])
        elif key == 'financial_outline':
            rows = [(L['estimated_investment'], finance.get('estimated_investment')),
                    (L['working_capital'], finance.get('working_capital'))]
            rows = [r for r in rows if r[1]]
            if rows:
                # Key/value box like the DPR "Project at a Glance" table
                table = doc.add_table(rows=len(rows), cols=2)
                table.alignment = WD_TABLE_ALIGNMENT.CENTER
                table.autofit = False
                table.columns[0].width, table.columns[1].width = Inches(2.2), Inches(4.3)
                for i, (label, value) in enumerate(rows):
                    cell_l, cell_v = table.rows[i].cells
                    cell_l.width, cell_v.width = Inches(2.2), Inches(4.3)
                    cell_l.text = cell_v.text = ''
                    run = cell_l.paragraphs[0].add_run(label)
                    run.bold = True
                    run.font.color.rgb = _KAU_NAVY
                    cell_v.paragraphs[0].add_run(str(value))
                    _set_cell_shading(cell_l, 'F2F2F2')
                    for cell in (cell_l, cell_v):
                        _set_cell_border(cell, color='999999')
                doc.add_paragraph()
            if finance.get('revenue_streams'):
                sub_label(L['revenue_streams'])
                bullets(finance['revenue_streams'])
            if finance.get('funding_sources'):
                sub_label(L['funding_sources'])
                bullets(finance['funding_sources'])
        elif key == 'risks':
            grid([L['risk'], L['mitigation']],
                 [(r.get('risk'), r.get('mitigation')) for r in c['risks']],
                 [2.4, 4.1])
        elif key == 'action_plan':
            grid([L['period'], L['activities']],
                 [(s.get('period'), list(s.get('activities') or [])) for s in c['action_plan']],
                 [1.6, 4.9])
        elif key == 'key_recommendations':
            for item in c['key_recommendations']:
                doc.add_paragraph(str(item), style='List Number')

    # Footer line on every page, like the PDF
    footer = doc.sections[0].footer.paragraphs[0]
    footer.alignment = center
    run = footer.add_run(f"{ctx['fpo_name']} · {L['doc_title']} · {L['attribution']}")
    run.italic = True
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)

    _mirror_complex_script(doc)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
