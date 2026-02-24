"""Sync-related API endpoints."""

import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from src.api.middleware.rate_limit import limiter
from src.api.routers.auth import get_current_user
from src.models.sync import SyncConfigResponse, SyncConfigUpdateRequest, SyncTriggerRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sync", tags=["sync"])


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
