#!/usr/bin/env python3
"""One-off: clear contaminated rows from cached_production_orders.

Bug 7 / bug-patterns.md #5 (Wave 4A, 2026-04-26): the upsert silently
rewrote mto_number on conflict, leaving rows attributed to the wrong MTO.
After migration 010 fixes the schema, the existing contaminated rows must
be cleared so the next sync repopulates them correctly from Kingdee.

Concrete contamination example: customer 瑞弧WeaArCo MTO DS256203S
returned 18 ghost 07.xx rows (07.01.06, 07.01.07, 07.01.78, 07.01.80=941,
07.02.022, 07.02.121, 07.04.078, 07.05.16.01..06, 07.08.001..003,
07.23.007, 07.23.034, 07.25.84, 07.33.010, 07.37.001) that don't exist
in any Kingdee form for that MTO — they migrated from sibling MTOs
DS242022S-A2 / WS2510003 across previous sync cycles.

The contamination cannot be repaired in place — the original mto_number
values were overwritten and are not recoverable from the cache. The fix
is to drop the contaminated rows and let the sync layer re-fetch from
Kingdee, where the truth still lives. Mirror of Wave 2's
scripts/cleanup_subcontract_contamination.py.

Modes:
    --customer <name>   Clear rows for MTOs of this customer (matches
                        cached_sales_orders.customer_name LIKE).
    --mto <mto_no>      Clear rows for one or more specific MTOs.
                        Repeatable.
    --all               Clear the entire table (safest after a Pattern 5
                        bug; the next sync repopulates everything).

Usage on CVM (prod):
    cd /opt/ops/apps/quickpulse/prod/repo
    docker compose exec quickpulse-prod \\
        python3 -m scripts.cleanup_production_orders_contamination --all
    # then trigger a sync via /api/sync/trigger or wait for the next cron.

The script makes no Kingdee API calls itself — it only touches the cache.
"""
import argparse
import asyncio
import sys
from pathlib import Path

# Allow running via `python3 -m scripts.cleanup_production_orders_contamination`
# from the repo root.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.database.connection import Database  # noqa: E402


async def _resolve_mtos_for_customer(db: Database, customer_pattern: str) -> list[str]:
    """Look up MTO numbers in cached_sales_orders matching a customer name."""
    pattern = f"%{customer_pattern}%"
    async with db._connection.execute(
        "SELECT DISTINCT mto_number FROM cached_sales_orders "
        "WHERE customer_name LIKE ? AND mto_number IS NOT NULL",
        (pattern,),
    ) as cursor:
        rows = await cursor.fetchall()
    return sorted(r[0] for r in rows)


async def _delete_for_mtos(db: Database, mtos: list[str]) -> int:
    """DELETE cached_production_orders rows for the given MTOs."""
    if not mtos:
        return 0
    placeholders = ",".join(["?"] * len(mtos))
    async with db._connection.execute(
        f"SELECT COUNT(*) FROM cached_production_orders "
        f"WHERE mto_number IN ({placeholders})",
        mtos,
    ) as cursor:
        before = (await cursor.fetchone())[0]
    await db._connection.execute(
        f"DELETE FROM cached_production_orders "
        f"WHERE mto_number IN ({placeholders})",
        mtos,
    )
    await db._connection.commit()
    return before


async def _delete_all(db: Database) -> int:
    """Wipe cached_production_orders entirely."""
    async with db._connection.execute(
        "SELECT COUNT(*) FROM cached_production_orders"
    ) as cursor:
        before = (await cursor.fetchone())[0]
    await db._connection.execute("DELETE FROM cached_production_orders")
    await db._connection.commit()
    return before


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--customer", help="Match cached_sales_orders.customer_name LIKE this pattern"
    )
    group.add_argument(
        "--mto", action="append", help="Specific MTO number (repeat for multiple)"
    )
    group.add_argument(
        "--all", action="store_true", help="Wipe the entire production_orders cache"
    )
    parser.add_argument(
        "--db",
        default="data/quickpulse.db",
        help="Path to SQLite cache (default: data/quickpulse.db)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be deleted without committing",
    )
    args = parser.parse_args()

    db = Database(Path(args.db))
    await db.connect()

    try:
        if args.all:
            if args.dry_run:
                async with db._connection.execute(
                    "SELECT COUNT(*) FROM cached_production_orders"
                ) as cur:
                    n = (await cur.fetchone())[0]
                print(f"[dry-run] Would DELETE {n} rows from cached_production_orders.")
                return 0
            n = await _delete_all(db)
            print(f"Deleted {n} rows from cached_production_orders (--all).")
            print("Next sync (auto or via /api/sync/trigger) will repopulate.")
            return 0

        if args.customer:
            mtos = await _resolve_mtos_for_customer(db, args.customer)
            if not mtos:
                print(f"No MTOs found for customer pattern '{args.customer}'.")
                return 1
            print(f"Customer '{args.customer}' matches {len(mtos)} MTOs:")
            for m in mtos:
                print(f"  - {m}")
        else:
            mtos = args.mto

        if args.dry_run:
            placeholders = ",".join(["?"] * len(mtos))
            async with db._connection.execute(
                f"SELECT COUNT(*) FROM cached_production_orders "
                f"WHERE mto_number IN ({placeholders})",
                mtos,
            ) as cur:
                n = (await cur.fetchone())[0]
            print(f"[dry-run] Would DELETE {n} rows from cached_production_orders "
                  f"for {len(mtos)} MTO(s).")
            return 0

        n = await _delete_for_mtos(db, mtos)
        print(f"Deleted {n} rows from cached_production_orders "
              f"for {len(mtos)} MTO(s).")
        print("Next sync (auto or via /api/sync/trigger) will repopulate.")
        return 0
    finally:
        await db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
