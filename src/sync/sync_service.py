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
TABLE_PURCHASE_ORDERS = "cached_purchase_orders"
TABLE_SUBCONTRACTING_ORDERS = "cached_subcontracting_orders"
TABLE_PRODUCTION_RECEIPTS = "cached_production_receipts"
TABLE_PURCHASE_RECEIPTS = "cached_purchase_receipts"
TABLE_MATERIAL_PICKING = "cached_material_picking"
TABLE_SALES_DELIVERY = "cached_sales_delivery"
TABLE_SALES_ORDERS = "cached_sales_orders"

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
        self._post_sync_callbacks: list = []

    def add_post_sync_callback(self, callback) -> None:
        """Register a callback to run after successful sync.

        Use this to invalidate in-memory caches after data refresh.

        Args:
            callback: Callable (sync or async) to run after sync completes
        """
        self._post_sync_callbacks.append(callback)

    def is_running(self) -> bool:
        return self._running or self._lock.locked()

    async def _run_post_sync_callbacks(self) -> None:
        """Execute all registered post-sync callbacks."""
        for callback in self._post_sync_callbacks:
            try:
                result = callback()
                # Support both sync and async callbacks
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                logger.warning("Post-sync callback error: %s", exc)

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

                # Run post-sync callbacks (e.g., clear memory cache)
                await self._run_post_sync_callbacks()

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
        """Sync a single date chunk - all 9 data sources."""
        count = 0

        # 1. Production orders (PRD_MO)
        orders = await self._sync_orders(start_date, end_date)
        count += len(orders)

        # 2. BOM entries (PRD_PPBOM)
        if orders:
            count += await self._sync_bom_for_orders(orders)

        # 3-9. Sync all other data sources by MTO numbers
        mto_numbers = list({o.mto_number for o in orders if o.mto_number})
        if mto_numbers:
            count += await self._sync_purchase_orders(mto_numbers)
            count += await self._sync_subcontracting_orders(mto_numbers)
            count += await self._sync_production_receipts(mto_numbers)
            count += await self._sync_purchase_receipts(mto_numbers)
            count += await self._sync_material_picking(mto_numbers)
            count += await self._sync_sales_delivery(mto_numbers)
            count += await self._sync_sales_orders(mto_numbers)

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
                float(o.qty),
                getattr(o, 'status', ''),  # Denormalized
                getattr(o, 'create_date', None),  # Denormalized
                model_to_json(o),
            )
            for o in orders
        ]

        await self.db.executemany(
            f"""
            INSERT INTO {TABLE_ORDERS} (
                mto_number, bill_no, workshop, material_code, material_name,
                specification, aux_attributes, qty, status, create_date, raw_data, synced_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(bill_no) DO UPDATE SET
                mto_number=excluded.mto_number, workshop=excluded.workshop,
                material_code=excluded.material_code, material_name=excluded.material_name,
                specification=excluded.specification, aux_attributes=excluded.aux_attributes,
                qty=excluded.qty, status=excluded.status, create_date=excluded.create_date,
                raw_data=excluded.raw_data, synced_at=CURRENT_TIMESTAMP
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
                e.mo_bill_no,
                getattr(e, 'mto_number', ''),  # Denormalized
                e.material_code, e.material_name,
                getattr(e, 'specification', ''),  # Denormalized
                getattr(e, 'aux_attributes', ''),  # Denormalized
                getattr(e, 'aux_prop_id', 0),  # Denormalized
                e.material_type,
                float(e.need_qty), float(e.picked_qty), float(e.no_picked_qty),
                model_to_json(e),
            )
            for e in bom_entries
        ]

        await self.db.executemany(
            f"""
            INSERT INTO {TABLE_BOM} (
                mo_bill_no, mto_number, material_code, material_name,
                specification, aux_attributes, aux_prop_id, material_type,
                need_qty, picked_qty, no_picked_qty, raw_data, synced_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            rows,
        )

    # =========================================================================
    # Sync methods for 7 additional data sources (by MTO numbers)
    # =========================================================================

    async def _sync_purchase_orders(self, mto_numbers: list[str]) -> int:
        """Sync purchase orders (外购件) for given MTO numbers."""
        if "purchase_order" not in self.readers:
            return 0

        all_records = await self._fetch_by_mto_numbers(
            "purchase_order", mto_numbers, "purchase_orders"
        )
        await self._upsert_purchase_orders(all_records)
        self.progress.update(
            "pur_order", f"Synced {len(all_records)} purchase orders",
            purchase_orders_count=len(all_records)
        )
        return len(all_records)

    async def _sync_subcontracting_orders(self, mto_numbers: list[str]) -> int:
        """Sync subcontracting orders (委外件) for given MTO numbers."""
        if "subcontracting_order" not in self.readers:
            return 0

        all_records = await self._fetch_by_mto_numbers(
            "subcontracting_order", mto_numbers, "subcontracting_orders"
        )
        await self._upsert_subcontracting_orders(all_records)
        self.progress.update(
            "sub_order", f"Synced {len(all_records)} subcontracting orders",
            subcontracting_orders_count=len(all_records)
        )
        return len(all_records)

    async def _sync_production_receipts(self, mto_numbers: list[str]) -> int:
        """Sync production receipts (自制件入库) for given MTO numbers."""
        if "production_receipt" not in self.readers:
            return 0

        all_records = await self._fetch_by_mto_numbers(
            "production_receipt", mto_numbers, "production_receipts"
        )
        await self._upsert_production_receipts(all_records)
        self.progress.update(
            "prd_receipt", f"Synced {len(all_records)} production receipts",
            production_receipts_count=len(all_records)
        )
        return len(all_records)

    async def _sync_purchase_receipts(self, mto_numbers: list[str]) -> int:
        """Sync purchase receipts (外购/委外入库) for given MTO numbers."""
        if "purchase_receipt" not in self.readers:
            return 0

        all_records = await self._fetch_by_mto_numbers(
            "purchase_receipt", mto_numbers, "purchase_receipts"
        )
        await self._upsert_purchase_receipts(all_records)
        self.progress.update(
            "pur_receipt", f"Synced {len(all_records)} purchase receipts",
            purchase_receipts_count=len(all_records)
        )
        return len(all_records)

    async def _sync_material_picking(self, mto_numbers: list[str]) -> int:
        """Sync material picking records (生产领料) for given MTO numbers."""
        if "material_picking" not in self.readers:
            return 0

        all_records = await self._fetch_by_mto_numbers(
            "material_picking", mto_numbers, "material_picking"
        )
        await self._upsert_material_picking(all_records)
        self.progress.update(
            "pick_mtrl", f"Synced {len(all_records)} material picking records",
            material_picking_count=len(all_records)
        )
        return len(all_records)

    async def _sync_sales_delivery(self, mto_numbers: list[str]) -> int:
        """Sync sales delivery records (销售出库) for given MTO numbers."""
        if "sales_delivery" not in self.readers:
            return 0

        all_records = await self._fetch_by_mto_numbers(
            "sales_delivery", mto_numbers, "sales_delivery"
        )
        await self._upsert_sales_delivery(all_records)
        self.progress.update(
            "sal_delivery", f"Synced {len(all_records)} sales delivery records",
            sales_delivery_count=len(all_records)
        )
        return len(all_records)

    async def _sync_sales_orders(self, mto_numbers: list[str]) -> int:
        """Sync sales orders (销售订单) for given MTO numbers."""
        if "sales_order" not in self.readers:
            return 0

        all_records = await self._fetch_by_mto_numbers(
            "sales_order", mto_numbers, "sales_orders"
        )
        await self._upsert_sales_orders(all_records)
        self.progress.update(
            "sal_order", f"Synced {len(all_records)} sales orders",
            sales_orders_count=len(all_records)
        )
        return len(all_records)

    async def _fetch_by_mto_numbers(
        self, reader_name: str, mto_numbers: list[str], data_type: str
    ) -> list:
        """Fetch records for multiple MTO numbers in parallel batches.

        Uses asyncio.gather for parallel fetching within reasonable batch sizes
        to avoid overwhelming the Kingdee API.
        """
        if not mto_numbers:
            return []

        reader = self.readers[reader_name]
        all_records = []
        batch_size = 10  # Parallel queries per batch

        for i in range(0, len(mto_numbers), batch_size):
            batch = mto_numbers[i : i + batch_size]
            try:
                results = await asyncio.gather(
                    *[reader.fetch_by_mto(mto) for mto in batch],
                    return_exceptions=True
                )
                for result in results:
                    if isinstance(result, Exception):
                        logger.warning("Error fetching %s: %s", data_type, result)
                    elif result:
                        all_records.extend(result)
            except Exception as exc:
                logger.warning("Batch error fetching %s: %s", data_type, exc)

        return all_records

    # =========================================================================
    # Upsert methods for 7 additional cache tables
    # =========================================================================

    async def _upsert_purchase_orders(self, records: Iterable) -> None:
        """Upsert purchase orders to cache."""
        if not records:
            return

        # Delete existing by MTO numbers for clean refresh
        mto_numbers = sorted({r.mto_number for r in records if r.mto_number})
        if mto_numbers:
            placeholders = ",".join(["?"] * len(mto_numbers))
            await self.db.execute_write(
                f"DELETE FROM {TABLE_PURCHASE_ORDERS} WHERE mto_number IN ({placeholders})",
                mto_numbers,
            )

        rows = [
            (
                r.bill_no, r.mto_number, r.material_code, r.material_name,
                r.specification, r.aux_attributes, r.aux_prop_id,
                float(r.order_qty), float(r.stock_in_qty), float(r.remain_stock_in_qty),
                model_to_json(r),
            )
            for r in records
        ]

        await self.db.executemany(
            f"""
            INSERT INTO {TABLE_PURCHASE_ORDERS} (
                bill_no, mto_number, material_code, material_name, specification,
                aux_attributes, aux_prop_id, order_qty, stock_in_qty, remain_stock_in_qty,
                raw_data, synced_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            rows,
        )

    async def _upsert_subcontracting_orders(self, records: Iterable) -> None:
        """Upsert subcontracting orders to cache."""
        if not records:
            return

        mto_numbers = sorted({r.mto_number for r in records if r.mto_number})
        if mto_numbers:
            placeholders = ",".join(["?"] * len(mto_numbers))
            await self.db.execute_write(
                f"DELETE FROM {TABLE_SUBCONTRACTING_ORDERS} WHERE mto_number IN ({placeholders})",
                mto_numbers,
            )

        rows = [
            (
                r.bill_no, r.mto_number, r.material_code,
                float(r.order_qty), float(r.stock_in_qty), float(r.no_stock_in_qty),
                model_to_json(r),
            )
            for r in records
        ]

        await self.db.executemany(
            f"""
            INSERT INTO {TABLE_SUBCONTRACTING_ORDERS} (
                bill_no, mto_number, material_code, order_qty, stock_in_qty,
                no_stock_in_qty, raw_data, synced_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            rows,
        )

    async def _upsert_production_receipts(self, records: Iterable) -> None:
        """Upsert production receipts to cache."""
        if not records:
            return

        mto_numbers = sorted({r.mto_number for r in records if r.mto_number})
        if mto_numbers:
            placeholders = ",".join(["?"] * len(mto_numbers))
            await self.db.execute_write(
                f"DELETE FROM {TABLE_PRODUCTION_RECEIPTS} WHERE mto_number IN ({placeholders})",
                mto_numbers,
            )

        rows = [
            (
                r.mto_number, r.material_code, float(r.real_qty), float(r.must_qty),
                model_to_json(r),
            )
            for r in records
        ]

        await self.db.executemany(
            f"""
            INSERT INTO {TABLE_PRODUCTION_RECEIPTS} (
                mto_number, material_code, real_qty, must_qty, raw_data, synced_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            rows,
        )

    async def _upsert_purchase_receipts(self, records: Iterable) -> None:
        """Upsert purchase receipts to cache."""
        if not records:
            return

        mto_numbers = sorted({r.mto_number for r in records if r.mto_number})
        if mto_numbers:
            placeholders = ",".join(["?"] * len(mto_numbers))
            await self.db.execute_write(
                f"DELETE FROM {TABLE_PURCHASE_RECEIPTS} WHERE mto_number IN ({placeholders})",
                mto_numbers,
            )

        rows = [
            (
                r.mto_number, r.material_code, float(r.real_qty), float(r.must_qty),
                r.bill_type_number, model_to_json(r),
            )
            for r in records
        ]

        await self.db.executemany(
            f"""
            INSERT INTO {TABLE_PURCHASE_RECEIPTS} (
                mto_number, material_code, real_qty, must_qty, bill_type_number,
                raw_data, synced_at
            )
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            rows,
        )

    async def _upsert_material_picking(self, records: Iterable) -> None:
        """Upsert material picking records to cache."""
        if not records:
            return

        mto_numbers = sorted({r.mto_number for r in records if r.mto_number})
        if mto_numbers:
            placeholders = ",".join(["?"] * len(mto_numbers))
            await self.db.execute_write(
                f"DELETE FROM {TABLE_MATERIAL_PICKING} WHERE mto_number IN ({placeholders})",
                mto_numbers,
            )

        rows = [
            (
                r.mto_number, r.material_code, float(r.app_qty), float(r.actual_qty),
                r.ppbom_bill_no, model_to_json(r),
            )
            for r in records
        ]

        await self.db.executemany(
            f"""
            INSERT INTO {TABLE_MATERIAL_PICKING} (
                mto_number, material_code, app_qty, actual_qty, ppbom_bill_no,
                raw_data, synced_at
            )
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            rows,
        )

    async def _upsert_sales_delivery(self, records: Iterable) -> None:
        """Upsert sales delivery records to cache."""
        if not records:
            return

        mto_numbers = sorted({r.mto_number for r in records if r.mto_number})
        if mto_numbers:
            placeholders = ",".join(["?"] * len(mto_numbers))
            await self.db.execute_write(
                f"DELETE FROM {TABLE_SALES_DELIVERY} WHERE mto_number IN ({placeholders})",
                mto_numbers,
            )

        rows = [
            (
                r.mto_number, r.material_code, float(r.real_qty), float(r.must_qty),
                model_to_json(r),
            )
            for r in records
        ]

        await self.db.executemany(
            f"""
            INSERT INTO {TABLE_SALES_DELIVERY} (
                mto_number, material_code, real_qty, must_qty, raw_data, synced_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            rows,
        )

    async def _upsert_sales_orders(self, records: Iterable) -> None:
        """Upsert sales orders to cache."""
        if not records:
            return

        mto_numbers = sorted({r.mto_number for r in records if r.mto_number})
        if mto_numbers:
            placeholders = ",".join(["?"] * len(mto_numbers))
            await self.db.execute_write(
                f"DELETE FROM {TABLE_SALES_ORDERS} WHERE mto_number IN ({placeholders})",
                mto_numbers,
            )

        rows = [
            (
                r.bill_no, r.mto_number, r.customer_name, r.delivery_date,
                model_to_json(r),
            )
            for r in records
        ]

        await self.db.executemany(
            f"""
            INSERT INTO {TABLE_SALES_ORDERS} (
                bill_no, mto_number, customer_name, delivery_date, raw_data, synced_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
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
