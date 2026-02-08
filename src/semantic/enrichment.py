"""Response enrichment — attaches computed metrics to ChildItems.

Pure function: iterates children, determines material class,
computes metrics via MetricEngine, and attaches to child.metrics.
"""

from __future__ import annotations

import logging

from src.models.mto_status import MTOStatusResponse
from src.semantic.metrics import MetricEngine

logger = logging.getLogger(__name__)


def enrich_response(response: MTOStatusResponse, engine: MetricEngine) -> None:
    """Enrich an MTOStatusResponse by computing metrics for each child item.

    Mutates response in-place by setting child.metrics for each child
    whose material class has registered metrics.

    Args:
        response: The response to enrich.
        engine: MetricEngine with registered material class configs.
    """
    enriched = 0
    skipped = 0
    total = len(response.children)

    for child in response.children:
        class_id = engine.detect_class_id(child.material_code)
        if not class_id:
            skipped += 1
            continue

        try:
            metrics = engine.compute_for_item(child, class_id)
        except Exception:
            logger.warning(
                "Metric computation failed for material_code=%s class_id=%s",
                child.material_code,
                class_id,
                exc_info=True,
            )
            child.metrics = None
            skipped += 1
            continue

        if metrics:
            child.metrics = metrics
            enriched += 1
            logger.debug(
                "Enriched material_code=%s class_id=%s metrics_count=%d",
                child.material_code,
                class_id,
                len(metrics),
            )
        else:
            skipped += 1

    logger.info(
        "Enrichment complete: %d enriched, %d skipped, %d total",
        enriched,
        skipped,
        total,
    )
