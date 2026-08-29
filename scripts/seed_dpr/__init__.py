"""
DPR Master Data Seed Scripts
============================
Grouped by KAU spec section. Each script exposes seed_*() functions that use
update_or_create — safe to re-run.

Run all seeds:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/seed_dpr/seed_all.py').read())
    seed_all_dpr_master()
    "

Run one group:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/seed_dpr/seed_project_definition.py').read())
    seed_project_definition()
    "

Spec: context/phase2/Dpr/Data Collection Module V1.0.pdf
Context: context/phase2/Dpr/DPR_V2_CONTEXT.md
"""
