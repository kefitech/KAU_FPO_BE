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
from typing import Optional

from django.conf import settings
from django.template.loader import render_to_string

from apps.fpo.services.dpr.calculation import compute, CalculationResult


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


def render_html_for_project(project, version_number: Optional[int] = None) -> str:
    """Compute + render — returns the raw HTML string.
    Useful for debugging without invoking WeasyPrint.

    `version_number` is baked into the cover + running footer per KAU §7.2.
    Pass None for one-off previews (renders "Preview" instead of vN).
    """
    result: CalculationResult = compute(project)
    return render_to_string('dpr/report.html', {
        'project': project,
        'r': result,
        'years': list(range(1, result.projection_years + 1)),
        'generated_at': datetime.now().strftime('%d %b %Y · %I:%M %p'),
        # KAU §7.2 — version + KAU §9.7 — attribution/disclaimer strings
        # rendered on cover + running footer.
        'version_number': version_number,
        'version_label': f'v{version_number}' if version_number else 'Preview',
    })


def render_pdf_for_project(project, version_number: Optional[int] = None) -> bytes:
    """Full pipeline: compute → render HTML → convert to PDF bytes."""
    from weasyprint import HTML   # deferred import — heavy dep, avoid at import time

    html = render_html_for_project(project, version_number=version_number)
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
    # running footer per KAU §7.2.
    pdf_bytes = render_pdf_for_project(project, version_number=version_number)
    with open(absolute_path, 'wb') as f:
        f.write(pdf_bytes)
    file_size = os.path.getsize(absolute_path)

    # Relative URL — served via Django's static/media handler in dev; in
    # prod the S3 URL builder replaces this with a presigned URL.
    file_url = f'{settings.MEDIA_URL}dpr/{project.uuid}/{filename}'

    # 3. Create the tracking row.
    doc = DPRDocument.objects.create(
        project=project,
        version_number=version_number,
        file_url=file_url,
        file_size=file_size,
        status=status or DPRDocument.Status.DRAFT,
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
