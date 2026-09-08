"""
Admin-side label enrichment for DPR section serialiser output.

Purpose: the FPO wizard serialisers return bare FK / M2M IDs (they hit
`/api/fpo/dpr/…` and the wizard already caches master lists client-side).
The admin oversight view needs human labels so a raw
`{"components": [24, 25, 27]}` becomes
`{"components": [{"id": 24, "name": "Grading"}, ...]}`.

We do this post-serialisation at the admin endpoint so the FPO wizard
contract stays untouched — no risk of breaking save flows.

Add a new section's enricher below, then register it in `ENRICHERS`. If a
section has no FK/M2M fields to enrich, no entry is needed.

Author: Athul Gopan (Kefi Tech Solutions)
"""
from typing import Any, Callable


def _label_for(model_cls, obj_id: int) -> dict[str, Any] | None:
    """Fetch (id, name) for one ID. Returns None when the row is missing.
    Uses `label_en` for DPR master rows; falls back to `code` or `str()`."""
    if obj_id is None:
        return None
    try:
        row = model_cls.objects.only('id').filter(pk=obj_id).first()
    except Exception:
        return None
    if row is None:
        return None
    name = (
        getattr(row, 'label_en', None)
        or getattr(row, 'name', None)
        or getattr(row, 'code', None)
        or str(row)
    )
    return {'id': row.id, 'name': name}


def _labels_for(model_cls, ids: list[int]) -> list[dict[str, Any]]:
    """Bulk-resolve a list of IDs while preserving input order."""
    if not ids:
        return []
    rows = {r.id: r for r in model_cls.objects.filter(pk__in=ids)}
    out: list[dict[str, Any]] = []
    for oid in ids:
        r = rows.get(oid)
        if r is None:
            continue
        name = (
            getattr(r, 'label_en', None)
            or getattr(r, 'name', None)
            or getattr(r, 'code', None)
            or str(r)
        )
        out.append({'id': r.id, 'name': name})
    return out


# ── Per-section enrichers ────────────────────────────────────────────────
# Each takes the serialiser's output dict, mutates it to replace bare IDs
# with {id, name} objects, and returns the modified dict. Import model
# classes lazily so this file doesn't force full app-model loading.

def _enrich_components(data: dict) -> dict:
    from apps.database.models import DPRComponent
    if 'components' in data and isinstance(data['components'], list):
        data['components'] = _labels_for(DPRComponent, data['components'])
    return data


def _enrich_nature_of_business(data: dict) -> dict:
    from apps.database.models import DPRNatureOfBusiness
    if 'natures' in data and isinstance(data['natures'], list):
        data['natures'] = _labels_for(DPRNatureOfBusiness, data['natures'])
    return data


def _enrich_products(data: dict) -> dict:
    """Products section has nested item rows with FKs on each row."""
    from apps.database.models import (
        DPRProductCategory, DPRProductType, DPRCapacityUnit,
    )
    for item in data.get('items', []):
        if not isinstance(item, dict):
            continue
        if item.get('category') is not None:
            item['category'] = _label_for(DPRProductCategory, item['category'])
        if item.get('product_type') is not None:
            item['product_type'] = _label_for(DPRProductType, item['product_type'])
        if item.get('unit_of_measurement') is not None:
            item['unit_of_measurement'] = _label_for(DPRCapacityUnit, item['unit_of_measurement'])
        if item.get('selling_unit') is not None:
            item['selling_unit'] = _label_for(DPRCapacityUnit, item['selling_unit'])
    return data


def _enrich_capacity(data: dict) -> dict:
    from apps.database.models import DPRCapacityUnit, DPRCapacityBasis
    if data.get('capacity_unit') is not None:
        data['capacity_unit'] = _label_for(DPRCapacityUnit, data['capacity_unit'])
    if data.get('capacity_basis') is not None:
        data['capacity_basis'] = _label_for(DPRCapacityBasis, data['capacity_basis'])
    return data


def _enrich_raw_material(data: dict) -> dict:
    from apps.database.models import (
        DPRCapacityUnit, DPRRawMaterialSource, DPRProcurementModel,
        DPRQualityStandard,
    )
    from apps.core.models.generic import MasterLookup

    if data.get('procurement_model') is not None:
        data['procurement_model'] = _label_for(DPRProcurementModel, data['procurement_model'])

    for m in data.get('materials', []) or []:
        if not isinstance(m, dict):
            continue
        for fk, cls in [
            ('unit_of_purchase',    DPRCapacityUnit),
            ('primary_source',      DPRRawMaterialSource),
            ('procurement_method',  DPRProcurementModel),
            ('quality_standard',    DPRQualityStandard),
        ]:
            if m.get(fk) is not None:
                m[fk] = _label_for(cls, m[fk])
        # commodity is a MasterLookup, not a DPR master
        if m.get('commodity') is not None:
            m['commodity'] = _label_for(MasterLookup, m['commodity'])

    for p in data.get('packaging_materials', []) or []:
        if isinstance(p, dict) and p.get('unit') is not None:
            p['unit'] = _label_for(DPRCapacityUnit, p['unit'])
    for c in data.get('consumables', []) or []:
        if isinstance(c, dict) and c.get('unit') is not None:
            c['unit'] = _label_for(DPRCapacityUnit, c['unit'])
    return data


def _enrich_market(data: dict) -> dict:
    from apps.database.models import (
        DPRProductCategory, DPRProductType, DPRIntendedMarket,
        DPRCapacityUnit, DPRBuyerType, DPRMarketingChannel,
    )
    for p in data.get('products', []) or []:
        if not isinstance(p, dict):
            continue
        for fk, cls in [
            ('product_category', DPRProductCategory),
            ('product_type',     DPRProductType),
            ('intended_market',  DPRIntendedMarket),
            ('unit_of_sale',     DPRCapacityUnit),
        ]:
            if p.get(fk) is not None:
                p[fk] = _label_for(cls, p[fk])
    for b in data.get('buyers', []) or []:
        if isinstance(b, dict) and b.get('buyer_category') is not None:
            b['buyer_category'] = _label_for(DPRBuyerType, b['buyer_category'])
    for c in data.get('channel_selections', []) or []:
        if isinstance(c, dict) and c.get('channel') is not None:
            c['channel'] = _label_for(DPRMarketingChannel, c['channel'])
    return data


def _enrich_location(data: dict) -> dict:
    """Location section has M2M FKs for land ownership and site status."""
    from apps.database.models import DPRLandOwnershipType, DPRSiteStatus
    if 'land_ownership_types' in data and isinstance(data['land_ownership_types'], list):
        data['land_ownership_types'] = _labels_for(DPRLandOwnershipType, data['land_ownership_types'])
    if 'site_statuses' in data and isinstance(data['site_statuses'], list):
        data['site_statuses'] = _labels_for(DPRSiteStatus, data['site_statuses'])
    return data


def _enrich_site(data: dict) -> dict:
    from apps.database.models import DPRCapacityUnit, DPRLandOwnershipType, DPRComponent
    for p in data.get('parcels', []) or []:
        if not isinstance(p, dict):
            continue
        if p.get('unit') is not None:
            p['unit'] = _label_for(DPRCapacityUnit, p['unit'])
        if p.get('ownership') is not None:
            p['ownership'] = _label_for(DPRLandOwnershipType, p['ownership'])
        if 'components' in p and isinstance(p['components'], list):
            p['components'] = _labels_for(DPRComponent, p['components'])
    return data


def _enrich_machinery(data: dict) -> dict:
    from apps.database.models import DPRMachineryCategory, DPRCapacityUnit, DPRComponent
    for it in data.get('items', []) or []:
        if not isinstance(it, dict):
            continue
        if it.get('machine_category') is not None:
            it['machine_category'] = _label_for(DPRMachineryCategory, it['machine_category'])
        if it.get('capacity_unit') is not None:
            it['capacity_unit'] = _label_for(DPRCapacityUnit, it['capacity_unit'])
        if it.get('project_component') is not None:
            it['project_component'] = _label_for(DPRComponent, it['project_component'])
    return data


def _enrich_technology(data: dict) -> dict:
    from apps.database.models import DPRTechnologyReason, DPRQualityStandard
    for t in data.get('technologies', []) or []:
        if not isinstance(t, dict):
            continue
        if 'reasons' in t and isinstance(t['reasons'], list):
            t['reasons'] = _labels_for(DPRTechnologyReason, t['reasons'])
        if 'certifications' in t and isinstance(t['certifications'], list):
            t['certifications'] = _labels_for(DPRQualityStandard, t['certifications'])
    return data


def _enrich_civil(data: dict) -> dict:
    from apps.database.models import DPRBuildingType, DPRCivilCategory
    for b in data.get('existing_buildings', []) or []:
        if isinstance(b, dict) and b.get('building_type') is not None:
            b['building_type'] = _label_for(DPRBuildingType, b['building_type'])
    for b in data.get('proposed_buildings', []) or []:
        if isinstance(b, dict) and b.get('building_type') is not None:
            b['building_type'] = _label_for(DPRBuildingType, b['building_type'])
    for s in data.get('site_dev_items', []) or []:
        if isinstance(s, dict) and s.get('category') is not None:
            s['category'] = _label_for(DPRCivilCategory, s['category'])
    return data


def _enrich_utilities(data: dict) -> dict:
    from apps.database.models import DPRFuelType, DPRWasteType, DPRRenewableInitiative
    for f in data.get('fuels', []) or []:
        if isinstance(f, dict) and f.get('fuel_type') is not None:
            f['fuel_type'] = _label_for(DPRFuelType, f['fuel_type'])
    for w in data.get('wastes', []) or []:
        if isinstance(w, dict) and w.get('waste_type') is not None:
            w['waste_type'] = _label_for(DPRWasteType, w['waste_type'])
    if 'renewable_initiatives' in data and isinstance(data['renewable_initiatives'], list):
        data['renewable_initiatives'] = _labels_for(DPRRenewableInitiative, data['renewable_initiatives'])
    return data


def _enrich_hr(data: dict) -> dict:
    from apps.database.models import DPRTrainingArea
    if 'training_areas' in data and isinstance(data['training_areas'], list):
        data['training_areas'] = _labels_for(DPRTrainingArea, data['training_areas'])
    return data


def _enrich_compliance(data: dict) -> dict:
    from apps.database.models import DPRStatutoryRegistration
    for it in data.get('items', []) or []:
        if isinstance(it, dict) and it.get('registration') is not None:
            it['registration'] = _label_for(DPRStatutoryRegistration, it['registration'])
    return data


def _enrich_ess(data: dict) -> dict:
    from apps.database.models import DPREnvironmentalImpact, DPRClimateRisk
    for i in data.get('environmental_impacts', []) or []:
        if isinstance(i, dict) and i.get('impact') is not None:
            i['impact'] = _label_for(DPREnvironmentalImpact, i['impact'])
    for r in data.get('climate_risks', []) or []:
        if isinstance(r, dict) and r.get('risk') is not None:
            r['risk'] = _label_for(DPRClimateRisk, r['risk'])
    return data


# section_key → enricher fn. Sections without FKs are omitted; they render fine as-is.
ENRICHERS: dict[str, Callable[[dict], dict]] = {
    'components':         _enrich_components,
    'nature-of-business': _enrich_nature_of_business,
    'products':           _enrich_products,
    'capacity':           _enrich_capacity,
    'raw-material':       _enrich_raw_material,
    'market':             _enrich_market,
    'location':           _enrich_location,
    'site':               _enrich_site,
    'machinery':          _enrich_machinery,
    'technology':         _enrich_technology,
    'civil':              _enrich_civil,
    'utilities':          _enrich_utilities,
    'hr':                 _enrich_hr,
    'compliance':         _enrich_compliance,
    'ess':                _enrich_ess,
}


def enrich_section_data(section_key: str, data: dict) -> dict:
    """Public entry — post-process serialised section data with FK labels.
    Safe no-op for sections without a registered enricher."""
    fn = ENRICHERS.get(section_key)
    if fn is None or not isinstance(data, dict):
        return data
    try:
        return fn(dict(data))  # shallow-copy so we don't mutate DRF's OrderedDict
    except Exception:
        # Enrichment failure should never break the admin view — return
        # raw data + let the admin see IDs rather than 500ing the page.
        import logging
        logging.getLogger(__name__).exception(
            'DPR admin enrichment failed for section %s', section_key,
        )
        return data
