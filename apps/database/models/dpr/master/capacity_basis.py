"""Capacity basis per KAU spec §2.3.9 (Per Hour / Shift / Day / Week / Month / Season / Year)."""

from ._base import DPRMasterBase


class DPRCapacityBasis(DPRMasterBase):
    class Meta(DPRMasterBase.Meta):
        db_table = 'dpr_capacity_basis'
        verbose_name = 'DPR — Capacity Basis'
        verbose_name_plural = 'DPR — Capacity Bases'
