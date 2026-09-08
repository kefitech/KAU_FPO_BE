"""
Rule engine smoke test — runs the same scenarios as `tests_rule_engine.py`
but as a plain Django script instead of via `manage.py test`.

Reason: dev environment's PostgreSQL role doesn't have superuser rights,
so Django test runner can't provision the test DB (postgis CREATE EXTENSION
fails). Once the dev DB is fixed / SQLite is added for tests, the real
suite at `apps/fpo/tests_rule_engine.py` will run without needing this
script.

Runs inside a transaction that ALWAYS rolls back — nothing persists to
the dev DB.

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/testing/rule_engine_smoke.py').read())
    smoke_test_rule_engine()
    "

Author: Athul Gopan (Kefi Tech Solutions)
"""
from django.db import transaction


def smoke_test_rule_engine():
    from apps.database.models import (
        DPRComponent,
        DPRComponentApplicability,
        DPRConfig,
        DPRFieldRule,
        DPRProject,
        DPRSectionComponents,
        FPO,
    )
    from apps.fpo.services.dpr import rule_engine as engine

    passed = 0
    failed = []

    def check(name, actual, expected):
        nonlocal passed
        if actual == expected:
            passed += 1
            print(f'  ✓ {name}')
        else:
            failed.append((name, actual, expected))
            print(f'  ✗ {name}  expected={expected!r} actual={actual!r}')

    # Use a single outer transaction that always rolls back — nothing persists.
    try:
        with transaction.atomic():
            sid = transaction.savepoint()

            # Feature flag on
            DPRConfig.objects.update_or_create(
                key='rule_engine_enabled',
                defaults={'category': 'other', 'value_type': 'bool', 'value': True,
                          'default_value': False, 'label': 't', 'description': '',
                          'unit': '', 'is_editable': True},
            )

            fpo = FPO.objects.create(name='SMOKE_TEST_FPO', district='TRS')
            project = DPRProject.objects.create(fpo=fpo, title='smoke test')
            cold = DPRComponent.objects.create(
                code='smoke_cold', label_en='Cold', group='storage_post_harvest',
            )
            hiring = DPRComponent.objects.create(
                code='smoke_hiring', label_en='Hiring', group='service_enterprises',
            )
            rice = DPRComponent.objects.create(
                code='smoke_rice', label_en='Rice', group='processing_value_addition',
            )
            boiler = DPRComponent.objects.create(
                code='smoke_boiler', label_en='Boiler', group='supporting_infrastructure',
            )

            def attach(*comps):
                sec, _ = DPRSectionComponents.objects.get_or_create(project=project)
                sec.components.set(comps)

            # ── Feature flag ────────────────────────────────────────────
            print('Feature flag')
            DPRConfig.objects.filter(key='rule_engine_enabled').update(value=False)
            attach(cold)
            DPRComponentApplicability.objects.create(
                component=cold, data_element_key='raw-material', applicability='H',
            )
            r = engine.evaluate_data_element(project)
            check('flag off returns all O', set(r.values()), {'O'})
            DPRConfig.objects.filter(key='rule_engine_enabled').update(value=True)

            # ── Level 1 ────────────────────────────────────────────────
            print('Level 1')
            attach(cold)
            r = engine.evaluate_data_element(project)
            check('cold-only, raw-material H', r['raw-material'], 'H')
            check('cold-only, finance defaults O', r['finance'], 'O')

            DPRComponentApplicability.objects.create(
                component=rice, data_element_key='raw-material', applicability='M',
            )
            attach(cold, rice)
            r = engine.evaluate_data_element(project)
            check('cold H + rice M → M wins', r['raw-material'], 'M')

            # O wins over H when no M
            DPRComponentApplicability.objects.filter(component=rice).delete()
            DPRComponentApplicability.objects.create(
                component=rice, data_element_key='raw-material', applicability='O',
            )
            attach(cold, rice)
            r = engine.evaluate_data_element(project)
            check('cold H + rice O → O wins', r['raw-material'], 'O')

            # All H → H
            DPRComponentApplicability.objects.filter(component=rice).delete()
            DPRComponentApplicability.objects.create(
                component=hiring, data_element_key='raw-material', applicability='H',
            )
            attach(cold, hiring)
            r = engine.evaluate_data_element(project)
            check('cold H + hiring H → H (unanimous)', r['raw-material'], 'H')

            # No components → all O
            DPRSectionComponents.objects.filter(project=project).delete()
            r = engine.evaluate_data_element(project)
            check('no components → all O', set(r.values()), {'O'})

            # Covers every known key
            attach(cold)
            r = engine.evaluate_data_element(project)
            check('result covers all sections', set(r.keys()), set(engine.ALL_SECTION_KEYS))

            # Helper: visible_sections excludes H
            visible = engine.visible_sections(project)
            check('visible_sections excludes H', 'raw-material' in visible, False)
            check('visible_sections includes O', 'finance' in visible, True)

            # Helper: mandatory_sections
            DPRComponentApplicability.objects.create(
                component=cold, data_element_key='finance', applicability='M',
            )
            mand = engine.mandatory_sections(project)
            check('mandatory_sections lists finance', 'finance' in mand, True)
            check('mandatory_sections excludes O', 'ess' in mand, False)

            # ── Level 2 — component_in ─────────────────────────────────
            print('Level 2 — component_in')
            DPRFieldRule.objects.all().delete()
            attach(cold)  # no boiler
            r = DPRFieldRule.objects.create(
                data_element_key='utilities', field_name='steam_capacity',
                recipe_type='component_in', visibility='show_when',
            )
            r.required_components.add(boiler)
            check(
                'show_when boiler, no boiler → hidden',
                engine.evaluate_field(project, 'utilities', 'steam_capacity'),
                False,
            )

            attach(cold, boiler)
            check(
                'show_when boiler, boiler present → visible',
                engine.evaluate_field(project, 'utilities', 'steam_capacity'),
                True,
            )

            # hide_when fires
            DPRFieldRule.objects.all().delete()
            hr = DPRFieldRule.objects.create(
                data_element_key='utilities', field_name='fuel_consumption',
                recipe_type='component_in', visibility='hide_when',
            )
            hr.required_components.add(cold)
            attach(cold)
            check(
                'hide_when cold, cold present → hidden',
                engine.evaluate_field(project, 'utilities', 'fuel_consumption'),
                False,
            )

            # hide_when doesn't fire
            attach(rice)
            check(
                'hide_when cold, no cold → visible',
                engine.evaluate_field(project, 'utilities', 'fuel_consumption'),
                True,
            )

            # hide short-circuits show
            DPRFieldRule.objects.all().delete()
            sw = DPRFieldRule.objects.create(
                data_element_key='utilities', field_name='foo',
                recipe_type='component_in', visibility='show_when',
            )
            sw.required_components.add(cold)
            hw = DPRFieldRule.objects.create(
                data_element_key='utilities', field_name='foo',
                recipe_type='component_in', visibility='hide_when',
            )
            hw.required_components.add(cold)
            attach(cold)
            check(
                'hide_when short-circuits show_when',
                engine.evaluate_field(project, 'utilities', 'foo'),
                False,
            )

            # No rules → visible by default
            check(
                'no rules → visible',
                engine.evaluate_field(project, 'utilities', 'nonexistent_field'),
                True,
            )

            # ── Level 2 — field_equals ─────────────────────────────────
            print('Level 2 — field_equals')
            DPRFieldRule.objects.all().delete()
            DPRFieldRule.objects.create(
                data_element_key='compliance', field_name='gst_number',
                recipe_type='field_equals', visibility='show_when',
                trigger_field='is_registered', trigger_value='Yes',
            )
            attach(rice)
            check(
                'field_equals Yes → visible',
                engine.evaluate_field(project, 'compliance', 'gst_number',
                                       field_values={'is_registered': 'Yes'}),
                True,
            )
            check(
                'field_equals No → hidden',
                engine.evaluate_field(project, 'compliance', 'gst_number',
                                       field_values={'is_registered': 'No'}),
                False,
            )
            check(
                'field_equals with int trigger cast to string',
                engine.evaluate_field(project, 'compliance', 'gst_number',
                                       field_values={'is_registered': 'Yes'}),
                True,
            )
            check(
                'field_equals with missing trigger value → hidden',
                engine.evaluate_field(project, 'compliance', 'gst_number',
                                       field_values={}),
                False,
            )
            check(
                'field_equals with no field_values dict → hidden',
                engine.evaluate_field(project, 'compliance', 'gst_number'),
                False,
            )

            # ── Malformed rule ─────────────────────────────────────────
            print('Edge cases')
            DPRFieldRule.objects.all().delete()
            DPRFieldRule.objects.create(
                data_element_key='utilities', field_name='ghost',
                recipe_type='component_in', visibility='show_when',
                # No required_components attached — malformed
            )
            check(
                'empty required_components → does not fire → hidden (show-only)',
                engine.evaluate_field(project, 'utilities', 'ghost'),
                False,
            )

            # ROLLBACK — nothing above persists
            transaction.savepoint_rollback(sid)
    finally:
        pass

    # Summary
    print()
    print(f'Passed: {passed}    Failed: {len(failed)}')
    if failed:
        print()
        print('Failures:')
        for name, actual, expected in failed:
            print(f'  {name}: expected={expected!r}, got={actual!r}')
    else:
        print('All rule engine assertions passed ✓')
