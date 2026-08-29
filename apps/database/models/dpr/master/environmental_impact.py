"""Environmental impact categories per KAU spec §2.3.20 A (Air Emissions, Dust, Noise, Wastewater, Solid Waste, Organic Waste, Plastic Waste, Hazardous Waste, Odour, Others)."""

from ._base import DPRMasterBase


class DPREnvironmentalImpact(DPRMasterBase):
    class Meta(DPRMasterBase.Meta):
        db_table = 'dpr_environmental_impact'
        verbose_name = 'DPR — Environmental Impact'
        verbose_name_plural = 'DPR — Environmental Impacts'
