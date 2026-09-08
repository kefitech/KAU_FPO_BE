"""
Hand-written migration for KAU RCD reply B.8 (2026-09-02).

Adds a M2M from DPRLandParcel -> DPRComponent so each parcel can declare
which project component(s) will use it.

Kept intentionally narrow — Django's makemigrations regenerated a huge
migration containing V2-rebuild drift (deletes of DPRAIContent, DPRCalculation,
DPRDocument, DPRMasterConfig, DPRSection + DPRProject field churn) that has
been sitting uncommitted in migration state. That drift needs a separate
review + migration and should not ride along with a small, targeted change.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("database", "0070_merge_20260829_0938"),
    ]

    operations = [
        migrations.AddField(
            model_name="dprlandparcel",
            name="components",
            field=models.ManyToManyField(
                help_text="Project components mapped to this specific parcel (per KAU RCD B.8).",
                related_name="land_parcels",
                to="database.dprcomponent",
            ),
        ),
    ]
