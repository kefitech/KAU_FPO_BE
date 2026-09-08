"""
DPR §Capital Tranche — time-phased financial event log.

Per KAU RCD reply A.3 (2026-09-02):
    "The system shall construct the opening/project implementation balance
     sheet based on the ACTUAL TIMING of promoter contribution, loan
     disbursement and project expenditure, rather than assuming that the
     entire project cost is incurred on Day 1."

One row = one dated inflow or outflow during the project implementation
period. The calc engine (apps/fpo/services/dpr/calculation.py) reads these
to build a time-phased capital schedule. When no tranches are recorded for
a project, the calc engine falls back to a uniform-monthly assumption over
`DPRConfig.implementation_period_months` — but that fallback is explicitly
labelled `is_estimated=True` in the CalculationResult so downstream (PDF,
API responses, admin views) can flag it as an assumption rather than
declared timing.

Author: Athul Gopan (Kefi Tech Solutions)
"""
from django.db import models

from apps.core.models.base import TimeStampedModel, AuditModel


class DPRCapitalTranche(TimeStampedModel, AuditModel):
    """One dated financial event in a project's implementation period.

    Positive amount + inflow type → cash comes in.
    Positive amount + outflow type → cash goes out (capex).

    `finance_field` optionally cross-references which DPRSectionFinance
    cost/MoF field this tranche relates to. Sum of tranches for a given
    field should reconcile to the section-level total on the Finance form —
    the calc engine surfaces any discrepancy as a warning.
    """

    class TrancheType(models.TextChoices):
        # Inflows (MoF)
        PROMOTER_CONTRIBUTION = 'promoter_contribution', 'Promoter contribution'
        LOAN_DISBURSEMENT     = 'loan_disbursement',     'Loan disbursement'
        SUBSIDY_RELEASE       = 'subsidy_release',       'Subsidy release'
        GRANT_RECEIPT         = 'grant_receipt',         'Grant receipt'
        OTHER_INFLOW          = 'other_inflow',          'Other inflow'
        # Outflows (Capex)
        CAPEX_LAND            = 'capex_land',            'Capex — land'
        CAPEX_CIVIL           = 'capex_civil',           'Capex — civil works'
        CAPEX_MACHINERY       = 'capex_machinery',       'Capex — plant & machinery'
        CAPEX_EQUIPMENT       = 'capex_equipment',       'Capex — equipment'
        CAPEX_UTILITIES       = 'capex_utilities',       'Capex — utilities'
        CAPEX_PRE_OPERATIVE   = 'capex_pre_operative',   'Capex — pre-operative expenses'
        CAPEX_OTHER           = 'capex_other',           'Capex — other'

    # Inflow types drive MoF; outflow types drive capex. Used by the calc
    # engine to classify without hardcoding string checks scattered around.
    INFLOW_TYPES = frozenset({
        TrancheType.PROMOTER_CONTRIBUTION,
        TrancheType.LOAN_DISBURSEMENT,
        TrancheType.SUBSIDY_RELEASE,
        TrancheType.GRANT_RECEIPT,
        TrancheType.OTHER_INFLOW,
    })
    OUTFLOW_TYPES = frozenset({
        TrancheType.CAPEX_LAND,
        TrancheType.CAPEX_CIVIL,
        TrancheType.CAPEX_MACHINERY,
        TrancheType.CAPEX_EQUIPMENT,
        TrancheType.CAPEX_UTILITIES,
        TrancheType.CAPEX_PRE_OPERATIVE,
        TrancheType.CAPEX_OTHER,
    })

    project = models.ForeignKey(
        'database.DPRProject',
        on_delete=models.CASCADE,
        related_name='capital_tranches',
    )

    tranche_type = models.CharField(
        max_length=30,
        choices=TrancheType.choices,
        db_index=True,
    )

    amount = models.DecimalField(
        max_digits=15, decimal_places=2,
        help_text='Amount in ₹. Positive value for both inflows and outflows — '
                  'direction is derived from tranche_type.',
    )

    expected_month = models.PositiveSmallIntegerField(
        help_text='1-indexed month within the project implementation period. '
                  'Month 1 = first month of construction / setup.',
    )

    is_actual = models.BooleanField(
        default=False,
        help_text='False = projected (planned tranche not yet executed). '
                  'True = actual (event has happened; timing is confirmed).',
    )

    description = models.CharField(
        max_length=255, blank=True,
        help_text='Optional short label — e.g. "First loan drawdown", "SBI Rs 25L".',
    )

    finance_field = models.CharField(
        max_length=60, blank=True,
        help_text='Optional cross-reference to a DPRSectionFinance field name '
                  '(e.g. "cost_plant_machinery" or "mof_bank_term_loan"). Used by '
                  'the calc engine to reconcile tranche sums against section totals.',
    )

    class Meta:
        db_table = 'dpr_capital_tranche'
        verbose_name = 'DPR — Capital Tranche'
        verbose_name_plural = 'DPR — Capital Tranches'
        ordering = ['expected_month', 'id']
        indexes = [
            models.Index(fields=['project', 'expected_month']),
        ]

    def __str__(self):
        return f'M{self.expected_month} · {self.get_tranche_type_display()} · ₹{self.amount}'

    @property
    def is_inflow(self) -> bool:
        return self.tranche_type in self.INFLOW_TYPES

    @property
    def is_outflow(self) -> bool:
        return self.tranche_type in self.OUTFLOW_TYPES
