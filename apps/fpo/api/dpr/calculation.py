"""
DPR calculation + PDF endpoints — turns the shell-callable calc engine into
HTTP-accessible features for the FPO wizard.

Routes (mounted at /api/fpo/dpr/):
    GET  /projects/<uuid>/calculation/                    → JSON serialisation of CalculationResult
    GET  /projects/<uuid>/pdf/                            → LEGACY one-shot preview (no side effects, no version row)
    POST /projects/<uuid>/documents/                      → generate + persist a new DPRDocument (bumps version_number)
    GET  /projects/<uuid>/documents/                      → list DPRDocument rows (excludes archived by default)
    GET  /projects/<uuid>/documents/<version>/download/   → download a specific version's PDF bytes

Ownership: reuses `get_project_or_error` — user must be primary owner or an
active secondary member of the FPO that owns the project.

Author: Athul Gopan (Kefi Tech Solutions)
"""
from __future__ import annotations

import os
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.http import FileResponse, HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.utils.responses import StandardResponse
from apps.database.models import DPRDocument
from apps.fpo.services.dpr.calculation import compute
from apps.fpo.services.dpr.financials_excel import render_financials_workbook
from apps.fpo.services.dpr.pdf import (
    build_pdf_filename,
    render_pdf_for_project,
    save_pdf_to_document,
)

from .projects import get_project_or_error


def _serialise(obj: Any) -> Any:
    """Coerce dataclass / Decimal / date / mapping graphs into JSON-safe types.

    Decimal → string preserves precision through the HTTP boundary (FE parses
    back to number). Lists/tuples/dicts recurse. Everything else passes
    through — assumes it's already a JSON primitive.
    """
    if obj is None:
        return None
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if is_dataclass(obj):
        return {f.name: _serialise(getattr(obj, f.name)) for f in fields(obj)}
    if isinstance(obj, dict):
        return {str(k): _serialise(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialise(x) for x in obj]
    return obj


@extend_schema(tags=['FPO - DPR Calculation'])
class DPRCalculationView(APIView):
    """GET the full 10-year financial calculation for a project.

    Returns the CalculationResult dataclass tree flattened to JSON:
      - projection_years, cost, mof, variance
      - capital_schedule (with is_estimated + per-month rows)
      - depreciation (per class + per-year rows + totals)
      - interest_schedule (loan amortisation)
      - profit_loss (Y1..YN)
      - cash_flow (Y0..YN)
      - balance_sheet (Y0..YN + A=E+L invariant per year)
      - ratios (NPV / IRR / DSCR / payback / break-even)

    Decimals are serialised as strings so the FE can parse without
    precision loss.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='Get 10-year financial calculation for a DPR project')
    def get(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        result = compute(project)
        return StandardResponse.success(
            _serialise(result),
            'Calculation computed',
        )


@extend_schema(tags=['FPO - DPR Calculation'])
class DPRPdfDownloadView(APIView):
    """GET the DPR as a PDF file. Streams the bytes as attachment.

    Filename: `dpr_<title-slug>_<uuid-short>.pdf`. Falls back to `dpr_<uuid>.pdf`
    when the project has no title.

    ┌─ Sync-now, Celery-later (decision 2026-09-02) ──────────────────────┐
    │ PDF generation currently runs SYNCHRONOUSLY in the request thread.  │
    │ Timing: compute() ~10-50ms + WeasyPrint ~3-4s = ~4-5s total.        │
    │ Blocks one gunicorn worker per PDF request.                         │
    │                                                                     │
    │ Chose sync because:                                                 │
    │   - 10-20 FPO testers, low concurrency                              │
    │   - Simple UX (click → file)                                        │
    │   - No storage / polling / notification infra needed                │
    │                                                                     │
    │ Migrate to Celery WHEN any of these become true:                    │
    │   - p95 generation > 10s (worker starvation risk)                   │
    │   - ≥50 concurrent generations regularly                            │
    │   - Product wants "email me the PDF when ready" or S3 archive       │
    │                                                                     │
    │ Infra ready: Celery 5.3 + Redis broker + @shared_task pattern       │
    │ (already used in apps/notifications/tasks.py etc.).                 │
    │ Migration path: ~1 day — see DPR_V2_BUILD_PLAN.md § "Deferred".     │
    └─────────────────────────────────────────────────────────────────────┘
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='Download the generated DPR PDF',
        responses={200: bytes},
    )
    def get(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        pdf_bytes = render_pdf_for_project(project)

        # Filename — keep it filesystem-safe and short. Uses title if present.
        raw_title = (project.title or '').strip() or 'dpr'
        slug = ''.join(c if c.isalnum() else '_' for c in raw_title)[:40].strip('_') or 'dpr'
        short_uuid = str(project.uuid)[:8]
        filename = f'{slug}_{short_uuid}.pdf'

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Content-Length'] = str(len(pdf_bytes))
        return response


# ─────────────────────────────────────────────────────────────────────────
# Versioned DPR document endpoints — KAU pre-UAT reply §7.1 + §7.2
# ─────────────────────────────────────────────────────────────────────────

def _serialise_document(doc: DPRDocument) -> dict:
    """Shape a DPRDocument for JSON responses."""
    return {
        'id': doc.id,
        'version_number': doc.version_number,
        'file_url': doc.file_url,
        'file_size': doc.file_size,
        'generated_at': doc.generated_at.isoformat() if doc.generated_at else None,
        'status': doc.status,
        'status_display': doc.get_status_display(),
        'is_archived': doc.is_archived,
        'filename': build_pdf_filename(doc.project, doc.version_number),
    }


class DPRDocumentGenerateView(APIView):
    """POST → generate + persist a new DPRDocument with a fresh monotonic
    version_number.

    Returns the new row's metadata (not the PDF bytes — the FE downloads
    via `/documents/<version>/download/`). This split lets the FE show the
    version + timestamp + status in a list before the user opens the file.

    Per KAU pre-UAT reply §7.2 (2026-09-08): version numbers never reset;
    older versions past the retention cap are soft-archived (`is_archived=True`),
    never deleted.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='Generate a new versioned DPR PDF',
        description='Creates a new DPRDocument row with fresh version_number '
                    '(monotonic per project, never resets). Returns the row '
                    'metadata; download the actual file via '
                    '/documents/<version>/download/.',
        request=None,
        responses={201: dict},
    )
    def post(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        doc = save_pdf_to_document(project)
        return StandardResponse.success(
            _serialise_document(doc),
            message=f'DPR v{doc.version_number} generated successfully.',
            status_code=201,
        )


class DPRDocumentListView(APIView):
    """GET → list DPRDocument rows for a project (newest first, excludes archived
    unless ?include_archived=true is passed).

    Per KAU pre-UAT reply §7.2 the download list must show both the version
    number and the generation timestamp per row; this endpoint returns both
    plus the status label (Draft / User-edited / Final) so the FPO can
    distinguish successive drafts at a glance.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='List generated DPR documents for a project',
        parameters=[],
        responses={200: dict},
    )
    def get(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        include_archived = request.query_params.get('include_archived', '').lower() in ('1', 'true', 'yes')
        qs = DPRDocument.objects.filter(project=project)
        if not include_archived:
            qs = qs.filter(is_archived=False)
        qs = qs.order_by('-version_number')
        return StandardResponse.success(
            [_serialise_document(d) for d in qs],
            message=f'{qs.count()} document(s) found.',
        )


@extend_schema(tags=['FPO - DPR Calculation'])
class DPRFinancialsExcelView(APIView):
    """GET → stream the projected financials as an .xlsx workbook.

    Per KAU pre-UAT reply §6.3 (2026-09-08): the bank appraisal officer needs
    the projected P&L / Cash Flow / Balance Sheet / ratios in a spreadsheet
    so they can plug them into their own model without re-typing. This is a
    read-only view over the same calc engine result the PDF renders.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='Download the projected DPR financials as an Excel workbook',
        description='Returns a multi-sheet .xlsx with the full calc engine '
                    'output — Cost & MoF, Capital Schedule, Depreciation, '
                    'Interest, P&L, Cash Flow, Balance Sheet, Ratios, DSCR.',
        responses={200: bytes, 404: dict},
    )
    def get(self, request, project_uuid):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        buf = render_financials_workbook(project)

        # Filename mirrors the PDF pattern for banker-familiarity: DPR_<FPO>_
        # Financials_<YYYYMMDD>.xlsx. Use the same _fpo_slug sanitiser the PDF
        # uses so both files line up in a bank folder.
        from datetime import datetime

        from apps.fpo.services.dpr.pdf import _fpo_slug

        stamp = datetime.now().strftime('%Y%m%d')
        filename = f'DPR_{_fpo_slug(project)}_Financials_{stamp}.xlsx'

        response = HttpResponse(
            buf.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Content-Length'] = str(len(response.content))
        return response


class DPRDocumentDownloadView(APIView):
    """GET → stream a specific version's PDF bytes.

    Serves from `MEDIA_ROOT/dpr/<project_uuid>/<filename>`. Safe against
    path-traversal because we look up the DPRDocument row first (uses the
    version_number captive to the URL) and then serve exactly the file_url
    it recorded. If the on-disk file is missing (e.g. media-volume wipe on
    a deploy), returns 410 Gone.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary='Download a specific version of a generated DPR PDF',
        responses={200: bytes, 404: dict, 410: dict},
    )
    def get(self, request, project_uuid, version_number: int):
        project, err = get_project_or_error(request.user, project_uuid)
        if err:
            return err
        try:
            doc = DPRDocument.objects.get(project=project, version_number=version_number)
        except DPRDocument.DoesNotExist:
            return StandardResponse.error(
                message=f'DPR v{version_number} not found for this project.',
                status_code=404,
            )
        # Reconstruct the absolute path from the stored MEDIA_URL-relative path.
        # Strip the MEDIA_URL prefix so we don't concatenate leading slashes.
        rel = doc.file_url
        if rel.startswith(settings.MEDIA_URL):
            rel = rel[len(settings.MEDIA_URL):]
        absolute_path = os.path.join(settings.MEDIA_ROOT, rel.lstrip('/'))
        if not os.path.exists(absolute_path):
            return StandardResponse.error(
                message=f'DPR v{version_number} file is missing from storage. '
                        f'Re-generate to produce a new version.',
                status_code=410,
            )
        filename = build_pdf_filename(project, version_number)
        response = FileResponse(open(absolute_path, 'rb'), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Content-Length'] = str(doc.file_size)
        return response
