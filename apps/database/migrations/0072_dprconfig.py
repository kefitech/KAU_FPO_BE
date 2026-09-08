"""
Hand-written migration for KAU RCD reply B.6 (2026-09-02).

Creates `DPRConfig` — the centrally-administered configuration table for the
DPR module. Replaces the previous `DPRMasterConfig` (deleted in migration 0044
during the V2 rebuild).

**Intentionally narrow — does NOT include drift cleanup.**
Django's makemigrations wanted to bundle this with a large drift cleanup
(removing 5 stale DPR tables: DPRAIContent, DPRCalculation, DPRDocument,
DPRMasterConfig, DPRSection + DPRProject field churn). That cleanup is
data-loss potential and gets its own reviewable migration in a follow-up
commit. See DPR_V2_BUILD_PLAN.md § "Migration drift finding".
"""
from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ("database", "0071_dprlandparcel_components"),
        # AuditModel FKs to user
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DPRConfig",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "key",
                    models.CharField(
                        db_index=True, max_length=100, unique=True,
                        help_text="Programmatic key used by calculation code, e.g. 'discount_rate_pct'.",
                    ),
                ),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("financial", "Financial assumptions"),
                            ("projection", "Projection settings"),
                            ("variance", "Variance thresholds"),
                            ("retention", "Retention & archival"),
                            ("risk", "Risk matrix"),
                            ("other", "Other"),
                        ],
                        max_length=20,
                        help_text="Grouping for admin UI.",
                    ),
                ),
                (
                    "value_type",
                    models.CharField(
                        choices=[
                            ("decimal", "Decimal (rate / percentage / money)"),
                            ("int", "Integer (count / years)"),
                            ("string", "String (enum / free text)"),
                            ("bool", "Boolean (yes / no)"),
                        ],
                        max_length=10,
                        help_text="How consumers should interpret `value` — enforced by the accessors.",
                    ),
                ),
                (
                    "value",
                    models.JSONField(
                        help_text="Current value. Stored as JSON scalar; the type matches value_type.",
                    ),
                ),
                (
                    "default_value",
                    models.JSONField(
                        help_text="Original seeded value — used for 'reset to default' and audit comparisons.",
                    ),
                ),
                ("label", models.CharField(max_length=200, help_text="Human-readable name shown in admin UI.")),
                ("description", models.TextField(blank=True, help_text="Longer explanation of what this parameter controls + any caveats.")),
                ("unit", models.CharField(blank=True, max_length=20, help_text='Display unit — e.g. "%", "years", "count", "₹". Blank for enums.')),
                ("min_value", models.JSONField(blank=True, null=True, help_text="Optional inclusive lower bound. Enforced in admin serializer.")),
                ("max_value", models.JSONField(blank=True, null=True, help_text="Optional inclusive upper bound. Enforced in admin serializer.")),
                (
                    "is_editable",
                    models.BooleanField(
                        default=True,
                        help_text="If False, admin UI displays value read-only. Used for computed / derived parameters that should not be changed manually.",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True, null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True, null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "DPR — Config",
                "verbose_name_plural": "DPR — Config",
                "db_table": "dpr_config",
                "ordering": ["category", "key"],
            },
        ),
    ]
