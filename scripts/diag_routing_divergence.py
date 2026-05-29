#!/usr/bin/env python3
"""Root-cause the live↔cache routing divergence for a single material (read-only).

Parity check found 03.06.03.001 = live {包材,自制} vs cache {包材} across 3 MTOs.
This dumps the actual children both paths emit + the live BD_MATERIAL classification
vs what the cache stored, to decide: logic bug or 18-day master-data staleness, and
which path is canonical.
"""
import asyncio
import logging
import os
import sys

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

MTO = sys.argv[1] if len(sys.argv) > 1 else "AS2603016"
CODE = sys.argv[2] if len(sys.argv) > 2 else "03.06.03.001"


async def main():
    config = Config.load()
    db = Database(config.db_path)
    await db.connect()
    client = KingdeeClient(config.kingdee)
    R = {n: cls(client) for n, cls in {
        "production_order": ProductionOrderReader, "production_bom": ProductionBOMReader,
        "production_receipt": ProductionReceiptReader, "purchase_order": PurchaseOrderReader,
        "purchase_receipt": PurchaseReceiptReader, "subcontracting_order": SubcontractingOrderReader,
        "material_picking": MaterialPickingReader, "sales_delivery": SalesDeliveryReader,
        "sales_order": SalesOrderReader}.items()}
    h = MTOQueryHandler(
        production_order_reader=R["production_order"], production_bom_reader=R["production_bom"],
        production_receipt_reader=R["production_receipt"], purchase_order_reader=R["purchase_order"],
        purchase_receipt_reader=R["purchase_receipt"], subcontracting_order_reader=R["subcontracting_order"],
        material_picking_reader=R["material_picking"], sales_delivery_reader=R["sales_delivery"],
        sales_order_reader=R["sales_order"],
        cache_reader=CacheReader(db, ttl_minutes=99_999_999), mto_config=MTOConfig("config/mto_config.json"),
        metric_engine=None, memory_cache_enabled=False)

    live = await h.get_status(MTO, source="live")
    cache = await h.get_status(MTO, source="cache")

    def show(label, resp):
        kids = [c for c in resp.children if c.material_code == CODE]
        print(f"\n--- {label}: {len(kids)} child(ren) for {CODE} ---")
        for c in kids:
            print(f"  type={c.material_type_name!r} is_purchase={c.is_purchase} is_fg={c.is_finished_goods} "
                  f"aux={c.aux_attributes!r} cat={c.material_group_name!r} "
                  f"need/must={c.prod_instock_must_qty} pick={c.pick_actual_qty} "
                  f"prod_in={c.prod_instock_real_qty} pur_in={c.purchase_stock_in_qty}")

    show("LIVE", live)
    show("CACHE", cache)

    # Live BD_MATERIAL classification (current master) vs what the cache stored 18d ago
    print(f"\n--- LIVE BD_MATERIAL master for {CODE} ---")
    try:
        rows = await client.query("BD_MATERIAL",
                                  ["FNumber", "FErpClsID", "FCategoryID.FName", "FIsPurchase", "FName"],
                                  f"FNumber = '{CODE}'", limit=5)
        for r in rows:
            print(" ", {k: r.get(k) for k in r})
    except Exception as e:
        print("  BD_MATERIAL query error:", e)

    print(f"\n--- CACHE stored (cached_production_bom) for {CODE} in {MTO} ---")
    crows = await db.execute_read(
        "SELECT material_code, material_type, category_name, is_purchase, material_group_name "
        "FROM cached_production_bom WHERE mto_number = ? AND material_code = ?", [MTO, CODE])
    for r in crows:
        print(" ", r)


if __name__ == "__main__":
    asyncio.run(main())
