"""Reconciliation comparison logic for cache vs live MTO responses.

Compares two MTO API response dicts field-by-field and returns a list
of Difference objects classified by severity.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Dict, List, Optional, Tuple


class Severity(Enum):
    CRITICAL = "critical"  # Missing child item
    HIGH = "high"          # Quantity difference > 10%
    MEDIUM = "medium"      # Quantity difference 1-10%
    LOW = "low"            # Quantity difference < 1% or metadata only


@dataclass
class Difference:
    mto_number: str
    material_code: str
    aux_attributes: str
    field_name: str
    cache_value: Optional[str]
    live_value: Optional[str]
    severity: Severity
    description: str


# JSON keys for quantity fields in the serialized API response
QTY_FIELDS = [
    "sales_order_qty",
    "prod_instock_must_qty",
    "prod_instock_real_qty",
    "purchase_order_qty",
    "purchase_stock_in_qty",
    "pick_actual_qty",
]


def compare_responses(
    cache_resp: dict, live_resp: dict, mto_number: str
) -> List[Difference]:
    """Compare cache and live API responses field-by-field.

    Both *cache_resp* and *live_resp* are expected to be the JSON dict
    returned by ``GET /api/mto/{mto_number}`` (serialized with aliases,
    so children live under ``child_items``).
    """
    diffs: List[Difference] = []

    # Build lookup maps keyed by (material_code, aux_attributes)
    cache_children = _build_child_map(cache_resp.get("child_items", []))
    live_children = _build_child_map(live_resp.get("child_items", []))

    # Items present in live but missing from cache
    for key in live_children:
        if key not in cache_children:
            code, aux = key
            diffs.append(Difference(
                mto_number=mto_number,
                material_code=code,
                aux_attributes=aux,
                field_name="child_item",
                cache_value=None,
                live_value="present",
                severity=Severity.CRITICAL,
                description=(
                    f"Child ({code}, aux='{aux}') exists in live "
                    "but missing from cache"
                ),
            ))

    # Items present in cache but missing from live
    for key in cache_children:
        if key not in live_children:
            code, aux = key
            diffs.append(Difference(
                mto_number=mto_number,
                material_code=code,
                aux_attributes=aux,
                field_name="child_item",
                cache_value="present",
                live_value=None,
                severity=Severity.MEDIUM,
                description=(
                    f"Child ({code}, aux='{aux}') exists in cache "
                    "but missing from live"
                ),
            ))

    # Compare matched items on quantity fields
    for key in cache_children:
        if key not in live_children:
            continue
        cache_child = cache_children[key]
        live_child = live_children[key]
        code, aux = key

        for field in QTY_FIELDS:
            c_val = _to_decimal(cache_child.get(field))
            l_val = _to_decimal(live_child.get(field))
            if c_val != l_val:
                severity = _classify_qty_diff(c_val, l_val)
                diffs.append(Difference(
                    mto_number=mto_number,
                    material_code=code,
                    aux_attributes=aux,
                    field_name=field,
                    cache_value=str(c_val),
                    live_value=str(l_val),
                    severity=severity,
                    description=f"{field}: cache={c_val} vs live={l_val}",
                ))

    return diffs


def _build_child_map(
    children: list,
) -> Dict[Tuple[str, str], dict]:
    """Build map keyed by (material_code, aux_attributes)."""
    result: Dict[Tuple[str, str], dict] = {}
    for child in children:
        code = child.get("material_code", "")
        aux = child.get("aux_attributes", "")
        result[(code, aux)] = child
    return result


def _to_decimal(val) -> Decimal:
    """Safely convert a value to Decimal."""
    if val is None:
        return Decimal("0")
    try:
        return Decimal(str(val))
    except InvalidOperation:
        return Decimal("0")


def _classify_qty_diff(cache: Decimal, live: Decimal) -> Severity:
    """Classify severity based on percentage difference."""
    if live == 0 and cache == 0:
        return Severity.LOW
    if live == 0:
        return Severity.HIGH
    pct = abs(cache - live) / abs(live) * 100
    if pct > 10:
        return Severity.HIGH
    elif pct > 1:
        return Severity.MEDIUM
    return Severity.LOW


def format_report(all_diffs: Dict[str, List[Difference]]) -> str:
    """Format a human-readable reconciliation report.

    *all_diffs* maps MTO number -> list of differences.
    """
    lines: List[str] = []
    lines.append("=" * 70)
    lines.append("RECONCILIATION REPORT")
    lines.append("=" * 70)

    total_mtos = len(all_diffs)
    mtos_with_diffs = sum(1 for d in all_diffs.values() if d)
    all_flat = [d for ds in all_diffs.values() for d in ds]
    critical_count = sum(1 for d in all_flat if d.severity == Severity.CRITICAL)
    high_count = sum(1 for d in all_flat if d.severity == Severity.HIGH)
    medium_count = sum(1 for d in all_flat if d.severity == Severity.MEDIUM)
    low_count = sum(1 for d in all_flat if d.severity == Severity.LOW)

    lines.append(f"\nSummary: {total_mtos} MTOs checked, "
                 f"{mtos_with_diffs} with differences, "
                 f"{critical_count} critical")
    lines.append(f"  CRITICAL: {critical_count}  HIGH: {high_count}  "
                 f"MEDIUM: {medium_count}  LOW: {low_count}")
    lines.append("")

    for mto, diffs in sorted(all_diffs.items()):
        if not diffs:
            lines.append(f"[OK] {mto}: no differences")
            continue

        lines.append(f"[!!] {mto}: {len(diffs)} difference(s)")
        for diff in sorted(diffs, key=lambda d: (d.severity.value, d.material_code)):
            sev = diff.severity.value.upper()
            lines.append(f"  [{sev}] {diff.description}")

    lines.append("")
    lines.append("=" * 70)
    return "\n".join(lines)
