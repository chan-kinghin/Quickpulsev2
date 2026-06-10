"""Tests for src/mto_config/mto_config.py against the REAL config file.

Locks three audit fixes (2026-06-10 data-path family):
1. A semantic class is registered for material_type_id=3 (委外) — before,
   detect_class_id_by_type(3, False) returned None, so 委外 rows rendered
   "- (语义层数据不可用)" and were dropped by every completion-status filter.
2. fulfilled_field accepts a list (union of cross-source receipt fields).
3. finished_goods/self_made fulfilled 口径 includes purchase_stock_in_qty
   (sister-plant/bought-in receipts, Wave 6B).
"""

from decimal import Decimal

import pytest

from src.models.mto_status import ChildItem
from src.mto_config.mto_config import MTOConfig, SemanticConfig

CONFIG_PATH = "config/mto_config.json"


@pytest.fixture(scope="module")
def config() -> MTOConfig:
    return MTOConfig(CONFIG_PATH)


@pytest.fixture(scope="module")
def engine(config):
    return config.build_metric_engine()


def _make_child(**kwargs) -> ChildItem:
    defaults = dict(
        material_code="08.01.045",
        material_name="Test Item",
        specification="",
        aux_attributes="",
        material_type=3,
        material_type_name="委外",
    )
    defaults.update(kwargs)
    return ChildItem(**defaults)


class TestMaterialClassCoverage:
    """Constants test: material_classes must cover all routed type IDs."""

    def test_type_ids_cover_1_2_3(self, config):
        type_ids = {mc.material_type_id for mc in config.material_classes}
        assert type_ids >= {1, 2, 3}, (
            "material_classes must register a semantic class for every "
            "material_type_id produced by _bom_row_to_child (1=自制/成品, "
            "2=包材, 3=委外) — a missing ID silently disables 完成率 and "
            "drops those rows from status filters"
        )

    def test_subcontracted_class_registered(self, config):
        ids = [mc.id for mc in config.material_classes]
        assert "subcontracted" in ids

    def test_subcontracted_has_semantic_config(self, config):
        mc = next(c for c in config.material_classes if c.id == "subcontracted")
        assert mc.material_type_id == 3
        assert mc.is_finished_goods is False
        assert mc.semantic is not None
        # 委外 branch of _bom_row_to_child: demand in purchase_order_qty,
        # fulfilment in purchase_stock_in_qty, picking in pick_actual_qty.
        assert mc.semantic.demand_field == "purchase_order_qty"
        assert mc.semantic.fulfilled_fields == ["purchase_stock_in_qty"]
        assert mc.semantic.picking_field == "pick_actual_qty"

    def test_subcontracted_pattern_never_matches_codes(self, config):
        """委外 has no reliable code prefix — routing is category-based.

        The never-matching pattern guarantees code-prefix routing (a known
        anti-pattern in this tenant) can't claim it.
        """
        assert config.get_class_for_material("08.01.045") is None

    def test_existing_code_routing_unchanged(self, config):
        assert config.get_class_for_material("07.02.151").id == "finished_goods"
        assert config.get_class_for_material("05.01.001").id == "self_made"
        assert config.get_class_for_material("03.01.001").id == "purchased"


class TestSubcontractedDetection:
    """detect_class_id_by_type(3, False) must resolve to the new class."""

    def test_detect_type_3(self, engine):
        assert engine.detect_class_id_by_type(3, is_finished_goods=False) == "subcontracted"

    def test_subcontracted_child_gets_metrics(self, engine):
        child = _make_child(
            purchase_order_qty=Decimal("500"),
            purchase_stock_in_qty=Decimal("250"),
            pick_actual_qty=Decimal("0"),
        )
        class_id = engine.detect_class_id_by_type(
            child.material_type, child.is_finished_goods
        )
        assert class_id == "subcontracted"

        metrics = engine.compute_for_item(child, class_id)
        assert metrics is not None
        assert metrics["fulfillment_rate"].value == Decimal("0.5")
        assert metrics["fulfillment_rate"].status == "in_progress"
        assert metrics["completion_status"].status == "in_progress"
        assert "over_pick_amount" in metrics

    def test_subcontracted_over_pick(self, engine):
        child = _make_child(
            purchase_order_qty=Decimal("100"),
            purchase_stock_in_qty=Decimal("100"),
            pick_actual_qty=Decimal("130"),
        )
        metrics = engine.compute_for_item(child, "subcontracted")
        assert metrics["over_pick_amount"].value == Decimal("30")
        assert metrics["over_pick_amount"].status == "warning"


class TestFulfilledUnionConfig:
    """finished_goods/self_made fulfilled 口径 is a cross-source union."""

    def test_finished_goods_union_fields(self, config):
        mc = next(c for c in config.material_classes if c.id == "finished_goods")
        assert mc.semantic.fulfilled_fields == [
            "prod_instock_real_qty", "purchase_stock_in_qty",
        ]
        # Primary stays a str for legacy consumers (schema_mapping keys dicts on it)
        assert mc.semantic.fulfilled_field == "prod_instock_real_qty"

    def test_self_made_union_fields(self, config):
        mc = next(c for c in config.material_classes if c.id == "self_made")
        assert mc.semantic.fulfilled_fields == [
            "prod_instock_real_qty", "purchase_stock_in_qty",
        ]

    def test_purchased_stays_single_field(self, config):
        """STK purchase_receipt_real_qty mirrors PO FStockInQty — the
        purchased 口径 must stay single-source (no double count)."""
        mc = next(c for c in config.material_classes if c.id == "purchased")
        assert mc.semantic.fulfilled_fields == ["purchase_stock_in_qty"]

    def test_no_class_unions_purchase_receipt_real_qty(self, config):
        """DOUBLE-COUNT GUARD: purchase_receipt_real_qty (raw STK rows)
        mirrors PO-side FStockInQty and must never appear in any 口径."""
        for mc in config.material_classes:
            if mc.semantic:
                assert "purchase_receipt_real_qty" not in mc.semantic.fulfilled_fields

    def test_finished_goods_sister_plant_receipt_completes(self, engine):
        """Live-verified DK251003S 07.02.151: fully received via purchase
        receipts (prod=0, purchase=242, sales=242) → 100% completed,
        not 0% red / 未开始."""
        child = _make_child(
            material_code="07.02.151",
            material_type=1,
            material_type_name="成品",
            is_finished_goods=True,
            sales_order_qty=Decimal("242"),
            prod_instock_real_qty=Decimal("0"),
            purchase_stock_in_qty=Decimal("242"),
        )
        class_id = engine.detect_class_id_by_type(1, is_finished_goods=True)
        assert class_id == "finished_goods"
        metrics = engine.compute_for_item(child, class_id)
        assert metrics["fulfillment_rate"].value == Decimal("1")
        assert metrics["completion_status"].status == "completed"

    def test_self_made_union_noop_when_no_purchase_receipts(self, engine):
        child = _make_child(
            material_code="05.01.001",
            material_type=1,
            material_type_name="自制",
            prod_instock_must_qty=Decimal("200"),
            prod_instock_real_qty=Decimal("150"),
            purchase_stock_in_qty=Decimal("0"),
        )
        metrics = engine.compute_for_item(child, "self_made")
        assert metrics["fulfillment_rate"].value == Decimal("0.75")


class TestSemanticConfigNormalization:
    """SemanticConfig.from_dict accepts string OR list for fulfilled_field."""

    def test_string_normalizes_to_single_item_list(self):
        sem = SemanticConfig.from_dict({"fulfilled_field": "prod_instock_real_qty"})
        assert sem.fulfilled_field == "prod_instock_real_qty"
        assert sem.fulfilled_fields == ["prod_instock_real_qty"]

    def test_list_keeps_order_and_primary(self):
        sem = SemanticConfig.from_dict(
            {"fulfilled_field": ["prod_instock_real_qty", "purchase_stock_in_qty"]}
        )
        assert sem.fulfilled_field == "prod_instock_real_qty"
        assert sem.fulfilled_fields == [
            "prod_instock_real_qty", "purchase_stock_in_qty",
        ]

    def test_missing_field_normalizes_to_empty(self):
        sem = SemanticConfig.from_dict({})
        assert sem.fulfilled_field is None
        assert sem.fulfilled_fields == []


class TestSemanticFieldValidation:
    """build_metric_engine validates every field in a fulfilled union."""

    def test_invalid_field_in_union_raises(self, tmp_path):
        import json

        with open(CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
        data["material_classes"][0]["semantic"]["fulfilled_field"] = [
            "prod_instock_real_qty", "nonexistent_field",
        ]
        bad_path = tmp_path / "bad_config.json"
        bad_path.write_text(json.dumps(data), encoding="utf-8")

        with pytest.raises(ValueError, match="nonexistent_field"):
            MTOConfig(str(bad_path)).build_metric_engine()
