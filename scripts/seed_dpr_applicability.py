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

# Sections that ALWAYS apply — never need a rule row (default = Optional).
# Listed here as documentation so future contributors don't waste time seeding
# universally-relevant sections: identification, components, nature-of-business,
# investment, location, rationale, baseline, market, finance, compliance,
# ess, implementation, risk, hr.
#
# Only sections whose applicability GENUINELY depends on the component are
# seeded — everything else defaults to Optional and shows for all projects.


# Rule template — one tuple per (component group, applicability plan).
# Each plan lists (section_key, M|H, note). Missing sections default to O.
#
# Compiled into flat RULES = [(component_code, section_key, level, note), …]
# below. Grouping keeps the intent readable while staying data-only.

_STORAGE_POST_HARVEST_PLAN = [
    # Storage components hold existing produce — no raw-material processing.
    ('raw-material', 'H', 'Storage component: stores existing produce, no raw-material processing.'),
    # Physical infrastructure sections are mandatory — you cannot build a
    # cold storage / warehouse without land, civil works, utilities, machinery.
    ('site',        'M', 'Storage requires land & site — mandatory.'),
    ('civil',       'M', 'Storage requires civil works — mandatory.'),
    ('utilities',   'M', 'Storage requires utilities (power, water, refrigeration) — mandatory.'),
    ('machinery',   'M', 'Storage requires plant & machinery — mandatory.'),
    ('technology',  'M', 'Storage technology / process flow — mandatory.'),
    ('capacity',    'M', 'Storage capacity / throughput — mandatory.'),
]

_PROCESSING_VALUE_ADDITION_PLAN = [
    # Processing lines depend fundamentally on raw material supply.
    ('raw-material', 'M', 'Processing: raw material sourcing plan is mandatory.'),
    ('products',     'M', 'Processing: finished-product definition mandatory.'),
    ('site',         'M', 'Processing requires land & site — mandatory.'),
    ('civil',        'M', 'Processing requires civil works — mandatory.'),
    ('utilities',    'M', 'Processing requires utilities — mandatory.'),
    ('machinery',    'M', 'Processing requires plant & machinery — mandatory.'),
    ('technology',   'M', 'Processing technology / flow diagram — mandatory.'),
    ('capacity',     'M', 'Processing capacity / throughput — mandatory.'),
]

_PRIMARY_PRODUCTION_PLAN = [
    # Primary production IS the source — no external raw material sourcing.
    ('raw-material', 'H', 'Primary production is the raw-material source; no external sourcing plan needed.'),
    ('site',         'M', 'Primary production requires land — mandatory.'),
    ('capacity',     'M', 'Production capacity / yield — mandatory.'),
    ('technology',   'M', 'Production technology / agronomy — mandatory.'),
]

_SERVICE_ENTERPRISE_PLAN = [
    # Services rent-out equipment or provide expertise — no material processing,
    # no finished products.
    ('raw-material', 'H', 'Service enterprise: no raw-material processing.'),
    ('products',     'H', 'Service enterprise: services delivered, not products.'),
    ('machinery',    'M', 'Service enterprise: equipment inventory is mandatory.'),
    ('capacity',     'M', 'Service capacity (hours/month, tests/day, etc.) mandatory.'),
    ('hr',           'M', 'Service enterprise: manpower is the core deliverable.'),
]

_MARKETING_BUSINESS_DEV_PLAN = [
    # Marketing/business dev deals with existing product — no processing,
    # no capacity, no machinery.
    ('raw-material', 'H', 'Marketing/business-dev: no raw-material processing.'),
    ('capacity',     'H', 'Marketing/business-dev: no production capacity.'),
    ('machinery',    'H', 'Marketing/business-dev: no plant & machinery.'),
    ('utilities',    'H', 'Marketing/business-dev: no utility infrastructure requirements.'),
    ('technology',   'H', 'Marketing/business-dev: not a technology-driven investment.'),
    ('products',     'M', 'Marketing: product portfolio mandatory.'),
    ('hr',           'M', 'Marketing: sales team / staffing plan mandatory.'),
]

_SUPPORTING_INFRA_PLAN = [
    # Supporting infra components are usually annexes to a larger enterprise
    # (roads, admin block, utility yard, renewable-energy). They rarely have
    # meaningful raw-material or capacity data of their own.
    ('raw-material', 'H', 'Supporting infrastructure: no raw-material processing of its own.'),
    ('products',     'H', 'Supporting infrastructure: no finished products of its own.'),
    ('capacity',     'H', 'Supporting infrastructure: no production capacity of its own.'),
    ('site',         'M', 'Supporting infrastructure requires land — mandatory.'),
    ('civil',        'M', 'Supporting infrastructure = civil works by definition.'),
]

# Which components fall into which plan. Codes come from DPRComponent seed.
_COMPONENT_TO_PLAN = {
    # Storage / post-harvest
    'cold_storage':       _STORAGE_POST_HARVEST_PLAN,
    'dry_storage':        _STORAGE_POST_HARVEST_PLAN,
    'warehouse':          _STORAGE_POST_HARVEST_PLAN,
    'pack_house':         _STORAGE_POST_HARVEST_PLAN,
    'collection_centre':  _STORAGE_POST_HARVEST_PLAN,
    'ripening_chamber':   _STORAGE_POST_HARVEST_PLAN,

    # Processing / value addition
    'food_processing':       _PROCESSING_VALUE_ADDITION_PLAN,
    'primary_processing':    _PROCESSING_VALUE_ADDITION_PLAN,
    'value_addition':        _PROCESSING_VALUE_ADDITION_PLAN,
    'feed_manufacturing':    _PROCESSING_VALUE_ADDITION_PLAN,
    'organic_bio_input_prod':_PROCESSING_VALUE_ADDITION_PLAN,

    # Primary production
    'crop_production':        _PRIMARY_PRODUCTION_PLAN,
    'horticulture':           _PRIMARY_PRODUCTION_PLAN,
    'plantation_crops':       _PRIMARY_PRODUCTION_PLAN,
    'seed_production':        _PRIMARY_PRODUCTION_PLAN,
    'nursery':                _PRIMARY_PRODUCTION_PLAN,
    'protected_cultivation':  _PRIMARY_PRODUCTION_PLAN,
    'livestock':              _PRIMARY_PRODUCTION_PLAN,
    'fisheries_aquaculture':  _PRIMARY_PRODUCTION_PLAN,

    # Service enterprises
    'custom_hiring_centre':      _SERVICE_ENTERPRISE_PLAN,
    'farm_machinery_bank':       _SERVICE_ENTERPRISE_PLAN,
    'agri_input_centre':         _SERVICE_ENTERPRISE_PLAN,
    'soil_testing_lab':          _SERVICE_ENTERPRISE_PLAN,
    'training_extension_centre': _SERVICE_ENTERPRISE_PLAN,

    # Marketing / business dev
    'retail_outlet':       _MARKETING_BUSINESS_DEV_PLAN,
    'wholesale_marketing': _MARKETING_BUSINESS_DEV_PLAN,
    'e_commerce':          _MARKETING_BUSINESS_DEV_PLAN,
    'export':              _MARKETING_BUSINESS_DEV_PLAN,
    'branding_packaging':  _MARKETING_BUSINESS_DEV_PLAN,

    # Supporting infrastructure
    'utility_infrastructure':  _SUPPORTING_INFRA_PLAN,
    'renewable_energy_system': _SUPPORTING_INFRA_PLAN,
    'administrative_building': _SUPPORTING_INFRA_PLAN,
    'processing_building':     _SUPPORTING_INFRA_PLAN,
    'internal_roads_site_dev': _SUPPORTING_INFRA_PLAN,
}


RULES = [
    (code, section, level, note)
    for code, plan in _COMPONENT_TO_PLAN.items()
    for section, level, note in plan
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
