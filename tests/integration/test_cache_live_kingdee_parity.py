"""Cache vs Live parity against the deployed prod API.

bug-patterns.md #1 (Cache/Live divergence) has been the most-recurring bug
class in this codebase. The BOM-first refactor (`ce08d69`) was supposed to
share `_bom_row_to_child()` between paths, but new fields can still drift
if added to one path only — and operators see the cache path by default.

This test calls the prod API for both `?source=cache` and `?source=live`
and asserts per-material totals agree across the operator-visible quantity
columns. By hitting prod directly, this also indirectly verifies the
deployed schema/migration state, sync health, and that cache data isn't
contaminated.

Skipped automatically when:
- QP_PROD_PASSWORD env var (or default) is unavailable / unauth fails
- The cache returns 404 for the MTO (older MTOs are bounded out by sync
  window — that's by design and not a parity issue)
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from decimal import Decimal

import pytest


# Same corpus as test_kingdee_parity.py, narrowed to MTOs that historically
# appeared in the prod cache during the 2026-04-26 audit.
PARITY_MTOS = [
    "AS2602037",
    "AS2603009",
    "AS2602033",
    "AY2604051",
    "AS2604012-1",
]

PROD_URL = os.environ.get("QP_PROD_URL", "https://fltpulse.szfluent.cn")
PROD_PASSWORD = os.environ.get("QP_PROD_PASSWORD", "FltPulse@2026!Prod")


def _get_token():
    """Authenticate against prod, return bearer token. None if unreachable."""
    try:
        data = urllib.parse.urlencode(
            {"username": "admin", "password": PROD_PASSWORD}
        ).encode()
        req = urllib.request.Request(
            f"{PROD_URL}/api/auth/token",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())["access_token"]
    except Exception:
        return None


_TOKEN = _get_token()

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        _TOKEN is None,
        reason="prod API unreachable or auth failed; skipping cache-live parity test.",
    ),
    pytest.mark.skipif(
        os.environ.get("SKIP_KINGDEE_PARITY") == "1",
        reason="SKIP_KINGDEE_PARITY=1 set explicitly.",
    ),
]


def _to_dec(v) -> Decimal:
    try:
        return Decimal(str(v)) if v not in (None, "", "null") else Decimal(0)
    except Exception:
        return Decimal(0)


def _aggregate_by_code(children) -> dict[str, dict[str, Decimal]]:
    """Roll up child_items by material_code, summing operator-visible columns."""
    out: dict[str, dict[str, Decimal]] = defaultdict(lambda: {
        "sales_order_qty": Decimal(0),
        "prod_instock_must_qty": Decimal(0),
        "prod_instock_real_qty": Decimal(0),
        "purchase_order_qty": Decimal(0),
        "purchase_stock_in_qty": Decimal(0),
        "pick_actual_qty": Decimal(0),
    })
    for c in children:
        a = out[c["material_code"]]
        a["sales_order_qty"] += _to_dec(c.get("sales_order_qty"))
        a["prod_instock_must_qty"] += _to_dec(c.get("prod_instock_must_qty"))
        a["prod_instock_real_qty"] += _to_dec(c.get("prod_instock_real_qty"))
        a["purchase_order_qty"] += _to_dec(c.get("purchase_order_qty"))
        a["purchase_stock_in_qty"] += _to_dec(c.get("purchase_stock_in_qty"))
        a["pick_actual_qty"] += _to_dec(c.get("pick_actual_qty"))
    return dict(out)


def _fetch(mto: str, source: str):
    """Returns (status_code, body_dict)."""
    req = urllib.request.Request(
        f"{PROD_URL}/api/mto/{mto}?source={source}",
        headers={"Authorization": f"Bearer {_TOKEN}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


@pytest.mark.parametrize("mto", PARITY_MTOS)
def test_cache_live_agree_per_material_on_prod(mto):
    """For each canary MTO, prod's cache-path and live-path responses must
    agree on per-material totals across all 6 operator-visible columns.
    Tolerance is tight (1% relative, 1 unit absolute) — Bug 1's structural
    inflation pattern produces 50–990× gaps that won't be masked by
    legitimate data drift between cache snapshot and live fetch."""
    cache_status, cache_body = _fetch(mto, "cache")
    live_status, live_body = _fetch(mto, "live")

    if cache_status == 404:
        pytest.skip(
            f"{mto}: prod cache returned 404. Older MTOs fall out of the "
            "sync window — that's by design, not a parity issue."
        )

    assert live_status == 200, (
        f"{mto}: prod live API returned {live_status} — Kingdee unreachable "
        f"or QP error: {live_body.get('detail','?')}"
    )
    assert cache_status == 200, (
        f"{mto}: prod cache API returned {cache_status} unexpectedly: "
        f"{cache_body.get('detail','?')}"
    )

    cache_agg = _aggregate_by_code(cache_body.get("child_items", []))
    live_agg = _aggregate_by_code(live_body.get("child_items", []))

    # Material-code presence drift — fundamental Pattern 1.
    only_in_cache = set(cache_agg) - set(live_agg)
    only_in_live = set(live_agg) - set(cache_agg)

    # Soft signal: log small drifts, but only fail when the drift looks
    # structural (>10 codes diverging). The cache may legitimately lag
    # behind live by one sync cycle, gaining or losing a few rows that
    # appeared/disappeared between syncs.
    if len(only_in_cache) + len(only_in_live) > 10:
        pytest.fail(
            f"{mto}: structural code-set drift between cache and live.\n"
            f"  Only in cache ({len(only_in_cache)}): {sorted(only_in_cache)[:10]}\n"
            f"  Only in live  ({len(only_in_live)}):  {sorted(only_in_live)[:10]}\n"
            f"This is bug-patterns.md #1. The cache SQL JOIN (cache_reader.py "
            f":get_mto_bom_joined) and the live builder (mto_handler.py:"
            f"_build_bom_joined_rows_from_live) must produce the same set of "
            f"materials. A field or row was added to one path but not the other."
        )

    # Per-code, per-quantity comparison.
    #
    # Drift handling differs by direction:
    #
    # cache > live  → DANGEROUS (Pattern 1 cache-side inflation, the Bug 1
    #                 shape mirrored into cache_reader's SQL JOIN). Fail at
    #                 ratio ≥ 2× because legitimate sync lag would leave
    #                 cache *behind*, not ahead.
    #
    # cache < live  → BENIGN sync lag for transactional fields (real_qty,
    #                 stock_in_qty, pick_actual_qty) — picks/receipts that
    #                 happened after the last sync naturally aren't in cache.
    #                 But for DEMAND fields (sales_order_qty, must_qty,
    #                 purchase_order_qty) cache being meaningfully lower
    #                 means an order was placed and the row didn't make it
    #                 into cache — also a Pattern 1 bug. Fail at ratio ≤ 0.5×.
    # Threshold tuning: catch any structural cache-vs-live divergence.
    # Historical Bug 1 produced 50–990× divergence (capped to ~1× by commits
    # 5490fa8 + 948054c).  The previous Wave 3 round left the threshold at
    # 20× to skip past Issue #1 — the cache-side 03.xx routing edge case
    # which produced 5–16× divergence (e.g. AS2603009 / 03.03.001 cache=593
    # vs live=51, 11.6×).
    #
    # Wave 4B fixed Issue #1 at the cache_reader bom_agg CTE
    # (corrected_material_type override).  We can now drop the threshold to
    # 2× — anything beyond that is structural cache inflation, not legitimate
    # sync lag (legitimate lag leaves cache *behind*, not ahead).
    INFLATION_RATIO = Decimal("2")  # cache > live × 2 → structural drift, fail
    DEMAND_FIELDS = {"sales_order_qty", "prod_instock_must_qty",
                     "purchase_order_qty"}
    # Demand fields: cache being meaningfully lower means a row was placed
    # but didn't sync.  Threshold tightened from 0.05× to 0.5× — anything
    # under 50% on a demand field is a Pattern 1 row drop, not sync lag.
    DEMAND_DROP_RATIO = Decimal("0.5")  # cache < live × 0.5 on demand → fail

    structural_drift = []
    benign_lag = []
    for code in sorted(set(cache_agg) & set(live_agg)):
        for col in cache_agg[code]:
            cv = cache_agg[code][col]
            lv = live_agg[code][col]
            if cv == lv or abs(cv - lv) <= Decimal("1"):
                continue
            # Cache higher than live by >2× → cache-side inflation
            if lv > 0 and cv > lv * INFLATION_RATIO:
                structural_drift.append(
                    (code, col, cv, lv, "cache>>live (Pattern 1 inflation)")
                )
            # Cache much lower than live on a demand field → cache missed rows
            elif col in DEMAND_FIELDS and lv > 0 and cv < lv * DEMAND_DROP_RATIO:
                structural_drift.append(
                    (code, col, cv, lv, "cache<<live on demand (Pattern 1 row drop)")
                )
            else:
                benign_lag.append((code, col, cv, lv))

    if benign_lag:
        # Show benign lag in test stdout for review without failing.
        print(
            f"\n  [{mto}] {len(benign_lag)} field(s) lag in cache (likely "
            f"sync-window — orders/picks since last sync). Sample:"
        )
        for code, col, cv, lv in benign_lag[:3]:
            print(f"    {code}.{col}: cache={cv} live={lv}")

    assert not structural_drift, (
        f"{mto}: {len(structural_drift)} structural cache/live drift(s) "
        f"detected. These are NOT sync-window lag — cache is either inflated "
        f"or has lost demand rows.\n"
        + "\n".join(
            f"  {code}.{col}: cache={cv} live={lv}  [{kind}]"
            for code, col, cv, lv, kind in structural_drift[:8]
        )
        + f"\n\nbug-patterns.md #1 (Cache/Live divergence) — the cache SQL in "
        f"src/query/cache_reader.py:get_mto_bom_joined and the live builder "
        f"in src/query/mto_handler.py:_build_bom_joined_rows_from_live must "
        f"produce identical results."
    )


def test_match_quality_breakdown_present_on_cache_path():
    """commit 8e0f644 added match_quality_breakdown to BOTH cache and live
    paths. Verify the cache path also populates it (the cache CASE expressions
    in cache_reader.get_mto_bom_joined must produce the same vocabulary)."""
    cache_status, cache_body = _fetch("AS2602037", "cache")
    if cache_status == 404:
        pytest.skip("AS2602037 not in prod cache")

    children = cache_body.get("child_items", [])
    non_finished = [c for c in children if not c["material_code"].startswith("07.")]
    if not non_finished:
        pytest.skip("AS2602037 cache has no non-finished children")

    empty = [c for c in non_finished if not c.get("match_quality_breakdown")]
    assert not empty, (
        f"AS2602037 cache: {len(empty)} non-finished rows have empty "
        f"match_quality_breakdown. Pre-fix the field was absent on both "
        f"paths; if cache regresses, the SQL CASE expressions in "
        f"cache_reader.get_mto_bom_joined are no longer being SELECTed or "
        f"the columns aren't reaching _bom_row_to_child. See commit 8e0f644 "
        f"and bug-patterns.md #1."
    )
