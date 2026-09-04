"""Procurement model options per KAU spec §2.3.10 A/C (Direct Purchase, Aggregation, Contract Farming, Collection Centre, etc)."""

from ._base import DPRMasterBase


class DPRProcurementModel(DPRMasterBase):
    class Meta(DPRMasterBase.Meta):
        db_table = 'dpr_procurement_model'
        verbose_name = 'DPR — Procurement Model'
        verbose_name_plural = 'DPR — Procurement Models'
