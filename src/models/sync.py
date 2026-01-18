"""Pydantic models for sync APIs."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SyncTriggerRequest(BaseModel):
    """Request to trigger manual sync."""

    model_config = ConfigDict(populate_by_name=True)

    days_back: int = Field(90, ge=1, le=365, description="Days to sync")
    chunk_days: int = Field(7, ge=1, le=30, description="Chunk size in days")
    force_full: bool = Field(False, alias="force", description="Force full refresh")


class SyncStatusResponse(BaseModel):
    """Sync status response."""

    status: str
    phase: str
    message: str
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    days_back: int
    progress: dict = Field(default_factory=dict)
    error: Optional[str] = None


class SyncConfigResponse(BaseModel):
    """Sync configuration response."""

    auto_sync_enabled: bool
    auto_sync_schedule: list[str]
    auto_sync_days: int
    manual_sync_default_days: int


class SyncConfigUpdateRequest(BaseModel):
    """Request to update sync configuration."""

    auto_sync_enabled: Optional[bool] = None
    auto_sync_days: Optional[int] = Field(None, ge=1, le=365)
    manual_sync_default_days: Optional[int] = Field(None, ge=1, le=365)
