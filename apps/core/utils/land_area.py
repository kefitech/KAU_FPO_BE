"""
Land area unit conversions.

Per KAU RCD reply B.3 (2026-09-02):
    "The system shall support the following land-area units:
     Acres, Cents, Ares, Hectares, Square metres.
     The system shall store/convert land area internally to a standard unit
     for calculations, while allowing the user to enter and view the area in
     the unit selected by them.
     The preferred standard unit for internal calculations shall be acres."

Canonical unit: **acre**. Every conversion goes acre <-> unit.

Precision: uses Decimal to avoid float rounding. Results returned as Decimal
so the caller can round to the display precision they want.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Union

# All ratios are "how many acres does 1 of this unit equal".
# Sources (SI): 1 hectare = 2.47105381 acres, 1 acre = 4046.8564224 sq m,
# 1 acre = 100 cents (Indian convention), 1 acre = 40.46856422 ares.
_ACRES_PER_UNIT: dict[str, Decimal] = {
    'acre':      Decimal('1'),
    'cent':      Decimal('0.01'),               # 100 cents = 1 acre
    'are':       Decimal('0.024710538146717'),  # 1 are = 100 sq m
    'hectare':   Decimal('2.47105381467165'),
    'sqm':       Decimal('0.00024710538146717'),
}

# Human-readable labels for the API + UI dropdowns.
UNIT_LABELS: dict[str, str] = {
    'acre':    'Acre',
    'cent':    'Cent',
    'are':     'Are',
    'hectare': 'Hectare',
    'sqm':     'Square metre',
}

VALID_UNITS = tuple(_ACRES_PER_UNIT.keys())
CANONICAL_UNIT = 'acre'


class UnknownUnitError(ValueError):
    """Raised when a caller passes a unit code not in VALID_UNITS."""


def _to_decimal(v: Union[int, float, str, Decimal, None]) -> Decimal:
    if v is None or v == '':
        return Decimal('0')
    if isinstance(v, Decimal):
        return v
    try:
        return Decimal(str(v))
    except InvalidOperation as exc:
        raise ValueError(f'Cannot convert {v!r} to Decimal') from exc


def to_acres(value: Union[int, float, str, Decimal, None], unit: str) -> Decimal:
    """Convert `value` in `unit` -> acres (canonical). Returns Decimal."""
    if unit not in _ACRES_PER_UNIT:
        raise UnknownUnitError(f'Unknown land unit {unit!r}. Valid: {VALID_UNITS}')
    return _to_decimal(value) * _ACRES_PER_UNIT[unit]


def from_acres(acres: Union[int, float, str, Decimal, None], unit: str) -> Decimal:
    """Convert `acres` -> value in `unit`. Returns Decimal."""
    if unit not in _ACRES_PER_UNIT:
        raise UnknownUnitError(f'Unknown land unit {unit!r}. Valid: {VALID_UNITS}')
    factor = _ACRES_PER_UNIT[unit]
    if factor == 0:
        raise ValueError(f'Zero conversion factor for {unit!r}')
    return _to_decimal(acres) / factor


def convert(
    value: Union[int, float, str, Decimal, None],
    from_unit: str,
    to_unit: str,
) -> Decimal:
    """Convert `value` from `from_unit` to `to_unit`. Both must be valid."""
    return from_acres(to_acres(value, from_unit), to_unit)
