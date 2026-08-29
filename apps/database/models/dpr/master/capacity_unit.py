"""Capacity units per KAU spec §2.3.9 (kg / MT / Quintal / Number / Litres / etc — 13 options)."""

from ._base import DPRMasterBase


class DPRCapacityUnit(DPRMasterBase):
    class Meta(DPRMasterBase.Meta):
        db_table = 'dpr_capacity_unit'
        verbose_name = 'DPR — Capacity Unit'
        verbose_name_plural = 'DPR — Capacity Units'
