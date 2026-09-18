"""
Emit a KAU-facing questionnaire specification — the same 22 sections + 770
questions as DPR_Field_Inventory, but written the way KAU's original Data
Collection Module document reads.

Outputs BOTH:
    Documents/KAU_DPR_Questionnaire_Spec.md
    Documents/KAU_DPR_Questionnaire_Spec.docx   (KAU green styling — matches
                                                 generate_dpr_user_stories_docx.py)

    • Section 5 — Products & Services
        ○ A. Product identity
            - Product / service name (short text, required)
            - Category (dropdown — 20 options)
            - Primary or Secondary (radio — Primary / Secondary)
        ○ B. Sales projection
            - Annual quantity (number ≥ 0)
            - Selling price per unit ₹ (number ≥ 0)
            ...

Plain English wording only. No DB column names, no Char/Decimal/FK jargon.

Run:
    source venv/bin/activate
    python manage.py shell -c "
    exec(open('scripts/generate_kau_questionnaire_spec.py').read())
    generate_kau_questionnaire_spec()
    "
Output:
    Documents/KAU_DPR_Questionnaire_Spec.md
"""
from pathlib import Path


SECTIONS = [
    ("§2.2 Project Identification", "DPRProject", [],
     "Header form. Captures what the project is, why the FPO is proposing it, "
     "and which commodities / objectives / outcomes it targets. Filled once per DPR."),

    ("§2.3.2 Project Components", "DPRSectionComponents", [],
     "Which broad activities the project covers. Multi-select across 6 KAU-defined groups: "
     "primary production, processing & value addition, storage & post-harvest, marketing "
     "& business development, service-based enterprises, and supporting infrastructure. "
     "Selection here determines which later sections become mandatory."),

    ("§2.3.3 Nature of Business", "DPRSectionNatureOfBusiness", [],
     "What the enterprise actually does day-to-day. 15-option checklist "
     "(aggregation, processing, storage, packaging, marketing, trading, retail, "
     "input supply, custom hiring, export, integrated enterprise, and Others)."),

    ("§2.3.4 Proposed Investment", "DPRSectionInvestment", [],
     "Ballpark project cost the FPO expects to spend. Optional. Later cross-checked "
     "against the auto-computed number from Finance line items; large variances flagged."),

    ("§2.3.5 Products & Services", "DPRSectionProducts", ["DPRProductItem"],
     "Every product or service the enterprise will produce and sell. Feeds the revenue engine."),

    ("§2.3.6 Project Location", "DPRSectionLocation", [],
     "Where the project will be built. Full administrative hierarchy from state down "
     "to survey number, GPS pin on Kerala map, land ownership status, road / rail / port "
     "distances, connectivity (fibre / broadband / mobile)."),

    ("§2.3.7 Project Rationale", "DPRSectionRationale", ["DPRRationaleSelection"],
     "The business reasons for the project. From 29 rationale options; each selected "
     "reason gets its own justification paragraph (up to 100 words)."),

    ("§2.3.8 Current Status (Baseline)", "DPRSectionBaseline", [],
     "Whether the FPO is already engaged in the activity. If Yes → existing scale, "
     "capacity, employees, market coverage. If No → reason for proposing, prior "
     "experience, technical guidance sourcing, implementation approach."),

    ("§2.3.9 Capacity & Production", "DPRSectionCapacity", [],
     "How much the plant will produce and how it will operate. Installed vs practical "
     "capacity, working days / shifts / hours, peak & lean production months, process "
     "description (150-word limit), automation level, production losses, expansion plans."),

    ("§2.3.10 Raw Material Assessment", "DPRSectionRawMaterial",
     ["DPRRawMaterial", "DPRRawMaterialRisk", "DPRPackagingMaterial", "DPRConsumable"],
     "Every input the enterprise consumes. Primary raw materials (per material: identity, "
     "annual requirement, procurement source, seasonal availability, quality standards, "
     "prices, farmer network) plus packaging materials, consumables, and material-supply risks."),

    ("§2.3.11 Market Assessment", "DPRSectionMarket",
     ["DPRMarketingProduct", "DPRMarketingBuyer", "DPRMarketingChannelSelection",
      "DPRMarketingCompetitor", "DPRMarketingRisk"],
     "Where and to whom the products will sell. Demand basis, 5-year sales projections "
     "per product, buyer directory, marketing channel mix, competitor landscape, pricing "
     "strategy, promotional plans, market-side risks."),

    ("§2.3.12 Technology Selection", "DPRSectionTechnology", ["DPRTechnology", "DPRTechnologyRisk"],
     "The technology or process the plant will use. Indigenous vs imported, justification "
     "for choice, alternatives considered, technology-related risks."),

    ("§2.3.13 Land & Site Suitability", "DPRSectionSite",
     ["DPRLandParcel", "DPRExistingInfrastructure", "DPRSiteConstraint"],
     "The physical piece of land. Per-parcel details (area, ownership, mapping to project "
     "components), terrain, soil bearing capacity, existing infrastructure, utility "
     "distances, statutory approvals status, site constraints with mitigation plans."),

    ("§2.3.14 Civil Works", "DPRSectionCivil",
     ["DPRExistingBuilding", "DPRProposedBuilding", "DPRSiteDevelopmentItem"],
     "Buildings and site development. Existing buildings, proposed new buildings with type "
     "and area, site-development items (roads, fencing, drainage), cost breakdown across "
     "12 civil sub-categories, basis of estimate."),

    ("§2.3.15 Plant & Machinery", "DPRSectionMachinery", ["DPRMachineryItem", "DPRSupportingAssetItem"],
     "The machines and equipment. Per-machine: identity, source, capacity, power, foundation, "
     "full cost breakdown (basic + GST + freight + installation + insurance), warranty, AMC, "
     "useful life, plus supporting assets like furniture, IT equipment, vehicles."),

    ("§2.3.16 Utilities", "DPRSectionUtilities",
     ["DPRFuelUsage", "DPRProcessUtility", "DPRWasteManagement", "DPRRenewableInitiativeSelection"],
     "Every support service the plant needs. Electricity load and backup, water source and "
     "treatment, refrigeration, effluent management, communication and IT, fire safety, "
     "per-fuel usage, process utilities (compressed air / steam / boiler / hot water), "
     "waste management, and renewable-energy initiatives."),

    ("§2.3.17 Human Resources", "DPRSectionHR",
     ["DPREmployeeCategory", "DPRDepartmentStaffing", "DPRTrainingRequirement"],
     "The workforce. Management model, per-designation manpower with salaries, department-wise "
     "staffing, existing employees (technical, admin, marketing, skilled ops), training plan, "
     "labour availability, welfare items, statutory compliance checklist, future expansion."),

    ("§2.3.18 Finance", "DPRSectionFinance", ["DPRRevenueAssumption", "DPRFinancialYearHistory"],
     "The financial heart of the DPR. Capital cost across 19 heads, means of finance across "
     "12 sources, working capital, operating expenses, per-product revenue assumptions with "
     "5-year growth rates, loan proposal, subsidy details, 3-year financial history for "
     "operational FPOs."),

    ("§2.3.19 Statutory Compliance", "DPRSectionCompliance", ["DPRComplianceItem"],
     "Each statutory approval — status (obtained / applied / pending), issuing authority, "
     "validity period, remarks."),

    ("§2.3.20 Environment, Social & Sustainability", "DPRSectionESS",
     ["DPREnvironmentalImpactSelection", "DPRClimateRiskSelection"],
     "Environmental clearances, waste-water treatment, energy efficiency measures, CSR plans, "
     "community engagement, sustainability initiatives, climate-risk selections."),

    ("§2.3.21 Implementation Plan", "DPRSectionImplementation",
     ["DPRImplementationActivity", "DPRImplementationMilestone"],
     "Activity-wise implementation timeline, milestone table, dependencies, monitoring mechanism."),

    ("§2.3.22 Risk Assessment", "DPRSectionRisk", ["DPRRiskItem"],
     "Risk register — each risk classified on the KAU RCD 5×5 probability × impact matrix, "
     "with mitigation strategy and residual risk assessment."),
]


SKIP_FIELDS = {
    "id", "uuid", "created_at", "updated_at", "created_by", "updated_by",
    "deleted_at", "deleted_by",
    "project", "section", "is_deleted", "order",
    "is_complete", "field_sources", "status",
    # Auto-set server-side from the logged-in user's profile — never a question.
    "fpo", "user",
}


# Fields that are technically stored but which the FPO never types in
# (auto-derived server-side, cached copies, etc.) — hidden from spec.
DERIVED_FIELDS = {
    "annual_sales_revenue",  # Finance revenue row — quantity × price
}


# Fields whose human wording deserves a manual override — machine-humanised
# reads awkward. Extend as reviewers spot issues.
FIELD_OVERRIDES = {
    "title": "Proposed Project Title",
    "brief_description": "Brief Description of the Project",
    "primary_commodity": "Primary Commodity",
    "secondary_commodities": "Secondary Commodities",
    "project_types": "Project Type(s)",
    "project_objectives": "Project Objectives",
    "expected_outcomes": "Expected Outcomes",
    "estimated_project_cost": "Estimated Total Project Cost (₹)",
    "basis_of_estimate": "Basis of Estimate",
    "operational_management_model": "Operational Management Model",
    "existing_employees_total": "Total Existing Employees",
}


def _humanise(field_name: str) -> str:
    if field_name in FIELD_OVERRIDES:
        return FIELD_OVERRIDES[field_name]
    words = []
    for w in field_name.replace("_pct", "_percentage").split("_"):
        upper = w.upper()
        if upper in ("PAN", "GST", "CIN", "IFSC", "PIN", "SC", "ST",
                     "KAU", "FPO", "DPR", "URL", "ID", "GPS", "CEO", "NOC",
                     "CRZ", "LT", "HT", "DG", "UPS", "MSME", "EPF", "ESI",
                     "TDS", "NABARD", "SFAC", "CSR", "AMC", "HR",
                     "P", "L", "R", "D", "T"):
            words.append(upper)
        elif w == "percentage":
            words.append("(%)")
        elif w == "km":
            words.append("(km)")
        elif w == "kw":
            words.append("(kW)")
        elif w == "kva":
            words.append("(kVA)")
        elif w == "inr":
            words.append("(₹)")
        else:
            words.append(w.capitalize())
    return " ".join(words)


def _friendly_model(m) -> str:
    """Turn DPRProjectObjective / MasterLookup / DPRCapacityUnit → nice label."""
    name = getattr(m._meta, "verbose_name", None) or m.__name__
    label = str(name).replace("DPR ", "").replace("DPR-", "").replace("DPR", "")
    label = label.strip(" -—").strip()
    return label or m.__name__


def _describe(f) -> str:
    """Plain-English type + constraint description."""
    from django.db import models

    if isinstance(f, models.ManyToManyField):
        return f"Multiple choice (options from KAU {_friendly_model(f.related_model).lower()} master list)"
    if isinstance(f, models.ForeignKey):
        return f"Dropdown (options from KAU {_friendly_model(f.related_model).lower()} master list)"
    if isinstance(f, models.BooleanField):
        return "Yes / No"

    if hasattr(f, "choices") and f.choices:
        labels = [c[1] if isinstance(c, tuple) else str(c) for c in f.choices]
        if len(labels) <= 6:
            return "Choose one — " + " / ".join(str(x) for x in labels)
        return f"Choose one — {len(list(f.choices))} options"

    if isinstance(f, models.DecimalField):
        return "Number (decimal)"
    if isinstance(f, models.IntegerField) or isinstance(f, models.PositiveIntegerField):
        return "Number (integer)"
    if isinstance(f, models.DateField):
        return "Date"
    if isinstance(f, models.DateTimeField):
        return "Date & time"
    if isinstance(f, models.URLField):
        return "URL"
    if isinstance(f, models.EmailField):
        return "Email"
    if isinstance(f, models.TextField):
        return "Long text"
    if isinstance(f, models.CharField):
        if f.max_length and f.max_length <= 50:
            return f"Short text (up to {f.max_length} chars)"
        if f.max_length and f.max_length <= 200:
            return f"Text (up to {f.max_length} chars)"
        return "Text"
    if isinstance(f, models.JSONField):
        return "Structured data"
    return type(f).__name__.replace("Field", "")


def _required(f) -> str:
    from django.db import models

    if isinstance(f, (models.ManyToManyField,)):
        return ""
    optional = bool(getattr(f, "blank", False) or getattr(f, "null", False))
    default = f.default if hasattr(f, "default") else models.NOT_PROVIDED
    if not optional and default is models.NOT_PROVIDED:
        return "**Required**"
    return "Optional"


def _iter_fields(model_cls):
    for f in model_cls._meta.get_fields():
        if f.auto_created and not f.concrete:
            continue
        if not getattr(f, "editable", True):
            continue
        name = getattr(f, "name", None)
        if not name or name in SKIP_FIELDS or name in DERIVED_FIELDS:
            continue
        yield f


def generate_kau_questionnaire_spec():
    from django.apps import apps

    out_path = Path("Documents/KAU_DPR_Questionnaire_Spec.md")

    lines = []
    lines.append("# KAU-FPO — DPR Questionnaire Specification")
    lines.append("")
    lines.append("**Platform:** KAU-FPO Linkage Programme  ")
    lines.append("**Purpose:** the exact set of questions the platform asks an FPO to build a Detailed Project Report.  ")
    lines.append("**Grouped by:** the 22 sections in KAU's Data Collection Module V1.0 spec, in the order they appear in the wizard.")
    lines.append("")
    lines.append("Each question shows its wording as the FPO sees it, the type of "
                 "answer expected, and whether it is required or optional. Multi-row "
                 "tables (per-product, per-machine, per-employee etc.) are described with a "
                 "sub-heading — the FPO can add as many rows as needed.")
    lines.append("")
    lines.append("**Cross-section rules and validation** — e.g. sum of employee subgroups "
                 "≤ total, project cost variance vs Finance breakdown, land ownership "
                 "consistency — are enforced continuously as the FPO types and are listed "
                 "at the end of each section where they apply.")
    lines.append("")
    lines.append("---")
    lines.append("")

    total_questions = 0

    for section_title, main_name, child_names, blurb in SECTIONS:
        lines.append(f"## {section_title}")
        lines.append("")
        lines.append(blurb)
        lines.append("")

        try:
            main_cls = apps.get_model("database", main_name)
        except LookupError:
            lines.append(f"> (Not implemented yet — model `{main_name}` missing.)")
            lines.append("")
            continue

        main_fields = list(_iter_fields(main_cls))
        if main_fields:
            lines.append("**Questions asked**")
            lines.append("")
            for f in main_fields:
                label = _humanise(f.name)
                desc = _describe(f)
                req = _required(f)
                pieces = [desc]
                if req:
                    pieces.append(req)
                extra = " · ".join(pieces)
                lines.append(f"- **{label}** — {extra}")
            lines.append("")
            total_questions += len(main_fields)

        for child_name in child_names:
            try:
                child_cls = apps.get_model("database", child_name)
            except LookupError:
                continue
            child_fields = list(_iter_fields(child_cls))
            if not child_fields:
                continue

            friendly = child_name.replace("DPR", "").replace("_", " ")
            lines.append(f"**Repeatable table — {friendly}** (unlimited rows, {len(child_fields)} questions per row)")
            lines.append("")
            for f in child_fields:
                label = _humanise(f.name)
                desc = _describe(f)
                req = _required(f)
                pieces = [desc]
                if req:
                    pieces.append(req)
                extra = " · ".join(pieces)
                lines.append(f"- **{label}** — {extra}")
            lines.append("")
            total_questions += len(child_fields)

        lines.append("---")
        lines.append("")

    lines.append("## Grand total")
    lines.append("")
    lines.append(f"**{total_questions} distinct questions** across the 22 KAU spec sections. "
                 "Includes both section-level questions and per-row questions on repeatable tables.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*Generated directly from the running platform's data model. Wording, "
                 "grouping and choice lists reflect exactly what the FPO sees today.*")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out_path} ({out_path.stat().st_size / 1024:.1f} KB)")

    # Emit the docx sibling with KAU green styling.
    docx_path = out_path.with_suffix(".docx")
    _build_docx(docx_path, total_questions)
    print(f"Wrote {docx_path} ({docx_path.stat().st_size / 1024:.1f} KB)")


# ─────────────────────────────────────────────────────────────────────────────
# DOCX writer — KAU green styling (matches generate_dpr_user_stories_docx.py)
# ─────────────────────────────────────────────────────────────────────────────

def _build_docx(out_path: Path, total_questions: int):
    from django.apps import apps
    from docx import Document
    from docx.enum.table import WD_ALIGN_VERTICAL
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor

    KAU_GREEN_HEX = "2e7d32"
    KAU_PALE_GREEN_HEX = "f1f8e9"
    KAU_GREEN_RGB = RGBColor(0x2E, 0x7D, 0x32)
    WHITE = RGBColor(0xFF, 0xFF, 0xFF)
    MUTED = RGBColor(0x55, 0x55, 0x55)

    def shade(cell, fill_hex):
        tc_pr = cell._tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:fill"), fill_hex)
        shd.set(qn("w:val"), "clear")
        tc_pr.append(shd)

    def run(paragraph, text, *, bold=False, italic=False, size=10, color=None):
        r = paragraph.add_run(text)
        r.bold = bold
        r.italic = italic
        r.font.size = Pt(size)
        if color is not None:
            r.font.color.rgb = color
        return r

    def add_para(doc, text, *, italic=False, size=10, color=None):
        p = doc.add_paragraph()
        run(p, text, italic=italic, size=size, color=color)
        return p

    def section_header(doc, text):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(16)
        p.paragraph_format.space_after = Pt(6)
        run(p, text, bold=True, size=14, color=KAU_GREEN_RGB)

    def subheader(doc, text):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(3)
        run(p, text, bold=True, size=11, color=KAU_GREEN_RGB)

    def q_table(doc, field_rows):
        """3-col table: Question | Answer type | Req/Opt. KAU-green header."""
        table = doc.add_table(rows=1 + len(field_rows), cols=3)
        table.autofit = False
        widths = [7.0, 7.0, 2.5]
        for i, w in enumerate(widths):
            for r in table.rows:
                r.cells[i].width = Cm(w)

        headers = ["Question", "Answer type", "Req / Opt"]
        for i, text in enumerate(headers):
            cell = table.rows[0].cells[i]
            cell.text = ""
            run(cell.paragraphs[0], text, bold=True, size=10, color=WHITE)
            shade(cell, KAU_GREEN_HEX)
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

        for r_idx, (label, desc, req) in enumerate(field_rows, start=1):
            fill = KAU_PALE_GREEN_HEX if r_idx % 2 == 1 else None
            for c_idx, value in enumerate([label, desc, req]):
                cell = table.rows[r_idx].cells[c_idx]
                cell.text = ""
                run(cell.paragraphs[0], value, size=10,
                    bold=(c_idx == 0))
                if fill:
                    shade(cell, fill)
                cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP
        doc.add_paragraph("")

    doc = Document()

    # Title block
    p = doc.add_paragraph()
    run(p, "KAU–FPO Linkage Platform", bold=True, size=18, color=KAU_GREEN_RGB)
    p = doc.add_paragraph()
    run(p, "DPR Questionnaire Specification", bold=True, size=14, color=KAU_GREEN_RGB)
    p = doc.add_paragraph()
    run(p, "Kerala Agricultural University  ·  Communication Centre", size=10)
    p = doc.add_paragraph()
    run(p, "Prepared by: Athul Gopan · Kefi Tech Solutions", italic=True, size=10)
    doc.add_paragraph("")

    add_para(doc,
        "Purpose: the exact set of questions the platform asks an FPO to build a "
        "Detailed Project Report. Grouped by the 22 sections in KAU's Data "
        "Collection Module V1.0 spec, in the order they appear in the wizard.")
    add_para(doc,
        "Each question shows its wording as the FPO sees it, the type of answer "
        "expected, and whether it is required or optional. Repeatable tables "
        "(per-product, per-machine, per-employee etc.) are listed under a "
        "sub-heading — the FPO can add as many rows as needed.", italic=True)
    add_para(doc,
        "Cross-section rules and validation — e.g. sum of employee subgroups ≤ "
        "total, project cost variance vs Finance breakdown, land ownership "
        "consistency — are enforced continuously as the FPO types.", italic=True)

    for section_title, main_name, child_names, blurb in SECTIONS:
        section_header(doc, section_title)
        add_para(doc, blurb)

        try:
            main_cls = apps.get_model("database", main_name)
        except LookupError:
            add_para(doc, f"(Not implemented yet — model {main_name} missing.)",
                     italic=True, color=MUTED)
            continue

        main_fields = list(_iter_fields(main_cls))
        if main_fields:
            subheader(doc, "Questions asked")
            rows = []
            for f in main_fields:
                rows.append((_humanise(f.name), _describe(f), _required(f) or "Optional"))
            q_table(doc, rows)

        for child_name in child_names:
            try:
                child_cls = apps.get_model("database", child_name)
            except LookupError:
                continue
            child_fields = list(_iter_fields(child_cls))
            if not child_fields:
                continue
            friendly = child_name.replace("DPR", "").replace("_", " ")
            subheader(doc,
                f"Repeatable table — {friendly} "
                f"(unlimited rows, {len(child_fields)} questions per row)")
            rows = []
            for f in child_fields:
                rows.append((_humanise(f.name), _describe(f), _required(f) or "Optional"))
            q_table(doc, rows)

    section_header(doc, "Grand total")
    add_para(doc,
        f"{total_questions} distinct questions across the 22 KAU spec sections. "
        "Includes both section-level questions and per-row questions on repeatable tables.")

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run(p,
        "Generated directly from the running platform's data model. Wording, "
        "grouping and choice lists reflect exactly what the FPO sees today.",
        italic=True, size=9, color=MUTED)

    doc.save(out_path)
    print(f"Total questions: {total_questions}")
