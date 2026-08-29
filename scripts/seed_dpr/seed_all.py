"""
Master DPR seed runner — calls all group seeds in order.

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/seed_dpr/seed_all.py').read())
    seed_all_dpr_master()
    "

Idempotent — safe to re-run.
"""


def seed_all_dpr_master():
    print('=' * 60)
    print('DPR Master Data Seed — all groups')
    print('=' * 60)

    exec(open('scripts/seed_dpr/seed_project_definition.py').read(), globals())
    seed_project_definition()
    print()

    exec(open('scripts/seed_dpr/seed_capacity_products.py').read(), globals())
    seed_capacity_products()
    print()

    exec(open('scripts/seed_dpr/seed_raw_material.py').read(), globals())
    seed_raw_material()
    print()

    exec(open('scripts/seed_dpr/seed_market.py').read(), globals())
    seed_market()
    print()

    exec(open('scripts/seed_dpr/seed_infrastructure.py').read(), globals())
    seed_infrastructure()
    print()

    exec(open('scripts/seed_dpr/seed_utilities_hr.py').read(), globals())
    seed_utilities_hr()
    print()

    exec(open('scripts/seed_dpr/seed_environment_risk.py').read(), globals())
    seed_environment_risk()
    print()

    exec(open('scripts/seed_dpr/seed_compliance.py').read(), globals())
    seed_compliance()
    print()

    print('=' * 60)
    print('All DPR master data seeded.')
    print('=' * 60)
