"""Tests for src/semantic/enrichment.py — response enrichment."""

import re
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest

from src.models.mto_status import ChildItem, MTOStatusResponse, ParentItem
from src.semantic.enrichment import enrich_response
from src.semantic.metrics import (
    MaterialClassMetrics,
    MetricDefinition,
    MetricEngine,
)


def _make_child(code: str, **kwargs) -> ChildItem:
    """Helper to build a ChildItem."""
    defaults = dict(
        material_code=code,
        material_name="Test",
        specification="",
        aux_attributes="",
        material_type=1,
        material_type_name="成品",
    )
    defaults.update(kwargs)
    return ChildItem(**defaults)


def _make_response(children: list[ChildItem]) -> MTOStatusResponse:
    """Helper to build a response with given children."""
    return MTOStatusResponse(
        mto_number="AK2510001",
        parent=ParentItem(mto_number="AK2510001"),
        children=children,
        query_time=datetime(2025, 6, 1, 12, 0),
    )


def _make_engine() -> MetricEngine:
    """Build engine with all 3 classes for testing (with patterns)."""
    engine = MetricEngine()
    engine.register_class(MaterialClassMetrics(
        class_id="finished_goods",
        pattern=re.compile(r"^07\."),
        demand_field="sales_order_qty",
        fulfilled_field="prod_instock_real_qty",
        metrics=[
            MetricDefinition(name="fulfillment_rate", label="入库完成率", format="percent",
                             thresholds={"completed": 1.0, "warning": 0.5}),
        ],
    ))
    engine.register_class(MaterialClassMetrics(
        class_id="self_made",
        pattern=re.compile(r"^05\."),
        demand_field="prod_instock_must_qty",
        fulfilled_field="prod_instock_real_qty",
        picking_field="pick_actual_qty",
        metrics=[
            MetricDefinition(name="fulfillment_rate", label="入库完成率", format="percent",
                             thresholds={"completed": 1.0, "warning": 0.5}),
            MetricDefinition(name="over_pick_amount", label="超领量", format="number"),
        ],
    ))
    engine.register_class(MaterialClassMetrics(
        class_id="purchased",
        pattern=re.compile(r"^03\."),
        demand_field="purchase_order_qty",
        fulfilled_field="purchase_stock_in_qty",
        picking_field="pick_actual_qty",
        metrics=[
            MetricDefinition(name="fulfillment_rate", label="入库完成率", format="percent",
                             thresholds={"completed": 1.0, "warning": 0.5}),
        ],
    ))
    return engine


class TestEnrichResponse:
    """Test enrich_response mutates children with metrics."""

    def test_enriches_all_material_types(self):
        children = [
            _make_child("07.01.001", sales_order_qty=Decimal("100"), prod_instock_real_qty=Decimal("80")),
            _make_child("05.01.001", material_type_name="自制",
                        prod_instock_must_qty=Decimal("50"), prod_instock_real_qty=Decimal("50"),
                        pick_actual_qty=Decimal("30")),
            _make_child("03.01.001", material_type=2, material_type_name="包材",
                        purchase_order_qty=Decimal("200"), purchase_stock_in_qty=Decimal("100"),
                        pick_actual_qty=Decimal("80")),
        ]
        response = _make_response(children)
        engine = _make_engine()

        # Before enrichment
        for child in response.children:
            assert child.metrics is None

        enrich_response(response, engine)

        # After enrichment — all 3 children should have metrics
        for child in response.children:
            assert child.metrics is not None
            assert "fulfillment_rate" in child.metrics

        # Check specific values
        fg = response.children[0].metrics
        assert fg["fulfillment_rate"].value == Decimal("80") / Decimal("100")
        assert fg["fulfillment_rate"].status == "in_progress"

        sm = response.children[1].metrics
        assert sm["fulfillment_rate"].value == Decimal("1")
        assert sm["fulfillment_rate"].status == "completed"

        pur = response.children[2].metrics
        assert pur["fulfillment_rate"].value == Decimal("100") / Decimal("200")
        assert pur["fulfillment_rate"].status == "in_progress"

    def test_unknown_material_code_skipped(self):
        children = [
            _make_child("99.01.001"),  # no matching class
        ]
        response = _make_response(children)
        engine = _make_engine()

        enrich_response(response, engine)
        assert response.children[0].metrics is None

    def test_empty_children(self):
        response = _make_response([])
        engine = _make_engine()

        # Should not raise
        enrich_response(response, engine)
        assert response.children == []

    def test_backward_compatible_serialization(self):
        """Enriched response should serialize the same structure, just with metrics added."""
        children = [
            _make_child("07.01.001", sales_order_qty=Decimal("50"), prod_instock_real_qty=Decimal("50")),
        ]
        response = _make_response(children)
        engine = _make_engine()

        enrich_response(response, engine)

        data = response.model_dump(by_alias=True)
        child_data = data["child_items"][0]

        # Original fields still present
        assert "material_code" in child_data
        assert "sales_order_qty" in child_data

        # Metrics added
        assert "metrics" in child_data
        assert child_data["metrics"]["fulfillment_rate"]["status"] == "completed"

    def test_metric_computation_failure_continues(self):
        """If compute_for_item raises, enrichment continues for remaining items."""
        children = [
            _make_child("07.01.001", sales_order_qty=Decimal("100"), prod_instock_real_qty=Decimal("50")),
            _make_child("05.01.001", material_type_name="自制",
                        prod_instock_must_qty=Decimal("50"), prod_instock_real_qty=Decimal("50")),
        ]
        response = _make_response(children)
        engine = _make_engine()

        # Patch compute_for_item to raise on first call, succeed on second
        original_compute = engine.compute_for_item
        call_count = 0

        def flaky_compute(item, class_id):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Simulated failure")
            return original_compute(item, class_id)

        with patch.object(engine, "compute_for_item", side_effect=flaky_compute):
            enrich_response(response, engine)

        # First child: computation failed → metrics should be None
        assert response.children[0].metrics is None
        # Second child: computation succeeded → metrics should be set
        assert response.children[1].metrics is not None
        assert "fulfillment_rate" in response.children[1].metrics

    def test_engine_without_patterns_skips_all(self):
        """Engine with no patterns registered → no class detection → all skipped."""
        children = [
            _make_child("07.01.001", sales_order_qty=Decimal("100")),
        ]
        response = _make_response(children)
        engine = MetricEngine()  # empty engine, no patterns

        enrich_response(response, engine)
        assert response.children[0].metrics is None

    def test_mixed_known_and_unknown_codes(self):
        """Only items with matching patterns get enriched."""
        children = [
            _make_child("07.01.001", sales_order_qty=Decimal("100"), prod_instock_real_qty=Decimal("100")),
            _make_child("99.99.999"),  # unknown
            _make_child("03.01.001", material_type=2, material_type_name="包材",
                        purchase_order_qty=Decimal("50"), purchase_stock_in_qty=Decimal("25")),
        ]
        response = _make_response(children)
        engine = _make_engine()

        enrich_response(response, engine)

        assert response.children[0].metrics is not None  # 07 → enriched
        assert response.children[1].metrics is None       # 99 → skipped
        assert response.children[2].metrics is not None  # 03 → enriched
