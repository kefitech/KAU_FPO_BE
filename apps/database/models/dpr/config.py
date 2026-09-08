"""
DPR §Config — KAU Central Admin-controlled configuration for the DPR module.

Per KAU RCD reply B.6 (2026-09-02):
    "Financial assumption defaults shall be set and controlled by the KAU
     Central Administrator and applied as the system defaults across FPO
     projects. FPO users shall not independently modify core financial
     assumptions such as inflation rate, depreciation rate, tax rate,
     discount rate, or other appraisal parameters. Changes to system-level
     financial assumptions by the KAU Administrator shall be recorded
     through an audit trail."

Replaces the previous `DPRMasterConfig` model (deleted in migration 0044
during the V2 rebuild, never replaced). Also holds config values from RCD
items B.4 (variance threshold), C.4 (PDF retention count), A.3 (projection
years).

Value shape: typed JSON storage — the `value_type` discriminator tells
callers how to interpret `value`. Consumers should use the `.as_decimal()`,
`.as_int()`, `.as_string()`, `.as_bool()` accessors rather than reading
`value` directly, so type coercion + defaults live in one place.

Access control: mutations are restricted to super_admin group at the API
layer (see `apps/accounts/api/admin/dpr/config.py`). AuditLog row is written
on every mutation via a helper in the ViewSet.
"""
from decimal import Decimal
from typing import Any, Optional

from django.db import models

from apps.core.models.base import TimeStampedModel, AuditModel


class DPRConfig(TimeStampedModel, AuditModel):
    """One row per configurable DPR parameter."""

    class Category(models.TextChoices):
        FINANCIAL   = 'financial',   'Financial assumptions'
        PROJECTION  = 'projection',  'Projection settings'
        VARIANCE    = 'variance',    'Variance thresholds'
        RETENTION   = 'retention',   'Retention & archival'
        RISK        = 'risk',        'Risk matrix'
        OTHER       = 'other',       'Other'

    class ValueType(models.TextChoices):
        DECIMAL = 'decimal', 'Decimal (rate / percentage / money)'
        INT     = 'int',     'Integer (count / years)'
        STRING  = 'string',  'String (enum / free text)'
        BOOL    = 'bool',    'Boolean (yes / no)'

    key = models.CharField(
        max_length=100, unique=True, db_index=True,
        help_text="Programmatic key used by calculation code, e.g. 'discount_rate_pct'.",
    )
    category = models.CharField(
        max_length=20, choices=Category.choices,
        help_text='Grouping for admin UI.',
    )
    value_type = models.CharField(
        max_length=10, choices=ValueType.choices,
        help_text='How consumers should interpret `value` — enforced by the accessors.',
    )
    value = models.JSONField(
        help_text='Current value. Stored as JSON scalar; the type matches value_type.',
    )
    default_value = models.JSONField(
        help_text='Original seeded value — used for "reset to default" and audit comparisons.',
    )
    label = models.CharField(
        max_length=200,
        help_text='Human-readable name shown in admin UI.',
    )
    description = models.TextField(
        blank=True,
        help_text='Longer explanation of what this parameter controls + any caveats.',
    )
    unit = models.CharField(
        max_length=20, blank=True,
        help_text='Display unit — e.g. "%", "years", "count", "₹". Blank for enums.',
    )
    min_value = models.JSONField(
        null=True, blank=True,
        help_text='Optional inclusive lower bound. Enforced in admin serializer.',
    )
    max_value = models.JSONField(
        null=True, blank=True,
        help_text='Optional inclusive upper bound. Enforced in admin serializer.',
    )
    is_editable = models.BooleanField(
        default=True,
        help_text='If False, admin UI displays value read-only. Used for '
                  'computed / derived parameters that should not be changed manually.',
    )

    class Meta:
        db_table = 'dpr_config'
        verbose_name = 'DPR — Config'
        verbose_name_plural = 'DPR — Config'
        ordering = ['category', 'key']

    def __str__(self):
        return f'{self.key} = {self.value}'

    # ── Typed accessors ────────────────────────────────────────────────────
    # Callers should use these rather than reading `self.value` directly.
    # If value_type disagrees with the stored value they raise instead of
    # silently coercing — bugs surface early.

    def as_decimal(self) -> Decimal:
        if self.value_type != self.ValueType.DECIMAL:
            raise TypeError(f'{self.key} is {self.value_type}, not decimal')
        return Decimal(str(self.value))

    def as_int(self) -> int:
        if self.value_type != self.ValueType.INT:
            raise TypeError(f'{self.key} is {self.value_type}, not int')
        return int(self.value)

    def as_string(self) -> str:
        if self.value_type != self.ValueType.STRING:
            raise TypeError(f'{self.key} is {self.value_type}, not string')
        return str(self.value)

    def as_bool(self) -> bool:
        if self.value_type != self.ValueType.BOOL:
            raise TypeError(f'{self.key} is {self.value_type}, not bool')
        return bool(self.value)

    # ── Convenience lookup for calculation code ────────────────────────────

    @classmethod
    def get(cls, key: str, default: Any = None) -> Optional['DPRConfig']:
        """Fetch by key, returning None (or `default`) if missing. Prefer
        typed accessors for the actual value: `DPRConfig.get(k).as_decimal()`."""
        try:
            return cls.objects.get(key=key)
        except cls.DoesNotExist:
            return default

    @classmethod
    def get_decimal(cls, key: str, fallback: Decimal = Decimal('0')) -> Decimal:
        row = cls.get(key)
        return row.as_decimal() if row else fallback

    @classmethod
    def get_int(cls, key: str, fallback: int = 0) -> int:
        row = cls.get(key)
        return row.as_int() if row else fallback

    @classmethod
    def get_str(cls, key: str, fallback: str = '') -> str:
        row = cls.get(key)
        return row.as_string() if row else fallback

    @classmethod
    def get_bool(cls, key: str, fallback: bool = False) -> bool:
        row = cls.get(key)
        return row.as_bool() if row else fallback
