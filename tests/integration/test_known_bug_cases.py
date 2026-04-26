"""Regression pins for the specific (MTO, material) cases that the
2026-04-26 18-MTO Kingdee comparison surfaced.

Where `test_kingdee_parity.py` enforces broad invariants across a corpus,
this file pins individual historical cases to their post-fix values. Each
test names the bug class, the original pre-fix number, and the post-fix
number — so when one fails, the diagnostic message immediately tells the
reader which bug came back and what the operator-visible value used to be.

These tests are deliberately surgical: they don't enumerate the full
universe of (MTO, material) pairs. Each pin is one chosen case where the
fix made a meaningful, measurable change.

Skipped automatically when KINGDEE_* env vars are absent.
"""
import os
from collections import defaultdict
from decimal import Decimal

import pytest

# Local-dev convenience: load .env for credentials (CI uses GitHub Secrets).
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from src.config import get_config
from src.kingdee.client import KingdeeClient
from src.query.mto_handler import MTOQueryHandler
from src.readers import (
    MaterialPickingReader,
    ProductionBOMReader,
    ProductionOrderReader,
    ProductionReceiptReader,
    PurchaseOrderReader,
    PurchaseReceiptReader,
    SalesDeliveryReader,
    SalesOrderReader,
    SubcontractingOrderReader,
)


def _kingdee_credentials_present() -> bool:
    return all(
        os.environ.get(k)
        for k in ("KINGDEE_SERVER_URL", "KINGDEE_ACCT_ID", "KINGDEE_USER_NAME",
                  "KINGDEE_APP_ID", "KINGDEE_APP_SEC")
    )


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _kingdee_credentials_present()
        or os.environ.get("SKIP_KINGDEE_PARITY") == "1",
        reason="KINGDEE_* env vars not set or SKIP_KINGDEE_PARITY=1.",
    ),
]


@pytest.fixture(scope="module")
def real_handler():
    config = get_config()
    client = KingdeeClient(config.kingdee)
    return MTOQueryHandler(
        production_order_reader=ProductionOrderReader(client),
        production_bom_reader=ProductionBOMReader(client),
        production_receipt_reader=ProductionReceiptReader(client),
        purchase_order_reader=PurchaseOrderReader(client),
        purchase_receipt_reader=PurchaseReceiptReader(client),
        subcontracting_order_reader=SubcontractingOrderReader(client),
        material_picking_reader=MaterialPickingReader(client),
        sales_delivery_reader=SalesDeliveryReader(client),
        sales_order_reader=SalesOrderReader(client),
        memory_cache_enabled=False,
    )


def _to_dec(v) -> Decimal:
    try:
        return Decimal(str(v)) if v not in (None, "", "null") else Decimal(0)
    except Exception:
        return Decimal(0)


def _sum_must_for_code(children, code: str) -> Decimal:
    """Sum prod_instock_must_qty across all aux variants of a self-made code."""
    return sum(
        (_to_dec(c.prod_instock_must_qty) for c in children if c.material_code == code),
        Decimal(0),
    )


def _rows_for_code(children, code: str):
    return [c for c in children if c.material_code == code]


# ============================================================================
# Bug 1 pins — BOM-rollup demand inflation (commits 5490fa8 + 948054c)
#
# Each test pins SUM(must_qty) for a specific (MTO, code) where the fix
# brought the value down from a structural N× inflation to the team's
# actual PRD_MO production target.
# ============================================================================
@pytest.mark.asyncio
async def test_bug1_AK2510034_05_02_08_027_box_must_match_PRDMO_target(real_handler):
    """05.02.08.027 盒子 in AK2510034: pre-fix=187,200 (50× inflation),
    post-fix=3,744 (matches PRD_MO target). The most-cited Bug 1 case."""
    response = await real_handler.get_status("AK2510034", use_cache=False, source="live")
    must_total = _sum_must_for_code(response.children, "05.02.08.027")
    assert Decimal("3700") <= must_total <= Decimal("3800"), (
        f"AK2510034 / 05.02.08.027 (盒子): SUM(must_qty)={must_total}. "
        f"Expected ~3744 (PRD_MO production target). Pre-Bug-1-fix value was "
        f"187,200 (50× via PPBOM cross-parent rollup). If this test fails, "
        f"check src/query/mto_handler.py:_build_bom_joined_rows_from_live and "
        f"bug-patterns.md #10."
    )


@pytest.mark.asyncio
async def test_bug1_AS2603009_05_07_02_01_shoetree_must_match_PRDMO_target(real_handler):
    """AS2603009 / 05.07.02.01 鞋撑: pre-fix=1,130,160 (680× inflation,
    worst case observed). Post-fix=1,662. Required Tier-3 PRD_MO all-aux
    rollup (commit 948054c follow-up to 5490fa8)."""
    response = await real_handler.get_status("AS2603009", use_cache=False, source="live")
    must_total = _sum_must_for_code(response.children, "05.07.02.01")
    assert Decimal("1600") <= must_total <= Decimal("1700"), (
        f"AS2603009 / 05.07.02.01 (鞋撑): SUM(must_qty)={must_total}. "
        f"Expected ~1662. Pre-fix value was 1,130,160 (680×) because PPBOM had "
        f"aux=0 with FMustQty=1,130,160 and PRD_MO sat at aux=105814 — Tier-2 "
        f"fallback missed and Tier-3 rollup wasn't yet implemented. If this "
        f"fails, _lookup_mo_qty's Tier-3 branch is broken; see commit 948054c."
    )


@pytest.mark.asyncio
async def test_bug1_AS2602037_05_06_02_21_watervalve_must_match_PRDMO_target(real_handler):
    """AS2602037 / 05.06.02.21 水阀: pre-fix=120,780 (6× inflation).
    Post-fix=20,130 (matches PRD_MO target)."""
    response = await real_handler.get_status("AS2602037", use_cache=False, source="live")
    must_total = _sum_must_for_code(response.children, "05.06.02.21")
    assert Decimal("19500") <= must_total <= Decimal("21000"), (
        f"AS2602037 / 05.06.02.21 (水阀): SUM(must_qty)={must_total}. "
        f"Expected ~20,130. Pre-fix value was 120,780 (6×) — same Tier-3 case "
        f"as 05.07.02.01 above. If this fails, the Tier-3 PRD_MO rollup or the "
        f"Bug-1 BOM-rollup cap regressed."
    )


# ============================================================================
# Bug 5b/6 pins — purchased multi-aux variants drop (commit 826e87a)
#
# Pre-fix: only the first PUR aux variant emitted as a synthetic row.
# Post-fix: every distinct PUR aux variant gets its own row.
# ============================================================================
@pytest.mark.asyncio
async def test_bug5b_AS2602037_03_23_001_decals_emit_all_aux_variants(real_handler):
    """AS2602037 / 03.23.001 贴纸: 2 aux variants. Pre-fix QP returned only
    the first (122 of 1,233 demand, 90% loss). Post-fix returns 2 rows
    summing to ~1,233."""
    response = await real_handler.get_status("AS2602037", use_cache=False, source="live")
    rows = _rows_for_code(response.children, "03.23.001")
    total_demand = sum((_to_dec(r.purchase_order_qty) for r in rows), Decimal(0))
    assert len(rows) >= 2, (
        f"AS2602037 / 03.23.001 (贴纸): got {len(rows)} aux row(s). "
        f"Expected ≥2 (Kingdee has 2 distinct aux variants). Pre-Bug-5b/6 fix "
        f"emitted only the first via the code-only `covered_codes` dedup. "
        f"If this fails, src/query/mto_handler.py block 2b is back to using "
        f"covered_codes_synthetic — see bug-patterns.md #11."
    )
    assert Decimal("1200") <= total_demand <= Decimal("1300"), (
        f"AS2602037 / 03.23.001 SUM(purchase_order_qty)={total_demand}. "
        f"Expected ~1,233 across 2 variants. Pre-fix was 122 (first variant only)."
    )


# ============================================================================
# Bug 7 pin — cross-MTO contamination via cached_subcontracting_orders
# (migration 009 + commit cc9ab22)
#
# Pre-fix: DS256203S returned material 07.25.80 with demand=780 even though
# Kingdee had zero rows for that (MTO, material) pair — the row had been
# silently migrated from a sibling MTO (DS242022S-A2 or WS2510003) due to
# UNIQUE not including mto_number.
# Post-fix: schema rebuilt with UNIQUE(bill_no, mto_number, material_code,
# aux_prop_id); the ghost cannot reappear unless the upsert/UNIQUE pair drifts.
# ============================================================================
@pytest.mark.asyncio
async def test_bug7_DS256203S_no_07_25_80_ghost(real_handler):
    """DS256203S must NOT have any child_item for material 07.25.80.
    The architectural alignment test (test_schema_upsert_alignment.py) and
    the upsert regression test (test_subcontract_upsert_preserves_distinct_mtos)
    cover the schema/upsert side; this one verifies the user-visible artifact."""
    # Cache and live should both be free of the ghost.
    for source in ("live",):  # cache=true default would auto-fall-through; live is the source of truth here
        response = await real_handler.get_status(
            "DS256203S", use_cache=False, source=source
        )
        ghosts = _rows_for_code(response.children, "07.25.80")
        assert not ghosts, (
            f"DS256203S source={source}: 07.25.80 ghost row reappeared "
            f"({len(ghosts)} row(s)). Pre-fix this happened because the "
            f"cached_subcontracting_orders UNIQUE excluded mto_number, so a "
            f"sibling MTO's subcontract record migrated under DS256203S. "
            f"Migration 009 fixed the schema; if this regresses, the "
            f"upsert is back to setting mto_number=excluded.mto_number on "
            f"conflict — see bug-patterns.md #5 and commit cc9ab22."
        )


@pytest.mark.asyncio
async def test_bug7_production_orders_DS256203S_no_07_01_80_ghost(real_handler):
    """DS256203S must NOT have any child_item for material 07.01.80 (Wave 4A).

    Pre-fix DS256203S returned 18 ghost 07.xx rows (07.01.06, 07.01.07,
    07.01.78, 07.01.80=941, 07.02.022, 07.02.121, 07.04.078,
    07.05.16.01..06, 07.08.001..003, 07.23.007, 07.23.034, 07.25.84,
    07.33.010, 07.37.001) because cached_production_orders UNIQUE
    excluded mto_number — sibling MTOs (DS242022S-A2 / WS2510003) of
    customer 瑞弧WeaArCo migrated their PRD_MO rows under DS256203S
    on each sync.

    07.01.80=941 is the most-cited example from the prod investigation;
    pinning that single code is the canonical fingerprint of the bug.

    Migration 010 + the upsert fix in _upsert_production_orders close
    the schema/upsert side; the architectural alignment test
    (test_production_orders_unique_includes_mto_number) and the upsert
    regression (test_production_orders_upsert_preserves_distinct_mtos)
    cover those layers. This test verifies the user-visible artifact end
    to end — if it regresses, the upsert is back to silently rewriting
    mto_number on conflict. See bug-patterns.md #5 (Wave 4A)."""
    for source in ("live",):
        response = await real_handler.get_status(
            "DS256203S", use_cache=False, source=source
        )
        ghosts = _rows_for_code(response.children, "07.01.80")
        assert not ghosts, (
            f"DS256203S source={source}: 07.01.80 ghost row reappeared "
            f"({len(ghosts)} row(s)). Pre-Wave-4A this happened because "
            f"cached_production_orders UNIQUE excluded mto_number, so a "
            f"sibling MTO's PRD_MO row migrated under DS256203S "
            f"(prod 2026-04-26 saw qty=941 for this code). Migration 010 "
            f"fixed the schema; if this regresses, the upsert is back to "
            f"setting mto_number=excluded.mto_number on conflict — see "
            f"bug-patterns.md #5 and the Wave 4A commit."
        )


# ============================================================================
# Match-quality observability pin — commit 8e0f644
#
# Every non-finished-goods row should have match_quality_breakdown populated.
# Empty dict is acceptable for 07.xx finished goods (the
# _build_aggregated_sales_child path doesn't populate it — minor known gap).
# ============================================================================
@pytest.mark.asyncio
async def test_match_quality_breakdown_populated_for_non_finished(real_handler):
    """commit 8e0f644 (Surface aux match quality) — non-07.xx rows must have
    match_quality_breakdown populated with the per-source quality labels.
    Empty dict means the live builder didn't populate it, which is the
    pre-fix state."""
    response = await real_handler.get_status("AK2510034", use_cache=False, source="live")
    non_finished = [c for c in response.children if not c.material_code.startswith("07.")]
    empty = [c for c in non_finished if not c.match_quality_breakdown]
    assert not empty, (
        f"{len(empty)} non-finished rows have empty match_quality_breakdown. "
        f"Expected every non-07.xx row to carry the per-source match quality "
        f"({{prod_receipt, pick, purchase_order, …}}). Pre-fix the field was "
        f"absent entirely; if this regresses, the live builder in "
        f"_build_bom_joined_rows_from_live is no longer setting it. "
        f"See commit 8e0f644."
    )

    # Spot-check value shape: at least one row should have a per-source label
    # that is one of the 4 documented tiers.
    ALLOWED = {"exact", "aux_zero_fallback", "all_aux_rollup", "no_match"}
    seen_labels = set()
    for c in non_finished:
        for src, q in (c.match_quality_breakdown or {}).items():
            seen_labels.add(q)
    unknown = seen_labels - ALLOWED
    assert not unknown, (
        f"match_quality_breakdown contains unknown tier labels: {unknown}. "
        f"Allowed: {ALLOWED}. The label vocabulary changed without updating "
        f"this test (or callers in the UI)."
    )


# ============================================================================
# Bug 1 + 5b/6 + 7 cumulative — total mismatches stay below the post-fix level.
#
# This is a soft canary: total mismatch counts can drift slightly with
# Kingdee data over time, but if they jump back up to pre-fix levels it
# signals a bigger regression than the surgical pins above caught.
# ============================================================================
@pytest.mark.asyncio
async def test_AK2510034_total_no_inflation_above_threshold(real_handler):
    """Sanity canary: AK2510034 had 53 BOM-rollup-inflated rows pre-fix.
    Post-fix should have zero rows where SUM(must) > 5× PRD_MO target.
    (test_kingdee_parity.py also enforces this; this is the explicit pin.)"""
    response = await real_handler.get_status("AK2510034", use_cache=False, source="live")

    # Pull PRD_MO targets to compare against
    config = get_config()
    client = KingdeeClient(config.kingdee)
    pr = ProductionOrderReader(client)
    prd_rows = await pr.fetch_by_mto("AK2510034")
    targets: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    for r in prd_rows:
        targets[r.material_code] += _to_dec(getattr(r, "qty", 0))

    inflated = []
    by_code = defaultdict(lambda: Decimal(0))
    for c in response.children:
        if c.material_code.startswith("05."):
            by_code[c.material_code] += _to_dec(c.prod_instock_must_qty)
    for code, total in by_code.items():
        target = targets.get(code)
        if target and target > 0 and total > target * Decimal(5):
            inflated.append((code, total, target, total / target))

    assert not inflated, (
        f"AK2510034 had {len(inflated)} self-made rows where SUM(must) > 5× "
        f"PRD_MO target — these are the Bug 1 inflation shape returning. "
        f"Worst 3:\n"
        + "\n".join(f"  {c}: must={m} target={t} ratio={r:.0f}×"
                    for c, m, t, r in sorted(inflated, key=lambda x: -x[3])[:3])
    )
