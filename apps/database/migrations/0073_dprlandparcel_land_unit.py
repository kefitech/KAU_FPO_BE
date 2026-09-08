"""
Hand-written migration for KAU RCD reply B.3 (2026-09-02).

Adds `land_unit` CharField to DPRLandParcel with 5 choices (acre/cent/are/
hectare/sqm) per spec. Defaults to 'acre' so existing rows get a sensible
value. The legacy `unit` FK (points to DPRCapacityUnit — kg/mt/litres/etc.)
is left in place for back-compat and slated for a future deprecation
migration once no active rows reference it.

Kept intentionally narrow — hand-written to avoid bundling with the V2
rebuild drift that Django's makemigrations wants to include. See
DPR_V2_BUILD_PLAN.md § "Migration drift finding".
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("database", "0072_dprconfig"),
    ]

    operations = [
        migrations.AddField(
            model_name="dprlandparcel",
            name="land_unit",
            field=models.CharField(
                choices=[
                    ("acre", "Acre"),
                    ("cent", "Cent"),
                    ("are", "Are"),
                    ("hectare", "Hectare"),
                    ("sqm", "Square metre"),
                ],
                default="acre",
                max_length=10,
                help_text="Unit for total_land_available + land_proposed_for_project. "
                          "Per KAU RCD B.3 — 5 fixed choices; canonical acre for cross-parcel math.",
            ),
        ),
    ]
