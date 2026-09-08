"""
Seed DPRConfig defaults — the KAU Central Admin-controlled parameters
that drive the DPR module.

Per KAU RCD reply B.6 (financial assumptions) + B.4 (variance threshold) +
C.4 (PDF retention) + A.3 (projection years).

Idempotent — safe to re-run. Existing rows are LEFT UNCHANGED (we do not
override an admin's edit on re-seed). Only new keys get inserted.

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/seed_dpr_config.py').read())
    seed_dpr_config()
    "
"""


# Each row: (key, category, value_type, default, label, description, unit, min, max)
# Financial defaults align with existing hardcoded values in dpr_calculation.py
# (to be swapped over to DPRConfig.get_* calls in a follow-up).
CONFIG_SEEDS = [
    # ── Financial assumptions (B.6) ─────────────────────────────────────
    (
        'discount_rate_pct', 'financial', 'decimal', '12.00',
        'Discount rate',
        'Discount rate used for NPV / IRR calculations in the DPR appraisal chapter. '
        'Standard 12% aligns with commercial bank lending baseline in India.',
        '%', '5', '25',
    ),
    (
        'inflation_rate_pct', 'financial', 'decimal', '6.00',
        'Inflation rate',
        'Annual inflation rate applied to operating costs and revenues in the '
        '10-year projection.',
        '%', '0', '15',
    ),
    (
        'tax_rate_pct', 'financial', 'decimal', '25.17',
        'Corporate tax rate',
        'Effective corporate tax rate for FPO / Producer Company income. '
        '25.17% is the current rate under Section 115BAA (base 22% + surcharge + cess).',
        '%', '0', '40',
    ),
    (
        'depreciation_rate_building_pct', 'financial', 'decimal', '5.00',
        'Depreciation — buildings',
        'Straight-line depreciation rate for civil works / buildings.',
        '%', '1', '20',
    ),
    (
        'depreciation_rate_machinery_pct', 'financial', 'decimal', '10.00',
        'Depreciation — machinery',
        'Straight-line depreciation rate for plant & machinery.',
        '%', '5', '25',
    ),
    (
        'depreciation_rate_equipment_pct', 'financial', 'decimal', '15.00',
        'Depreciation — equipment',
        'Straight-line depreciation rate for smaller equipment / furniture.',
        '%', '5', '30',
    ),
    (
        'loan_interest_rate_default_pct', 'financial', 'decimal', '10.50',
        'Loan interest rate (default)',
        'Default interest rate used when the user has not supplied a project-specific rate. '
        'FPO term loan baseline.',
        '%', '5', '20',
    ),
    (
        'loan_tenure_default_years', 'financial', 'int', 7,
        'Loan tenure (default)',
        'Default term-loan tenure in years, used when the user has not supplied one.',
        'years', 1, 20,
    ),
    (
        'loan_moratorium_default_months', 'financial', 'int', 12,
        'Loan moratorium (default)',
        'Default moratorium period in months, used when the user has not supplied one.',
        'months', 0, 36,
    ),
    # Per KAU pre-UAT reply §2.2 (2026-09-08). Two lawful treatments for
    # interest that accrues during the moratorium:
    #   'serviced'    — interest paid periodically, loan balance stays flat
    #                   (i.e. FPO services interest even before principal starts).
    #   'capitalised' — interest is added to loan outstanding, no cash
    #                   payment during moratorium; post-moratorium principal
    #                   is calculated on the grown balance.
    # KAU can flip the default at any time via /admin/dpr-config without
    # a code deploy. Applies uniformly to all projects.
    (
        'moratorium_interest_treatment', 'financial', 'string', 'serviced',
        'Interest during moratorium',
        'How interest accruing during the loan moratorium is treated: '
        '"serviced" (paid periodically, loan balance flat) or '
        '"capitalised" (added to loan outstanding). '
        'Per KAU pre-UAT reply §2.2 (2026-09-08).',
        '', '', '',
    ),

    # ── Projection settings (A.3) ───────────────────────────────────────
    (
        'projection_years', 'projection', 'int', 10,
        'Projection years',
        'Number of years to project the balance sheet, P&L, and cash flow. '
        'KAU RCD A.3 specifies 10 years.',
        'years', 3, 20,
    ),
    (
        'implementation_period_months', 'projection', 'int', 12,
        'Implementation period',
        'Assumed project implementation duration in months. Used by the capital '
        'schedule to distribute costs and means of finance across the construction '
        'period when explicit tranche data is not provided. Superseded on a '
        'per-project basis when the DPRCapitalTranche model is added.',
        'months', 1, 60,
    ),

    # ── Variance thresholds (B.4) ───────────────────────────────────────
    (
        'project_cost_variance_pct', 'variance', 'decimal', '10.00',
        'Project cost variance threshold',
        'Maximum tolerated variance between the user-entered total project cost '
        'and the auto-computed sum. Above this, the system shows a warning '
        '(not an error). KAU RCD B.4.',
        '%', '0', '100',
    ),

    # ── Retention & archival (C.4) ──────────────────────────────────────
    (
        'pdf_version_retention_count', 'retention', 'int', 10,
        'PDF version retention limit',
        'Number of previous DPR PDF versions to retain per project (in addition '
        'to the current). Older PDFs are auto-archived on new generation.',
        'count', 1, 50,
    ),

    # ── Risk matrix (B.9 — placeholders, matrix logic in Phase 4) ────────
    (
        'risk_matrix_size', 'risk', 'int', 5,
        'Risk matrix size',
        'Grid dimension for the probability × impact matrix (N × N). '
        'Standard 5x5. Actual matrix cells are configured separately in Phase 4.',
        'count', 3, 7,
    ),

    # ── Dynamic questionnaire feature flag (Phase 6 — KAU RCD A.1) ───────
    # OFF by default = current behaviour (all 22 sections shown to every FPO).
    # Flip to true once Phase 6c ships and KAU signs off on the seeded
    # applicability rules. Safe rollback path — flip back to false if a
    # regression appears; no data affected.
    (
        'rule_engine_enabled', 'other', 'bool', False,
        'Dynamic questionnaire rule engine',
        'When enabled, the DPR wizard filters sections based on the project\'s '
        'selected components using DPRComponentApplicability rules (KAU RCD A.1). '
        'When disabled, all 22 sections are shown to every FPO (Phase 6 rollback path).',
        '', None, None,
    ),
]


def seed_dpr_config():
    from apps.database.models import DPRConfig

    created = 0
    skipped = 0
    for row in CONFIG_SEEDS:
        key, category, value_type, default, label, description, unit, mn, mx = row
        _, was_created = DPRConfig.objects.get_or_create(
            key=key,
            defaults=dict(
                category=category,
                value_type=value_type,
                value=default,          # Fresh installs start at default
                default_value=default,
                label=label,
                description=description,
                unit=unit,
                min_value=mn,
                max_value=mx,
                is_editable=True,
            ),
        )
        if was_created:
            created += 1
            print(f'  + {key}')
        else:
            skipped += 1

    print(f'\nDPRConfig seed complete: {created} created, {skipped} already present.')
