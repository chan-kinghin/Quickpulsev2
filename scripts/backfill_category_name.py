#!/usr/bin/env python3
"""
Backfill cached_production_bom.category_name from Kingdee BD_MATERIAL.

Existing rows pre-date migration 015 and have category_name='' (the default).
The routing in mto_handler._bom_row_to_child treats empty category_name as a
sync gap (warns + falls back to legacy material_type). For correct routing
without waiting for the next full sync, run this script to populate the column.

Idempotent: re-running re-fetches only DISTINCT material codes that still have
empty category_name.

Usage:
    python3 scripts/backfill_category_name.py            # default DB
    python3 scripts/backfill_category_name.py --db PATH  # override

See docs/PLAN_fix_baocai_routing_2026-05-22.md.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import aiosqlite
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from k3cloud_webapi_sdk.main import K3CloudApiSdk

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("backfill")


def init_sdk() -> K3CloudApiSdk:
    sdk = K3CloudApiSdk(os.environ["KINGDEE_SERVER_URL"])
    sdk.InitConfig(
        acct_id=os.environ["KINGDEE_ACCT_ID"],
        user_name=os.environ["KINGDEE_USER_NAME"],
        app_id=os.environ["KINGDEE_APP_ID"],
        app_secret=os.environ["KINGDEE_APP_SEC"],
        server_url=os.environ["KINGDEE_SERVER_URL"],
        lcid=int(os.environ.get("KINGDEE_LCID", 2052)),
    )
    return sdk


def _multilang(v) -> str:
    if isinstance(v, list) and v:
        first = v[0]
        if isinstance(first, dict):
            return first.get("Value") or first.get("Name") or ""
    return v if isinstance(v, str) else ""


def fetch_category_name(sdk: K3CloudApiSdk, material_code: str) -> str | None:
    """Return CategoryID.Name for a material code, or None if unfetchable."""
    try:
        resp = sdk.View("BD_MATERIAL", {"Number": material_code})
        if isinstance(resp, str):
            resp = json.loads(resp)
        if not resp.get("Result", {}).get("ResponseStatus", {}).get("IsSuccess"):
            return None
        data = resp["Result"]["Result"]
        mb_raw = data.get("MaterialBase")
        mb = mb_raw[0] if isinstance(mb_raw, list) and mb_raw else (mb_raw or {})
        cat = mb.get("CategoryID") or {}
        if not isinstance(cat, dict):
            return None
        return _multilang(cat.get("Name"))
    except Exception as e:
        log.warning("View BD_MATERIAL %s failed: %s", material_code, e)
        return None


async def main(db_path: Path) -> None:
    sdk = init_sdk()

    async with aiosqlite.connect(db_path) as db:
        # 1. Find DISTINCT material codes that still need backfill
        async with db.execute(
            "SELECT DISTINCT material_code FROM cached_production_bom "
            "WHERE COALESCE(category_name, '') = '' AND material_code != ''"
        ) as cur:
            codes = [r[0] async for r in cur]

        log.info("Codes needing category_name backfill: %d", len(codes))
        if not codes:
            log.info("Nothing to do.")
            return

        # 2. Fetch each distinct code (in-memory cache implicit — we already deduped)
        resolved: dict[str, str] = {}
        unresolved: list[str] = []
        for i, code in enumerate(codes, 1):
            name = fetch_category_name(sdk, code)
            if name:
                resolved[code] = name
            else:
                unresolved.append(code)
            if i % 50 == 0:
                log.info("Progress: %d/%d resolved=%d unresolved=%d",
                         i, len(codes), len(resolved), len(unresolved))

        log.info(
            "Fetch complete. resolved=%d unresolved=%d",
            len(resolved), len(unresolved),
        )

        if unresolved:
            log.warning("First 10 unresolved codes: %s", unresolved[:10])

        # 3. Bulk UPDATE
        await db.executemany(
            "UPDATE cached_production_bom SET category_name = ? WHERE material_code = ?",
            [(name, code) for code, name in resolved.items()],
        )
        await db.commit()

        # 4. Report distribution
        async with db.execute(
            "SELECT COALESCE(category_name, '(empty)') AS c, COUNT(*) AS n "
            "FROM cached_production_bom GROUP BY c ORDER BY n DESC"
        ) as cur:
            dist = [(r[0], r[1]) async for r in cur]
        log.info("=== Distribution after backfill ===")
        for c, n in dist:
            log.info("  %-12s %d", c, n)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(PROJECT_ROOT / "data/quickpulse.db"))
    args = p.parse_args()
    asyncio.run(main(Path(args.db)))
