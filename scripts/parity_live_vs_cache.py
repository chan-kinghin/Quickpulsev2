#!/usr/bin/env python3
"""Phase 2 gate: live vs cache aggregation parity on real MTOs (read-only).

If the live Python aggregation and the cache SQL aggregation (get_mto_bom_joined)
produce the same STRUCTURE for real MTOs, the cutover-to-live is safe and the
duplicated CTE can be deleted. If they diverge structurally, that is a LOGIC bug
(the two paths disagree TODAY) that must be fixed before any cutover.

The local cache is ~18 days stale, so QUANTITY diffs are partly staleness, not logic.
The staleness-ROBUST signal is structural: same set of material_codes, same child
counts, same routing/type. Quantity diffs are reported separately and flagged.

Read-only. Hits Kingdee live (sequential, gentle) + reads the local cache DB.
"""
import asyncio
import logging
import os
import sys
from collections import defaultdict
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)

from src.config import Config  # noqa: E402
from src.database.connection import Database  # noqa: E402
from src.kingdee.client import KingdeeClient  # noqa: E402
from src.mto_config import MTOConfig  # noqa: E402
from src.query.cache_reader import CacheReader  # noqa: E402
from src.query.mto_handler import MTOQueryHandler  # noqa: E402
from src.readers.factory import (  # noqa: E402
    MaterialPickingReader, ProductionBOMReader, ProductionOrderReader,
    ProductionReceiptReader, PurchaseOrderReader, PurchaseReceiptReader,
    SalesDeliveryReader, SalesOrderReader, SubcontractingOrderReader,
)

MTOS = sys.argv[1:] or ["AS2603016", "AS2604011", "AK2510022", "AS2603015",
                        "AK2510034", "AS2512042-2", "AS2510071-2B", "AK2509054-14"]
QTY_FIELDS = ["sales_order_qty", "prod_instock_must_qty", "purchase_order_qty",
              "pick_actual_qty", "prod_instock_real_qty", "purchase_stock_in_qty"]


async def build():
    config = Config.load()
    db = Database(config.db_path)
    await db.connect()
    client = KingdeeClient(config.kingdee)
    R = {
        "production_order": ProductionOrderReader(client), "production_bom": ProductionBOMReader(client),
        "production_receipt": ProductionReceiptReader(client), "purchase_order": PurchaseOrderReader(client),
        "purchase_receipt": PurchaseReceiptReader(client), "subcontracting_order": SubcontractingOrderReader(client),
        "material_picking": MaterialPickingReader(client), "sales_delivery": SalesDeliveryReader(client),
        "sales_order": SalesOrderReader(client),
    }
    mto_config = MTOConfig("config/mto_config.json")
    handler = MTOQueryHandler(
        production_order_reader=R["production_order"], production_bom_reader=R["production_bom"],
        production_receipt_reader=R["production_receipt"], purchase_order_reader=R["purchase_order"],
        purchase_receipt_reader=R["purchase_receipt"], subcontracting_order_reader=R["subcontracting_order"],
        material_picking_reader=R["material_picking"], sales_delivery_reader=R["sales_delivery"],
        sales_order_reader=R["sales_order"],
        cache_reader=CacheReader(db, ttl_minutes=99_999_999),  # huge TTL: return the stale rows for comparison
        mto_config=mto_config, metric_engine=None, memory_cache_enabled=False,
    )
    return handler


def by_code(children):
    """Aggregate children to code -> {count, types:set, qtys: summed}."""
    agg = {}
    for c in children:
        e = agg.setdefault(c.material_code, {"count": 0, "types": set(), "qtys": defaultdict(Decimal)})
        e["count"] += 1
        e["types"].add(c.material_type_name)
        for q in QTY_FIELDS:
            e["qtys"][q] += getattr(c, q, Decimal(0)) or Decimal(0)
    return agg


async def main():
    handler = await build()
    print(f"parity check on {len(MTOS)} MTOs (cache synced 2026-05-11, ~18d stale)\n")
    struct_ok = 0
    for mto in MTOS:
        try:
            live = await handler.get_status(mto, source="live")
            cache = await handler.get_status(mto, source="cache")
        except Exception as e:
            print(f"{mto:<16} ERROR: {type(e).__name__}: {str(e)[:70]}")
            continue
        L, C = by_code(live.children), by_code(cache.children)
        only_live = sorted(set(L) - set(C))
        only_cache = sorted(set(C) - set(L))
        common = set(L) & set(C)
        routing_mismatch = [c for c in common if L[c]["types"] != C[c]["types"]]
        count_mismatch = [c for c in common if L[c]["count"] != C[c]["count"]]
        qty_diff = [c for c in common if any(L[c]["qtys"][q] != C[c]["qtys"][q] for q in QTY_FIELDS)]

        structural = not only_live and not only_cache and not routing_mismatch and not count_mismatch
        if structural:
            struct_ok += 1
        tag = "STRUCT-OK " if structural else "STRUCT-DIFF"
        print(f"{mto:<16} {tag}  live_codes={len(L):<4} cache_codes={len(C):<4} "
              f"only_live={len(only_live)} only_cache={len(only_cache)} "
              f"routing_mismatch={len(routing_mismatch)} count_mismatch={len(count_mismatch)} "
              f"| qty_diff_codes={len(qty_diff)} (staleness-possible)")
        if only_live[:5]:
            print(f"                 only in LIVE (cache missing): {only_live[:8]}")
        if only_cache[:5]:
            print(f"                 only in CACHE (live missing): {only_cache[:8]}")
        if routing_mismatch[:5]:
            ex = routing_mismatch[0]
            print(f"                 routing e.g. {ex}: live={L[ex]['types']} cache={C[ex]['types']}")
        await asyncio.sleep(1.0)

    print(f"\nSTRUCTURAL parity: {struct_ok}/{len(MTOS)} MTOs match exactly on code-set + routing + child-count.")
    print("(Quantity diffs are expected from the 18-day-stale cache; structural diffs would be real logic bugs.)")


if __name__ == "__main__":
    asyncio.run(main())
