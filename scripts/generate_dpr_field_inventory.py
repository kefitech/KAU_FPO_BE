"""
Walk every DPR model and emit a human-readable field inventory grouped
by wizard section. This is the "what did we ask KAU FPOs to fill in?"
document — used for KAU review.

Output: Documents/DPR_Field_Inventory.md
Then run generate_dpr_docx.py or hand-convert to .docx.

Run:
    source venv/bin/activate
    python manage.py shell -c "
    exec(open('scripts/generate_dpr_field_inventory.py').read())
    generate_dpr_field_inventory()
    "
"""

from pathlib import Path


# Wizard section → (main section model class name, ordered list of child model names)
# Same order as the FPO wizard sidebar. Kept as strings (not imports) so this
# script never breaks if a class is renamed — apps.get_model handles resolution.
SECTIONS = [
    ("§2.2 Project Identification",
        "DPRProject",
        [],
        "The header form for every DPR — captures what the project is, why, and what commodities/objectives/outcomes it targets."),
    ("§2.3.2 Project Components",
        "DPRSectionComponents",
        [],
        "Multi-select across 6 KAU groups. Drives which downstream sections become mandatory."),
    ("§2.3.3 Nature of Business",
        "DPRSectionNatureOfBusiness",
        [],
        "What the enterprise actually does — 15-option checklist."),
    ("§2.3.4 Proposed Investment",
        "DPRSectionInvestment",
        [],
        "Ballpark project cost + basis. Cross-checked against auto-computed Finance number."),
    ("§2.3.5 Products & Services",
        "DPRSectionProducts",
        ["DPRProductItem"],
        "Per-product table with KAU spec's 10 columns. Feeds the revenue engine."),
    ("§2.3.6 Project Location",
        "DPRSectionLocation",
        [],
        "Full administrative hierarchy + GPS + connectivity + land ownership."),
    ("§2.3.7 Project Rationale",
        "DPRSectionRationale",
        ["DPRRationaleSelection"],
        "Business reasons for the project, each with a justification."),
    ("§2.3.8 Current Status / Baseline",
        "DPRSectionBaseline",
        [],
        "Conditional — existing vs new enterprise; different field sets per branch."),
    ("§2.3.9 Capacity & Production",
        "DPRSectionCapacity",
        [],
        "Installed + practical capacity, working schedule, process description, losses, expansion."),
    ("§2.3.10 Raw Material Assessment",
        "DPRSectionRawMaterial",
        ["DPRRawMaterial", "DPRRawMaterialRisk", "DPRPackagingMaterial", "DPRConsumable"],
        "The biggest section — per-material rows with 40+ fields, plus packaging, consumables, risks."),
    ("§2.3.11 Market Assessment",
        "DPRSectionMarket",
        ["DPRMarketingProduct", "DPRMarketingBuyer", "DPRMarketingChannelSelection",
         "DPRMarketingCompetitor", "DPRMarketingRisk"],
        "Demand, buyers, channel mix, competitors, pricing, promotion, risks."),
    ("§2.3.12 Technology Selection",
        "DPRSectionTechnology",
        ["DPRTechnology", "DPRTechnologyRisk"],
        "Technology chosen, source, alternatives, risks."),
    ("§2.3.13 Land & Site Suitability",
        "DPRSectionSite",
        ["DPRLandParcel", "DPRExistingInfrastructure", "DPRSiteConstraint"],
        "Per-parcel land + terrain + utilities + constraints + statutory approvals."),
    ("§2.3.14 Civil Works",
        "DPRSectionCivil",
        ["DPRExistingBuilding", "DPRProposedBuilding", "DPRSiteDevelopmentItem"],
        "Existing + proposed buildings + site-dev items + cost breakdown."),
    ("§2.3.15 Plant & Machinery",
        "DPRSectionMachinery",
        ["DPRMachineryItem", "DPRSupportingAssetItem"],
        "Per-machine table with 50 fields + supporting-assets list."),
    ("§2.3.16 Utilities",
        "DPRSectionUtilities",
        ["DPRFuelUsage", "DPRProcessUtility", "DPRWasteManagement", "DPRRenewableInitiativeSelection"],
        "Electricity, water, refrigeration, effluent, comm/IT, safety, fuels, process utilities, waste, renewables."),
    ("§2.3.17 Human Resources",
        "DPRSectionHR",
        ["DPREmployeeCategory", "DPRDepartmentStaffing", "DPRTrainingRequirement"],
        "Management, per-designation manpower, department staffing, existing employees, training, welfare, compliance, expansion."),
    ("§2.3.18 Finance",
        "DPRSectionFinance",
        ["DPRRevenueAssumption", "DPRFinancialYearHistory"],
        "The heart of the DPR — capital cost, means of finance, working capital, opex, revenue assumptions per product, loan, subsidy, 3-year history."),
    ("§2.3.19 Statutory Compliance",
        "DPRSectionCompliance",
        ["DPRComplianceItem"],
        "Per-approval status, authority, validity."),
    ("§2.3.20 Environment, Social & Sustainability",
        "DPRSectionESS",
        ["DPREnvironmentalImpactSelection", "DPRClimateRiskSelection"],
        "Environmental clearances, waste-water, energy efficiency, CSR, community, sustainability."),
    ("§2.3.21 Implementation Plan",
        "DPRSectionImplementation",
        ["DPRImplementationActivity", "DPRImplementationMilestone"],
        "Milestones, phased activities, monitoring mechanism."),
    ("§2.3.22 Risk Assessment",
        "DPRSectionRisk",
        ["DPRRiskItem"],
        "Risk register per KAU RCD's 5×5 probability × impact matrix."),
]


# Fields we skip for the KAU review doc — internal plumbing, not KAU-facing.
SKIP_FIELDS = {
    "id", "uuid", "created_at", "updated_at", "created_by", "updated_by",
    "deleted_at", "deleted_by",
    "project", "section", "is_deleted", "order",
    "is_complete", "field_sources", "status",
}


def _humanise(field_name: str) -> str:
    """turn 'expected_annual_growth_rate_pct' → 'Expected Annual Growth Rate %'."""
    if not field_name:
        return ""
    parts = field_name.replace("_pct", "_percentage").split("_")
    words = []
    for w in parts:
        upper = w.upper()
        if upper in ("PAN", "GST", "CIN", "IFSC", "PIN", "SC", "ST",
                     "M2M", "FK", "KAU", "FPO", "DPR", "URL", "ID",
                     "GPS", "CEO", "NOC", "CRZ", "LT", "HT",
                     "DG", "UPS", "MSME", "EPF", "ESI", "TDS",
                     "NABARD", "SFAC", "CSR", "AMC", "HR"):
            words.append(upper)
        elif w == "percentage":
            words.append("%")
        else:
            words.append(w.capitalize())
    return " ".join(words)


def _field_meta(f) -> str:
    """type + choices + max_length + nullable — one-line summary."""
    from django.db import models

    parts = []
    field_type = type(f).__name__.replace("Field", "")
    parts.append(field_type)

    if hasattr(f, "max_length") and f.max_length:
        parts.append(f"max {f.max_length}")
    if hasattr(f, "max_digits") and f.max_digits:
        parts.append(f"{f.max_digits}.{f.decimal_places}")

    choices = getattr(f, "choices", None)
    if choices:
        vals = [c[1] if isinstance(c, tuple) else str(c) for c in choices][:5]
        more = "…" if len(list(choices)) > 5 else ""
        parts.append(f"choices: {', '.join(str(v) for v in vals)}{more}")

    if isinstance(f, models.ForeignKey):
        parts.append(f"→ {f.related_model.__name__}")
    elif isinstance(f, models.ManyToManyField):
        parts.append(f"↔ {f.related_model.__name__}")

    if getattr(f, "null", False) or getattr(f, "blank", False):
        pass  # too noisy to mark every optional field

    return " · ".join(parts)


def _iter_fields(model_cls):
    """Concrete (declared) fields only. No inherited plumbing like created_at."""
    for f in model_cls._meta.get_fields():
        if f.auto_created and not f.concrete:
            continue
        if not getattr(f, "editable", True):
            continue
        name = f.name
        if name in SKIP_FIELDS:
            continue
        yield f


def generate_dpr_field_inventory():
    from django.apps import apps

    out_path = Path("Documents/DPR_Field_Inventory.md")

    lines = []
    lines.append("# DPR Module — Complete Field Inventory")
    lines.append("")
    lines.append("**Platform:** KAU-FPO Linkage Programme  ")
    lines.append("**Purpose:** exhaustive list of every field an FPO fills in to build a DPR.  ")
    lines.append("**Grouped by:** the 22 wizard sections in the order they appear.")
    lines.append("")
    lines.append("Each row shows the field's stored name, a human-readable label, "
                 "and its type + constraints (max length, decimal precision, choices, "
                 "FK target). Section-level fields are listed first; sub-tables "
                 "(repeatable rows) follow with their own header.")
    lines.append("")
    lines.append("---")
    lines.append("")

    total_fields = 0

    for section_title, main_name, child_names, blurb in SECTIONS:
        lines.append(f"## {section_title}")
        lines.append("")
        lines.append(blurb)
        lines.append("")

        try:
            main_cls = apps.get_model("database", main_name)
        except LookupError:
            lines.append(f"> (Model `{main_name}` not found — skipped)")
            lines.append("")
            continue

        # Main section table
        main_fields = list(_iter_fields(main_cls))
        if main_fields:
            lines.append(f"### Section-level fields ({len(main_fields)})")
            lines.append("")
            lines.append("| Field | Label | Type & constraints |")
            lines.append("|---|---|---|")
            for f in main_fields:
                lines.append(f"| `{f.name}` | {_humanise(f.name)} | {_field_meta(f)} |")
            lines.append("")
            total_fields += len(main_fields)

        # Child sub-tables (repeatable rows)
        for child_name in child_names:
            try:
                child_cls = apps.get_model("database", child_name)
            except LookupError:
                lines.append(f"> (Sub-table model `{child_name}` not found — skipped)")
                lines.append("")
                continue

            child_fields = list(_iter_fields(child_cls))
            if not child_fields:
                continue

            lines.append(f"### Sub-table: `{child_name}` — {len(child_fields)} fields per row (unlimited rows)")
            lines.append("")
            lines.append("| Field | Label | Type & constraints |")
            lines.append("|---|---|---|")
            for f in child_fields:
                lines.append(f"| `{f.name}` | {_humanise(f.name)} | {_field_meta(f)} |")
            lines.append("")
            total_fields += len(child_fields)

        lines.append("---")
        lines.append("")

    # Grand total
    lines.append(f"## Grand total")
    lines.append("")
    lines.append(f"**{total_fields} distinct fields** across the 22 wizard sections.")
    lines.append("")
    lines.append("This does not count internal audit columns (`created_at`, `updated_at`, "
                 "`created_by`, `updated_by`, `is_deleted`, `order`) which every table "
                 "carries but never surface to the FPO.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*Generated from the live Django models — this file is always in sync "
                 "with what the platform actually stores.*")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out_path} ({out_path.stat().st_size / 1024:.1f} KB)")
    print(f"Total field count: {total_fields}")
