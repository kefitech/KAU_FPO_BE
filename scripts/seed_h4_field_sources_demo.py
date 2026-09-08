"""
H4 demo seeder — writes sample AI-inferred / system-default field source values
into a chosen DPRProject so the KAU tester can see FieldSourceBadge in action
on the wizard.

Usage from Django shell:
    exec(open('scripts/seed_h4_field_sources_demo.py').read())
    seed_h4_field_sources_demo('7a44dcf8-8b49-4fd1-a036-1f264b12f026')

Sources planted (deliberately spread across visible wizard fields so a KAU
tester walking through Finance + HR sees blue / purple / orange badges):

Finance section:
    ai_inferred    — rate_of_interest_pct, moratorium_period_months,
                     repayment_period_years, subsidy_scheme_name
    system_default — cost_land, cost_buildings, cost_pre_operative
    user_overridden — loan_type   (simulates: AI picked "term_loan", user changed it)

HR section:
    ai_inferred    — operational_management_model, expansion_year,
                     additional_salary_requirement
    system_default — existing_regular_employees
    user_overridden — additional_employees_planned

Safe to re-run — overwrites the H4 keys, leaves all other keys untouched.
"""
from apps.database.models.dpr import DPRProject
from apps.fpo.services.dpr.field_sources import (
    SOURCE_AI_INFERRED,
    SOURCE_SYSTEM_DEFAULT,
    SOURCE_USER_OVERRIDDEN,
)


_H4_DEMO_MAP: dict[str, dict[str, str]] = {
    'finance': {
        'rate_of_interest_pct':      SOURCE_AI_INFERRED,
        'moratorium_period_months':  SOURCE_AI_INFERRED,
        'repayment_period_years':    SOURCE_AI_INFERRED,
        'subsidy_scheme_name':       SOURCE_AI_INFERRED,
        'cost_land':                 SOURCE_SYSTEM_DEFAULT,
        'cost_buildings':            SOURCE_SYSTEM_DEFAULT,
        'cost_pre_operative':        SOURCE_SYSTEM_DEFAULT,
        'loan_type':                 SOURCE_USER_OVERRIDDEN,
    },
    'hr': {
        'operational_management_model': SOURCE_AI_INFERRED,
        'expansion_year':               SOURCE_AI_INFERRED,
        'additional_salary_requirement': SOURCE_AI_INFERRED,
        'existing_regular_employees':   SOURCE_SYSTEM_DEFAULT,
        'additional_employees_planned': SOURCE_USER_OVERRIDDEN,
    },
}


def seed_h4_field_sources_demo(project_uuid: str) -> DPRProject:
    project = DPRProject.objects.get(uuid=project_uuid)
    existing = dict(project.field_sources or {})
    for section_key, field_map in _H4_DEMO_MAP.items():
        section = dict(existing.get(section_key, {}))
        section.update(field_map)
        existing[section_key] = section
    project.field_sources = existing
    project.save(update_fields=['field_sources'])

    print(f'Seeded field-source demo values for project {project.uuid}')
    print('Now open the wizard on Finance + HR sections — badges should be visible.')
    print()
    for section_key, field_map in _H4_DEMO_MAP.items():
        print(f'  [{section_key}]')
        for field, source in field_map.items():
            print(f'    {field:38s} -> {source}')
    return project
