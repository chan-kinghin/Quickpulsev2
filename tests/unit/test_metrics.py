"""Tests for src/semantic/metrics.py — MetricEngine computation."""

import re
from decimal import Decimal

import pytest

from src.models.mto_status import ChildItem, MetricValue
from src.semantic.metrics import (
    MaterialClassMetrics,
    MetricDefinition,
    MetricEngine,
)

ZERO = Decimal("0")


def _make_child(**kwargs) -> ChildItem:
    """Helper to build a ChildItem with minimal required fields."""
    defaults = dict(
        material_code="07.01.001",
        material_name="Test Item",
        specification="",
        aux_attributes="",
        material_type=1,
        material_type_name="成品",
    )
    defaults.update(kwargs)
    return ChildItem(**defaults)


def _make_engine_with_all_classes() -> MetricEngine:
    """Build an engine with all 3 material classes registered (with patterns)."""
    engine = MetricEngine()

    engine.register_class(MaterialClassMetrics(
        class_id="finished_goods",
        pattern=re.compile(r"^07\."),
        demand_field="sales_order_qty",
        fulfilled_field="prod_instock_real_qty",
        picking_field=None,
        metrics=[
            MetricDefinition(
                name="fulfillment_rate", label="入库完成率", format="percent",
                thresholds={"completed": 1.0, "warning": 0.5},
            ),
            MetricDefinition(
                name="completion_status", label="完成状态", format="status",
                thresholds={"completed": 1.0, "warning": 0.5},
            ),
        ],
    ))

    engine.register_class(MaterialClassMetrics(
        class_id="self_made",
        pattern=re.compile(r"^05\."),
        demand_field="prod_instock_must_qty",
        fulfilled_field="prod_instock_real_qty",
        picking_field="pick_actual_qty",
        metrics=[
            MetricDefinition(
                name="fulfillment_rate", label="入库完成率", format="percent",
                thresholds={"completed": 1.0, "warning": 0.5},
            ),
            MetricDefinition(
                name="completion_status", label="完成状态", format="status",
                thresholds={"completed": 1.0, "warning": 0.5},
            ),
            MetricDefinition(
                name="over_pick_amount", label="超领量", format="number",
            ),
        ],
    ))

    engine.register_class(MaterialClassMetrics(
        class_id="purchased",
        pattern=re.compile(r"^03\."),
        demand_field="purchase_order_qty",
        fulfilled_field="purchase_stock_in_qty",
        picking_field="pick_actual_qty",
        metrics=[
            MetricDefinition(
                name="fulfillment_rate", label="入库完成率", format="percent",
                thresholds={"completed": 1.0, "warning": 0.5},
            ),
            MetricDefinition(
                name="completion_status", label="完成状态", format="status",
                thresholds={"completed": 1.0, "warning": 0.5},
            ),
            MetricDefinition(
                name="over_pick_amount", label="超领量", format="number",
            ),
        ],
    ))

    return engine


class TestEngineClassDetection:
    """Test MetricEngine.detect_class_id — config-driven class detection."""

    def test_finished_goods(self):
        engine = _make_engine_with_all_classes()
        assert engine.detect_class_id("07.01.001") == "finished_goods"
        assert engine.detect_class_id("07.99.999") == "finished_goods"

    def test_self_made(self):
        engine = _make_engine_with_all_classes()
        assert engine.detect_class_id("05.01.001") == "self_made"

    def test_purchased(self):
        engine = _make_engine_with_all_classes()
        assert engine.detect_class_id("03.01.001") == "purchased"

    def test_unknown_code_returns_none(self):
        engine = _make_engine_with_all_classes()
        assert engine.detect_class_id("99.01.001") is None
        assert engine.detect_class_id("") is None

    def test_empty_engine_returns_none(self):
        engine = MetricEngine()
        assert engine.detect_class_id("07.01.001") is None

    def test_engine_without_patterns_returns_none(self):
        """Classes registered without patterns cannot be detected."""
        engine = MetricEngine()
        engine.register_class(MaterialClassMetrics(
            class_id="finished_goods",
            demand_field="sales_order_qty",
        ))
        assert engine.detect_class_id("07.01.001") is None


class TestMetricEngine:
    """Test MetricEngine.compute_for_item for all material types."""

    def test_unknown_class_returns_none(self):
        engine = MetricEngine()
        child = _make_child()
        assert engine.compute_for_item(child, "unknown_class") is None

    def test_registered_classes(self):
        engine = _make_engine_with_all_classes()
        assert sorted(engine.class_ids) == ["finished_goods", "purchased", "self_made"]

    # --- finished_goods (07.xx) ---

    def test_finished_goods_full_fulfillment(self):
        engine = _make_engine_with_all_classes()
        child = _make_child(
            material_code="07.01.001",
            sales_order_qty=Decimal("100"),
            prod_instock_real_qty=Decimal("100"),
        )
        metrics = engine.compute_for_item(child, "finished_goods")
        assert metrics is not None

        # Unified aliases
        assert metrics["demand_qty"].value == Decimal("100")
        assert metrics["fulfilled_qty"].value == Decimal("100")

        # Fulfillment rate = 100%
        assert metrics["fulfillment_rate"].value == Decimal("1")
        assert metrics["fulfillment_rate"].format == "percent"
        assert metrics["fulfillment_rate"].status == "completed"

        # Completion status
        assert metrics["completion_status"].status == "completed"

    def test_finished_goods_partial_fulfillment(self):
        engine = _make_engine_with_all_classes()
        child = _make_child(
            sales_order_qty=Decimal("200"),
            prod_instock_real_qty=Decimal("120"),
        )
        metrics = engine.compute_for_item(child, "finished_goods")

        rate = metrics["fulfillment_rate"]
        assert rate.value == Decimal("120") / Decimal("200")
        assert rate.status == "in_progress"

    def test_finished_goods_zero_demand(self):
        engine = _make_engine_with_all_classes()
        child = _make_child(
            sales_order_qty=ZERO,
            prod_instock_real_qty=ZERO,
        )
        metrics = engine.compute_for_item(child, "finished_goods")
        assert metrics["fulfillment_rate"].value == ZERO
        assert metrics["fulfillment_rate"].status == "not_started"

    def test_finished_goods_zero_demand_with_fulfilled(self):
        engine = _make_engine_with_all_classes()
        child = _make_child(
            sales_order_qty=ZERO,
            prod_instock_real_qty=Decimal("10"),
        )
        metrics = engine.compute_for_item(child, "finished_goods")
        # Edge case: demand=0 but fulfilled>0 → rate=1 (completed)
        assert metrics["fulfillment_rate"].value == Decimal("1")
        assert metrics["fulfillment_rate"].status == "completed"

    # --- self_made (05.xx) ---

    def test_self_made_with_over_pick(self):
        engine = _make_engine_with_all_classes()
        child = _make_child(
            material_code="05.01.001",
            material_type=1,
            material_type_name="自制",
            prod_instock_must_qty=Decimal("50"),
            prod_instock_real_qty=Decimal("30"),
            pick_actual_qty=Decimal("80"),  # picked more than demand
        )
        metrics = engine.compute_for_item(child, "self_made")

        # Fulfillment rate
        assert metrics["fulfillment_rate"].value == Decimal("30") / Decimal("50")
        assert metrics["fulfillment_rate"].status == "in_progress"

        # Over-pick detection
        over_pick = metrics["over_pick_amount"]
        assert over_pick.value == Decimal("30")  # 80 - 50
        assert over_pick.status == "warning"

    def test_self_made_no_over_pick(self):
        engine = _make_engine_with_all_classes()
        child = _make_child(
            material_code="05.01.001",
            material_type=1,
            material_type_name="自制",
            prod_instock_must_qty=Decimal("100"),
            prod_instock_real_qty=Decimal("60"),
            pick_actual_qty=Decimal("50"),
        )
        metrics = engine.compute_for_item(child, "self_made")
        assert metrics["over_pick_amount"].value == ZERO
        assert metrics["over_pick_amount"].status is None

    # --- purchased (03.xx) ---

    def test_purchased_full_fulfillment(self):
        engine = _make_engine_with_all_classes()
        child = _make_child(
            material_code="03.01.001",
            material_type=2,
            material_type_name="包材",
            purchase_order_qty=Decimal("500"),
            purchase_stock_in_qty=Decimal("500"),
            pick_actual_qty=Decimal("400"),
        )
        metrics = engine.compute_for_item(child, "purchased")

        assert metrics["fulfillment_rate"].value == Decimal("1")
        assert metrics["fulfillment_rate"].status == "completed"
        assert metrics["over_pick_amount"].value == ZERO

    def test_purchased_below_warning_threshold(self):
        engine = _make_engine_with_all_classes()
        child = _make_child(
            material_code="03.01.001",
            material_type=2,
            material_type_name="包材",
            purchase_order_qty=Decimal("1000"),
            purchase_stock_in_qty=Decimal("100"),
            pick_actual_qty=ZERO,
        )
        metrics = engine.compute_for_item(child, "purchased")

        rate = metrics["fulfillment_rate"]
        assert rate.value == Decimal("100") / Decimal("1000")
        assert rate.status == "warning"  # 10% < 50% warning threshold


class TestNegativeValueClamping:
    """Test that negative demand/fulfilled/picking values are clamped to zero."""

    def test_negative_demand_clamped(self):
        engine = _make_engine_with_all_classes()
        child = _make_child(
            sales_order_qty=Decimal("-100"),
            prod_instock_real_qty=Decimal("50"),
        )
        metrics = engine.compute_for_item(child, "finished_goods")
        # Negative demand clamped to 0 → rate=1 (fulfilled>0, demand=0)
        assert metrics["fulfillment_rate"].value == Decimal("1")
        assert metrics["fulfillment_rate"].status == "completed"

    def test_negative_fulfilled_clamped(self):
        engine = _make_engine_with_all_classes()
        child = _make_child(
            sales_order_qty=Decimal("100"),
            prod_instock_real_qty=Decimal("-50"),
        )
        metrics = engine.compute_for_item(child, "finished_goods")
        # Negative fulfilled clamped to 0 → rate=0/100=0
        assert metrics["fulfillment_rate"].value == ZERO
        assert metrics["fulfillment_rate"].status == "not_started"

    def test_negative_picking_clamped(self):
        engine = _make_engine_with_all_classes()
        child = _make_child(
            material_code="05.01.001",
            material_type=1,
            material_type_name="自制",
            prod_instock_must_qty=Decimal("100"),
            prod_instock_real_qty=Decimal("50"),
            pick_actual_qty=Decimal("-30"),
        )
        metrics = engine.compute_for_item(child, "self_made")
        # Negative picking clamped to 0 → over_pick = 0 - 100 < 0 → clamped to 0
        assert metrics["over_pick_amount"].value == ZERO
        assert metrics["over_pick_amount"].status is None

    def test_both_negative_clamped(self):
        engine = _make_engine_with_all_classes()
        child = _make_child(
            sales_order_qty=Decimal("-10"),
            prod_instock_real_qty=Decimal("-5"),
        )
        metrics = engine.compute_for_item(child, "finished_goods")
        # Both clamped to 0 → rate=0
        assert metrics["fulfillment_rate"].value == ZERO
        assert metrics["fulfillment_rate"].status == "not_started"


class TestOverPickBoundaries:
    """Test over-pick edge cases."""

    def test_pick_exactly_equals_demand(self):
        engine = _make_engine_with_all_classes()
        child = _make_child(
            material_code="05.01.001",
            material_type=1,
            material_type_name="自制",
            prod_instock_must_qty=Decimal("100"),
            prod_instock_real_qty=Decimal("80"),
            pick_actual_qty=Decimal("100"),
        )
        metrics = engine.compute_for_item(child, "self_made")
        # pick == demand → over_pick = 0 → no warning
        assert metrics["over_pick_amount"].value == ZERO
        assert metrics["over_pick_amount"].status is None

    def test_pick_slightly_above_demand(self):
        engine = _make_engine_with_all_classes()
        child = _make_child(
            material_code="05.01.001",
            material_type=1,
            material_type_name="自制",
            prod_instock_must_qty=Decimal("100"),
            prod_instock_real_qty=Decimal("80"),
            pick_actual_qty=Decimal("100.01"),
        )
        metrics = engine.compute_for_item(child, "self_made")
        assert metrics["over_pick_amount"].value == Decimal("0.01")
        assert metrics["over_pick_amount"].status == "warning"

    def test_zero_demand_with_picking(self):
        engine = _make_engine_with_all_classes()
        child = _make_child(
            material_code="05.01.001",
            material_type=1,
            material_type_name="自制",
            prod_instock_must_qty=ZERO,
            prod_instock_real_qty=ZERO,
            pick_actual_qty=Decimal("50"),
        )
        metrics = engine.compute_for_item(child, "self_made")
        assert metrics["over_pick_amount"].value == Decimal("50")
        assert metrics["over_pick_amount"].status == "warning"


class TestStatusThresholdBoundaries:
    """Test exact boundary conditions for _rate_to_status."""

    def test_rate_exactly_at_completed_threshold(self):
        engine = _make_engine_with_all_classes()
        child = _make_child(
            sales_order_qty=Decimal("100"),
            prod_instock_real_qty=Decimal("100"),
        )
        metrics = engine.compute_for_item(child, "finished_goods")
        assert metrics["fulfillment_rate"].status == "completed"

    def test_rate_just_below_completed_threshold(self):
        engine = _make_engine_with_all_classes()
        child = _make_child(
            sales_order_qty=Decimal("1000"),
            prod_instock_real_qty=Decimal("999"),
        )
        metrics = engine.compute_for_item(child, "finished_goods")
        assert metrics["fulfillment_rate"].status == "in_progress"

    def test_rate_exactly_at_warning_threshold(self):
        engine = _make_engine_with_all_classes()
        child = _make_child(
            sales_order_qty=Decimal("100"),
            prod_instock_real_qty=Decimal("50"),
        )
        metrics = engine.compute_for_item(child, "finished_goods")
        # 50% == warning threshold → in_progress (not warning, since rate >= warning)
        assert metrics["fulfillment_rate"].status == "in_progress"

    def test_rate_just_below_warning_threshold(self):
        engine = _make_engine_with_all_classes()
        child = _make_child(
            sales_order_qty=Decimal("1000"),
            prod_instock_real_qty=Decimal("499"),
        )
        metrics = engine.compute_for_item(child, "finished_goods")
        # 49.9% < 50% warning threshold → warning
        assert metrics["fulfillment_rate"].status == "warning"

    def test_completion_status_matches_fulfillment_rate(self):
        """completion_status should use same threshold logic as fulfillment_rate."""
        engine = _make_engine_with_all_classes()
        child = _make_child(
            sales_order_qty=Decimal("100"),
            prod_instock_real_qty=Decimal("75"),
        )
        metrics = engine.compute_for_item(child, "finished_goods")
        assert metrics["fulfillment_rate"].status == metrics["completion_status"].status


class TestMetricValueSerialization:
    """Test MetricValue serializes correctly on ChildItem."""

    def test_metrics_none_by_default(self):
        child = _make_child()
        assert child.metrics is None

        data = child.model_dump(by_alias=True)
        assert data["metrics"] is None

    def test_metrics_dict_serializes(self):
        child = _make_child()
        child.metrics = {
            "fulfillment_rate": MetricValue(
                value=Decimal("0.75"),
                label="入库完成率",
                format="percent",
                status="in_progress",
            ),
        }

        data = child.model_dump(by_alias=True)
        assert "metrics" in data
        assert data["metrics"]["fulfillment_rate"]["value"] == Decimal("0.75")
        assert data["metrics"]["fulfillment_rate"]["status"] == "in_progress"

    def test_metrics_json_round_trip(self):
        child = _make_child()
        child.metrics = {
            "demand_qty": MetricValue(value=Decimal("100"), label="需求量"),
            "fulfillment_rate": MetricValue(
                value=Decimal("0.5"), label="完成率", format="percent", status="in_progress",
            ),
        }

        json_str = child.model_dump_json(by_alias=True)
        assert '"metrics"' in json_str
        assert '"fulfillment_rate"' in json_str

    def test_completion_status_none_value_serializes(self):
        """completion_status has value=None but status set — should serialize cleanly."""
        child = _make_child()
        child.metrics = {
            "completion_status": MetricValue(
                value=None, label="完成状态", format="status", status="completed",
            ),
        }

        data = child.model_dump(by_alias=True)
        assert data["metrics"]["completion_status"]["value"] is None
        assert data["metrics"]["completion_status"]["status"] == "completed"

    def test_over_pick_amount_serializes(self):
        child = _make_child()
        child.metrics = {
            "over_pick_amount": MetricValue(
                value=Decimal("30"), label="超领量", format="number", status="warning",
            ),
        }

        data = child.model_dump(by_alias=True)
        assert data["metrics"]["over_pick_amount"]["value"] == Decimal("30")
        assert data["metrics"]["over_pick_amount"]["status"] == "warning"

    def test_over_pick_zero_serializes(self):
        child = _make_child()
        child.metrics = {
            "over_pick_amount": MetricValue(
                value=ZERO, label="超领量", format="number", status=None,
            ),
        }

        data = child.model_dump(by_alias=True)
        assert data["metrics"]["over_pick_amount"]["value"] == ZERO
        assert data["metrics"]["over_pick_amount"]["status"] is None


class TestUnknownMetricName:
    """Test that unknown metric names are handled gracefully."""

    def test_unknown_metric_name_returns_none(self):
        engine = MetricEngine()
        engine.register_class(MaterialClassMetrics(
            class_id="test_class",
            demand_field="sales_order_qty",
            metrics=[
                MetricDefinition(name="nonexistent_metric", label="Test"),
            ],
        ))
        child = _make_child(sales_order_qty=Decimal("100"))
        metrics = engine.compute_for_item(child, "test_class")
        # Unknown metric skipped, but demand_qty still computed
        assert "demand_qty" in metrics
        assert "nonexistent_metric" not in metrics
