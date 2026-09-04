"""Waste type options per KAU spec §2.3.16 F (Organic, Solid, Liquid, Plastic, Hazardous, Packaging, Wastewater, Others)."""

from ._base import DPRMasterBase


class DPRWasteType(DPRMasterBase):
    class Meta(DPRMasterBase.Meta):
        db_table = 'dpr_waste_type'
        verbose_name = 'DPR — Waste Type'
        verbose_name_plural = 'DPR — Waste Types'
