"""
DPR §Applicability — dynamic questionnaire rule engine schema (Phase 6a).

Per KAU RCD reply A.1 (2026-09-02):
    "The applicability rules should be implemented through a configurable
     rule/master-data framework, rather than hard-coded into individual
     screens. This will allow authorised KAU administrators to modify
     applicability rules, add or modify project components, modify
     conditional requirements, and accommodate new types of agricultural
     enterprises without requiring changes to the core application."

Two levels, matching RCD structure:

    Level 1 (DPRComponentApplicability):
        For each (Project Component × Data Element / section), record
        whether the section is Mandatory / Optional-Conditional / Hidden.
        This drives the sidebar filter — an 'H' rule hides the section
        from the wizard entirely.

    Level 2 (DPRFieldRule):
        For fields WITHIN an activated section, record recipe-based
        conditions — "show field X only when component Y is selected" or
        "show field X only when field Z equals value W". Deliberately
        structured (not JSON) so admin UI is buildable and FK integrity
        works when components are deleted.

Only Level 1 is admin-editable in Phase 6c (the M/O/H matrix). Level 2
rules are seeded via `scripts/seed_dpr_field_rules.py` — devs edit the
seed script when KAU asks during UAT. This keeps the admin UI simple
(no JSON, no boolean-tree builder) while the schema stays future-proof.

Feature flag:
    Phase 6d enforcement is gated by `DPRConfig.get('rule_engine_enabled')`.
    Off during initial rollout / UAT rule refinement; flip on when KAU signs
    off on the seeded rules. When off, all sections are shown (current
    behaviour), keeping a rollback path.

Author: Athul Gopan (Kefi Tech Solutions)
"""
from django.db import models

from apps.core.models.base import TimeStampedModel, AuditModel


class DPRComponentApplicability(TimeStampedModel, AuditModel):
    """Level 1 rule: which sections apply to which project components.

    One row per (component, section). Missing rows are treated as Optional
    by the rule engine — so seed rules only need to cover explicit M and H
    cases; the rest default to O and stay shown.
    """

    class Applicability(models.TextChoices):
        MANDATORY = 'M', 'Mandatory'
        OPTIONAL  = 'O', 'Optional / Conditional'
        HIDDEN    = 'H', 'Hidden'

    component = models.ForeignKey(
        'database.DPRComponent',
        on_delete=models.CASCADE,
        related_name='applicability_rules',
        help_text='Which project component this rule applies to.',
    )
    data_element_key = models.CharField(
        max_length=50, db_index=True,
        help_text="Section key from DPR_SECTIONS in src/lib/api/dpr.ts — "
                  "e.g. 'raw-material', 'utilities', 'finance'. Free-text "
                  "rather than enum so admin can add rules for new sections "
                  "without a migration.",
    )
    applicability = models.CharField(
        max_length=1, choices=Applicability.choices,
        db_index=True,
        help_text='M = mandatory (must complete to submit). '
                  'O = optional/conditional (shown but not required). '
                  'H = hidden (not shown in wizard).',
    )
    notes = models.TextField(
        blank=True,
        help_text='Admin-visible explanation for why this rule exists — '
                  'e.g. "Cold Storage: no raw material processed onsite".',
    )

    class Meta:
        db_table = 'dpr_component_applicability'
        verbose_name = 'DPR — Component Applicability'
        verbose_name_plural = 'DPR — Component Applicability Rules'
        ordering = ['component', 'data_element_key']
        unique_together = [('component', 'data_element_key')]
        indexes = [
            models.Index(fields=['data_element_key', 'applicability']),
        ]

    def __str__(self):
        return f'{self.component.code} × {self.data_element_key} = {self.applicability}'


class DPRFieldRule(TimeStampedModel, AuditModel):
    """Level 2 rule: conditional visibility of individual fields.

    Recipe-based rather than JSON — every rule is one of two shapes:

    Recipe 'component_in':
        Show/hide `field_name` in `data_element_key` section based on
        whether the project has ANY component in `required_components`.

    Recipe 'field_equals':
        Show/hide `field_name` based on whether `trigger_field` in the
        SAME section equals `trigger_value`.

    Cross-section conditions are deliberately NOT supported — prevents
    circular dependencies and keeps the engine hot path predictable.
    """

    class RecipeType(models.TextChoices):
        COMPONENT_IN = 'component_in', 'Component selected'
        FIELD_EQUALS = 'field_equals', 'Sibling field value'

    class Visibility(models.TextChoices):
        SHOW_WHEN = 'show_when', 'Show when condition met'
        HIDE_WHEN = 'hide_when', 'Hide when condition met'

    data_element_key = models.CharField(
        max_length=50, db_index=True,
        help_text='Section key this rule applies to.',
    )
    field_name = models.CharField(
        max_length=100, db_index=True,
        help_text='Name of the field WITHIN the section — matches the field '
                  'key used in the section serializer / FE form schema.',
    )
    recipe_type = models.CharField(
        max_length=20, choices=RecipeType.choices,
        help_text='Which recipe shape this rule uses. Determines which of '
                  'the type-specific fields below are meaningful.',
    )
    visibility = models.CharField(
        max_length=10, choices=Visibility.choices,
        default=Visibility.SHOW_WHEN,
        help_text='Direction — do we show or hide when the condition is met?',
    )

    # ── Recipe 'component_in' fields ─────────────────────────────────────
    # Populated when recipe_type == COMPONENT_IN; empty otherwise.
    required_components = models.ManyToManyField(
        'database.DPRComponent',
        blank=True,
        related_name='field_rules',
        help_text="For recipe 'component_in' — the rule fires when the project "
                  "has ANY of these components selected. Ignored for other recipes.",
    )

    # ── Recipe 'field_equals' fields ─────────────────────────────────────
    # Populated when recipe_type == FIELD_EQUALS; blank otherwise.
    trigger_field = models.CharField(
        max_length=100, blank=True,
        help_text="For recipe 'field_equals' — sibling field in the same section "
                  "whose value we check.",
    )
    trigger_value = models.CharField(
        max_length=200, blank=True,
        help_text="For recipe 'field_equals' — the value trigger_field must equal "
                  "for this rule to fire. Compared as string.",
    )

    notes = models.TextField(
        blank=True,
        help_text='Admin-visible explanation — e.g. "steam_capacity only shown '
                  'when boiler component selected".',
    )

    class Meta:
        db_table = 'dpr_field_rule'
        verbose_name = 'DPR — Field Rule'
        verbose_name_plural = 'DPR — Field Rules'
        ordering = ['data_element_key', 'field_name', 'id']
        indexes = [
            models.Index(fields=['data_element_key', 'field_name']),
        ]

    def __str__(self):
        return f'{self.data_element_key}.{self.field_name} [{self.recipe_type}]'
