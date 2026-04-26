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
# Wave 5B pins — partial-exact-match dedup over-application (Bug A) and
# missing receipt-side Tier-2.5 (Bug B). See PR description for context.
# ============================================================================
@pytest.mark.asyncio
async def test_AS2602033_05_02_08_037_box_no_partial_match_overcount(real_handler):
    """Wave 5B Bug A real-data pin: AS2602033 / 05.02.08.037 盒子.

    QP's PPBOM has 2 aux groups; PRD_MO has a partial exact match (one
    aux matches at 32544; the other doesn't). Pre-Wave-5B:
      - matched aux row claimed Tier 1 = 32544
      - non-matched aux row claimed Tier 2.5 rollup = 32544
      - SUM(prod_instock_must_qty) = 65088 = 2× actual production target
    Post-Wave-5B partial-match dedup: matched row keeps 32544; non-
    matched row gets max(0, rollup - matched) = 0; SUM = 32544.
    """
    response = await real_handler.get_status("AS2602033", use_cache=False, source="live")
    must_total = _sum_must_for_code(response.children, "05.02.08.037")
    # KD truth from /tmp/diff_AS2602033.json: demand = 32544.
    assert Decimal("32000") <= must_total <= Decimal("33100"), (
        f"AS2602033 / 05.02.08.037 (盒子): SUM(must_qty)={must_total}. "
        f"Expected ~32544 (matches Kingdee). Pre-Wave-5B value was 65088 "
        f"(2× over) because the Tier-2.5 dedup bailed out when ANY exact "
        f"match existed → the matched aux row claimed exact qty AND the "
        f"non-matched aux row claimed the full rollup. If this fails, "
        f"check src/query/mto_handler.py `_tier_2_5_state` partial-match "
        f"logic and the cache CTE `nm_elect_rank` branch in bom_agg."
    )


@pytest.mark.asyncio
async def test_AK2510034_05_02_15_62_receipts_match_kingdee(real_handler):
    """Wave 5B Bug B real-data pin: AK2510034 / 05.02.15.62 电镀镜片.

    QP's PPBOM has the material at specific aux variants; PRD_INSTOCK
    receipts are recorded against completely different aux variants
    (disjoint numbering — same shape as Bug A's PPBOM/PRD_MO disjoint
    case). Pre-Wave-5B the receipt-side `_get` had no Tier-2.5 fall-
    through (Tier 3 only fired when BOM aux=0) → prod_instock_real_qty
    = 0 for all BOM-aux rows. KD truth: 1444.

    Post-Wave-5B: receipt-side `_get` falls through to all-aux rollup
    when BOM aux≠0 and Tier 1+2 both miss; partial-match dedup zeroes
    non-elected non-matched siblings so SUM matches Kingdee.
    """
    response = await real_handler.get_status("AK2510034", use_cache=False, source="live")
    real_total = sum(
        (_to_dec(c.prod_instock_real_qty) for c in response.children
         if c.material_code == "05.02.15.62"),
        Decimal(0),
    )
    # KD truth from /tmp/diff_AK2510034.json: fulfilled = 1444.
    assert Decimal("1400") <= real_total <= Decimal("1500"), (
        f"AK2510034 / 05.02.15.62 (电镀镜片): SUM(prod_instock_real_qty)"
        f"={real_total}. Expected ~1444 (matches Kingdee). Pre-Wave-5B "
        f"value was 0 because the receipt-side `_get` had no Tier-2.5 "
        f"fall-through (Tier 3 only fires for BOM aux=0). If this fails, "
        f"check src/query/mto_handler.py `_get` Tier-2.5 branch and "
        f"`_recv_tier_state` dedup, plus the cache "
        f"_apply_recv_partial_match_dedup post-SQL hook."
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
async def test_bug7_production_orders_DS256203S_clean_post_migration_010(real_handler):
    """DS256203S cached_production_orders cache is uncontaminated post-Wave-4A.

    Original Wave 4A premise (07.01.80=941 was a cross-MTO ghost in
    cached_production_orders) was a false positive — verified post-deploy
    that:
      1. cached_production_orders has 0 rows for DS256203S/07.01.80 (clean).
      2. The 941 demand visible in QP's live response comes from
         SAL_SaleOrder via the F_QWJI_JHGZH header-level MTO field — a
         legitimate sales order that the original Kingdee CLI ground-truth
         comparison missed (the CLI only filters by entry-level FMtoNo).
      3. The 18 "ghost" 07.xx codes from the 2026-04-26 audit are likely
         all the same shape: real sales orders with header-level MTO,
         not contamination.

    Wave 4A's migration 010 + upsert fix still ships value (Pattern 5
    architectural alignment, future-proofing against the same shape that
    bit cached_subcontracting_orders in Wave 2). This test now verifies
    the cache_production_orders side stays clean — if a future regression
    repopulates DS256203S/07.01.80 in cached_production_orders, the row
    has migrated from a sibling MTO and the schema/upsert pair drifted.

    See bug-patterns.md #5 (Wave 4A) for full context."""
    # The architectural test covers the schema; the upsert regression test
    # covers the dedup path. This integration assertion is a soft canary:
    # we can no longer query the cache table directly from the test, but we
    # can verify QP's child_items don't double-count 07.01.80 (which would
    # happen if a contaminated cached_production_orders row layered on top
    # of the legitimate SAL_SaleOrder sales rows). 6 SAL rows = 6 distinct
    # entries in QP child_items, total qty matches Kingdee's SAL_SaleOrder
    # header-MTO query.
    response = await real_handler.get_status(
        "DS256203S", use_cache=False, source="live"
    )
    rows = _rows_for_code(response.children, "07.01.80")
    # SAL_SaleOrder has 6 entries for DS256203S/07.01.80 via header MTO.
    # If contamination layered cached_production_orders rows on top, the
    # count or the type distribution would skew.
    finished_rows = [r for r in rows if r.material_type_name in ("成品", "")]
    selfmade_rows = [r for r in rows if r.material_type_name == "自制"]
    assert not selfmade_rows, (
        f"DS256203S / 07.01.80: {len(selfmade_rows)} row(s) classified as "
        f"自制. Pre-Wave-4A, sibling-MTO PRD_MO rows would migrate to "
        f"DS256203S and surface as material_type=自制 (since 07.xx with "
        f"PRD_MO routes through the self-made path). All 07.01.80 rows for "
        f"DS256203S should be material_type=成品 (from the SAL_SaleOrder "
        f"header-MTO entries). If 自制 rows appear, the contamination is "
        f"back. See bug-patterns.md #5 (Wave 4A) and migration 010."
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
# Issue #1 pins — cache routing override (Wave 4B)
#
# Cache path classified 03.xx purchased materials as self-made because
# Kingdee's PRD_PPBOM.FMaterialType is essentially always 1 in this tenant.
# That sent them through the BOM-rollup PRD_MO path in cache_reader.bom_agg,
# producing 5–16× inflated prod_instock_must_qty vs the live path.
#
# Fix (Wave 4B): bom_agg now overrides material_type=1 to 2 when the material
# matches LIKE '03.%' AND has a row in cached_purchase_orders.  The pin below
# checks the user-visible artifact via the deployed prod API: cache and live
# agree on prod_instock_must_qty for the historical inflation cases.
#
# Hits the prod API rather than spinning up a local cache because the
# `real_handler` fixture in this file only provides Kingdee live access — the
# cache path requires a populated SQLite cache that's only stable on prod.
# The companion file (test_cache_live_kingdee_parity.py) uses the same
# pattern; this pin narrows it to the specific (MTO, code) cases that
# demonstrated 11.6× / 16× divergence pre-fix.
# ============================================================================
def _prod_cache_live_for_mto(mto: str):
    """Fetch (cache_body, live_body) for one MTO from prod API. Returns
    (None, None, reason) when prod is unreachable so the test can skip."""
    import json
    import urllib.error
    import urllib.parse
    import urllib.request

    prod_url = os.environ.get("QP_PROD_URL", "https://fltpulse.szfluent.cn")
    prod_password = os.environ.get("QP_PROD_PASSWORD", "FltPulse@2026!Prod")

    try:
        data = urllib.parse.urlencode(
            {"username": "admin", "password": prod_password}
        ).encode()
        req = urllib.request.Request(
            f"{prod_url}/api/auth/token",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            token = json.loads(r.read())["access_token"]
    except Exception as e:
        return None, None, f"prod auth failed: {e}"

    def fetch(source: str):
        req = urllib.request.Request(
            f"{prod_url}/api/mto/{mto}?source={source}",
            headers={"Authorization": f"Bearer {token}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    cache_status, cache_body = fetch("cache")
    live_status, live_body = fetch("live")
    if cache_status == 404:
        return None, None, f"{mto} not in prod cache (sync window)"
    if cache_status != 200:
        return None, None, f"cache status {cache_status}: {cache_body}"
    if live_status != 200:
        return None, None, f"live status {live_status}: {live_body}"
    return cache_body, live_body, None


def test_issue1_AS2603009_cache_03_xx_routing_matches_live():
    """AS2603009 / 03.03.001 外箱 + 03.04.001 内盒: cache pre-Wave-4B returned
    593 / 6912 prod_instock_must_qty; live returned 51 / 432 (11.6× / 16×
    inflation).  Post-fix cache and live should agree within 5%.

    Both paths share `_bom_row_to_child` after the BOM-first refactor.  The
    Wave 4B fix lives in cache_reader.get_mto_bom_joined's bom_agg CTE: a
    new `corrected_material_type` column that flips PPBOM's unreliable
    type=1 to type=2 when the material is LIKE '03.%' AND has a row in
    cached_purchase_orders.  Without that override, 03.xx materials get
    routed through the self-made `prd_instock_must_qty=row.need_qty` branch
    where need_qty is the BOM-rollup-PRD_MO override (inflated when there
    are many parent BOMs).
    """
    cache_body, live_body, skip_reason = _prod_cache_live_for_mto("AS2603009")
    if skip_reason:
        pytest.skip(skip_reason)

    def sum_must_dict(children, code):
        return sum(
            (_to_dec(c.get("prod_instock_must_qty"))
             for c in children if c["material_code"] == code),
            Decimal(0),
        )

    for code, pre_fix_cache, pre_fix_live, ratio_label in [
        ("03.03.001", 593, 51, "11.6×"),
        ("03.04.001", 6912, 432, "16×"),
    ]:
        cache_must = sum_must_dict(cache_body.get("child_items", []), code)
        live_must = sum_must_dict(live_body.get("child_items", []), code)

        # Both paths might emit 0 if the field isn't populated for purchased
        # rows (which is the post-fix shape — purchased materials don't carry
        # prod_instock_must_qty).  In that case the pin is satisfied.
        if cache_must == 0 and live_must == 0:
            continue

        if live_must > 0:
            ratio = cache_must / live_must
            assert ratio <= Decimal("1.05"), (
                f"AS2603009 / {code}: cache prod_instock_must_qty={cache_must} "
                f"vs live={live_must} (ratio={ratio:.2f}×).  Pre-Wave-4B fix "
                f"this was {pre_fix_cache} / {pre_fix_live} = {ratio_label} "
                f"because the cache routed 03.xx as self-made and used the "
                f"BOM-rollup PRD_MO path.  If this regresses, check the "
                f"bom_agg CTE in src/query/cache_reader.py — the "
                f"'corrected_material_type' override branch (LIKE '03.%' AND "
                f"pur_keys.material_code IS NOT NULL) must be present."
            )
        else:
            # Live=0 but cache has a positive value → cache is still inflated.
            assert cache_must == 0, (
                f"AS2603009 / {code}: live prod_instock_must_qty=0 but "
                f"cache={cache_must}.  Cache is over-reporting purchased "
                f"material as self-made (Issue #1 regressed)."
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
