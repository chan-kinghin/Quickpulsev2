"""Synchronization service for QuickPulse data cache."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable, Iterator, Optional

from src.database.connection import Database
from src.exceptions import SyncError
from src.sync.progress import SyncProgress

logger = logging.getLogger(__name__)

# Cache table names
TABLE_ORDERS = "cached_production_orders"
TABLE_BOM = "cached_production_bom"

# Sync performance settings
BOM_BATCH_SIZE = 50  # Number of bill numbers per batched query
BOM_QUERY_TIMEOUT = 60  # Seconds timeout per batch query
BOM_MAX_RETRIES = 2  # Retries for failed batches


@dataclass
class SyncResult:
    """Result of a sync operation."""

    status: str
    days_back: int
    records_synced: int
    started_at: datetime
    finished_at: datetime


def date_chunks(
    start: date, end: date, chunk_days: int
) -> Iterator[tuple[date, date]]:
    """Generate date range chunks for batch processing."""
    current = start
    while current <= end:
        chunk_end = min(current + timedelta(days=chunk_days - 1), end)
        yield current, chunk_end
        current = chunk_end + timedelta(days=1)


def model_to_json(model) -> str:
    """Serialize a Pydantic model to JSON string."""
    return json.dumps(model.model_dump(mode="json"), ensure_ascii=False)


class SyncService:
    """Coordinate data synchronization into the cache."""

    def __init__(self, readers: dict, db: Database, progress: SyncProgress):
        self.readers = readers
        self.db = db
        self.progress = progress
        self._lock = asyncio.Lock()
        self._running = False

    def is_running(self) -> bool:
        return self._running or self._lock.locked()

    async def run_sync(
        self, days_back: int = 90, chunk_days: int = 7, force_full: bool = False
    ) -> SyncResult:
        if self.is_running():
            raise SyncError("Sync task already running")

        async with self._lock:
            self._running = True
            started_at = datetime.now()
            records_synced = 0

            try:
                if force_full:
                    await self._clear_cache()

                self.progress.start(days_back)
                records_synced = await self._sync_date_range(
                    days_back, chunk_days
                )
                self.progress.finish_success()

                result = SyncResult(
                    status="success",
                    days_back=days_back,
                    records_synced=records_synced,
                    started_at=started_at,
                    finished_at=datetime.now(),
                )
                await self._record_history(result)
                return result

            except Exception as exc:
                self.progress.finish_error(str(exc))
                result = SyncResult(
                    status="error",
                    days_back=days_back,
                    records_synced=records_synced,
                    started_at=started_at,
                    finished_at=datetime.now(),
                )
                await self._record_history(result, error_message=str(exc))
                raise
            finally:
                self._running = False

    async def _sync_date_range(self, days_back: int, chunk_days: int) -> int:
        """Sync all chunks in date range."""
        end_date = date.today()
        start_date = end_date - timedelta(days=days_back)
        chunks = list(date_chunks(start_date, end_date, chunk_days))
        total = max(len(chunks), 1)
        records_synced = 0

        for i, (chunk_start, chunk_end) in enumerate(chunks, start=1):
            self.progress.update(
                "chunk",
                f"Syncing {chunk_start} to {chunk_end}",
                chunk_index=i,
                total_chunks=total,
                percent=int((i / total) * 100),
            )
            records_synced += await self._sync_chunk(chunk_start, chunk_end)

        self.progress.update("finalize", "Finalizing sync", records_synced=records_synced)
        return records_synced

    async def _sync_chunk(self, start_date: date, end_date: date) -> int:
        """Sync a single date chunk."""
        count = 0

        orders = await self._sync_orders(start_date, end_date)
        count += len(orders)

        if orders:
            count += await self._sync_bom_for_orders(orders)

        return count

    async def _sync_orders(self, start_date: date, end_date: date) -> list:
        """Fetch and cache production orders for date range."""
        if "production_order" not in self.readers:
            return []

        orders = await self.readers["production_order"].fetch_by_date_range(
            start_date, end_date
        )
        await self._upsert_production_orders(orders)
        self.progress.update(
            "prd_mo", f"Synced {len(orders)} production orders", prd_mo_count=len(orders)
        )
        return orders

    async def _sync_bom_for_orders(self, orders: list) -> int:
        """Fetch and cache BOM entries for given orders using batched queries.

        Instead of making N individual API calls (one per order), this method
        batches bill numbers into groups and uses IN queries for efficiency.
        Each batch has a timeout to prevent hanging on slow API responses.
        """
        if "production_bom" not in self.readers:
            return 0

        bill_nos = [order.bill_no for order in orders]
        if not bill_nos:
            return 0

        # Split into batches for efficient querying
        batches = [
            bill_nos[i : i + BOM_BATCH_SIZE]
            for i in range(0, len(bill_nos), BOM_BATCH_SIZE)
        ]

        all_bom_entries = []
        failed_batches = 0

        for batch_idx, batch in enumerate(batches, start=1):
            self.progress.update(
                "prd_ppbom",
                f"Fetching BOM batch {batch_idx}/{len(batches)} ({len(batch)} orders)",
                bom_batch=batch_idx,
                bom_total_batches=len(batches),
            )

            # Try to fetch this batch with timeout and retries
            batch_entries = await self._fetch_bom_batch_with_retry(batch)
            if batch_entries is not None:
                all_bom_entries.extend(batch_entries)
            else:
                failed_batches += 1
                logger.warning(
                    "BOM batch %d/%d failed after retries, skipping %d orders",
                    batch_idx, len(batches), len(batch)
                )

        # Upsert all successfully fetched entries
        await self._upsert_production_bom(all_bom_entries)

        status_msg = f"Synced {len(all_bom_entries)} BOM entries"
        if failed_batches > 0:
            status_msg += f" ({failed_batches} batches failed)"

        self.progress.update(
            "prd_ppbom", status_msg, prd_ppbom_count=len(all_bom_entries)
        )
        return len(all_bom_entries)

    async def _fetch_bom_batch_with_retry(self, bill_nos: list[str]) -> list | None:
        """Fetch BOM entries for a batch of bill numbers with timeout and retries.

        Returns None if all retries fail, allowing sync to continue with other batches.
        """
        reader = self.readers["production_bom"]

        for attempt in range(BOM_MAX_RETRIES + 1):
            try:
                entries = await asyncio.wait_for(
                    reader.fetch_by_bill_nos(bill_nos),
                    timeout=BOM_QUERY_TIMEOUT,
                )
                return entries
            except asyncio.TimeoutError:
                logger.warning(
                    "BOM batch timeout (attempt %d/%d) for %d orders",
                    attempt + 1, BOM_MAX_RETRIES + 1, len(bill_nos)
                )
            except Exception as exc:
                logger.warning(
                    "BOM batch error (attempt %d/%d): %s",
                    attempt + 1, BOM_MAX_RETRIES + 1, exc
                )

            # Small delay before retry
            if attempt < BOM_MAX_RETRIES:
                await asyncio.sleep(1)

        return None

    async def _clear_cache(self) -> None:
        await self.db.execute_write(f"DELETE FROM {TABLE_ORDERS}")
        await self.db.execute_write(f"DELETE FROM {TABLE_BOM}")

    async def _upsert_production_orders(self, orders: Iterable) -> None:
        if not orders:
            return

        rows = [
            (
                o.mto_number, o.bill_no, o.workshop, o.material_code,
                o.material_name, o.specification, o.aux_attributes,
                float(o.qty), model_to_json(o),
            )
            for o in orders
        ]

        await self.db.executemany(
            f"""
            INSERT INTO {TABLE_ORDERS} (
                mto_number, bill_no, workshop, material_code, material_name,
                specification, aux_attributes, qty, raw_data, synced_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(bill_no) DO UPDATE SET
                mto_number=excluded.mto_number, workshop=excluded.workshop,
                material_code=excluded.material_code, material_name=excluded.material_name,
                specification=excluded.specification, aux_attributes=excluded.aux_attributes,
                qty=excluded.qty, raw_data=excluded.raw_data, synced_at=CURRENT_TIMESTAMP
            """,
            rows,
        )

    async def _upsert_production_bom(self, bom_entries: Iterable) -> None:
        if not bom_entries:
            return

        # Delete existing entries for these MO bill numbers (BOM is replaced, not merged)
        mo_bill_nos = sorted({e.mo_bill_no for e in bom_entries if e.mo_bill_no})
        if mo_bill_nos:
            placeholders = ",".join(["?"] * len(mo_bill_nos))
            await self.db.execute_write(
                f"DELETE FROM {TABLE_BOM} WHERE mo_bill_no IN ({placeholders})",
                mo_bill_nos,
            )

        rows = [
            (
                e.mo_bill_no, e.material_code, e.material_name, e.material_type,
                float(e.need_qty), float(e.picked_qty), float(e.no_picked_qty),
                model_to_json(e),
            )
            for e in bom_entries
        ]

        await self.db.executemany(
            f"""
            INSERT INTO {TABLE_BOM} (
                mo_bill_no, material_code, material_name, material_type,
                need_qty, picked_qty, no_picked_qty, raw_data, synced_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            rows,
        )

    async def _record_history(
        self, result: SyncResult, error_message: Optional[str] = None
    ) -> None:
        await self.db.execute_write(
            """
            INSERT INTO sync_history (
                started_at, finished_at, status, days_back, records_synced, error_message
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                result.started_at.isoformat(),
                result.finished_at.isoformat(),
                result.status,
                result.days_back,
                result.records_synced,
                error_message,
            ],
        )
