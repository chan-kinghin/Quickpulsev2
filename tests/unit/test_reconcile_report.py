"""Tests for scripts/reconcile_report.py — comparison logic."""

import sys
from decimal import Decimal
from pathlib import Path

import pytest

# Add scripts/ to path so we can import reconcile_report directly
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from reconcile_report import (
    Difference,
    Severity,
    _build_child_map,
    _classify_qty_diff,
    _to_decimal,
    compare_responses,
    format_report,
)


# ---------------------------------------------------------------------------
# Helpers to build response dicts matching the serialized API shape
# ---------------------------------------------------------------------------

def _make_child(
    material_code: str = "07.01.001",
    aux_attributes: str = "",
    sales_order_qty: float = 100,
    prod_instock_must_qty: float = 0,
    prod_instock_real_qty: float = 0,
    purchase_order_qty: float = 0,
    purchase_stock_in_qty: float = 0,
    pick_actual_qty: float = 0,
    material_type_code: int = 1,
    material_type: str = "自制",
    material_name: str = "TestItem",
    specification: str = "A",
    bom_short_name: str = "",
) -> dict:
    return {
        "material_code": material_code,
        "material_name": material_name,
        "specification": specification,
        "aux_attributes": aux_attributes,
        "bom_short_name": bom_short_name,
        "material_type_code": material_type_code,
        "material_type": material_type,
        "sales_order_qty": sales_order_qty,
        "prod_instock_must_qty": prod_instock_must_qty,
        "prod_instock_real_qty": prod_instock_real_qty,
        "purchase_order_qty": purchase_order_qty,
        "purchase_stock_in_qty": purchase_stock_in_qty,
        "pick_actual_qty": pick_actual_qty,
    }


def _make_response(children: list) -> dict:
    return {
        "mto_number": "AK2510034",
        "parent_item": {
            "mto_number": "AK2510034",
            "customer_name": "Test Customer",
            "delivery_date": "2025-10-01",
        },
        "child_items": children,
        "query_time": "2025-01-01T00:00:00",
        "data_source": "cache",
    }


# ---------------------------------------------------------------------------
# Tests: _to_decimal
# ---------------------------------------------------------------------------

class TestToDecimal:
    def test_none_returns_zero(self):
        assert _to_decimal(None) == Decimal("0")

    def test_int(self):
        assert _to_decimal(42) == Decimal("42")

    def test_float(self):
        assert _to_decimal(3.14) == Decimal("3.14")

    def test_string(self):
        assert _to_decimal("100.50") == Decimal("100.50")

    def test_invalid_returns_zero(self):
        assert _to_decimal("not_a_number") == Decimal("0")

    def test_decimal_passthrough(self):
        assert _to_decimal(Decimal("99")) == Decimal("99")


# ---------------------------------------------------------------------------
# Tests: _classify_qty_diff
# ---------------------------------------------------------------------------

class TestClassifyQtyDiff:
    def test_both_zero(self):
        assert _classify_qty_diff(Decimal("0"), Decimal("0")) == Severity.LOW

    def test_live_zero_cache_nonzero(self):
        assert _classify_qty_diff(Decimal("10"), Decimal("0")) == Severity.HIGH

    def test_diff_over_10_percent(self):
        # cache=120, live=100 -> 20% diff -> HIGH
        assert _classify_qty_diff(Decimal("120"), Decimal("100")) == Severity.HIGH

    def test_diff_between_1_and_10_percent(self):
        # cache=105, live=100 -> 5% diff -> MEDIUM
        assert _classify_qty_diff(Decimal("105"), Decimal("100")) == Severity.MEDIUM

    def test_diff_under_1_percent(self):
        # cache=100.5, live=100 -> 0.5% diff -> LOW
        assert _classify_qty_diff(Decimal("100.5"), Decimal("100")) == Severity.LOW

    def test_exact_1_percent_boundary(self):
        # cache=101, live=100 -> 1% exactly -> LOW (must be > 1)
        assert _classify_qty_diff(Decimal("101"), Decimal("100")) == Severity.LOW

    def test_exact_10_percent_boundary(self):
        # cache=110, live=100 -> 10% exactly -> MEDIUM (must be > 10)
        assert _classify_qty_diff(Decimal("110"), Decimal("100")) == Severity.MEDIUM


# ---------------------------------------------------------------------------
# Tests: _build_child_map
# ---------------------------------------------------------------------------

class TestBuildChildMap:
    def test_empty_list(self):
        assert _build_child_map([]) == {}

    def test_single_child(self):
        child = _make_child(material_code="05.01.001", aux_attributes="Red")
        result = _build_child_map([child])
        assert ("05.01.001", "Red") in result
        assert result[("05.01.001", "Red")] is child

    def test_multiple_children_different_keys(self):
        c1 = _make_child(material_code="05.01.001", aux_attributes="Red")
        c2 = _make_child(material_code="05.01.002", aux_attributes="Blue")
        result = _build_child_map([c1, c2])
        assert len(result) == 2

    def test_same_code_different_aux(self):
        c1 = _make_child(material_code="05.01.001", aux_attributes="Red")
        c2 = _make_child(material_code="05.01.001", aux_attributes="Blue")
        result = _build_child_map([c1, c2])
        assert len(result) == 2
        assert ("05.01.001", "Red") in result
        assert ("05.01.001", "Blue") in result

    def test_missing_fields_default_empty(self):
        result = _build_child_map([{}])
        assert ("", "") in result


# ---------------------------------------------------------------------------
# Tests: compare_responses
# ---------------------------------------------------------------------------

class TestCompareResponses:
    def test_identical_responses_no_diffs(self):
        child = _make_child()
        cache = _make_response([child])
        live = _make_response([child])
        diffs = compare_responses(cache, live, "AK2510034")
        assert diffs == []

    def test_missing_child_in_cache_critical(self):
        """Child exists in live but not cache -> CRITICAL."""
        child = _make_child(material_code="05.01.001")
        cache = _make_response([])
        live = _make_response([child])
        diffs = compare_responses(cache, live, "AK2510034")
        assert len(diffs) == 1
        assert diffs[0].severity == Severity.CRITICAL
        assert diffs[0].field_name == "child_item"
        assert diffs[0].cache_value is None
        assert diffs[0].live_value == "present"

    def test_extra_child_in_cache_medium(self):
        """Child exists in cache but not live -> MEDIUM."""
        child = _make_child(material_code="05.01.001")
        cache = _make_response([child])
        live = _make_response([])
        diffs = compare_responses(cache, live, "AK2510034")
        assert len(diffs) == 1
        assert diffs[0].severity == Severity.MEDIUM
        assert diffs[0].field_name == "child_item"
        assert diffs[0].cache_value == "present"
        assert diffs[0].live_value is None

    def test_qty_mismatch_high_severity(self):
        """Quantity difference > 10% -> HIGH."""
        cache_child = _make_child(sales_order_qty=200)
        live_child = _make_child(sales_order_qty=100)
        cache = _make_response([cache_child])
        live = _make_response([live_child])
        diffs = compare_responses(cache, live, "AK2510034")
        assert len(diffs) == 1
        assert diffs[0].severity == Severity.HIGH
        assert diffs[0].field_name == "sales_order_qty"

    def test_qty_mismatch_medium_severity(self):
        """Quantity difference 1-10% -> MEDIUM."""
        cache_child = _make_child(sales_order_qty=105)
        live_child = _make_child(sales_order_qty=100)
        cache = _make_response([cache_child])
        live = _make_response([live_child])
        diffs = compare_responses(cache, live, "AK2510034")
        assert len(diffs) == 1
        assert diffs[0].severity == Severity.MEDIUM

    def test_qty_mismatch_low_severity(self):
        """Quantity difference < 1% -> LOW."""
        cache_child = _make_child(sales_order_qty=100.5)
        live_child = _make_child(sales_order_qty=100)
        cache = _make_response([cache_child])
        live = _make_response([live_child])
        diffs = compare_responses(cache, live, "AK2510034")
        assert len(diffs) == 1
        assert diffs[0].severity == Severity.LOW

    def test_multiple_qty_diffs_on_same_child(self):
        """Multiple fields differ on the same child item."""
        cache_child = _make_child(
            sales_order_qty=200,
            pick_actual_qty=50,
        )
        live_child = _make_child(
            sales_order_qty=100,
            pick_actual_qty=30,
        )
        cache = _make_response([cache_child])
        live = _make_response([live_child])
        diffs = compare_responses(cache, live, "AK2510034")
        assert len(diffs) == 2
        fields = {d.field_name for d in diffs}
        assert "sales_order_qty" in fields
        assert "pick_actual_qty" in fields

    def test_empty_responses_no_diffs(self):
        cache = _make_response([])
        live = _make_response([])
        diffs = compare_responses(cache, live, "AK2510034")
        assert diffs == []

    def test_aux_attributes_distinguish_children(self):
        """Same material_code but different aux_attributes are separate items."""
        cache_child_red = _make_child(
            material_code="05.01.001", aux_attributes="Red", sales_order_qty=100
        )
        cache_child_blue = _make_child(
            material_code="05.01.001", aux_attributes="Blue", sales_order_qty=50
        )
        live_child_red = _make_child(
            material_code="05.01.001", aux_attributes="Red", sales_order_qty=100
        )
        live_child_blue = _make_child(
            material_code="05.01.001", aux_attributes="Blue", sales_order_qty=50
        )
        cache = _make_response([cache_child_red, cache_child_blue])
        live = _make_response([live_child_red, live_child_blue])
        diffs = compare_responses(cache, live, "AK2510034")
        assert diffs == []


# ---------------------------------------------------------------------------
# Tests: format_report
# ---------------------------------------------------------------------------

class TestFormatReport:
    def test_no_diffs(self):
        report = format_report({"AK2510034": []})
        assert "0 with differences" in report
        assert "0 critical" in report
        assert "[OK] AK2510034" in report

    def test_with_diffs(self):
        diff = Difference(
            mto_number="AK2510034",
            material_code="05.01.001",
            aux_attributes="",
            field_name="sales_order_qty",
            cache_value="200",
            live_value="100",
            severity=Severity.HIGH,
            description="sales_order_qty: cache=200 vs live=100",
        )
        report = format_report({"AK2510034": [diff]})
        assert "1 with differences" in report
        assert "[!!] AK2510034" in report
        assert "[HIGH]" in report

    def test_multiple_mtos(self):
        report = format_report({
            "AK001": [],
            "AK002": [
                Difference(
                    mto_number="AK002",
                    material_code="05.01.001",
                    aux_attributes="",
                    field_name="child_item",
                    cache_value=None,
                    live_value="present",
                    severity=Severity.CRITICAL,
                    description="Child missing from cache",
                )
            ],
        })
        assert "2 MTOs checked" in report
        assert "1 with differences" in report
        assert "1 critical" in report
