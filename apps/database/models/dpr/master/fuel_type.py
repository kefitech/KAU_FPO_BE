"""Fuel type options per KAU spec §2.3.16 C (Diesel, Petrol, LPG, PNG, Firewood, Biomass, Briquettes, Furnace Oil, Biogas, Others)."""

from ._base import DPRMasterBase


class DPRFuelType(DPRMasterBase):
    class Meta(DPRMasterBase.Meta):
        db_table = 'dpr_fuel_type'
        verbose_name = 'DPR — Fuel Type'
        verbose_name_plural = 'DPR — Fuel Types'
