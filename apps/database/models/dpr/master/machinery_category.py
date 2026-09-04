"""
Machinery Categories per KAU spec §2.3.15 A.
Each category carries a default depreciation rate for the calculation engine.
"""

from django.db import models

from ._base import DPRMasterBase


class DPRMachineryCategory(DPRMasterBase):
    default_depreciation_rate_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=10,
        help_text='Default straight-line depreciation rate (%). '
                  'Used when the FPO does not override per-machinery. '
                  'Spec Ch 4.8 requires per-asset-class depreciation.',
    )
    default_useful_life_years = models.IntegerField(
        default=10,
        help_text='Default useful life in years (spec Ch 4.7 AI-assisted estimation).',
    )

    class Meta(DPRMasterBase.Meta):
        db_table = 'dpr_machinery_category'
        verbose_name = 'DPR — Machinery Category'
        verbose_name_plural = 'DPR — Machinery Categories'
