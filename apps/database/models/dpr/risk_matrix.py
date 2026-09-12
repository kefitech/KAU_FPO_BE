"""
DPR §Risk Matrix — configurable probability × impact grid for scoring risk items.

Per KAU RCD reply B.9 (2026-09-02):
    "The system shall use the user-provided risk assessments to derive
     category-wise risk levels using a configurable probability–impact matrix.
     The overall project risk shall then be classified using a simple
     rule-based approach:
       High Risk: One or more risk categories are assessed as High.
       Moderate Risk: No category is High, but one or more assessed as Moderate.
       Low Risk: All assessed categories are Low.
     The probability–impact matrix and overall risk classification rules
     shall be configurable, allowing KAU to review and refine them during
     UAT or in future versions."

Shape: one row per (probability, impact) cell. Admin edits cell.risk_class.
Consumers use `get_risk_class(probability, impact)` to look up the class for a
user's risk assessment.

Levels match `LEVEL_CHOICES` on DPRRiskItem (Very Low / Low / Medium / High /
Very High) so a full 5×5 default grid = 25 cells. Admin can seed a smaller
subset (3×3 = 9 cells) — the matrix is level-agnostic; anything a risk item
carries can be looked up, and unmapped combinations return None.

Author: Athul Gopan (Kefi Tech Solutions)
"""
from typing import Optional

from django.db import models

from apps.core.models.base import TimeStampedModel, AuditModel


class DPRRiskMatrixCell(TimeStampedModel, AuditModel):
    """One (probability, impact) → risk_class mapping."""

    class Level(models.TextChoices):
        VERY_LOW  = 'very_low',  'Very Low'
        LOW       = 'low',       'Low'
        MEDIUM    = 'medium',    'Medium'
        HIGH      = 'high',      'High'
        VERY_HIGH = 'very_high', 'Very High'

    class RiskClass(models.TextChoices):
        LOW      = 'low',      'Low'
        MODERATE = 'moderate', 'Moderate'
        HIGH     = 'high',     'High'

    probability = models.CharField(
        max_length=12, choices=Level.choices,
        help_text="Probability level from the user's risk assessment.",
    )
    impact = models.CharField(
        max_length=12, choices=Level.choices,
        help_text="Impact level from the user's risk assessment.",
    )
    risk_class = models.CharField(
        max_length=10, choices=RiskClass.choices,
        help_text='Classification assigned when the (probability, impact) pair applies. '
                  'Admin-editable via /api/admin/dpr/risk-matrix/.',
    )
    # Numerical score is optional but useful for future weighted aggregations
    # (e.g. Wayanad turmeric with 5 High risks may need a separate signal
    # from a project with 1 High risk). Not consumed today.
    score = models.PositiveSmallIntegerField(
        default=0,
        help_text='Optional numeric weight for future weighted aggregations. '
                  'Not consumed by the current rule-based classifier.',
    )

    class Meta:
        db_table = 'dpr_risk_matrix_cell'
        verbose_name = 'DPR — Risk Matrix Cell'
        verbose_name_plural = 'DPR — Risk Matrix Cells'
        constraints = [
            models.UniqueConstraint(
                fields=['probability', 'impact'],
                name='dpr_risk_matrix_unique_cell',
            ),
        ]
        ordering = ['probability', 'impact']

    def __str__(self):
        return f'{self.get_probability_display()} × {self.get_impact_display()} = {self.get_risk_class_display()}'

    # ── Lookup helper — cached at the class level ────────────────────────
    _CACHE: Optional[dict] = None

    @classmethod
    def _load_cache(cls) -> dict:
        cache = {(c.probability, c.impact): c.risk_class for c in cls.objects.all()}
        cls._CACHE = cache
        return cache

    @classmethod
    def get_risk_class(cls, probability: str, impact: str) -> Optional[str]:
        """Return the configured risk class for a (probability, impact) pair.
        Returns None when either field is blank/unknown (caller should skip)."""
        if not probability or not impact:
            return None
        cache = cls._CACHE if cls._CACHE is not None else cls._load_cache()
        return cache.get((probability, impact))

    @classmethod
    def invalidate_cache(cls) -> None:
        """Call after admin edits — next lookup rebuilds from DB."""
        cls._CACHE = None
