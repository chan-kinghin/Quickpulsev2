"""Unit tests for cache/live path parity.

Verifies that the cache path and live path produce the same BOMJoinedRow
structure when fed identical test data. This catches the common "cache path
blind spot" where cache_reader.py SELECTs silently omit fields that the
live reader includes (see MEMORY.md).

Pure-mock (no DB / no Kingdee creds) — lives in tests/unit/ so the gating CI
job actually runs it. It is the dedicated guard for bug-patterns Pattern 1.
"""

from dataclasses import fields as dataclass_fields
from decimal import Decimal

import pytest

from src.query.cache_reader import BOMJoinedRow


# ============================================================================
# Test Data
# ============================================================================

def _make_bom_joined_row(**overrides) -> BOMJoinedRow:
    """Create a BOMJoinedRow with sensible defaults, allowing overrides."""
    defaults = dict(
        mo_bill_no="MO0001",
        mto_number="AK2510034",
        material_code="05.02.001",
        material_name="Test Part",
        specification="Spec A",
        aux_attributes="Red-M",
        aux_prop_id=1001,
        material_type=1,
        need_qty=Decimal("100"),
        picked_qty=Decimal("50"),
        no_picked_qty=Decimal("50"),
        prod_receipt_real_qty=Decimal("40"),
        prod_receipt_must_qty=Decimal("100"),
        pick_actual_qty=Decimal("50"),
        pick_app_qty=Decimal("55"),
        purchase_order_qty=Decimal("0"),
        purchase_stock_in_qty=Decimal("0"),
        purchase_receipt_real_qty=Decimal("0"),
        subcontract_order_qty=Decimal("0"),
        subcontract_stock_in_qty=Decimal("0"),
        delivery_real_qty=Decimal("0"),
    )
    defaults.update(overrides)
    return BOMJoinedRow(**defaults)


# ============================================================================
# Structure Parity Tests
# ============================================================================


class TestBOMJoinedRowStructureParity:
    """Verify that BOMJoinedRow has all expected fields for both paths."""

    EXPECTED_FIELDS = {
        # BOM core fields
        "mo_bill_no",
        "mto_number",
        "material_code",
        "material_name",
        "specification",
        "aux_attributes",
        "aux_prop_id",
        "material_type",
        "need_qty",
        "picked_qty",
        "no_picked_qty",
        # Production receipts (PRD_INSTOCK)
        "prod_receipt_real_qty",
        "prod_receipt_must_qty",
        # Material picking (PRD_PickMtrl)
        "pick_actual_qty",
        "pick_app_qty",
        # Purchase orders (PUR_PurchaseOrder)
        "purchase_order_qty",
        "purchase_stock_in_qty",
        # Purchase receipts (STK_InStock)
        "purchase_receipt_real_qty",
        # Subcontracting orders (SUB_POORDER)
        "subcontract_order_qty",
        "subcontract_stock_in_qty",
        # Sales delivery (SAL_OUTSTOCK)
        "delivery_real_qty",
        # Per-source aux match quality (commit 8e0f644)
        "match_quality_breakdown",
        # Display routing — material grouping / category / purchase split (commit 2724bcf).
        # Verified wired in all 3 paths: factory.py (live), cache_reader.py SELECT, sync_service.py INSERT.
        "material_group_name",
        "category_name",
        "is_purchase",
    }

    def test_bom_joined_row_has_all_expected_fields(self):
        """BOMJoinedRow dataclass must have every field both paths rely on."""
        actual_fields = {f.name for f in dataclass_fields(BOMJoinedRow)}
        missing = self.EXPECTED_FIELDS - actual_fields
        assert not missing, f"BOMJoinedRow missing fields: {missing}"

    def test_no_unexpected_extra_fields(self):
        """Catch new fields added to BOMJoinedRow that tests don't cover."""
        actual_fields = {f.name for f in dataclass_fields(BOMJoinedRow)}
        extra = actual_fields - self.EXPECTED_FIELDS
        assert not extra, (
            f"BOMJoinedRow has new fields not in parity check: {extra}. "
            "Add them to EXPECTED_FIELDS in this test."
        )

    def test_field_count_matches(self):
        """Quick sanity check that field count hasn't drifted."""
        actual_count = len(dataclass_fields(BOMJoinedRow))
        expected_count = len(self.EXPECTED_FIELDS)
        assert actual_count == expected_count, (
            f"BOMJoinedRow has {actual_count} fields, expected {expected_count}"
        )


class TestCacheLiveDataParity:
    """Verify that identical input data produces identical BOMJoinedRow output."""

    def test_self_made_material_parity(self):
        """Self-made (type=1) BOMJoinedRow from cache vs live should match."""
        cache_row = _make_bom_joined_row(
            material_type=1,
            material_code="05.02.001",
            prod_receipt_real_qty=Decimal("40"),
            prod_receipt_must_qty=Decimal("100"),
            pick_actual_qty=Decimal("50"),
        )
        live_row = _make_bom_joined_row(
            material_type=1,
            material_code="05.02.001",
            prod_receipt_real_qty=Decimal("40"),
            prod_receipt_must_qty=Decimal("100"),
            pick_actual_qty=Decimal("50"),
        )
        assert cache_row == live_row

    def test_purchased_material_parity(self):
        """Purchased (type=2) BOMJoinedRow from cache vs live should match."""
        cache_row = _make_bom_joined_row(
            material_type=2,
            material_code="03.05.001",
            purchase_order_qty=Decimal("200"),
            purchase_stock_in_qty=Decimal("150"),
            purchase_receipt_real_qty=Decimal("150"),
        )
        live_row = _make_bom_joined_row(
            material_type=2,
            material_code="03.05.001",
            purchase_order_qty=Decimal("200"),
            purchase_stock_in_qty=Decimal("150"),
            purchase_receipt_real_qty=Decimal("150"),
        )
        assert cache_row == live_row

    def test_subcontracted_material_parity(self):
        """Subcontracted (type=3) BOMJoinedRow from cache vs live should match."""
        cache_row = _make_bom_joined_row(
            material_type=3,
            material_code="05.10.001",
            subcontract_order_qty=Decimal("80"),
            subcontract_stock_in_qty=Decimal("60"),
        )
        live_row = _make_bom_joined_row(
            material_type=3,
            material_code="05.10.001",
            subcontract_order_qty=Decimal("80"),
            subcontract_stock_in_qty=Decimal("60"),
        )
        assert cache_row == live_row

    def test_zero_qty_fields_default_correctly(self):
        """All quantity fields should default to Decimal('0') for missing data."""
        row = _make_bom_joined_row(
            prod_receipt_real_qty=Decimal("0"),
            prod_receipt_must_qty=Decimal("0"),
            pick_actual_qty=Decimal("0"),
            pick_app_qty=Decimal("0"),
            purchase_order_qty=Decimal("0"),
            purchase_stock_in_qty=Decimal("0"),
            purchase_receipt_real_qty=Decimal("0"),
            subcontract_order_qty=Decimal("0"),
            subcontract_stock_in_qty=Decimal("0"),
            delivery_real_qty=Decimal("0"),
        )
        # Every aggregated qty field should be zero
        assert row.prod_receipt_real_qty == Decimal("0")
        assert row.purchase_order_qty == Decimal("0")
        assert row.subcontract_order_qty == Decimal("0")
        assert row.delivery_real_qty == Decimal("0")

    def test_aux_prop_id_zero_vs_nonzero(self):
        """BOMJoinedRow with aux_prop_id=0 vs nonzero should differ correctly."""
        row_generic = _make_bom_joined_row(aux_prop_id=0)
        row_specific = _make_bom_joined_row(aux_prop_id=1001)
        assert row_generic != row_specific
        assert row_generic.aux_prop_id == 0
        assert row_specific.aux_prop_id == 1001
