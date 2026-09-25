"""
DPR PDF renderer — bridges CalculationResult → landscape A4 PDF.

Public entry points:
    * `render_pdf_for_project(project) -> bytes`   — in-memory PDF bytes
    * `save_pdf_to_disk(project, path) -> path`    — one-off dev/debug write
    * `save_pdf_to_document(project) -> DPRDocument` — production save that
      creates a versioned DPRDocument row per KAU pre-UAT reply §7.2

Uses:
    - apps.fpo.services.dpr.calculation.compute(project) for the numbers
    - apps/fpo/templates/dpr/report.html for the layout
    - WeasyPrint for HTML → PDF conversion

Downstream callers:
    - FPO API endpoint (add later) — inline PDF download
    - Celery task (existing pattern) — generate + upload to S3
    - Admin preview view

Author: Athul Gopan (Kefi Tech Solutions)
"""
import os
import re
from datetime import datetime
from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.template.loader import render_to_string

from apps.fpo.services.dpr.calculation import compute, CalculationResult
from apps.fpo.services.dpr.chart_helpers import (
    cost_breakdown_pie,
    pnl_trend_bar,
    repayment_schedule_bar,
)


# Human-readable labels for the ~19 cost fields + ~12 MoF fields on
# DPRSectionFinance. Used to render the "Project at a Glance" breakdown
# sub-rows in the PDF instead of raw model field names.
# Keys mirror COST_FIELDS / MOF_FIELDS in calculation.py; if either list
# changes, update this map in lock-step.
COST_LABELS = {
    'cost_land_purchase':               'Land purchase',
    'cost_land_development':            'Land development',
    'cost_civil_works':                 'Civil works',
    'cost_buildings':                   'Buildings',
    'cost_plant_machinery':             'Plant & machinery',
    'cost_equipment':                   'Equipment',
    'cost_utilities':                   'Utilities (power, water)',
    'cost_other_capex':                 'Other capex',
    'cost_site_development':            'Site development',
    'cost_furniture_fixtures':          'Furniture & fixtures',
    'cost_office_equipment':            'Office equipment',
    'cost_vehicles':                    'Vehicles',
    'cost_electrification':             'Electrification',
    'cost_water_supply':                'Water supply',
    'cost_pre_operative_expenses':      'Pre-operative expenses',
    'cost_preliminary_expenses':        'Preliminary expenses',
    'cost_technical_consultancy':       'Technical consultancy',
    'cost_contingencies':               'Contingencies',
    'cost_margin_for_working_capital':  'Margin for working capital',
    'cost_interest_during_construction':'Interest during construction',
}
MOF_LABELS = {
    'mof_promoters_contribution':       "Promoter's contribution",
    'mof_bank_term_loan':               'Bank term loan',
    'mof_government_grant':             'Government grant',
    'mof_government_subsidy':           'Government subsidy',
    'mof_other_sources':                'Other sources',
    'mof_share_capital':                'Share capital',
    'mof_internal_accruals':            'Internal accruals',
    'mof_working_capital_loan':         'Working capital loan',
    'mof_venture_capital':              'Venture capital',
    'mof_csr_support':                  'CSR support',
    'mof_nabard_assistance':            'NABARD assistance',
    'mof_other_financial_assistance':   'Other financial assistance',
}


def _ai_chapters_for_pdf(project) -> dict:
    """Return {chapter_key: text} of all AI-generated narrative chapters
    that have live `user_edited` content for this project.

    The PDF template distributes chapters at logical spots — executive
    summary before the Project-at-Glance table, financial analysis before
    §7 P&L, risk_analysis inside §11 Risk Assessment, etc.

    Returns an empty dict when nothing has been generated yet; the template
    guards each render with `{% if pdf_ai.<key> %}` so an unfilled DPR
    still renders cleanly (just without narratives).
    """
    try:
        from apps.database.models import DPRAIContent
    except ImportError:
        return {}
    out: dict = {}
    for row in DPRAIContent.objects.filter(project=project):
        # Prefer user_edited (live version); fall back to original_ai for
        # a chapter that was generated once and never manually edited.
        text = (row.user_edited or row.original_ai or '').strip()
        if text:
            out[row.chapter] = text
    return out


def _ai_stale_chapters_for_pdf(project) -> dict:
    """Return {chapter_key: stale_reason} for stale AI chapters with active text.

    Only appears in Preview PDFs — the pre-final gate blocks the versioned
    Generate flow before it reaches template rendering. Preview PDFs still
    render so the FPO can see what the DPR looks like, but each stale
    chapter shows an amber note pointing out it needs regeneration.
    """
    try:
        from apps.database.models import DPRAIContent
    except ImportError:
        return {}
    out: dict = {}
    for row in DPRAIContent.objects.filter(project=project, is_stale=True).exclude(user_edited=''):
        out[row.chapter] = row.stale_reason or 'An upstream section was edited after this chapter was generated.'
    return out


def _products_for_pdf(project) -> tuple[list[dict], str]:
    """Return (products, hero_image_path) for the PDF template.

    `products` is a list of {'name', 'category', 'quantity', 'unit',
    'price', 'description', 'image_path', 'is_value_added'} dicts — one
    per DPRProductItem, ordered by (order, id).

    `hero_image_path` is the absolute file path of the first product with
    an image, used as the cover hero image. Empty string if no product has
    a photo. Absolute path (not URL) so WeasyPrint reads it directly from
    disk — avoids HTTP overhead + works whether MEDIA_URL is set or not.
    """
    try:
        from apps.database.models import DPRSectionProducts, DPRProductItem
    except ImportError:
        return [], ''
    section = DPRSectionProducts.objects.filter(project=project).first()
    if not section:
        return [], ''
    hero_path = ''
    out: list[dict] = []
    for item in DPRProductItem.objects.filter(section=section).order_by('order', 'id'):
        img_path = ''
        if item.image:
            try:
                img_path = item.image.path
                if not hero_path:
                    hero_path = img_path
            except (ValueError, NotImplementedError):
                # image.path raises for non-local storage backends (S3).
                # In prod we'd swap to item.image.url with WeasyPrint's
                # url_fetcher configured. For now, local storage only.
                img_path = ''
        out.append({
            'name': item.name or '—',
            'category': str(item.category) if item.category_id else '',
            'product_type': str(item.product_type) if item.product_type_id else '',
            'quantity': item.annual_quantity,
            'unit': str(item.unit_of_measurement) if item.unit_of_measurement_id else '',
            'price': item.selling_price_per_unit,
            'selling_unit': str(item.selling_unit) if item.selling_unit_id else '',
            'description': (item.description or '').strip(),
            'image_path': img_path,
            'is_value_added': item.is_value_added,
            'primary_or_secondary': item.primary_or_secondary or '',
        })
    return out, hero_path


def _technologies_with_flow(project) -> list[dict]:
    """Return [{'name', 'description', 'steps'}, ...] for each DPRTechnology on
    the project that has a non-empty `process_flow_sequence`.

    Steps are parsed by splitting on newlines and stripping empties. Used by
    the PDF template to render one vertical flowchart per technology in the
    Manufacturing Process chapter. Returns [] when no technology has a
    populated flow — the whole chapter is omitted in that case.
    """
    try:
        from apps.database.models import DPRSectionTechnology, DPRTechnology
    except ImportError:
        return []
    section = DPRSectionTechnology.objects.filter(project=project).first()
    if not section:
        return []
    out: list[dict] = []
    for tech in DPRTechnology.objects.filter(section=section).order_by('id'):
        seq = (getattr(tech, 'process_flow_sequence', '') or '').strip()
        if not seq:
            continue
        steps = [line.strip() for line in seq.splitlines() if line.strip()]
        if not steps:
            continue
        out.append({
            'name': (getattr(tech, 'name', '') or 'Process Flow').strip(),
            'description': (getattr(tech, 'process_description', '') or '').strip(),
            'steps': steps,
        })
    return out


def _breakdown_rows(by_field: dict, labels: dict) -> list[tuple[str, object]]:
    """Return [(label, value), ...] pairs for non-zero fields, in labels-dict order.

    The label map dictates display order so the PDF reads consistently
    regardless of how Python iterates the by_field dict. Fields not in
    the label map are appended at the end using the raw field name.
    """
    from decimal import Decimal
    rows: list[tuple[str, object]] = []
    for key, label in labels.items():
        val = by_field.get(key) or Decimal('0')
        if val and val > 0:
            rows.append((label, val))
    # Include any unknown keys (defensive — surfaces if calculation.py adds
    # a field but this map wasn't updated).
    for key, val in by_field.items():
        if key not in labels and val and val > 0:
            rows.append((key, val))
    return rows


# ── Filename convention (KAU pre-UAT reply §7.2, 2026-09-08) ─────────────
# Format: DPR_<FPO-slug>_v<version_number>.pdf
# FPO slug: alphanumeric + underscore, whitespace → underscore, drop everything
# else. Truncated to 40 chars so the final filename stays comfortably under
# 100 chars on any filesystem. Fallback = project UUID short-form if the
# FPO name is empty / all-punctuation (edge case — safety net).

_FPO_NAME_SANITISER = re.compile(r'[^A-Za-z0-9]+')


def _fpo_slug(project) -> str:
    """Sanitise the FPO name into a filesystem-safe token.

    "Nyna's Farm for Duck" → "Nynas_Farm_for_Duck"
    "  " / empty          → project UUID first 8 chars

    Deliberately does not lowercase — preserving case makes the filename
    readable at a glance in the download list.
    """
    name = getattr(getattr(project, 'fpo', None), 'name', '') or ''
    slug = _FPO_NAME_SANITISER.sub('_', name).strip('_')
    if not slug:
        slug = str(project.uuid)[:8]
    return slug[:40]


def build_pdf_filename(project, version_number: int) -> str:
    """Return the KAU-mandated filename: DPR_<FPO-slug>_v<n>.pdf."""
    return f'DPR_{_fpo_slug(project)}_v{version_number}.pdf'


def _key_assumptions_rows() -> list[dict]:
    """Rows for the PDF's "Key Assumptions" mini-table (KAU 2026-09-19 P2.1).

    Every DPRConfig-configured rate the calc engine reads gets listed here
    so the DPR reader (banker / KAU reviewer) can see at a glance which
    figures are platform assumptions vs FPO-entered.

    Each row: {label, value_pct, source}. `value_pct` is a plain string
    with a "%" suffix; template renders it as-is.
    """
    # Local import so a plain `render_pdf_for_project` call in a bare
    # Django shell doesn't force apps.fpo.services.dpr.provenance to load
    # before the Django app registry is ready.
    from .provenance import collect_system_assumptions
    return [
        {'label': a.label, 'value_pct': f'{a.value}%', 'source': 'KAU DPR platform default'}
        for a in collect_system_assumptions()
    ]


def _debt_equity_ratio_display(by_field: dict) -> str:
    """Format the debt-to-equity ratio as `x.xx : 1` — the standard
    banking convention KAU wants on the DPR cover appraisal table.

    Returns "—" when there's no equity component (division by zero) or
    the two amounts sum to zero (empty MoF section).

    Example: bank loan ₹ 60 L, promoter equity ₹ 40 L  →  "1.50 : 1".
    """
    debt = by_field.get('mof_bank_term_loan') or Decimal('0')
    equity = by_field.get('mof_promoters_contribution') or Decimal('0')
    if not isinstance(debt, Decimal):
        debt = Decimal(str(debt))
    if not isinstance(equity, Decimal):
        equity = Decimal(str(equity))
    if equity <= 0:
        return '—'
    ratio = (debt / equity).quantize(Decimal('0.01'))
    return f'{ratio} : 1'


class DPRValidationError(Exception):
    """Raised by render_pdf_for_project when mode='final' but a chapter has
    unresolved needs_review / hard consistency mismatches.

    `errors` — list of {'chapter': str, 'reason': str}. The API layer can
    surface these to the FPO so they know which chapters to fix.
    """
    def __init__(self, errors: list[dict]):
        super().__init__(f'Cannot render final PDF — {len(errors)} chapter(s) need review')
        self.errors = errors


def _pre_final_validation(project) -> list[dict]:
    """KAU 2026-09-19 P6.5 + Kefitech P6.6 — hard gate before final PDF render.

    Flags any AI chapter that still has:
      * needs_review=True (placeholder scrubber caught unresolved [X] tokens)
      * consistency_warnings with kind='mismatch' (hard drift, not just soft
        drift)
    AND any structural chain warning of severity='error' from
    `apps.fpo.services.dpr.chain_consistency.check_operational_chain()`.

    Returns a list of {chapter, reason} dicts. Empty list = safe to render.
    Preview renders always allowed regardless — the gate only fires on
    mode='final'.
    """
    from apps.database.models import DPRAIContent
    from .chain_consistency import check_operational_chain

    errors: list[dict] = []
    for row in DPRAIContent.objects.filter(project=project):
        if row.needs_review and row.placeholder_hits:
            n = sum(h.get('count', 1) for h in row.placeholder_hits)
            errors.append({
                'chapter': row.chapter,
                'reason': (
                    f'{n} placeholder token(s) auto-replaced with "Not '
                    f'available" — regenerate after filling the missing '
                    f'wizard field(s).'
                ),
            })
        hard = [w for w in (row.consistency_warnings or []) if w.get('kind') == 'mismatch']
        if hard:
            metrics = ', '.join(sorted({w['metric'] for w in hard}))
            errors.append({
                'chapter': row.chapter,
                'reason': (
                    f'Numeric mismatch vs calc engine on: {metrics}. '
                    f'Regenerate this chapter or edit-in-place before '
                    f'requesting a final DPR.'
                ),
            })

    # Kefitech P6.6 — structural operational-chain checks. Only severity
    # 'error' entries block the render (warnings surface elsewhere on the
    # AI Content Health card without blocking).
    # `check` carried through so the pre-flight endpoint can map back to a
    # wizard section key for the "Fix in section →" jump link.
    for cw in check_operational_chain(project):
        if cw.severity == 'error':
            errors.append({
                'chapter': cw.section,
                'check':   cw.check,
                'reason':  cw.message,
            })

    # Finance §Cat E — Section E must have at least one revenue assumption
    # before the versioned/banker PDF can be produced. The calc engine has a
    # Products-section fallback that keeps Preview useful during wizard
    # iteration, but the "shall be entered" wording in the section validator
    # means the FPO cannot ship a final DPR with an empty Section E.
    fin = getattr(project, 'section_finance', None)
    if fin is not None and not fin.revenue_assumptions.exists():
        errors.append({
            'chapter': 'finance',
            'reason': (
                'Finance §E — at least one revenue assumption (product/service) '
                'must be entered before the DPR can be generated. Open Finance → '
                'E. Revenue Assumptions and add one row per product/service.'
            ),
        })

    # KAU RCD B.5 — stale AI narratives. If any chapter has active text
    # (user_edited or original_ai) AND its upstream section has been edited
    # after generation, block the final PDF so the banker doesn't receive a
    # DPR whose narrative reflects an older version of the underlying data.
    # Preview still renders (mode='preview' skips this whole function).
    stale_rows = DPRAIContent.objects.filter(
        project=project, is_stale=True,
    ).exclude(user_edited='')
    for row in stale_rows:
        errors.append({
            'chapter': row.chapter,
            'reason': (
                f'Narrative is stale — {row.stale_reason or "an upstream section was edited after generation"}. '
                f'Open AI Content → {row.chapter.replace("_", " ").title()} and regenerate before requesting a final DPR.'
            ),
        })
    return errors


def render_html_for_project(
    project,
    version_number: Optional[int] = None,
    mode: str = 'preview',
) -> str:
    """Compute + render — returns the raw HTML string.
    Useful for debugging without invoking WeasyPrint.

    `version_number` is baked into the cover + running footer per KAU §7.2.
    Pass None for one-off previews (renders "Preview" instead of vN).

    `mode` — 'preview' (default) or 'final'. Kefitech 2026-09-19 P6.3:
    * preview → orange asterisks on [system_default] rates + a "Source"
      column on the Key Assumptions table. Meant for the FPO reviewing
      their draft.
    * final   → asterisks + source column hidden. Meant for the DPR that
      leaves the platform (bank / scheme officer sees clean numbers with
      provenance mentioned only in prose, not as visible UI badges).
    """
    if mode not in ('preview', 'final'):
        raise ValueError(f"mode must be 'preview' or 'final', got {mode!r}")

    result: CalculationResult = compute(project)
    pdf_products, pdf_hero_image = _products_for_pdf(project)
    return render_to_string('dpr/report.html', {
        'project': project,
        'r': result,
        'years': list(range(1, result.projection_years + 1)),
        'generated_at': datetime.now().strftime('%d %b %Y · %I:%M %p'),
        # KAU §7.2 — version + KAU §9.7 — attribution/disclaimer strings
        # rendered on cover + running footer.
        'version_number': version_number,
        'version_label': f'v{version_number}' if version_number else 'Preview',
        # P6.3 mode flag — template renders provenance markers only when True.
        'preview_mode': mode == 'preview',
        # Project-at-Glance breakdown rows — pre-computed so the template
        # renders human-readable labels without extra filter machinery.
        'cost_breakdown_rows': _breakdown_rows(result.cost.by_field, COST_LABELS),
        'mof_breakdown_rows':  _breakdown_rows(result.mof.by_field, MOF_LABELS),
        # Debt-to-equity as banking-convention ratio (e.g. "1.50 : 1"),
        # not raw rupees — per KAU 2026-09-19 reviewer feedback.
        'debt_equity_ratio_display': _debt_equity_ratio_display(result.mof.by_field),
        # KAU 2026-09-19 P2.1 — Key Assumptions mini-table listing every
        # DPRConfig-configured rate the calc engine used. Rendered just
        # before the Limitations chapter so bank / KAU reviewer can see
        # which figures are platform defaults vs project-specific.
        'key_assumptions_rows': _key_assumptions_rows(),
        # Per-technology process flowcharts. Empty list = section omitted.
        'technologies_with_flow': _technologies_with_flow(project),
        # Product list + cover hero image (first product with a photo).
        # `pdf_hero_image` is an absolute file path — WeasyPrint reads
        # from disk. Empty string when no product has a photo (hero omitted).
        'pdf_products': pdf_products,
        'pdf_hero_image': pdf_hero_image,
        # matplotlib-rendered charts (data-URLs). Empty string when there's
        # no data to plot — template omits the <img> in that case.
        'chart_cost_pie':     cost_breakdown_pie(result.cost.by_field),
        'chart_pnl_bar':      pnl_trend_bar(result.profit_loss.rows) if result.profit_loss else '',
        'chart_repayment_bar':repayment_schedule_bar(result.interest_schedule.rows) if result.interest_schedule and getattr(result.interest_schedule, 'rows', None) else '',
        # AI narrative chapters (Gemini-generated). Dict of {chapter_key: text}.
        # Empty when nothing has been generated — template guards each section.
        'pdf_ai':             _ai_chapters_for_pdf(project),
        # KAU RCD B.5 — {chapter: stale_reason} for narratives whose upstream
        # section was edited after generation. Preview PDFs surface an amber
        # note per stale chapter; the pre-final gate blocks versioned Generate
        # before it reaches this template.
        'pdf_ai_stale':       _ai_stale_chapters_for_pdf(project),
    })


def render_pdf_for_project(
    project,
    version_number: Optional[int] = None,
    mode: str = 'preview',
) -> bytes:
    """Full pipeline: compute → render HTML → convert to PDF bytes.

    `mode='final'` runs the Kefitech P6.5 pre-flight gate first — if any
    AI chapter has unresolved placeholder tokens or hard numeric
    mismatches vs the calc engine, raises `DPRValidationError` with a
    per-chapter reason list instead of rendering an unreliable DPR.
    Preview mode always renders regardless.
    """
    from weasyprint import HTML   # deferred import — heavy dep, avoid at import time

    if mode == 'final':
        errors = _pre_final_validation(project)
        if errors:
            raise DPRValidationError(errors)

    html = render_html_for_project(project, version_number=version_number, mode=mode)
    return HTML(string=html).write_pdf()


def save_pdf_to_disk(project, output_path: Optional[str] = None) -> str:
    """Write PDF to disk. Returns the absolute path written.

    One-off dev / debug helper. Does NOT create a DPRDocument row — use
    `save_pdf_to_document` for the production flow that tracks versions
    per KAU §7.2.

    Default path: /tmp/dpr_<uuid>.pdf. Callers pass a specific path when
    integrating with S3 upload / Django FileField storage.
    """
    if output_path is None:
        output_path = f'/tmp/dpr_{project.uuid}.pdf'
    with open(output_path, 'wb') as f:
        f.write(render_pdf_for_project(project))
    return output_path


def save_pdf_to_document(project, status: Optional[str] = None):
    """Production save flow — generates PDF, writes to disk, creates DPRDocument.

    Per KAU pre-UAT reply §7.1 + §7.2 (2026-09-08):
      1. Compute the next monotonic version_number for this project
         (never resets — old versions may be archived but the counter
         keeps going up).
      2. Render + write PDF to `MEDIA_ROOT/dpr/<project_uuid>/DPR_<FPO>_v<n>.pdf`.
      3. Create DPRDocument row with status (defaults to 'draft').
      4. Enforce retention: if the project has more than
         `pdf_retention_count` (DPRConfig default 10) UN-archived
         documents, mark the oldest ones as `is_archived=True` (soft
         retire — never delete, per KAU "the current or final approved
         DPR is not inadvertently deleted").

    Returns the created DPRDocument row.
    """
    # Deferred imports so this module remains importable in migrations
    # / management commands that don't need the ORM registered yet.
    from django.utils import timezone

    from apps.database.models import DPRDocument, DPRConfig

    # 1. Compute next version — monotonic per project, never resets.
    version_number = DPRDocument.next_version_for_project(project)

    # 2. Build target path + write bytes.
    filename = build_pdf_filename(project, version_number)
    project_dir = os.path.join(settings.MEDIA_ROOT, 'dpr', str(project.uuid))
    os.makedirs(project_dir, exist_ok=True)
    absolute_path = os.path.join(project_dir, filename)

    # Pass the version number into the render so it appears on the cover +
    # running footer per KAU §7.2. `mode='final'` strips provenance
    # asterisks + the Source column — versioned documents are what the
    # FPO sends to bankers, whereas the ephemeral /pdf/ endpoint stays
    # in preview mode for wizard-time sanity checks.
    pdf_bytes = render_pdf_for_project(
        project, version_number=version_number, mode='final',
    )
    with open(absolute_path, 'wb') as f:
        f.write(pdf_bytes)
    file_size = os.path.getsize(absolute_path)

    # Relative URL — served via Django's static/media handler in dev; in
    # prod the S3 URL builder replaces this with a presigned URL.
    file_url = f'{settings.MEDIA_URL}dpr/{project.uuid}/{filename}'

    # 3. Create the tracking row.
    # Default is FINAL — this function is the versioned Generate flow that
    # produces banker-ready PDFs (matches the mode='final' render above).
    # Callers can still pass an explicit status (e.g. USER_EDITED) if needed.
    doc = DPRDocument.objects.create(
        project=project,
        version_number=version_number,
        file_url=file_url,
        file_size=file_size,
        status=status or DPRDocument.Status.FINAL,
    )

    # 4. Retention — soft-archive oldest excess un-archived documents.
    _enforce_retention(project, DPRConfig.get_int('pdf_version_retention_count', 10))

    # Explicit refresh so callers get consistent server-computed fields
    # (generated_at was set by auto_now_add and is now populated).
    doc.refresh_from_db()
    # generated_at is DB-set — reference for callers if they need it.
    doc.generated_at = doc.generated_at or timezone.now()
    return doc


def _enforce_retention(project, retention_cap: int) -> int:
    """Mark oldest un-archived DPRDocuments beyond `retention_cap` as archived.

    Returns the number of rows archived by this pass. Never deletes rows
    per KAU §7.1 ("The system should ensure that the current or final
    approved DPR is not inadvertently deleted"). Archived rows stay in the
    DB — the FE list simply filters them out by default.
    """
    from apps.database.models import DPRDocument

    if retention_cap <= 0:
        return 0
    live_qs = DPRDocument.objects.filter(project=project, is_archived=False).order_by('-version_number')
    excess = list(live_qs[retention_cap:])
    if not excess:
        return 0
    ids = [d.id for d in excess]
    DPRDocument.objects.filter(id__in=ids).update(is_archived=True)
    return len(ids)
