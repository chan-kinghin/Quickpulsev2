# Decision: collapse the MTO-query dual-aggregation → live-only + result cache

## Status: REVISED 2026-05-29 by the parity gate — Phase 3 cutover BLOCKED until routing is made canonical

> **Parity-gate finding (the reason the plan changed).** Ran `scripts/parity_live_vs_cache.py`
> (live vs cache on 8 real MTOs) + `scripts/diag_routing_divergence.py` (root-cause). Result:
> the live and cache aggregations **disagree on routing in BOTH directions, and it is NOT staleness**:
> - `03.06.03.001` (外销包材, IsPurchase=True): CACHE correct (包材/purchase), LIVE wrong (emits a spurious 自制 child + is_purchase=False).
> - `08.12.02.18` (委外加工): LIVE correct (委外), CACHE wrong (包材).
> Neither path is canonical — each has independent Pattern-3 routing bugs. Root cause: routing must
> follow `BD_MATERIAL.CategoryID`, but the cache stores `category_name=''` for PUR-only/synthetic rows
> (→ falls back to 包材) and the live path routes by receipt-form. **Therefore "delete the CTE, trust
> live" is UNSAFE — it would ship live's bugs.** Phase 3 must NOT proceed until ONE canonical, correct
> CategoryID-based routing exists and is verified. This is the dual-aggregation bug farm, confirmed.

> Phase 1 (SDK auth warmup) shipped (`266d2e2`). Phase 1b/2/3 re-sequenced below.

## TL;DR recommendation
Make the **MTO query path live-only**, fronted by the existing in-memory result cache (L1)
plus a small **persistent result cache** (stale-while-revalidate). Delete the duplicated
**`cache_reader.get_mto_bom_joined`** (535-line SQL CTE) + `_row_to_bom_joined` + the cache-path
dedup mirrors — that duplication is the documented #1 bug generator (Pattern 1/2). **Keep
`sync_service` + scheduler + the raw `cached_*` tables** — they are a *separate* consumer
(fleet-wide over-pick/over-ship/freshness alerts) that per-MTO live queries cannot replace.

This is surgical, NOT "delete the whole cache". It removes the dual-compute that generates
bugs, while leaving the bulk-scan substrate the alerts feature legitimately needs.

## Problem & root cause
The same MTO aggregation is computed two ways that must be hand-kept in sync:
- Live: `mto_handler._build_bom_joined_rows_from_live` (~645 lines Python).
- Cache: `cache_reader.get_mto_bom_joined` (~535-line SQL CTE) + `_row_to_bom_joined` positional remap.
Every fix must mirror across both (bug-patterns Pattern 1/2, 5+ recurrences incl. the aux
oscillation). This dual-compute — not "caching" — is the structural bug source.

## Evidence gathered 2026-05-29 (this is why the recommendation is safe)
**Memory** (`scripts/loadtest_live_memory.py`, real python3.11 image under hard `--memory=512m`):
live path fits 512M with huge margin — realistic MTO @12 concurrent = 65 MB (13%); ~10×-real
extreme @12 = 274 MB (54%); never OOM-killed. Memory is NOT a blocker.

**Latency** (`scripts/probe_live_latency.py`, real Kingdee, read-only, laptop→Hangzhou = pessimistic):
- Steady-state cold live query ≈ **1–5 s** (warm runs: 0.9 / 3.45 / 4.52 s). CVM co-located → faster.
- First query of a fresh process ≈ **18 s** = one-time SDK auth/init (NOT per-query). Today's
  startup "cache warming" uses the cache path, so it does NOT warm SDK auth → under live-only the
  first user after a restart pays ~18 s. **Mitigation: warm SDK auth at boot (Phase 1).**
- Bottleneck form is consistently **SAL_SaleOrder** (`sales_order` reader), scales with row count
  — independent optimization target (possibly the close-status fields / missing filter).

## Key nuance — the raw cache has TWO consumers (verified)
- `get_mto_bom_joined` (the dup CTE) is called **only** by the MTO query path (`mto_handler.py:385`).
  → deletable once the query path is live-only.
- Alerts/freshness (`get_over_pick_alerts`/`get_over_ship_alerts`/`table_freshness`) read the raw
  `cached_*` tables with **simple sum-by-mto+material** queries — NOT through the dup CTE, and NOT
  replaceable by per-MTO live calls (fleet-wide scan). → sync + raw tables must STAY.

## Target architecture
- **Compute**: live Python path only (`_fetch_live` → `_build_bom_joined_rows_from_live` → `_bom_row_to_child`).
- **L1**: in-memory TTL result cache (exists) — hot MTOs `<100 ms`.
- **L2-new**: persistent *result* cache — one table `cached_mto_response(mto_number PK, response_json,
  computed_at)`. Stale-while-revalidate: serve last-good instantly, refresh in background. Stores
  OUTPUT not raw rows → **cannot drift from live** (unlike today's re-derivation).
- **Boot**: warm SDK auth (one tiny query) so no user eats the ~18 s.
- **Keep**: `sync_service` + scheduler + raw `cached_*` tables — sole job now = alerts/freshness.
- **Delete**: `get_mto_bom_joined` + `_row_to_bom_joined` + cache-path dedup mirrors
  (`_apply_recv_partial_match_dedup`, etc.).

## Phased rollout (RE-SEQUENCED after the parity finding)
- **Phase 1 — DONE (`266d2e2`):** warm SDK auth at startup. (1b result-cache layer deferred until Phase 2a proves the direction.)
- **Phase 2a — NEW, critical prerequisite: make routing canonical.** PRECISE ROOT CAUSE (traced
  2026-05-29): the routing MAP `_CATEGORY_TO_TYPE` (mto_handler.py:1592) is already correct
  (外销包材→包材, 委外加工→委外, 主料/半成品→自制). The bug is that synthetic/PUR-only rows lack
  `category_name`, so each path hits a different bad fallback:
  - LIVE: empty `category_name` → falls back to legacy `material_type` (mto_handler.py:1619-1621) → 自制.
  - CACHE: the PUR-only synthetic builder HARD-CODES `material_type_name="包材"` (mto_handler.py:544) → ignores category.
  FIX: plumb `FCategoryId` onto the PUR path so every row routes through `_CATEGORY_TO_TYPE`. Scope
  (3-path + migration — handle with the pre-change checklist + TDD):
    - `factory.py`: add `FMaterialId.FCategoryId.FName` (+ `FIsPurchase`) FieldMappings to PurchaseOrder & PurchaseReceipt readers.
    - `readers/models.py`: add `category_name` (+ `is_purchase`) to `PurchaseOrderModel` / `PurchaseReceiptModel`.
    - synthetic PUR-only builders: LIVE `mto_handler.py:~509-546` (drop the hard-coded 包材, set `category_name`) + CACHE `cache_reader.py` synthetic path.
    - migration: `cached_purchase_orders` / `cached_purchase_receipts` get a `category_name` column; `sync_service` writes it; schema.sql + a guarded ADD COLUMN migration (per migration-drift finding).
  Verify against ground truth (03.06.03.001 外销包材→包材, 08.12.02.18 委外加工→委外) before/after.
  Valuable on its own even if we never collapse — it fixes live mislabeling users see today.
- **Phase 2b — clean parity:** re-run parity on a fresh-synced cache (or same-inputs harness) so the
  comparison is staleness-free; require structural parity + explained routing before any cutover.
- **Phase 3 — cutover + delete:** only after 2a/2b are green — route query path to live (+ result cache),
  then delete `get_mto_bom_joined` + `_row_to_bom_joined` + cache-path dedup mirrors. Sync/raw tables stay for alerts.

## Rollback
- Phase 1: remove the flag / revert the two commits (no behavior depended on it).
- Phase 2: flip the flag back to the cache path.
- Phase 3: `git revert` (after this, live is the only path — but it's already the more-trusted path,
  and the cache==live parity guard now runs in CI).

## Acceptance criteria
- [ ] Phase 1: SDK auth warmed at boot (log line; first post-restart live query no longer ~18 s);
      result-cache layer has unit tests; no default-behavior change; gating suite green.
- [ ] Phase 2: live vs old-cache parity holds on a sampled set (documented diffs explained); dev p95
      latency acceptable; alerts/freshness endpoints unaffected.
- [ ] Phase 3: `get_mto_bom_joined` and its remap deleted; only one aggregation path remains;
      alerts/freshness still green; full suite green.

## Risks / open questions
- **SAL_SaleOrder slowness** dominates live latency — worth a separate look (Phase 0/parallel).
- **Result-cache staleness policy**: TTL + SWR refresh cadence; what "fresh enough" means for users.
- **Live becomes the sole query path** → its correctness is now load-bearing (mitigated: it's already
  the trusted path; parity guard is now wired into CI as of `49ddaaf`).
- Sync stays → we do NOT reclaim the ~290 MB sync footprint (acceptable; memory was never the constraint).

## The decision needed from you
Approve Phase 2+ (the cutover + deletion). Phase 1 is safe/additive and I'll start it now per /goal.
Also: keep the persistent result cache (recommended, buys downtime-resilience + snappy repeat views,
drift-proof), or go pure live + L1-only (simpler, but every post-restart/cold view is 1–5 s)?
