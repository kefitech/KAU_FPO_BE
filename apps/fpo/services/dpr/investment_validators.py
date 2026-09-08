"""
Validation service for §2.3.4 Proposed Project Investment.

KAU-spec rules:
    - This section is CONDITIONAL — the whole section may be left blank.
    - If `estimated_project_cost` is provided, it shall be > 0.
    - If `estimated_project_cost` is provided, `basis_of_estimate` is recommended
      (warning, not error).

KAU RCD reply B.4 — cross-section variance check:
    If both §2.3.4 estimated_project_cost AND §2.3.18 Finance line items are
    populated, the system compares the two. When the variance exceeds
    `DPRConfig.project_cost_variance_pct` (default 10%, admin-editable), a
    warning is raised prompting the FPO to reconcile the two numbers before
    the auto-computed cost becomes authoritative for the DPR PDF.
"""
from typing import Any

from .calculation import compute_user_estimate_variance


def _err(code: str, field: str, message: str) -> dict[str, Any]:
    return {'code': code, 'field': field, 'message': message}


def _warn(code: str, field: str, message: str) -> dict[str, Any]:
    return {'code': code, 'field': field, 'message': message}


def _fmt_inr(amount) -> str:
    """Format a Decimal amount in INR with thousands separators. Bare
    string helper — no locale dependency."""
    try:
        return f'₹{amount:,.0f}'
    except (TypeError, ValueError):
        return f'₹{amount}'


def validate_section(section) -> dict[str, Any]:
    errors: list[dict] = []
    warnings: list[dict] = []

    if section.estimated_project_cost is not None:
        if section.estimated_project_cost <= 0:
            errors.append(_err(
                'cost_positive', 'estimated_project_cost',
                'Estimated Project Cost shall be greater than zero.',
            ))
        if not section.basis_of_estimate:
            warnings.append(_warn(
                'basis_recommended', 'basis_of_estimate',
                'Basis of Estimate is recommended when a project cost is provided.',
            ))

    # RCD B.4 — variance between user estimate and auto-computed Finance cost.
    # Only fires when the user gave a positive estimate AND the Finance section
    # has real numbers (skipped/zero cases return exceeds_threshold=False).
    variance = compute_user_estimate_variance(section.project)
    if variance.exceeds_threshold:
        direction = 'below' if variance.delta > 0 else 'above'
        warnings.append(_warn(
            'estimate_variance_high',
            'estimated_project_cost',
            (
                f'Your estimate of {_fmt_inr(variance.user_estimate)} is '
                f'{variance.pct:.1f}% {direction} the auto-computed project cost of '
                f'{_fmt_inr(variance.computed_cost)} (threshold {variance.threshold_pct}%). '
                f'Review the Finance section line items or update this estimate.'
            ),
        ))

    return {
        'errors': errors,
        'warnings': warnings,
        'is_complete': len(errors) == 0,
    }
