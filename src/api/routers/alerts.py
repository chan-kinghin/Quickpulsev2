"""Anomaly alert endpoints — over-pick (超领) and over-ship (超发).

Cache-backed, deterministic SQL at mto+material grain. These deliberately
NEVER touch the aux-level BOM join (the historical silent-fallback path) —
every figure here is a hard sum the user can reconcile by hand.
See docs/PLAN_freshness_and_alerts_2026-05-29.md.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from src.api.middleware.rate_limit import limiter
from src.api.routers.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("/over-pick")
@limiter.limit("30/minute")
async def get_over_pick(
    request: Request,
    limit: int = Query(200, ge=1, le=1000),
    current_user: str = Depends(get_current_user),
):
    """Materials picked beyond their applied quantity (超领), summed per mto+material.

    `severe=true` flags 申请量=0 却实发>0 (picked without any application — a
    material-control black hole). `skipped_incomplete` counts mto+material pairs
    excluded because a picking row had NULL qty (never coerced to 0).
    """
    cache_reader = request.app.state.cache_reader
    try:
        return await cache_reader.get_over_pick_alerts(limit=limit)
    except Exception as exc:  # noqa: BLE001 - surface as 500 with context, never swallow
        logger.exception("over-pick alert query failed")
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/over-ship")
@limiter.limit("30/minute")
async def get_over_ship(
    request: Request,
    limit: int = Query(200, ge=1, le=1000),
    current_user: str = Depends(get_current_user),
):
    """Deliveries exceeding the sales-order quantity (超发), per mto+material.

    Open orders only (close_status != 'B'). Coarse mto+material grain — the UI
    must label results as "含辅助属性差异，需人工核" rather than implying an
    aux-exact match.
    """
    cache_reader = request.app.state.cache_reader
    try:
        return await cache_reader.get_over_ship_alerts(limit=limit)
    except Exception as exc:  # noqa: BLE001 - surface as 500 with context, never swallow
        logger.exception("over-ship alert query failed")
        raise HTTPException(status_code=500, detail="Internal server error") from exc
