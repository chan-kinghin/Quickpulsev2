"""Automatic sync scheduler."""

from __future__ import annotations

import asyncio
import threading
import time

import schedule

from src.config import SyncConfig
from src.sync.sync_service import SyncService


class SyncScheduler:
    """Schedule periodic sync runs using the schedule library."""

    def __init__(self, config: SyncConfig, sync_service: SyncService, loop: asyncio.AbstractEventLoop):
        self.config = config
        self.sync_service = sync_service
        self.loop = loop
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        """Start auto sync scheduler."""
        if not self.config.auto_sync.enabled:
            return

        schedule.clear()
        for time_str in self.config.auto_sync.schedule:
            schedule.every().day.at(time_str).do(self._sync_job)

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the scheduler."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
        schedule.clear()

    def _sync_job(self) -> None:
        self.config.reload()
        days_back = self.config.auto_sync.days_back
        chunk_days = self.config.performance.chunk_days
        if self.sync_service.is_running():
            return
        asyncio.run_coroutine_threadsafe(
            self.sync_service.run_sync(days_back=days_back, chunk_days=chunk_days),
            self.loop,
        )

    def _run_scheduler(self) -> None:
        while not self._stop_event.is_set():
            schedule.run_pending()
            time.sleep(1)
