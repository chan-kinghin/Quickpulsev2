#!/usr/bin/env python3
"""
Smoke test the 2026-05-22 包材 routing fix end-to-end against local cache.

Queries an MTO known to contain 03.xx (packaging) and 08.xx (outsourced) BOM
items, runs the handler in source='cache' mode, and asserts at least one
ChildItem comes back with material_type_name='包材' and one with '委外'.

Prerequisites: migration 015 applied, backfill_category_name.py run.
"""
from __future__ import annotations

import asyncio
import os
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

# Avoid Kingdee live calls — mock readers
os.environ.setdefault("KINGDEE_SERVER_URL", "http://localhost/dummy/")
os.environ.setdefault("KINGDEE_ACCT_ID", "dummy")
os.environ.setdefault("KINGDEE_USER_NAME", "dummy")
os.environ.setdefault("KINGDEE_APP_ID", "dummy")
os.environ.setdefault("KINGDEE_APP_SEC", "dummy")

from src.database.connection import Database
from src.query.cache_reader import CacheReader
from src.query.mto_handler import MTOQueryHandler
from src.mto_config import MTOConfig

MTO = sys.argv[1] if len(sys.argv) > 1 else "AS2603016"


async def main():
    db_path = PROJECT_ROOT / "data/quickpulse.db"
    if not db_path.exists():
        print(f"FAIL: {db_path} not found", file=sys.stderr)
        sys.exit(1)

    db = Database(str(db_path))
    await db.connect()
    cache_reader = CacheReader(db, ttl_minutes=60 * 24 * 365)  # ignore staleness

    # Minimal handler — we only need cache path
    from unittest.mock import MagicMock, AsyncMock
    readers = {}
    for name in ["production_order", "production_bom", "production_receipt",
                 "purchase_order", "purchase_receipt", "subcontracting_order",
                 "material_picking", "sales_delivery", "sales_order"]:
        m = MagicMock()
        m.client = MagicMock()
        m.client.lookup_aux_properties = AsyncMock(return_value={})
        m.fetch_by_mto = AsyncMock(return_value=[])
        readers[name] = m

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
        cache_reader=cache_reader,
    )

    print(f"Querying {MTO} via cache...")
    result = await handler.get_status(MTO, source="cache")

    type_counter = Counter()
    cat_counter = Counter()
    for child in result.children:
        type_counter[child.material_type_name] += 1
    print(f"\nChild count: {len(result.children)}")
    print(f"Type distribution: {dict(type_counter)}")

    # Acceptance
    failures = []
    if type_counter.get("包材", 0) == 0:
        failures.append("Expected ≥1 child with material_type_name='包材' — got 0")
    if type_counter.get("委外", 0) == 0:
        failures.append("Expected ≥1 child with material_type_name='委外' — got 0")

    if failures:
        print("\n=== SMOKE TEST FAILED ===")
        for f in failures:
            print(f"  ✗ {f}")
        # Diagnostic: show category_name distribution from cache
        async with db._connection.execute(
            "SELECT COALESCE(category_name,'(empty)'), COUNT(*) "
            "FROM cached_production_bom WHERE mto_number = ? GROUP BY 1",
            [MTO],
        ) as cur:
            print(f"\ncategory_name in cached_production_bom for {MTO}:")
            async for row in cur:
                print(f"  {row[0]!r}: {row[1]}")
        sys.exit(1)

    print(f"\n=== SMOKE TEST PASSED ===")
    print(f"  ✓ {type_counter.get('包材', 0)} child(ren) labeled '包材'")
    print(f"  ✓ {type_counter.get('委外', 0)} child(ren) labeled '委外'")
    print(f"  ✓ {type_counter.get('自制', 0)} child(ren) labeled '自制'")


if __name__ == "__main__":
    asyncio.run(main())
