"""
DPR §Rule Engine — dynamic questionnaire evaluator (Phase 6b).

Per KAU RCD reply A.1. This service answers three questions per DPR project:

    1. `visible_sections(project)` → list of section keys that should appear
       in the wizard sidebar. Sections with an `H` (Hidden) applicability
       rule for ANY of the project's selected components are filtered out.

    2. `evaluate_data_element(project)` → dict mapping every known section
       key to `M` / `O` / `H`. Used by the readiness endpoint + PDF renderer
       to know which sections to require, show, or skip.

    3. `evaluate_field(project, section_key, field_name, field_values)` →
       `True` if the field should be visible, `False` otherwise. Applies
       Level 2 DPRFieldRule recipes.

Multi-component semantics (RCD A.1: "Combine the applicable requirements
of multiple selected components"):

    - A section is HIDDEN only if EVERY selected component says H.
      One component saying M or O wins over another saying H — the more
      inclusive rule prevails so we never accidentally hide a section a
      user actually needs.
    - A section is MANDATORY if ANY selected component says M.
    - Otherwise Optional. (This includes: no rules at all, mix of O and H
      where at least one is O, only O rules.)

Missing rules default to Optional — matches the seed strategy where we
only encode explicit M or H cases and let everything else default.

Feature flag:
    All evaluation short-circuits when `DPRConfig.rule_engine_enabled` is
    False — every section is Optional, every field is visible. This is the
    Phase 6d rollback path.

Performance:
    All rules for a project are batch-loaded in ONE query per public call.
    No queries inside the evaluation loops. Callers evaluating many
    projects in a batch (admin dashboards, bulk PDF generation) should
    still call once-per-project — the engine is not project-aware across
    calls.

Author: Athul Gopan (Kefi Tech Solutions)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from apps.database.models import (
    DPRComponentApplicability,
    DPRConfig,
    DPRFieldRule,
    DPRProject,
)


# Canonical section key list — matches DPR_SECTIONS in src/lib/api/dpr.ts.
# Kept as a module constant so callers can iterate the full universe of
# sections without pulling in the FE types. `evaluate_data_element` always
# returns an entry for every key here.
ALL_SECTION_KEYS: tuple[str, ...] = (
    'identification',
    'components',
    'nature-of-business',
    'investment',
    'products',
    'location',
    'rationale',
    'baseline',
    'capacity',
    'raw-material',
    'market',
    'technology',
    'site',
    'civil',
    'machinery',
    'utilities',
    'hr',
    'finance',
    'compliance',
    'ess',
    'implementation',
    'risk',
)

# Applicability values — mirrored from DPRComponentApplicability.Applicability
# so callers don't need to import the model just to compare strings.
MANDATORY = 'M'
OPTIONAL  = 'O'
HIDDEN    = 'H'


@dataclass
class _RuleBundle:
    """All rules relevant to one project, batch-loaded once."""
    component_ids: list[int]
    # section_key → list of applicability values from all selected components
    level1: dict[str, list[str]] = field(default_factory=dict)
    # (section_key, field_name) → list of DPRFieldRule rows
    level2: dict[tuple[str, str], list[DPRFieldRule]] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Feature flag
# ─────────────────────────────────────────────────────────────────────────────

def is_engine_enabled() -> bool:
    """Read the DPRConfig feature flag. False → engine short-circuits everywhere.

    Cheap enough to call per-request; DPRConfig is a small table and the
    read hits the query cache after warmup. Callers doing tight loops
    (e.g. batch PDF generation) can cache the result themselves.
    """
    row = DPRConfig.get('rule_engine_enabled')
    if row is None:
        # Missing flag = safe default = off (show everything). Matches the
        # seed script's default value.
        return False
    try:
        return row.as_bool()
    except TypeError:
        # Flag row exists but wrong type — treat as off rather than raise.
        # Admin sees the type mismatch in the config UI and fixes it.
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Batch loader
# ─────────────────────────────────────────────────────────────────────────────

def _project_component_ids(project: DPRProject) -> list[int]:
    """Return the list of DPRComponent PKs selected for this project.

    Components live on `DPRSectionComponents.components` M2M — the section
    may not exist for very-early-draft projects, in which case there are
    no rules to apply.
    """
    section_components = getattr(project, 'section_components', None)
    if section_components is None:
        return []
    return list(section_components.components.values_list('id', flat=True))


def _load_rules(project: DPRProject) -> _RuleBundle:
    """Batch-load all applicability + field rules that could affect this project.

    Two queries total:
        1. All Level 1 rules whose component ∈ project's components
        2. All Level 2 rules (there are few — no need to filter by component)
    """
    component_ids = _project_component_ids(project)
    bundle = _RuleBundle(component_ids=component_ids)

    if component_ids:
        for rule in DPRComponentApplicability.objects.filter(
            component_id__in=component_ids,
        ).only('data_element_key', 'applicability'):
            bundle.level1.setdefault(rule.data_element_key, []).append(rule.applicability)

    # Level 2 rules are section+field scoped, not component scoped at the
    # table level (M2M is inside the row). Load them all; the count is
    # low (dozens) so no index-filter needed.
    for rule in DPRFieldRule.objects.prefetch_related('required_components').all():
        key = (rule.data_element_key, rule.field_name)
        bundle.level2.setdefault(key, []).append(rule)

    return bundle


# ─────────────────────────────────────────────────────────────────────────────
# Level 1 — section applicability
# ─────────────────────────────────────────────────────────────────────────────

def _combine_applicability(values: Iterable[str]) -> str:
    """Multi-component combination: M wins > O wins > H.

    Rationale (RCD A.1: "Combine the applicable requirements of multiple
    selected components"):
      - ANY component saying M → M (the strictest requirement wins)
      - Otherwise ANY component saying O → O (shown but optional)
      - Only when EVERY rule says H → H (all selected components agree
        the section doesn't apply)
    """
    values = list(values)
    if not values:
        return OPTIONAL
    if MANDATORY in values:
        return MANDATORY
    if OPTIONAL in values:
        return OPTIONAL
    return HIDDEN  # all values are H


def evaluate_data_element(project: DPRProject) -> dict[str, str]:
    """Return {section_key: 'M'|'O'|'H'} for every section in ALL_SECTION_KEYS.

    Feature flag off → every section returns O (shown, not required).

    Missing rules default to O — a section with no rule at all for any of
    the project's components is shown but not mandatory.
    """
    if not is_engine_enabled():
        return {k: OPTIONAL for k in ALL_SECTION_KEYS}

    bundle = _load_rules(project)
    return {
        key: _combine_applicability(bundle.level1.get(key, []))
        for key in ALL_SECTION_KEYS
    }


def visible_sections(project: DPRProject) -> list[str]:
    """Convenience: section keys the wizard sidebar should show, in order.

    Everything except Hidden. Used by `[uuid]/layout.tsx` to filter the
    sidebar nav.
    """
    result = evaluate_data_element(project)
    return [k for k in ALL_SECTION_KEYS if result[k] != HIDDEN]


def mandatory_sections(project: DPRProject) -> list[str]:
    """Convenience: only the mandatory sections. Used by readiness / submit.

    A section being O means it doesn't block submission even if empty.
    """
    result = evaluate_data_element(project)
    return [k for k in ALL_SECTION_KEYS if result[k] == MANDATORY]


# ─────────────────────────────────────────────────────────────────────────────
# Level 2 — field visibility within an activated section
# ─────────────────────────────────────────────────────────────────────────────

def _rule_fires(
    rule: DPRFieldRule,
    component_ids: set[int],
    field_values: dict[str, object],
) -> bool:
    """Return True if this rule's condition is currently satisfied.

    Ignores `visibility` — the caller applies show_when/hide_when semantics.
    """
    if rule.recipe_type == DPRFieldRule.RecipeType.COMPONENT_IN:
        # M2M prefetched in _load_rules.
        required = {c.id for c in rule.required_components.all()}
        # Empty required set = malformed rule; treat as "does not fire" so
        # a mis-configured admin edit doesn't hide fields silently.
        if not required:
            return False
        return bool(required & component_ids)

    if rule.recipe_type == DPRFieldRule.RecipeType.FIELD_EQUALS:
        if not rule.trigger_field:
            return False
        actual = field_values.get(rule.trigger_field)
        # String comparison — DB stores trigger_value as CharField. Callers
        # pass raw section-form values which may be Decimal / int / bool /
        # str; cast to string for the comparison.
        return str(actual) == rule.trigger_value

    # Unknown recipe type — safest default is "does not fire" (rule ignored).
    return False


def evaluate_field(
    project: DPRProject,
    section_key: str,
    field_name: str,
    field_values: dict[str, object] | None = None,
) -> bool:
    """Return True if `field_name` should be visible in the section.

    Feature flag off → always True.

    Semantics when multiple rules exist for the same field:
      - `show_when` rules: field is visible iff at least ONE rule fires
      - `hide_when` rules: field is hidden if any rule fires (short-circuit)
      - No rules for the field → visible by default

    `field_values` is the map of sibling field values in the SAME section,
    needed for `field_equals` recipe evaluation. Pass an empty dict (or
    omit) when evaluating from a context that doesn't have current values
    — e.g. server-side field-list generation for a section GET — in which
    case field_equals rules never fire.
    """
    if not is_engine_enabled():
        return True

    bundle = _load_rules(project)
    rules = bundle.level2.get((section_key, field_name), [])
    if not rules:
        return True

    component_ids = set(bundle.component_ids)
    field_values = field_values or {}

    show_rules = [r for r in rules if r.visibility == DPRFieldRule.Visibility.SHOW_WHEN]
    hide_rules = [r for r in rules if r.visibility == DPRFieldRule.Visibility.HIDE_WHEN]

    # Hide-when: any firing rule hides the field.
    for rule in hide_rules:
        if _rule_fires(rule, component_ids, field_values):
            return False

    # Show-when: at least one rule must fire; if there are no show-when
    # rules, the field is visible by default (only hide-when rules control
    # it).
    if show_rules:
        return any(_rule_fires(r, component_ids, field_values) for r in show_rules)

    return True
