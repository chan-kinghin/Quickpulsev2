"""Anomaly alert endpoints — over-pick (超领) and over-ship (超发).

Cache-backed, deterministic SQL at mto+material grain. These deliberately
NEVER touch the aux-level BOM join (the historical silent-fallback path) —
every figure here is a hard sum the user can reconcile by hand.
See docs/PLAN_freshness_and_alerts_2026-05-29.md.

Sample orders (样品单, order_type=Y, e.g. AY/DY prefixes) are excluded by
default: their over-pick/over-ship is expected noise (~40 historical rows) that
drowns the real signal. The exclusion is applied here in the router — NOT in the
cache reader — so the response can always report ``excluded_sample_count``,
preventing the filter from becoming a silent failure. Pass
``include_samples=true`` to keep them; the count is still reported either way.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from src.api.middleware.rate_limit import limiter
from src.api.routers.auth import get_current_user
from src.query.mto_classifier import classify_mto

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


def _filter_samples(result: dict, include_samples: bool) -> dict:
    """Drop 样品单 (order_type=Y) alerts unless explicitly included.

    Always sets ``excluded_sample_count`` to the number of sample rows found,
    regardless of ``include_samples`` — so a zero count proves the filter ran
    rather than silently skipping. ``alerts`` is rebuilt only when excluding.
    """
    alerts = result.get("alerts", [])
    sample_count = sum(
        1 for a in alerts if classify_mto(a.get("mto_number")).is_sample
    )
    if not include_samples and sample_count:
        result["alerts"] = [
            a for a in alerts if not classify_mto(a.get("mto_number")).is_sample
        ]
    result["excluded_sample_count"] = sample_count
    return result


@router.get("/over-pick")
@limiter.limit("30/minute")
async def get_over_pick(
    request: Request,
    limit: int = Query(200, ge=1, le=1000),
    include_samples: bool = Query(False),
    current_user: str = Depends(get_current_user),
):
    """Materials picked beyond their applied quantity (超领), summed per mto+material.

    `severe=true` flags 申请量=0 却实发>0 (picked without any application — a
    material-control black hole). `skipped_incomplete` counts mto+material pairs
    excluded because a picking row had NULL qty (never coerced to 0).
    `excluded_sample_count` reports how many 样品单 (order_type=Y) rows were
    dropped (or would have been, when `include_samples=true`).
    """
    cache_reader = request.app.state.cache_reader
    try:
        result = await cache_reader.get_over_pick_alerts(limit=limit)
        return _filter_samples(result, include_samples)
    except Exception as exc:  # noqa: BLE001 - surface as 500 with context, never swallow
        logger.exception("over-pick alert query failed")
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/over-ship")
@limiter.limit("30/minute")
async def get_over_ship(
    request: Request,
    limit: int = Query(200, ge=1, le=1000),
    include_samples: bool = Query(False),
    current_user: str = Depends(get_current_user),
):
    """Deliveries exceeding the sales-order quantity (超发), per mto+material.

    Open orders only (close_status != 'B'). Coarse mto+material grain — the UI
    must label results as "含辅助属性差异，需人工核" rather than implying an
    aux-exact match. `excluded_sample_count` reports how many 样品单
    (order_type=Y) rows were dropped (or would have been, when
    `include_samples=true`).
    """
    cache_reader = request.app.state.cache_reader
    try:
        result = await cache_reader.get_over_ship_alerts(limit=limit)
        return _filter_samples(result, include_samples)
    except Exception as exc:  # noqa: BLE001 - surface as 500 with context, never swallow
        logger.exception("over-ship alert query failed")
        raise HTTPException(status_code=500, detail="Internal server error") from exc
