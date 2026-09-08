"""
Seed the initial DPR component applicability rules — Phase 6a.

Per KAU RCD reply A.1 (2026-09-02):
    "The following should be treated as an initial domain applicability
     framework, to be validated by KAU during testing/UAT rather than as
     a rigid hard-coded matrix."

This script seeds the ONE example KAU explicitly gave in the RCD:
    Custom Hiring Centre × raw-material = HIDDEN

Plus one inferred rule that follows the same logic:
    Cold Storage × raw-material = HIDDEN
    (Cold storage moves goods, doesn't process raw material.)

Everything else defaults to Optional (O) — sections are shown but not
mandatory. KAU admin refines during UAT via `/admin/dpr-applicability`
(the M/O/H matrix) once Phase 6c ships.

Level 2 field rules (e.g. "hide steam_capacity unless boiler component
selected") are intentionally NOT seeded here. They ship per-request as
KAU flags them during UAT — the schema is future-proof but we don't
speculate on field-level rules ahead of the domain review.

Idempotent — uses `update_or_create` on (component, data_element_key).
Re-running always applies the latest rule set.

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/seed_dpr_applicability.py').read())
    seed_dpr_applicability()
    "

Author: Athul Gopan (Kefi Tech Solutions)
"""
from apps.database.models import DPRComponent, DPRComponentApplicability


# ─────────────────────────────────────────────────────────────────────────────
# Rules — only explicit M / H cases. Missing rules default to O.
# Format: (component_code, data_element_key, applicability, notes)
# ─────────────────────────────────────────────────────────────────────────────

RULES = [
    # ── Custom Hiring Centre ───────────────────────────────────────────────
    # From RCD A.1: "for a Custom Hiring Centre, raw-material assessment
    # should not normally be displayed, while machinery/equipment,
    # capacity/service delivery, manpower, financial, market, statutory,
    # implementation and risk-related information would be relevant."
    (
        'custom_hiring_centre', 'raw-material', 'H',
        'RCD A.1 explicit: Custom Hiring Centre offers services, does not process raw material.',
    ),

    # ── Cold Storage ───────────────────────────────────────────────────────
    # From RCD A.1: cold storage relevant sections listed as Capacity,
    # Technology, Land/Site, Civil, P&M, Utilities, HR, Financial,
    # Compliance, ESS, Implementation, Risk. Raw-material not listed →
    # inferring HIDDEN because cold storage stores existing produce, does
    # not process raw material into finished goods.
    (
        'cold_storage', 'raw-material', 'H',
        'Cold Storage stores existing produce; no raw-material processing.',
    ),
]


def seed_dpr_applicability():
    created = 0
    updated = 0
    skipped = 0

    for component_code, section_key, applicability, notes in RULES:
        try:
            component = DPRComponent.objects.get(code=component_code)
        except DPRComponent.DoesNotExist:
            print(f'  SKIP — component "{component_code}" not found in DPRComponent master')
            skipped += 1
            continue

        _, was_created = DPRComponentApplicability.objects.update_or_create(
            component=component,
            data_element_key=section_key,
            defaults={
                'applicability': applicability,
                'notes': notes,
            },
        )
        if was_created:
            created += 1
        else:
            updated += 1

    total = DPRComponentApplicability.objects.count()
    print(f'DPR applicability seed complete:')
    print(f'  created:  {created}')
    print(f'  updated:  {updated}')
    print(f'  skipped (missing component): {skipped}')
    print(f'  total rules in DB: {total}')
    print()
    print(f'Note: sections not listed default to Optional (shown, not required).')
    print(f'KAU refines via /admin/dpr-applicability matrix once Phase 6c ships.')
