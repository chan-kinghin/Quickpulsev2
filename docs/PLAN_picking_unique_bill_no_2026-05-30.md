# Plan: cached_material_picking UNIQUE must include bill_no (Pattern 5 fix)

## Status: In Progress

## Design Spec
### Problem
`cached_material_picking` is the **only** document cache table whose UNIQUE key
omits the document `bill_no`. Key is `(mto_number, material_code, ppbom_bill_no,
aux_prop_id)`; the sync upsert does DELETE-by-mto then `ON CONFLICT(... same 4 ...)
DO UPDATE`. When one `(mto, material, ppbom, aux)` is picked across **multiple
领料单 (FBillNo)**, the upsert/in-memory-dedup keeps only the LAST doc → the cache
**UNDER-counts** vs live Kingdee. This is bug-patterns.md **Pattern 5** (UNIQUE
narrower than logical identity), already fixed for sibling tables in migrations
009 (subcontract) / 010 (production orders).

**Live proof (probed 2026-05-30):** `DK261025S / 03.11.002` = 3 live pick rows
across 2 bills, over = **81,360**; cache shows over = **43,280**. The 3 rows are
distinct under `(bill_no, ppbom, aux)` (0 residual collisions) → adding `bill_no`
fully un-collapses, no entry-seq column needed.

### Solution
Bring picking in line with every sibling table: UNIQUE =
`(bill_no, mto_number, material_code, ppbom_bill_no, aux_prop_id)`.

1. **schema.sql** — add `bill_no TEXT` column to `cached_material_picking`; change
   inline `UNIQUE(...)` to include `bill_no` (the Pattern-5 guard test
   `test_schema_upsert_alignment.py` parses this inline UNIQUE).
2. **migration 018** — 12-step table rebuild (SQLite can't DROP an inline-UNIQUE
   autoindex). Mirrors migration 010. Backfills `bill_no` from
   `json_extract(raw_data,'$.bill_no')`, COALESCE to ''. Drops old table (kills
   the legacy narrow `idx_pick_unique_v2`), recreates the 3 secondary indexes.
   Runs AFTER 014 so the narrow index it transiently creates is removed.
3. **sync_service.py** `_upsert_material_picking_no_commit` — add `bill_no` to the
   in-memory dedup key, INSERT columns, and `ON CONFLICT(...)` target.

### Files to Modify
- `src/database/schema.sql` (modify table + UNIQUE)
- `src/database/migrations/018_material_picking_unique_with_bill_no.sql` (create)
- `src/sync/sync_service.py` (`_upsert_material_picking_no_commit`)
- `tests/unit/test_sync_service.py` (new regression test)

### Data-preservation note (IMPORTANT — operational)
The migration preserves existing rows but **cannot recover already-collapsed
docs** (only the last bill survived each group). Existing prod/dev data stays
under-counted until a **re-sync** re-populates the now-correct grain. Self-heals
per-MTO as the scheduler re-syncs; a one-time full re-sync (~12 min, OOM-sensitive
— run one env at a time) fixes it immediately.

## Test Cases
- [ ] `test_picking_shared_key_different_bill_kept_separate`: two picks, same
      (mto, material, ppbom, aux), different bill_no → 2 rows, actual_qty SUMs
      (was 1 row before fix)
- [ ] `test_schema_upsert_alignment` (existing guard) stays green with the new
      5-col key
- [ ] existing over-pick / picking sync tests unaffected (bill_no nullable)

## Acceptance Criteria
- [ ] schema UNIQUE == upsert ON CONFLICT == `(bill_no, mto, material, ppbom, aux)`
- [ ] migration 018 applies cleanly on a COPY of the real DB; bill_no backfilled;
      constraint is 5-col
- [ ] full unit suite green
- [ ] (deploy-time) re-sync flagged to operator
