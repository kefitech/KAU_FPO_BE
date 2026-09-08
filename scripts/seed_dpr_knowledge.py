"""
Seed a starter set of DPR knowledge base entries.

Per KAU RCD A.2 — AI narratives must be grounded in authoritative sources
(KAU PoP, government schemes, Kefi Tech SOPs, Kerala statutory portals,
AGMARKNET). This script seeds ~12 realistic sample entries across all 5
source types so the retrieval service and admin UI have live data.

Idempotent — uses `update_or_create` on (source_type, source_name, title).
Re-running always applies the latest content.

Run:
    source venv/bin/activate && python manage.py shell -c "
    exec(open('scripts/seed_dpr_knowledge.py').read())
    seed_dpr_knowledge()
    "

Note: commodity/component filters are populated only when the referenced
MasterLookup / DPRComponent exists. Missing references are silently skipped
(a warning is printed) so the script runs cleanly on any fresh DB.

Author: Athul Gopan (Kefi Tech Solutions)
"""
from apps.core.models.generic import MasterLookup
from apps.database.models import DPRComponent, DPRKnowledgeEntry, DPRNatureOfBusiness


def _commodity(code):
    """Fetch a commodity MasterLookup by code, or None if missing."""
    try:
        return MasterLookup.objects.get(category='commodity', code=code)
    except MasterLookup.DoesNotExist:
        return None


def _component(code):
    """Fetch a DPRComponent by code, or None if missing."""
    try:
        return DPRComponent.objects.get(code=code)
    except DPRComponent.DoesNotExist:
        return None


ENTRIES = [
    # ── AGMARKNET — market prices (section: market, tags: prices) ─────────
    {
        'source_type': 'agmarknet',
        'source_name': 'AGMARKNET — Kerala (Aug 2026)',
        'source_url': 'https://agmarknet.gov.in',
        'source_version': 'Aug 2026',
        'title': 'Turmeric (Rhizome) — Kerala mandi prices, Aug 2026',
        'content': (
            'Turmeric rhizome (dried) at Kerala mandis (Kochi, Wayanad, '
            'Idukki) averaged ₹12,800/quintal in August 2026, with a range '
            'of ₹11,200 – ₹14,100/qtl. Prices rose 8% YoY driven by lower '
            'Andhra output and steady export demand from Iran and Bangladesh.'
        ),
        'section_keys': ['market'],
        'tags': ['prices', 'monthly'],
        'commodity_codes': ['turmeric'],
    },
    {
        'source_type': 'agmarknet',
        'source_name': 'AGMARKNET — Kerala (Aug 2026)',
        'source_url': 'https://agmarknet.gov.in',
        'source_version': 'Aug 2026',
        'title': 'Black Pepper — Kerala mandi prices, Aug 2026',
        'content': (
            'Malabar Garbled Grade 1 black pepper averaged ₹63,500/quintal '
            'across Kochi and Wayanad mandis in August 2026. High-quality '
            'organic-certified lots command a 10-15% premium.'
        ),
        'section_keys': ['market'],
        'tags': ['prices', 'monthly'],
        'commodity_codes': ['pepper', 'black_pepper'],
    },

    # ── KAU PoP — commodity practices (section: technology, raw-material) ──
    {
        'source_type': 'kau_pop',
        'source_name': 'KAU Package of Practices — Turmeric',
        'source_url': 'https://kau.in/pop/turmeric',
        'source_version': '2024 Edition',
        'title': 'Turmeric curing — post-harvest protocol',
        'content': (
            'Cure turmeric rhizomes within 3 days of harvest to preserve '
            'curcumin content. Standard protocol: boil in 0.05-0.10% alkali '
            'solution for 45-60 minutes until translucent; sun-dry on clean '
            'concrete for 5-8 days until moisture drops to 10-12%. '
            'Mechanical dryers at 55-60°C reduce drying to 40-50 hours and '
            'yield higher curcumin retention (typically 3.5-4%).'
        ),
        'section_keys': ['technology', 'raw-material'],
        'tags': ['post-harvest', 'protocol'],
        'commodity_codes': ['turmeric'],
    },
    {
        'source_type': 'kau_pop',
        'source_name': 'KAU Package of Practices — Black Pepper',
        'source_url': 'https://kau.in/pop/pepper',
        'source_version': '2024 Edition',
        'title': 'Black pepper drying and grading',
        'content': (
            'Sun-dry pepper berries on tarpaulins for 4-5 days until moisture '
            'reaches 10-11%. Grade by density using indented cylinder '
            'graders: Malabar Garbled 1 (>570 g/L), MG2 (550-570), MG Special '
            'Extra Bold (>4.75 mm sieve). Machine-cleaned lots fetch 5-8% '
            'premium over hand-cleaned.'
        ),
        'section_keys': ['technology', 'raw-material'],
        'tags': ['post-harvest', 'grading'],
        'commodity_codes': ['pepper', 'black_pepper'],
    },

    # ── Government schemes (section: compliance, tags: scheme) ─────────────
    {
        'source_type': 'scheme',
        'source_name': 'PMKSY — Per Drop More Crop',
        'source_url': 'https://pmksy.gov.in/microirrigation',
        'source_version': 'GoI 2024-25',
        'title': 'PMKSY — subsidy for micro-irrigation systems',
        'content': (
            'Per Drop More Crop provides 55% subsidy (SC/ST/small farmers) '
            'or 45% (other) on drip and sprinkler installations up to 5 '
            'hectares per beneficiary. Eligible: individual farmers, FPOs, '
            'SHGs. Application through State Horticulture Mission. Timeline '
            'from application to disbursement typically 60-90 days.'
        ),
        'section_keys': ['compliance', 'finance', 'utilities'],
        'tags': ['scheme', 'subsidy', 'irrigation'],
    },
    {
        'source_type': 'scheme',
        'source_name': 'MOFPI — PMFME Scheme',
        'source_url': 'https://pmfme.mofpi.gov.in',
        'source_version': '2024-25',
        'title': 'PMFME — Micro Food Processing Enterprises',
        'content': (
            'Pradhan Mantri Formalisation of Micro Food Processing scheme '
            'provides 35% credit-linked capital subsidy (max ₹10 lakh) for '
            'setting up or upgrading individual micro food processing units. '
            'FPO-led common infrastructure gets 35% subsidy up to ₹3 crore. '
            'Kerala DIC handles applications; DoIH is the state nodal agency.'
        ),
        'section_keys': ['compliance', 'finance'],
        'tags': ['scheme', 'subsidy', 'processing'],
    },
    {
        'source_type': 'scheme',
        'source_name': 'NABARD — RIDF',
        'source_url': 'https://www.nabard.org/ridf',
        'source_version': '2024-25',
        'title': 'NABARD Rural Infrastructure Development Fund',
        'content': (
            'RIDF Tranche XXX provides refinance to state governments for '
            'rural infrastructure at 6.5-7.5% p.a. FPO warehousing, cold '
            'storage, and market yard projects can be routed through the '
            'state RIDF allocation. Typical loan cover 75-80% of project '
            'cost with 7-year repayment.'
        ),
        'section_keys': ['finance'],
        'tags': ['scheme', 'loan', 'infrastructure'],
    },

    # ── Kefi Tech SOPs (section-agnostic operational guides) ───────────────
    {
        'source_type': 'sop',
        'source_name': 'Kefi Tech SOP — FPO Registration',
        'source_version': 'v1.2 (2026-06)',
        'title': 'End-to-end FPO registration timeline',
        'content': (
            'FPO registration under the Companies Act (2013) or the state '
            'Cooperative Societies Act typically takes 45-60 days: name '
            'reservation (7-10 d), MOA/AOA drafting + digital signatures '
            '(5-7 d), incorporation filing (15-25 d), PAN/TAN (5-7 d), bank '
            'account and GST (7-10 d). Budget ₹25,000-40,000 for legal + '
            'filing fees inclusive of professional charges.'
        ),
        'section_keys': ['compliance', 'implementation'],
        'tags': ['registration', 'process'],
    },
    {
        'source_type': 'sop',
        'source_name': 'Kefi Tech SOP — Cold Storage Sizing',
        'source_version': 'v2.0 (2026-04)',
        'title': 'Sizing a modular cold storage for FPO produce',
        'content': (
            'Rule-of-thumb: 6-8 cubic feet per quintal for palletised '
            'storage of horticultural produce; 4-5 cft/qtl for bulk stacked '
            'goods. Modular refrigeration units (PUF-panel, plug-and-play) '
            'range ₹18-25 lakh per 25 MT capacity chamber. Include a 20% '
            'buffer for peak-season inflow. Insulation of at least 100 mm '
            'PUF is standard for +2 to +8°C ranges.'
        ),
        'section_keys': ['machinery', 'civil', 'utilities'],
        'tags': ['cold-storage', 'sizing'],
        'component_codes': ['cold_storage'],
    },

    # ── Kerala statutory / regulatory ──────────────────────────────────────
    {
        'source_type': 'statutory',
        'source_name': 'Kerala Panchayati Raj Act, 1994',
        'source_url': 'https://lsg.kerala.gov.in',
        'source_version': 'as amended 2023',
        'title': 'Local body registration and NOC requirements',
        'content': (
            'Any commercial establishment in Kerala requires a Panchayat / '
            'Municipality trade licence renewed annually. Food processing '
            'and storage units additionally need a No-Objection Certificate '
            'from the local body confirming site suitability (typically '
            'issued within 15-30 days). Charges vary ₹500-5,000 based on '
            'turnover slab.'
        ),
        'section_keys': ['compliance', 'site'],
        'tags': ['statutory', 'licence'],
    },
    {
        'source_type': 'statutory',
        'source_name': 'FSSAI — Kerala Regional Office',
        'source_url': 'https://fssai.gov.in',
        'source_version': '2024-25',
        'title': 'FSSAI licence categories for food FPOs',
        'content': (
            'Basic Registration: turnover < ₹12 lakh, ₹100/year. State '
            'Licence: ₹12 lakh - ₹20 crore, ₹2,000-5,000/year. Central '
            'Licence: > ₹20 crore or interstate trade, ₹7,500/year. Food '
            'processing and storage FPOs almost always need State Licence '
            'at minimum. Application through FoSCoS portal; approval 30-60 '
            'days.'
        ),
        'section_keys': ['compliance'],
        'tags': ['statutory', 'licence', 'fssai'],
    },
    {
        'source_type': 'statutory',
        'source_name': 'Kerala State Pollution Control Board',
        'source_url': 'https://kspcb.kerala.gov.in',
        'source_version': '2024',
        'title': 'KSPCB consent for food processing units',
        'content': (
            'Food processing units in Kerala require Consent to Establish '
            '(CTE) before construction and Consent to Operate (CTO) before '
            'commissioning. Categorised as Green / Orange / Red based on '
            'pollution potential — most FPO-scale processing falls in Green '
            'or Orange. Timeline: 60-90 days for CTE, 30-45 days for CTO. '
            'Fee based on capital investment slabs.'
        ),
        'section_keys': ['compliance', 'ess'],
        'tags': ['statutory', 'environmental'],
    },
]


def seed_dpr_knowledge():
    created = 0
    updated = 0
    skipped_refs = 0

    for spec in ENTRIES:
        commodity_codes = spec.pop('commodity_codes', [])
        component_codes = spec.pop('component_codes', [])
        business_codes = spec.pop('business_codes', [])

        entry, was_created = DPRKnowledgeEntry.objects.update_or_create(
            source_type=spec['source_type'],
            source_name=spec['source_name'],
            title=spec['title'],
            defaults={
                'source_url': spec.get('source_url', ''),
                'source_version': spec.get('source_version', ''),
                'content': spec['content'],
                'language': spec.get('language', 'en'),
                'section_keys': spec.get('section_keys', []),
                'tags': spec.get('tags', []),
                'is_active': True,
            },
        )

        # Reset M2Ms every run so seed edits are reflected
        entry.commodities.clear()
        for code in commodity_codes:
            m = _commodity(code)
            if m:
                entry.commodities.add(m)
            else:
                skipped_refs += 1
        entry.components.clear()
        for code in component_codes:
            c = _component(code)
            if c:
                entry.components.add(c)
            else:
                skipped_refs += 1
        entry.business_types.clear()
        for code in business_codes:
            try:
                b = DPRNatureOfBusiness.objects.get(code=code)
                entry.business_types.add(b)
            except DPRNatureOfBusiness.DoesNotExist:
                skipped_refs += 1

        if was_created:
            created += 1
        else:
            updated += 1

    total = DPRKnowledgeEntry.objects.filter(is_active=True).count()
    print(f'DPR knowledge base seed complete:')
    print(f'  created:  {created}')
    print(f'  updated:  {updated}')
    print(f'  skipped_refs (missing commodity/component/business): {skipped_refs}')
    print(f'  total active entries in DB: {total}')
