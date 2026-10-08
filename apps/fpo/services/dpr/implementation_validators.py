"""
Validation service for §2.3.21 Project Implementation Plan.

KAU-spec rules:
    Cat A: activity name required; start_date must precede completion_date (if both entered)
    Cat B: procurement_method required
    Cat E: monitoring_frequency required
    "Others" specify text for procurement/responsibility/milestone
"""
from typing import Any


def _err(code: str, field: str, message: str) -> dict[str, Any]:
    return {'code': code, 'field': field, 'message': message}


def validate_section(section) -> dict[str, Any]:
    errors: list[dict] = []
    warnings: list[dict] = []

    # Cat A
    for i, act in enumerate(section.activities.all()):
        p = f'activities[{i}]'
        if not (act.activity_name or '').strip():
            errors.append(_err('activity_name_required', f'{p}.activity_name', 'Activity name is required.'))
        if act.proposed_start_date and act.proposed_completion_date:
            if act.proposed_start_date > act.proposed_completion_date:
                errors.append(_err(
                    'start_before_completion', f'{p}.proposed_start_date',
                    'Start Date shall precede Completion Date.',
                ))

    # Cat B
    if not section.procurement_method:
        errors.append(_err('procurement_method_required', 'procurement_method', 'Procurement Method shall be specified.'))
    if section.procurement_method == 'other' and not (section.procurement_method_other or '').strip():
        errors.append(_err('procurement_other_required', 'procurement_method_other', 'Please specify — "Others" was selected for procurement method.'))

    # Cat C
    if 'other' in (section.responsibility_agencies or []) and not (section.responsibility_agency_other or '').strip():
        errors.append(_err('responsibility_other_required', 'responsibility_agency_other', 'Please specify — "Others" was selected in responsibility agencies.'))

    # Cat D — milestone "other" text
    for i, m in enumerate(section.milestones.all()):
        if m.milestone_type == 'other' and not (m.milestone_type_other or '').strip():
            errors.append(_err(
                'milestone_other_required', f'milestones[{i}].milestone_type_other',
                'Please specify — "Others" was selected for milestone type.',
            ))

    # Cat E
    if not section.monitoring_frequency:
        errors.append(_err('monitoring_frequency_required', 'monitoring_frequency', 'Monitoring Frequency shall be specified.'))

    # KAU contradiction review 2026-10-08 (S03-02, C02-13, Pattern 7):
    # civil/construction activities scheduled to START before the expected
    # approval dates of the Building Permit / CTE that the compliance
    # section says must precede construction. Warn per offending activity.
    try:
        import re as _re
        _CIVIL_RE = _re.compile(
            r'civil|construction|building|shed|foundation|erection|'
            r'site prep|land development', _re.IGNORECASE)
        compliance = getattr(section.project, 'section_compliance', None)
        permit_dates = []
        if compliance is not None:
            for item in compliance.items.select_related('registration'):
                code = getattr(item.registration, 'code', '') if item.registration_id else ''
                if code in ('building_permit', 'consent_establish') and item.expected_date_of_approval:
                    if item.status != 'available':
                        permit_dates.append((code, item.expected_date_of_approval))
        if permit_dates:
            latest_code, latest_date = max(permit_dates, key=lambda t: t[1])
            for i, act in enumerate(section.activities.all()):
                if not act.proposed_start_date:
                    continue
                if _CIVIL_RE.search(act.activity_name or '') and act.proposed_start_date < latest_date:
                    warnings.append(_warn(
                        'civil_before_permit', f'activities[{i}].proposed_start_date',
                        f'"{act.activity_name}" starts {act.proposed_start_date:%d %b %Y}, '
                        f'before the expected approval of '
                        f'{"the Building Permit" if latest_code == "building_permit" else "the Consent to Establish (CTE)"} '
                        f'({latest_date:%d %b %Y}). Construction cannot legally begin '
                        f'before these clearances — move the activity after the '
                        f'approval date or update the expected date in §2.3.19.',
                    ))
    except Exception:  # noqa: BLE001 — cross-section lookups must never break this validator
        pass

    return {
        'errors': errors,
        'warnings': warnings,
        'is_complete': len(errors) == 0,
    }
