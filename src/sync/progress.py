"""Sync progress tracking utilities."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class SyncProgressData(BaseModel):
    status: str = "idle"
    phase: str = ""
    message: str = ""
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    days_back: int = 0
    progress: dict = Field(default_factory=dict)
    error: Optional[str] = None


class SyncProgress:
    """Persist sync progress to disk for API consumption."""

    def __init__(self, status_file: Path):
        self.status_file = status_file
        self._data = SyncProgressData()

    def start(self, days_back: int) -> None:
        self._data = SyncProgressData(
            status="running",
            phase="init",
            message="Starting sync...",
            started_at=datetime.now(timezone.utc),
            days_back=days_back,
        )
        self._save()

    def update(self, phase: str, message: str, **progress) -> None:
        self._data.phase = phase
        self._data.message = message
        self._data.progress.update(progress)
        self._save()

    def finish_success(self) -> None:
        self._data.status = "success"
        self._data.finished_at = datetime.now(timezone.utc)
        self._data.message = "Sync completed successfully"
        self._save()

    def finish_error(self, error: str) -> None:
        self._data.status = "error"
        self._data.finished_at = datetime.now(timezone.utc)
        self._data.error = error
        self._save()

    def _save(self) -> None:
        self.status_file.parent.mkdir(parents=True, exist_ok=True)
        with self.status_file.open("w", encoding="utf-8") as handle:
            json.dump(self._data.model_dump(mode="json"), handle, indent=2, default=str)

    def load(self) -> SyncProgressData:
        if self.status_file.exists():
            with self.status_file.open("r", encoding="utf-8") as handle:
                return SyncProgressData(**json.load(handle))
        return SyncProgressData()
