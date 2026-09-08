"""
Hand-written migration for KAU RCD replies C.6 + C.7 (2026-09-02).

Adds `field_sources` JSONField to DPRProject — the central per-project
map of {section_key: {field_name: source}} for provenance tracking of
AI-inferred, system-defaulted, and user-overridden values.

Default `{}` on existing rows means every existing field is implicitly
user_entered — accurate since no AI/system inference has run yet.

Also includes an `AlterModelTable` op — Django's migration state had the
DPRProject table as the default `database_dprproject`, but the physical
DB has `dpr_project` (from a rename during the V2 rebuild that never got
committed to a migration). Without syncing state to match DB first, the
AddField SQL targets the wrong table and fails. This op is a state-only
sync — no physical DDL, no data change.

See DPR_V2_BUILD_PLAN.md § "Migration drift finding" for the wider drift.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("database", "0073_dprlandparcel_land_unit"),
    ]

    operations = [
        # State-only sync: migration state now knows DPRProject lives in
        # `dpr_project` (was default `database_dprproject`). The physical DB
        # is already at this name — this is bookkeeping, not DDL.
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterModelTable(
                    name="dprproject",
                    table="dpr_project",
                ),
            ],
            database_operations=[],
        ),
        # Now the real change — add the field_sources column.
        migrations.AddField(
            model_name="dprproject",
            name="field_sources",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    "Per-field provenance map: {section_key: {field_name: source}}. "
                    "source ∈ user_entered / ai_inferred / system_default / user_overridden. "
                    "See apps/fpo/services/dpr/field_sources.py for accessor helpers."
                ),
            ),
        ),
    ]
