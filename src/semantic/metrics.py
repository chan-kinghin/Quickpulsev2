"""Metric computation engine for the semantic layer.

Computes unified business metrics (fulfillment rate, completion status, etc.)
from material-type-specific Kingdee fields. Each material class maps its own
sparse fields to shared semantic roles (demand, fulfilled, picking).

Safety: uses getattr-based field lookup — never eval().
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Optional

from src.models.mto_status import MetricValue

logger = logging.getLogger(__name__)

ZERO = Decimal("0")
ONE = Decimal("1")


@dataclass
class MetricDefinition:
    """A single metric to compute (e.g., fulfillment_rate)."""

    name: str
    label: str
    format: str = "number"  # "number" | "percent" | "status"
    thresholds: dict[str, float] = field(default_factory=dict)


@dataclass
class MaterialClassMetrics:
    """Metric configuration for one material class.

    Maps semantic roles to ChildItem field names and declares
    which metrics to compute.
    """

    class_id: str
    pattern: Optional[re.Pattern] = None
    demand_field: Optional[str] = None
    fulfilled_field: Optional[str] = None
    picking_field: Optional[str] = None
    metrics: list[MetricDefinition] = field(default_factory=list)


class MetricEngine:
    """Computes business metrics for ChildItems based on material class config.

    Usage:
        engine = MetricEngine()
        engine.register_class(MaterialClassMetrics(
            class_id="finished_goods",
            demand_field="sales_order_qty",
            fulfilled_field="prod_instock_real_qty",
            metrics=[MetricDefinition(name="fulfillment_rate", label="入库完成率", format="percent")]
        ))
        metrics = engine.compute_for_item(child_item, "finished_goods")
    """

    def __init__(self) -> None:
        self._class_configs: dict[str, MaterialClassMetrics] = {}

    def register_class(self, config: MaterialClassMetrics) -> None:
        """Register metric configuration for a material class."""
        self._class_configs[config.class_id] = config

    @property
    def class_ids(self) -> list[str]:
        """Return all registered material class IDs."""
        return list(self._class_configs.keys())

    def detect_class_id(self, material_code: str) -> Optional[str]:
        """Detect material class from code using registered patterns."""
        for config in self._class_configs.values():
            if config.pattern and config.pattern.match(material_code):
                return config.class_id
        return None

    def compute_for_item(
        self, item, class_id: str
    ) -> Optional[dict[str, MetricValue]]:
        """Compute all metrics for a ChildItem given its material class.

        Args:
            item: A ChildItem (or any object with quantity fields as attributes).
            class_id: The material class identifier (e.g., "finished_goods").

        Returns:
            Dict of metric_name -> MetricValue, or None if class_id not registered.
        """
        config = self._class_configs.get(class_id)
        if not config:
            return None

        # Read semantic field values from item
        demand = _get_decimal(item, config.demand_field)
        fulfilled = _get_decimal(item, config.fulfilled_field)
        picking = _get_decimal(item, config.picking_field)

        logger.debug(
            "Computing metrics for class=%s: demand=%s, fulfilled=%s, picking=%s",
            class_id, demand, fulfilled, picking,
        )

        result: dict[str, MetricValue] = {}

        # Always produce unified aliases
        if config.demand_field:
            result["demand_qty"] = MetricValue(
                value=demand, label="需求量", format="number"
            )
        if config.fulfilled_field:
            result["fulfilled_qty"] = MetricValue(
                value=fulfilled, label="已完成量", format="number"
            )

        # Compute declared metrics
        for metric_def in config.metrics:
            mv = self._compute_metric(metric_def, demand, fulfilled, picking)
            if mv is not None:
                result[metric_def.name] = mv

        return result if result else None

    def _compute_metric(
        self,
        metric_def: MetricDefinition,
        demand: Decimal,
        fulfilled: Decimal,
        picking: Decimal,
    ) -> Optional[MetricValue]:
        """Compute a single metric from semantic field values."""
        name = metric_def.name

        if name == "fulfillment_rate":
            return self._compute_fulfillment_rate(metric_def, demand, fulfilled)
        elif name == "completion_status":
            return self._compute_completion_status(metric_def, demand, fulfilled)
        elif name == "over_pick_amount":
            return self._compute_over_pick(metric_def, demand, picking)
        else:
            logger.warning("Unknown metric: %s", name)
            return None

    def _compute_fulfillment_rate(
        self, metric_def: MetricDefinition, demand: Decimal, fulfilled: Decimal
    ) -> MetricValue:
        """Compute fulfillment_rate = fulfilled / demand."""
        if demand < ZERO:
            logger.warning("Negative demand value: %s, clamping to zero", demand)
            demand = ZERO
        if fulfilled < ZERO:
            logger.warning("Negative fulfilled value: %s, clamping to zero", fulfilled)
            fulfilled = ZERO

        if demand == ZERO:
            rate = ONE if fulfilled > ZERO else ZERO
        else:
            rate = fulfilled / demand

        # Determine status from thresholds
        status = self._rate_to_status(float(rate), metric_def.thresholds)

        return MetricValue(
            value=rate,
            label=metric_def.label,
            format=metric_def.format,
            status=status,
        )

    def _compute_completion_status(
        self, metric_def: MetricDefinition, demand: Decimal, fulfilled: Decimal
    ) -> MetricValue:
        """Compute completion_status from fulfillment ratio."""
        if demand < ZERO:
            logger.warning("Negative demand value: %s, clamping to zero", demand)
            demand = ZERO
        if fulfilled < ZERO:
            logger.warning("Negative fulfilled value: %s, clamping to zero", fulfilled)
            fulfilled = ZERO

        if demand == ZERO:
            rate = ONE if fulfilled > ZERO else ZERO
        else:
            rate = fulfilled / demand

        status = self._rate_to_status(float(rate), metric_def.thresholds)

        return MetricValue(
            value=None,
            label=metric_def.label,
            format="status",
            status=status,
        )

    def _compute_over_pick(
        self, metric_def: MetricDefinition, demand: Decimal, picking: Decimal
    ) -> MetricValue:
        """Compute over_pick_amount = picking - demand (only meaningful when > 0)."""
        if picking < ZERO:
            logger.warning("Negative picking value: %s, clamping to zero", picking)
            picking = ZERO
        if demand < ZERO:
            logger.warning("Negative demand value: %s, clamping to zero", demand)
            demand = ZERO

        over = picking - demand
        status = "warning" if over > ZERO else None

        return MetricValue(
            value=over if over > ZERO else ZERO,
            label=metric_def.label,
            format=metric_def.format,
            status=status,
        )

    @staticmethod
    def _rate_to_status(rate: float, thresholds: dict[str, float]) -> str:
        """Convert a rate to a status string based on thresholds.

        Thresholds example: {"completed": 1.0, "warning": 0.5}
        - rate >= completed_threshold → "completed"
        - rate >= warning_threshold → "in_progress"
        - rate > 0 → "in_progress"
        - rate == 0 → "not_started"
        """
        completed_threshold = thresholds.get("completed", 1.0)
        warning_threshold = thresholds.get("warning", 0.0)

        if rate >= completed_threshold:
            return "completed"
        elif rate > 0:
            if rate < warning_threshold:
                return "warning"
            return "in_progress"
        else:
            return "not_started"


def _get_decimal(obj, field_name: Optional[str]) -> Decimal:
    """Safely read a Decimal field from an object by name."""
    if not field_name:
        return ZERO
    val = getattr(obj, field_name, None)
    if val is None:
        return ZERO
    if isinstance(val, Decimal):
        return val
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError, TypeError):
        return ZERO
