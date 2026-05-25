# Plan: Fix 包材 (and 委外) missing from dashboard — route on `CategoryID`, not `FMaterialType`

## Status: Complete — shipped 2026-05-22, live-verified 2026-05-25

Commits: `2957933` (CategoryID routing) → `dc503c1` (migration housekeeping) →
`6b54a67`/`f352938` (ship scripts/ into Docker for backfill) → `2724bcf`/`e3d12a2`
(IsPurchase split → revert) → `2199d01` (sub-badge inside 包材 chip).

Live verification on prod (`HEAD=004b7d0`, 2026-05-25):
- `cached_production_bom` has `category_name` populated for 77,821/77,821 rows (100%)
- Distribution: 包装成品 55,536 / 半成品 17,803 / **外销包材 3,888** / **委外加工 585** / 辅料 5 / 主料 4
- 122 distinct 外销包材 materials, 55 distinct 委外加工 materials surface in the cache
- Before the fix these would all have collapsed to 自制 (since PPBOM.FMaterialType=1 for 99.94%)

## Background — see also

- `docs/MATERIAL_CLASSIFICATION_FIELDS_2026-05-09.md` — earlier (partially wrong) investigation that recommended `ErpClsID`
- `docs/probes/probe_erp_cls_routing.py` — the 2026-05-22 probe that overturned that recommendation
- `docs/probes/_probe_output/erp_cls_routing.json` — raw probe output

## Problem

Colleagues report **包材 is missing from the dashboard**. Investigation found:

| Reality (probed live) | Dashboard shows |
|---|---|
| `03.03.001 外箱` (outer carton) is `CategoryID=CHLB03_SYS / 外销包材` | Labeled **自制** |
| `08.01.45 成人PU帽` is `CategoryID=CHLB08_SYS / 委外加工` | Labeled **自制** |
| 4,259 cached BOM rows with `03.xx` prefix (packaging) | All labeled **自制** |
| 0 cached BOM rows in the entire system label as 委外 | 委外 chip is dead |

### Root cause

`src/query/mto_handler.py:1535` routes the display label on `row.material_type`, which traces back to `PRD_PPBOM.FMaterialType` (`src/readers/factory.py:294`). In this Fluent K3Cloud tenant, **`FMaterialType` is `1` for 99.94% of PPBOM rows** (88,175 / 88,225 in local cache) — it carries no routing information.

### Why the previously-planned fix won't work

The 2026-05-09 plan (`docs/MATERIAL_CLASSIFICATION_FIELDS_2026-05-09.md`) proposed switching to `MaterialBase.ErpClsID`. Today's probe shows **`ErpClsID` is also flat** in this tenant — 22 of 23 sampled codes come back as `2`, including outer cartons, inner boxes, blisters, and outsourced caps. Switching `FMaterialType` → `ErpClsID` would have moved one broken classifier to another.

### The correct routing field

`BD_MATERIAL.MaterialBase.CategoryID.Number` (Kingdee 存货类别 system enum). Live data is clean and deterministic:

| `CategoryID.Number` | `CategoryID.Name` | Display label | Notes |
|---|---|---|---|
| `CHLB01_SYS` | 主料 | 自制 | Raw materials (silicone, PVC) |
| `CHLB02_SYS` | 辅料 | 自制 | Adhesives, tape |
| `CHLB03_SYS` | 外销包材 | **包材** | The 包材 signal |
| `CHLB05_SYS` | 半成品 | 自制 | Self-made intermediates |
| `CHLB07_SYS` | 包装成品 | 成品 | Already handled separately |
| `CHLB08_SYS` | 委外加工 | **委外** | Fixes the dead 委外 chip |
| (null / unknown) | — | 自制 (fallback) | Log a warning |

## Solution

Extend the cache to carry `category_id` per BOM row, sourced from `BD_MATERIAL.MaterialBase.CategoryID.Number`. Route the handler on `category_id` via a static mapping. Keep `material_type` in the schema (don't drop) until rollout is verified.

### Phased design

**Phase 1 — Backend plumbing (1 commit, behind feature flag)**

1. Add `category_id TEXT` and `category_name TEXT` columns to `cached_production_bom` (migration 014).
2. Add `category_id`, `category_name` to `ProductionBOMModel` (`src/readers/models.py`).
3. Extend the PPBOM `FieldMapping` in `factory.py` to pull these from the live API. **Verification needed during implementation**: confirm the dot-chain `FMaterialId.FCategoryID.FNumber` (or equivalent) works in `ExecuteBillQuery`. If not, fall back to a per-material `BD_MATERIAL.View` call (cached in-memory during sync).
4. Update sync writer (`sync_service.py`) to INSERT the two new columns.
5. Update `cache_reader.py` SELECT + `_row_to_*` methods to surface `category_id` on `BOMJoinedRow`.

**Phase 2 — Routing change (1 commit, feature flag off → on)**

6. Add a mapping helper `_category_to_label(category_id) -> (MaterialType, display_name)` keyed by the table above. Put the mapping in `config/mto_config.json` so it's easy to tune.
7. In `mto_handler.py:_bom_row_to_child`, replace the `effective_type = row.material_type` branch with `effective_type = _category_to_label(row.category_id)`. Behind env flag `ROUTE_ON_CATEGORY_ID=true`.
8. Add an observability log when `category_id` is missing or unmapped — these are sync gaps, not handler bugs.

**Phase 3 — Backfill + cutover (1 commit + 1 sync run)**

9. Backfill script (`scripts/backfill_category_id.py`): iterate distinct material codes in `cached_production_bom`, call `BD_MATERIAL.View` (cached, ~few hundred unique codes), UPDATE rows. Estimated runtime: ~5-10 minutes for the local cache.
10. Run backfill in dev → flip `ROUTE_ON_CATEGORY_ID=true` in dev → manual verification → roll to prod.

### Files to modify

| File | Change | Phase |
|---|---|---|
| `data/quickpulse.db` schema → new migration `src/database/migrations/014_add_category_id.sql` | add 2 columns + index | 1 |
| `src/readers/models.py` | add `category_id`, `category_name` to `ProductionBOMModel` | 1 |
| `src/readers/factory.py` | add `FMaterialId.FCategoryID.*` FieldMappings | 1 |
| `src/sync/sync_service.py` | INSERT new columns | 1 |
| `src/query/cache_reader.py` | SELECT + propagate to `BOMJoinedRow` | 1 |
| `src/query/mto_handler.py` | new `_category_to_label` + flip `_bom_row_to_child` routing | 2 |
| `config/mto_config.json` | add `category_to_label` mapping table | 2 |
| `src/config.py` | add `ROUTE_ON_CATEGORY_ID` env flag | 2 |
| `scripts/backfill_category_id.py` | new — one-time backfill | 3 |
| `tests/unit/test_cache_reader.py` | extend row tuples (positional!) | 1 |
| `tests/unit/test_mto_handler.py` | new tests for category routing | 2 |

### Files NOT to touch

- `src/frontend/dashboard.html`, `dashboard.js` — the 包材/委外 filter chips and badge styles already exist. No frontend change needed.

## Test Cases

### Unit Tests (Phase 1)

- [ ] `test_cache_reader` row tuple round-trip: `category_id="CHLB03_SYS"` is persisted and retrieved
- [ ] `test_production_bom_model` accepts `category_id` and `category_name` with sensible defaults (`""`)
- [ ] `test_sync_service` writes both new columns from a synthetic Kingdee row

### Unit Tests (Phase 2)

- [ ] `_category_to_label("CHLB03_SYS")` returns `(MaterialType.PURCHASED, "包材")`
- [ ] `_category_to_label("CHLB08_SYS")` returns `(MaterialType.SUBCONTRACTED, "委外")`
- [ ] `_category_to_label("CHLB05_SYS")` returns `(MaterialType.SELF_MADE, "自制")`
- [ ] `_category_to_label("")` (missing) falls back to `(MaterialType.SELF_MADE, "自制")` AND emits a warning log
- [ ] `_category_to_label("UNKNOWN_CODE")` falls back identically AND emits a warning log
- [ ] With `ROUTE_ON_CATEGORY_ID=false`, handler still uses legacy `material_type` (backward compat)
- [ ] With `ROUTE_ON_CATEGORY_ID=true`, handler uses category routing

### Integration Tests (Phase 2)

- [ ] For a known MTO containing both `03.xx` and `05.xx` materials, `get_status()` returns children with both `material_type_name="包材"` and `material_type_name="自制"` — counts > 0 for each
- [ ] For a known MTO containing `08.xx` outsourced material, at least one child returns `material_type_name="委外"`

### Manual Verification (Phase 3, dev only)

1. Run backfill in dev: `python3 scripts/backfill_category_id.py --env=dev`
2. SQL check: `SELECT category_id, COUNT(*) FROM cached_production_bom GROUP BY category_id` — expect ≥4 distinct non-empty values
3. Open dev dashboard, query AS2603021 (the screenshot MTO)
4. **Expected**: the 247 rows split across 自制 / 包材 chips. Previously printed packaging rows (`05.20.01.11.066` etc.) move into 包材 IF they're truly `CHLB03_SYS`. If they stay 自制 because `MaterialGroup.Number` says `05.20` → `CHLB05_SYS`, that's also correct (printed half-finished, not packaging).
5. Verify the 包材 chip toggle actually filters rows now (not just decorative)
6. Verify at least one 委外 row appears for any MTO containing `08.xx`
7. Spot-check that no row that USED to display correctly (e.g. 07.xx 成品) regressed

## Acceptance Criteria

- [ ] In dev, an MTO with `03.xx` components shows ≥1 row labeled 包材
- [ ] In dev, an MTO with `08.xx` components shows ≥1 row labeled 委外
- [ ] In dev, an MTO with only `05.xx` self-made parts shows 0 rows labeled 包材 / 委外 (no false positives)
- [ ] All existing tests pass (`pytest --ignore=tests/e2e --ignore=tests/integration`)
- [ ] Backfill script is idempotent (re-running doesn't duplicate or corrupt data)
- [ ] Warning log surfaces when `category_id` is missing — confirms gap visibility per "feedback-deployment-friction" guidance
- [ ] Dashboard load time for AS2603021 is within ±10% of current (no perf regression)

## Verification To Do BEFORE Phase 1 implementation

- [ ] **Confirm `FMaterialId.FCategoryID.FNumber` is queryable via `ExecuteBillQuery`** by extending `docs/probes/probe_erp_cls_routing.py` to do an `ExecuteBillQuery({"FormId": "PRD_PPBOM", "FieldKeys": "FMaterialId.FNumber,FMaterialId.FCategoryID.FNumber"})` on a known MTO. If it errors, fall back to per-material `View` calls during sync (slower but works).
- [ ] **Confirm sample mapping holds for `04.xx` and `09.xx` codes** (not in initial probe — may exist in other MTOs).

## Risks & Open Questions

| Risk | Mitigation |
|---|---|
| Sync slowdown if dot-chain doesn't work and we need per-material `View` calls | Cache the `BD_MATERIAL` lookup in memory during a sync run; ~few thousand distinct codes total |
| Users see a dramatic UI change (lots of rows reclassified) | Communicate in a release note: "包材 chip now functional — same data, correct labels" |
| Future material categories Fluent adds (`CHLB09_SYS`?) silently fall through to 自制 fallback | Warning log + a periodic check could surface unmapped codes for human review |
| `material_type` column becomes dead weight | Leave in place for one release cycle; remove in a follow-up PR once stability is confirmed |

## Memory updates after merge

- Mark `kingdee-classification.md` `ErpClsID` claim as **incorrect for this tenant** — point to this plan
- Add a new memory entry: `kingdee-routing-uses-categoryid.md` with the mapping table
- Update `docs/MATERIAL_CLASSIFICATION_FIELDS_2026-05-09.md` with a footer pointing here
