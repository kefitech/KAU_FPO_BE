"""
Field-source provenance helpers for the DPR module.

Per KAU RCD replies C.6 + C.7 (2026-09-02):
    C.6 — "AI-derived and system-inferred values shall be clearly
           identifiable to the user."
    C.7 — "AI-derived and system-inferred values should be editable by the
           user. Where a user overrides an AI-derived or system-estimated
           value: the user-provided value shall take precedence... An audit
           trail shall be maintained for such overrides."

Storage: single JSONField `DPRProject.field_sources` — shape
    { "<section_key>": { "<field_name>": "<source>" } }

Sources (SOURCE_* constants below):
    user_entered      — user typed / picked this value. Default when key absent.
    ai_inferred       — populated by an AI narrative / suggestion pass.
    system_default    — populated by a computed default (e.g. depreciation).
    user_overridden   — was ai_inferred or system_default, user then edited it.

Callers should use these helpers rather than reading/writing the JSON dict
directly, so the auto-flip-on-override logic + audit hooks live in one place.
"""
from typing import Any, Optional


SOURCE_USER_ENTERED   = 'user_entered'
SOURCE_AI_INFERRED    = 'ai_inferred'
SOURCE_SYSTEM_DEFAULT = 'system_default'
SOURCE_USER_OVERRIDDEN = 'user_overridden'

VALID_SOURCES = frozenset({
    SOURCE_USER_ENTERED,
    SOURCE_AI_INFERRED,
    SOURCE_SYSTEM_DEFAULT,
    SOURCE_USER_OVERRIDDEN,
})

# Sources that indicate a value was NOT typed by the user — an incoming user
# edit on any of these should flip the source to `user_overridden` and audit.
_INFERRED_SOURCES = frozenset({SOURCE_AI_INFERRED, SOURCE_SYSTEM_DEFAULT})


def get_source(project, section_key: str, field_name: str) -> str:
    """Look up the source for one field. Falls back to user_entered when absent."""
    sources = project.field_sources or {}
    return sources.get(section_key, {}).get(field_name, SOURCE_USER_ENTERED)


def set_source(project, section_key: str, field_name: str, source: str, save: bool = True) -> None:
    """Explicitly set the source. Used by AI/system-default writers, and by
    the auto-flip-on-override helper below. `save=False` to batch several
    updates before saving."""
    if source not in VALID_SOURCES:
        raise ValueError(f'Invalid source {source!r}. Must be one of {sorted(VALID_SOURCES)}.')
    sources = dict(project.field_sources or {})
    section = dict(sources.get(section_key, {}))
    if source == SOURCE_USER_ENTERED:
        # user_entered is the implicit default — remove the key to keep the JSON tight
        section.pop(field_name, None)
    else:
        section[field_name] = source
    if section:
        sources[section_key] = section
    else:
        sources.pop(section_key, None)
    project.field_sources = sources
    if save:
        project.save(update_fields=['field_sources'])


def get_section_sources(project, section_key: str) -> dict[str, str]:
    """Return the full source map for one section — {field_name: source}.
    Used by serializers to include provenance in section GET responses."""
    return dict((project.field_sources or {}).get(section_key, {}))


def flip_to_overridden_if_inferred(
    project, section_key: str, changed_fields: dict[str, Any], user, request=None,
) -> list[dict]:
    """Auto-flip logic — call from a section's PATCH handler with the dict of
    (field_name -> new_value) that the user just changed. Any field whose
    prior source was ai_inferred or system_default gets flipped to
    user_overridden + an AuditLog row written.

    Returns a list of dicts describing each flip (for the API response, so the
    UI can toast "3 AI-inferred values overridden").
    """
    from apps.core.models.generic import AuditLog

    flips: list[dict] = []
    sources = project.field_sources or {}
    section = dict(sources.get(section_key, {}))

    for field_name, new_value in changed_fields.items():
        prior = section.get(field_name)
        if prior in _INFERRED_SOURCES:
            section[field_name] = SOURCE_USER_OVERRIDDEN
            flips.append({
                'section_key': section_key,
                'field_name': field_name,
                'prior_source': prior,
                'new_source': SOURCE_USER_OVERRIDDEN,
                'new_value': new_value,
            })
            AuditLog.log(
                user=user,
                action=AuditLog.Action.DPR_AI_VALUE_OVERRIDE,
                instance=project,
                request=request,
                changes={
                    'section': section_key,
                    'field': field_name,
                    'prior_source': prior,
                    'new_source': SOURCE_USER_OVERRIDDEN,
                    'new_value': _safe_json(new_value),
                },
            )

    if flips:
        sources = dict(sources)
        sources[section_key] = section
        project.field_sources = sources
        project.save(update_fields=['field_sources'])

    return flips


def _safe_json(v: Any) -> Any:
    """Coerce Decimal / date / etc to JSON-safe types before storing in
    AuditLog.changes JSONField."""
    from decimal import Decimal
    from datetime import date, datetime
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        return [_safe_json(x) for x in v]
    if isinstance(v, dict):
        return {k: _safe_json(val) for k, val in v.items()}
    return v
