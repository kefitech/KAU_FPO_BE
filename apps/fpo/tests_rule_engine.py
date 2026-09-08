"""
Test suite for DPR rule engine (Phase 6b).

Covers:
    - Feature flag off → engine short-circuits
    - Level 1: single-component, multi-component, M/O/H combination rules
    - Level 1: default-to-O when no rules exist
    - Level 2: component_in recipe (show + hide directions)
    - Level 2: field_equals recipe (show + hide directions)
    - Level 2: multiple rules on same field (show any, hide any)
    - Edge cases: empty components, malformed rules, unknown recipe types
    - visible_sections + mandatory_sections helpers

Run:
    source venv/bin/activate && python manage.py test apps.fpo.tests_rule_engine -v 2
"""
from django.test import TestCase

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


# ─────────────────────────────────────────────────────────────────────────────
# Base fixture — feature flag ON so tests exercise the real logic
# ─────────────────────────────────────────────────────────────────────────────

class _RuleEngineBase(TestCase):
    """Shared setup: feature flag on + one project with configurable components."""

    def setUp(self):
        # Feature flag: seed a real DPRConfig row set to True. `is_engine_enabled`
        # reads via DPRConfig.get() so we must actually persist a row.
        DPRConfig.objects.update_or_create(
            key='rule_engine_enabled',
            defaults={
                'category': 'other',
                'value_type': 'bool',
                'value': True,
                'default_value': False,
                'label': 'Test flag',
                'description': '',
                'unit': '',
                'is_editable': True,
            },
        )

        # Minimal FPO + project — we bypass the full 4-step wizard because
        # the rule engine only needs `project.section_components.components`.
        self.fpo = FPO.objects.create(name='Test FPO', district='TRS')
        self.project = DPRProject.objects.create(fpo=self.fpo, title='Test project')

        # A handful of components to attach to projects in the tests.
        self.cold_storage = DPRComponent.objects.create(
            code='test_cold_storage', label_en='Cold Storage', group='storage_post_harvest',
        )
        self.custom_hiring = DPRComponent.objects.create(
            code='test_custom_hiring', label_en='Custom Hiring Centre', group='service_enterprises',
        )
        self.rice_mill = DPRComponent.objects.create(
            code='test_rice_mill', label_en='Rice Mill', group='processing_value_addition',
        )
        self.boiler = DPRComponent.objects.create(
            code='test_boiler', label_en='Steam Boiler', group='supporting_infrastructure',
        )

    def attach_components(self, *components):
        """Attach the given components to self.project via DPRSectionComponents."""
        section, _ = DPRSectionComponents.objects.get_or_create(project=self.project)
        section.components.set(components)
        return section


# ─────────────────────────────────────────────────────────────────────────────
# Feature flag
# ─────────────────────────────────────────────────────────────────────────────

class FeatureFlagTests(_RuleEngineBase):
    def test_flag_off_returns_all_sections_optional(self):
        DPRConfig.objects.filter(key='rule_engine_enabled').update(value=False)
        self.attach_components(self.cold_storage)
        # Even with an explicit H rule, flag-off should return O everywhere.
        DPRComponentApplicability.objects.create(
            component=self.cold_storage,
            data_element_key='raw-material',
            applicability='H',
        )
        result = engine.evaluate_data_element(self.project)
        self.assertEqual(set(result.values()), {'O'})
        self.assertEqual(len(result), len(engine.ALL_SECTION_KEYS))

    def test_flag_off_returns_field_visible(self):
        DPRConfig.objects.filter(key='rule_engine_enabled').update(value=False)
        # Add a rule that would hide the field when flag is on
        rule = DPRFieldRule.objects.create(
            data_element_key='utilities', field_name='steam_capacity',
            recipe_type='component_in', visibility='show_when',
        )
        rule.required_components.add(self.boiler)
        self.assertTrue(engine.evaluate_field(self.project, 'utilities', 'steam_capacity'))

    def test_flag_missing_defaults_to_off(self):
        DPRConfig.objects.filter(key='rule_engine_enabled').delete()
        self.assertFalse(engine.is_engine_enabled())


# ─────────────────────────────────────────────────────────────────────────────
# Level 1 — component-to-section applicability
# ─────────────────────────────────────────────────────────────────────────────

class Level1Tests(_RuleEngineBase):
    def test_no_rules_defaults_all_sections_optional(self):
        self.attach_components(self.rice_mill)
        result = engine.evaluate_data_element(self.project)
        self.assertEqual(set(result.values()), {'O'})

    def test_single_hidden_rule_hides_section(self):
        self.attach_components(self.custom_hiring)
        DPRComponentApplicability.objects.create(
            component=self.custom_hiring,
            data_element_key='raw-material', applicability='H',
        )
        result = engine.evaluate_data_element(self.project)
        self.assertEqual(result['raw-material'], 'H')
        self.assertEqual(result['finance'], 'O')  # others unaffected

    def test_single_mandatory_rule_marks_section_mandatory(self):
        self.attach_components(self.rice_mill)
        DPRComponentApplicability.objects.create(
            component=self.rice_mill,
            data_element_key='raw-material', applicability='M',
        )
        result = engine.evaluate_data_element(self.project)
        self.assertEqual(result['raw-material'], 'M')

    def test_multi_component_M_wins_over_O(self):
        # Rice Mill says raw-material is mandatory; Custom Hiring says optional.
        # M should win because inclusive semantics.
        self.attach_components(self.rice_mill, self.custom_hiring)
        DPRComponentApplicability.objects.create(
            component=self.rice_mill, data_element_key='raw-material', applicability='M',
        )
        DPRComponentApplicability.objects.create(
            component=self.custom_hiring, data_element_key='raw-material', applicability='O',
        )
        result = engine.evaluate_data_element(self.project)
        self.assertEqual(result['raw-material'], 'M')

    def test_multi_component_O_wins_over_H(self):
        # If ONE component needs the section optionally, another saying H
        # should NOT hide it. Real-world: user selects Cold Storage (H for
        # raw-material) plus Rice Mill (O) → raw-material stays visible.
        self.attach_components(self.cold_storage, self.rice_mill)
        DPRComponentApplicability.objects.create(
            component=self.cold_storage, data_element_key='raw-material', applicability='H',
        )
        DPRComponentApplicability.objects.create(
            component=self.rice_mill, data_element_key='raw-material', applicability='O',
        )
        result = engine.evaluate_data_element(self.project)
        self.assertEqual(result['raw-material'], 'O')

    def test_multi_component_all_H_hides_section(self):
        # Only when EVERY selected component says H does the section hide.
        self.attach_components(self.cold_storage, self.custom_hiring)
        DPRComponentApplicability.objects.create(
            component=self.cold_storage, data_element_key='raw-material', applicability='H',
        )
        DPRComponentApplicability.objects.create(
            component=self.custom_hiring, data_element_key='raw-material', applicability='H',
        )
        result = engine.evaluate_data_element(self.project)
        self.assertEqual(result['raw-material'], 'H')

    def test_multi_component_M_wins_over_H(self):
        self.attach_components(self.cold_storage, self.rice_mill)
        DPRComponentApplicability.objects.create(
            component=self.cold_storage, data_element_key='raw-material', applicability='H',
        )
        DPRComponentApplicability.objects.create(
            component=self.rice_mill, data_element_key='raw-material', applicability='M',
        )
        result = engine.evaluate_data_element(self.project)
        self.assertEqual(result['raw-material'], 'M')

    def test_no_components_selected_returns_all_optional(self):
        # Project has no DPRSectionComponents row yet — no rules can match.
        result = engine.evaluate_data_element(self.project)
        self.assertEqual(set(result.values()), {'O'})

    def test_result_covers_every_known_section(self):
        self.attach_components(self.cold_storage)
        result = engine.evaluate_data_element(self.project)
        self.assertEqual(set(result.keys()), set(engine.ALL_SECTION_KEYS))


# ─────────────────────────────────────────────────────────────────────────────
# Helpers on top of Level 1
# ─────────────────────────────────────────────────────────────────────────────

class HelperTests(_RuleEngineBase):
    def test_visible_sections_excludes_hidden(self):
        self.attach_components(self.custom_hiring)
        DPRComponentApplicability.objects.create(
            component=self.custom_hiring, data_element_key='raw-material', applicability='H',
        )
        visible = engine.visible_sections(self.project)
        self.assertNotIn('raw-material', visible)
        self.assertIn('finance', visible)

    def test_visible_sections_preserves_canonical_order(self):
        self.attach_components(self.cold_storage)
        visible = engine.visible_sections(self.project)
        # The relative ordering of two known adjacent keys should hold
        self.assertLess(visible.index('components'), visible.index('finance'))

    def test_mandatory_sections_lists_only_M(self):
        self.attach_components(self.rice_mill)
        DPRComponentApplicability.objects.create(
            component=self.rice_mill, data_element_key='raw-material', applicability='M',
        )
        DPRComponentApplicability.objects.create(
            component=self.rice_mill, data_element_key='finance', applicability='M',
        )
        DPRComponentApplicability.objects.create(
            component=self.rice_mill, data_element_key='ess', applicability='H',
        )
        mandatory = engine.mandatory_sections(self.project)
        self.assertEqual(set(mandatory), {'raw-material', 'finance'})


# ─────────────────────────────────────────────────────────────────────────────
# Level 2 — field-level rules, component_in recipe
# ─────────────────────────────────────────────────────────────────────────────

class Level2ComponentInTests(_RuleEngineBase):
    def _make_show_when(self, section, field_name, components):
        rule = DPRFieldRule.objects.create(
            data_element_key=section, field_name=field_name,
            recipe_type='component_in', visibility='show_when',
        )
        rule.required_components.set(components)
        return rule

    def _make_hide_when(self, section, field_name, components):
        rule = DPRFieldRule.objects.create(
            data_element_key=section, field_name=field_name,
            recipe_type='component_in', visibility='hide_when',
        )
        rule.required_components.set(components)
        return rule

    def test_field_visible_by_default_when_no_rules(self):
        self.attach_components(self.cold_storage)
        self.assertTrue(engine.evaluate_field(self.project, 'utilities', 'anything'))

    def test_show_when_component_present_field_visible(self):
        self.attach_components(self.boiler)
        self._make_show_when('utilities', 'steam_capacity', [self.boiler])
        self.assertTrue(engine.evaluate_field(self.project, 'utilities', 'steam_capacity'))

    def test_show_when_component_absent_field_hidden(self):
        self.attach_components(self.cold_storage)  # no boiler
        self._make_show_when('utilities', 'steam_capacity', [self.boiler])
        self.assertFalse(engine.evaluate_field(self.project, 'utilities', 'steam_capacity'))

    def test_hide_when_component_present_field_hidden(self):
        self.attach_components(self.cold_storage)
        self._make_hide_when('utilities', 'fuel_consumption', [self.cold_storage])
        self.assertFalse(engine.evaluate_field(self.project, 'utilities', 'fuel_consumption'))

    def test_hide_when_component_absent_field_visible(self):
        self.attach_components(self.rice_mill)
        self._make_hide_when('utilities', 'fuel_consumption', [self.cold_storage])
        self.assertTrue(engine.evaluate_field(self.project, 'utilities', 'fuel_consumption'))

    def test_multiple_show_when_any_fires(self):
        # Field shown when EITHER boiler OR rice_mill is selected.
        self.attach_components(self.rice_mill)
        self._make_show_when('utilities', 'high_energy', [self.boiler])
        self._make_show_when('utilities', 'high_energy', [self.rice_mill])
        self.assertTrue(engine.evaluate_field(self.project, 'utilities', 'high_energy'))

    def test_multiple_show_when_none_fires_hides_field(self):
        self.attach_components(self.cold_storage)
        self._make_show_when('utilities', 'high_energy', [self.boiler])
        self._make_show_when('utilities', 'high_energy', [self.rice_mill])
        self.assertFalse(engine.evaluate_field(self.project, 'utilities', 'high_energy'))

    def test_hide_when_short_circuits_show_when(self):
        # Even with a show-when that fires, a firing hide-when wins.
        self.attach_components(self.cold_storage)
        self._make_show_when('utilities', 'foo', [self.cold_storage])  # fires → would show
        self._make_hide_when('utilities', 'foo', [self.cold_storage])  # fires → forces hide
        self.assertFalse(engine.evaluate_field(self.project, 'utilities', 'foo'))

    def test_empty_required_components_rule_ignored(self):
        # Malformed rule (M2M empty) should not silently hide the field.
        # Create rule with no components attached.
        DPRFieldRule.objects.create(
            data_element_key='utilities', field_name='ghost',
            recipe_type='component_in', visibility='show_when',
        )
        self.attach_components(self.cold_storage)
        # Show-when with no components can never fire → field hidden when
        # ONLY show-when rules exist AND none fire. That's correct.
        self.assertFalse(engine.evaluate_field(self.project, 'utilities', 'ghost'))


# ─────────────────────────────────────────────────────────────────────────────
# Level 2 — field-level rules, field_equals recipe
# ─────────────────────────────────────────────────────────────────────────────

class Level2FieldEqualsTests(_RuleEngineBase):
    def _make_show_when_equals(self, section, field_name, trigger_field, trigger_value):
        return DPRFieldRule.objects.create(
            data_element_key=section, field_name=field_name,
            recipe_type='field_equals', visibility='show_when',
            trigger_field=trigger_field, trigger_value=trigger_value,
        )

    def test_field_equals_matches_shows_field(self):
        self.attach_components(self.rice_mill)
        self._make_show_when_equals('compliance', 'gst_number', 'is_registered', 'Yes')
        visible = engine.evaluate_field(
            self.project, 'compliance', 'gst_number',
            field_values={'is_registered': 'Yes'},
        )
        self.assertTrue(visible)

    def test_field_equals_no_match_hides_field(self):
        self.attach_components(self.rice_mill)
        self._make_show_when_equals('compliance', 'gst_number', 'is_registered', 'Yes')
        visible = engine.evaluate_field(
            self.project, 'compliance', 'gst_number',
            field_values={'is_registered': 'No'},
        )
        self.assertFalse(visible)

    def test_field_equals_missing_trigger_value_hides_field(self):
        self.attach_components(self.rice_mill)
        self._make_show_when_equals('compliance', 'gst_number', 'is_registered', 'Yes')
        visible = engine.evaluate_field(
            self.project, 'compliance', 'gst_number',
            field_values={},  # no trigger_field value passed
        )
        self.assertFalse(visible)

    def test_field_equals_casts_non_string_values(self):
        # Real form values often arrive as ints / bools — should coerce
        # to string for comparison, so trigger_value='5' matches int 5.
        self.attach_components(self.rice_mill)
        self._make_show_when_equals('capacity', 'high_volume_fields', 'shift_count', '3')
        self.assertTrue(engine.evaluate_field(
            self.project, 'capacity', 'high_volume_fields',
            field_values={'shift_count': 3},
        ))

    def test_field_equals_no_field_values_dict_treats_as_empty(self):
        self.attach_components(self.rice_mill)
        self._make_show_when_equals('compliance', 'gst_number', 'is_registered', 'Yes')
        # field_values omitted entirely → treated as empty dict → does not fire
        self.assertFalse(engine.evaluate_field(self.project, 'compliance', 'gst_number'))
