#!/usr/bin/env python3
"""Probe REAL live-path latency against Kingdee (read-only, gentle).

Gating data for the "delete L2 / live-only" decision: how slow is a cold live MTO
query, and which form is the bottleneck. Sequential, small MTO list, 1s pause between
— this is exactly what the dashboard does on a normal live query, just timed. NOT a
load/concurrency test, does NOT write anything.

Run from a network close to the ERP for a representative number (laptop→Kingdee will
be pessimistic vs CVM→Kingdee). Reports per-MTO total + per-form fetch time + row counts.
"""
import asyncio
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)

from src.config import Config  # noqa: E402
from src.kingdee.client import KingdeeClient  # noqa: E402
from src.mto_config import MTOConfig  # noqa: E402
from src.query.mto_handler import MTOQueryHandler  # noqa: E402
from src.readers.factory import (  # noqa: E402
    MaterialPickingReader, ProductionBOMReader, ProductionOrderReader,
    ProductionReceiptReader, PurchaseOrderReader, PurchaseReceiptReader,
    SalesDeliveryReader, SalesOrderReader, SubcontractingOrderReader,
)

MTOS = sys.argv[1:] or ["AK2510034", "AS2509051", "DS256203S", "DK251003S"]


def build_handler():
    config = Config.load()
    client = KingdeeClient(config.kingdee)
    readers = {
        "production_order": ProductionOrderReader(client),
        "production_bom": ProductionBOMReader(client),
        "production_receipt": ProductionReceiptReader(client),
        "purchase_order": PurchaseOrderReader(client),
        "purchase_receipt": PurchaseReceiptReader(client),
        "subcontracting_order": SubcontractingOrderReader(client),
        "material_picking": MaterialPickingReader(client),
        "sales_delivery": SalesDeliveryReader(client),
        "sales_order": SalesOrderReader(client),
    }
    mto_config = MTOConfig("config/mto_config.json")
    handler = MTOQueryHandler(
        production_order_reader=readers["production_order"],
        production_bom_reader=readers["production_bom"],
        production_receipt_reader=readers["production_receipt"],
        purchase_order_reader=readers["purchase_order"],
        purchase_receipt_reader=readers["purchase_receipt"],
        subcontracting_order_reader=readers["subcontracting_order"],
        material_picking_reader=readers["material_picking"],
        sales_delivery_reader=readers["sales_delivery"],
        sales_order_reader=readers["sales_order"],
        cache_reader=None,
        mto_config=mto_config,
        metric_engine=mto_config.build_metric_engine(),
        memory_cache_enabled=False,  # force a true cold live query every time
    )
    return handler, readers


def instrument(readers, timings):
    """Wrap each reader.fetch_by_mto to record (seconds, rowcount)."""
    for name, r in readers.items():
        orig = r.fetch_by_mto

        def make(name, orig):
            async def timed(mto):
                t = time.perf_counter()
                rows = await orig(mto)
                timings[name] = (time.perf_counter() - t, len(rows))
                return rows
            return timed
        r.fetch_by_mto = make(name, orig)


async def main():
    handler, readers = build_handler()
    print(f"probing {len(MTOS)} MTOs (cold live, sequential)\n")
    results = []
    for mto in MTOS:
        timings = {}
        instrument(readers, timings)
        t0 = time.perf_counter()
        try:
            resp = await handler.get_status(mto, use_cache=False)
            total = time.perf_counter() - t0
            n_children = len(resp.children)
            results.append((mto, total, n_children))
            slow = sorted(timings.items(), key=lambda kv: -kv[1][0])[:3]
            slow_str = ", ".join(f"{k}={v[0]:.2f}s/{v[1]}rows" for k, v in slow)
            print(f"{mto:<14} TOTAL {total:6.2f}s  children={n_children:<4}  slowest forms: {slow_str}")
        except Exception as e:
            total = time.perf_counter() - t0
            print(f"{mto:<14} ERROR after {total:6.2f}s: {type(e).__name__}: {str(e)[:80]}")
        await asyncio.sleep(1.0)  # be gentle on the ERP

    if results:
        times = sorted(t for _, t, _ in results)
        med = times[len(times) // 2]
        print(f"\nsummary (n={len(results)}): min={times[0]:.2f}s  median={med:.2f}s  max={times[-1]:.2f}s")


if __name__ == "__main__":
    asyncio.run(main())
