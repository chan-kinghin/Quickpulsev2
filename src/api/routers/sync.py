"""Sync-related API endpoints."""

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from src.api.middleware.rate_limit import limiter
from src.api.routers.auth import get_current_user
from src.models.sync import SyncConfigResponse, SyncConfigUpdateRequest, SyncTriggerRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sync", tags=["sync"])

# Chinese labels for the 9 cache tables surfaced on the freshness card.
_TABLE_LABELS = {
    "cached_production_orders": "生产订单",
    "cached_production_bom": "生产用料清单",
    "cached_purchase_orders": "采购订单",
    "cached_subcontracting_orders": "委外订单",
    "cached_production_receipts": "生产入库单",
    "cached_purchase_receipts": "采购入库单",
    "cached_material_picking": "生产领料单",
    "cached_sales_delivery": "销售出库单",
    "cached_sales_orders": "销售订单",
}


def _staleness_threshold_hours(
    schedule: list[str], grace_factor: float = 1.5, floor_hours: float = 6.0
) -> float:
    """Largest gap between consecutive scheduled syncs (wrapping midnight) × grace.

    Derived from the auto-sync schedule so the overnight no-sync window isn't
    misread as "stale". E.g. schedule 07/12/16/18 → max gap 13h (18:00→07:00) →
    ~19.5h threshold.
    """
    minutes = []
    for s in schedule:
        try:
            hh, mm = str(s).split(":")
            minutes.append(int(hh) * 60 + int(mm))
        except (ValueError, AttributeError):
            continue
    if not minutes:
        return 26.0  # no schedule known → ~1 day default
    minutes.sort()
    gaps = [b - a for a, b in zip(minutes, minutes[1:])]
    gaps.append(minutes[0] + 1440 - minutes[-1])  # wrap across midnight
    return max(floor_hours, round(max(gaps) / 60.0 * grace_factor, 1))


@router.post("/trigger")
@limiter.limit("2/minute")
async def trigger_sync(
    request: Request,
    body: SyncTriggerRequest,
    current_user: str = Depends(get_current_user),
):
    sync_service = request.app.state.sync_service

    if sync_service.is_running():
        raise HTTPException(status_code=409, detail="Sync task already running")

    task = asyncio.create_task(
        sync_service.run_sync(
            days_back=body.days_back,
            chunk_days=body.chunk_days,
            force_full=body.force_full,
        )
    )

    def _on_sync_done(t):
        if t.exception():
            logger.error("Sync failed: %s", t.exception())

    task.add_done_callback(_on_sync_done)
    request.app.state.sync_task = task
    return {"status": "sync_started", "days_back": body.days_back}


@router.get("/status")
@limiter.limit("30/minute")
async def get_sync_status(
    request: Request,
    current_user: str = Depends(get_current_user),
):
    progress = request.app.state.sync_progress.load()
    sync_service = request.app.state.sync_service
    is_running = sync_service.is_running()
    percent = progress.progress.get("percent", 0)
    records_synced = progress.progress.get("records_synced")

    return {
        "is_running": is_running,
        "progress": percent,
        "current_task": progress.message or progress.phase,
        "last_sync": progress.finished_at,
        "records_synced": records_synced,
        "status": progress.status,
        "phase": progress.phase,
        "message": progress.message,
        "started_at": progress.started_at,
        "finished_at": progress.finished_at,
        "days_back": progress.days_back,
        "error": progress.error,
    }


@router.get("/freshness")
@limiter.limit("30/minute")
async def get_data_freshness(
    request: Request,
    current_user: str = Depends(get_current_user),
):
    """Per-table data freshness — surfaces a silently-stalled cache table.

    Whole-table MAX(synced_at) + COUNT(*) (no per-MTO LIKE). The staleness
    threshold is derived from the auto-sync schedule so an overnight gap is not
    misread as stale. Any stale/empty table emits a `freshness_alert` WARNING
    (Loki-greppable) so the failure stops being silent.
    """
    cache_reader = request.app.state.cache_reader
    config = request.app.state.config
    schedule = list(getattr(config.sync.auto_sync, "schedule", []) or [])
    threshold_hours = _staleness_threshold_hours(schedule)

    facts = await cache_reader.table_freshness()
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

    tables = []
    stale = []
    for f in facts:
        last = f["last_synced_at"]
        if last is not None and last.tzinfo is not None:
            last = last.replace(tzinfo=None)
        if f["row_count"] == 0 or last is None:
            verdict, age_hours = "empty", None
        else:
            age_hours = round((now_utc - last).total_seconds() / 3600, 2)
            verdict = "stale" if age_hours > threshold_hours else "fresh"
        if verdict != "fresh":
            stale.append(f["table"])
        tables.append(
            {
                "table": f["table"],
                "label": _TABLE_LABELS.get(f["table"], f["table"]),
                "last_synced_at": f["last_synced_at"].isoformat()
                if f["last_synced_at"]
                else None,
                "row_count": f["row_count"],
                "age_hours": age_hours,
                "verdict": verdict,
            }
        )

    if stale:
        logger.warning(
            "freshness_alert event=freshness_alert stale_tables=%s threshold_hours=%.1f",
            ",".join(stale),
            threshold_hours,
        )

    rated = [t for t in tables if t["age_hours"] is not None]
    oldest = max(rated, key=lambda t: t["age_hours"], default=None)

    return {
        "tables": tables,
        "oldest": oldest,
        "stale_count": len(stale),
        "threshold_hours": threshold_hours,
        "checked_at": now_utc.isoformat(),
    }


@router.get("/config")
async def get_sync_config(
    api_request: Request,
    current_user: str = Depends(get_current_user),
) -> SyncConfigResponse:
    config = api_request.app.state.config
    return SyncConfigResponse(
        auto_sync_enabled=config.sync.auto_sync.enabled,
        auto_sync_schedule=config.sync.auto_sync.schedule,
        auto_sync_days=config.sync.auto_sync.days_back,
        manual_sync_default_days=config.sync.manual_sync.default_days,
    )


@router.put("/config")
async def update_sync_config(
    request: SyncConfigUpdateRequest,
    api_request: Request,
    current_user: str = Depends(get_current_user),
):
    config = api_request.app.state.config

    if request.auto_sync_days is not None:
        config.sync.auto_sync.days_back = request.auto_sync_days
    if request.auto_sync_enabled is not None:
        config.sync.auto_sync.enabled = request.auto_sync_enabled
    if request.manual_sync_default_days is not None:
        config.sync.manual_sync.default_days = request.manual_sync_default_days

    config.sync.save()
    return {"status": "config_updated"}


@router.get("/history")
async def get_sync_history(
    api_request: Request,
    limit: int = Query(10, ge=1, le=100),
    current_user: str = Depends(get_current_user),
):
    db = api_request.app.state.db
    rows = await db.execute_read(
        """
        SELECT started_at, finished_at, status, days_back, records_synced, error_message
        FROM sync_history
        ORDER BY started_at DESC
        LIMIT ?
        """,
        [limit],
    )
    return [
        {
            "started_at": row[0],
            "finished_at": row[1],
            "status": row[2],
            "days_back": row[3],
            "records_synced": row[4],
            "error_message": row[5],
        }
        for row in rows
    ]
