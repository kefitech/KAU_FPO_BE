"""Renewable energy initiative options per KAU spec §2.3.16 J (Solar Power, Solar Water Heater, Biogas Plant, Biomass Gasifier, Wind, Rainwater Harvesting, Energy Efficient Equipment, Others)."""

from ._base import DPRMasterBase


class DPRRenewableInitiative(DPRMasterBase):
    class Meta(DPRMasterBase.Meta):
        db_table = 'dpr_renewable_initiative'
        verbose_name = 'DPR — Renewable Initiative'
        verbose_name_plural = 'DPR — Renewable Initiatives'
