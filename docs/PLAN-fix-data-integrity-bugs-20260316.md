# Plan: Fix Data Integrity Bugs — Material Name/Code Mismatches & Related Issues

## Status: Not Started

## Problem Statement

A user reported that material code `07.03.040` (潜水镜/diving mask) displays with description `外箱条码贴纸10*10CM` (sticker) — a clear mismatch. Investigation revealed **24 distinct bugs** across 4 layers of the system: reader/field mapping, cache sync, SQL aggregation, and query handler logic. These bugs affect all material types (07.xx, 05.xx, 03.xx) and cause wrong names, wrong quantities, duplicate rows, and cache/live divergence.

## Root Cause Categories

### A. Material Name/Description Mismatches (7 bugs)
### B. Cache vs Live Path Divergence (5 bugs)
### C. Schema & Sync Integrity (8 bugs)
### D. Form & Field Mapping Issues (2 bugs)
### E. Staleness & Freshness Gaps (2 bugs)

---

## Design Spec

### Full Bug Inventory

| # | Category | Severity | File | Description |
|---|----------|----------|------|-------------|
| A1 | Name | **High** | `mto_handler.py` | 07.xx finished goods leak into PPBOM loop — duplicate rows with wrong description |
| A2 | Name | **High** | `cache_reader.py` | `MIN(material_name)` in GROUP BY picks lexicographically smallest, not correct/latest |
| A3 | Name | **High** | `cache_reader.py` | `MIN(material_type)` misroutes quantities to wrong source table |
| A4 | Name | Medium | `cache_reader.py` | `MIN(mo_bill_no)` / `MIN(mto_number)` returns wrong order link |
| A5 | Name | Medium | `models.py` | `PurchaseReceiptModel`, `SubcontractingOrderModel`, `MaterialPickingModel`, `SalesDeliveryModel` all missing `material_name`/`specification` fields |
| A6 | Name | Medium | `factory.py` | STK_InStock, PRD_PickMtrl, SAL_OUTSTOCK configs don't fetch `FMaterialId.FName` |
| A7 | Name | Medium | `cache_reader.py` | Production receipts recover `material_name` from `raw_data` JSON blob — fragile |
| B1 | Diverge | **High** | `mto_handler.py` | Python `_get()` fallback doesn't match SQL dual-JOIN `pr0` behaviour |
| B2 | Diverge | **High** | `cache_reader.py` | Dual-JOIN fallback double-counts receipts when BOM has aux=0 AND variant rows |
| B3 | Diverge | Medium | `mto_handler.py` | `receipt_by_material` for 07.xx built from PPBOM rows, not actual receipts |
| B4 | Diverge | Medium | `mto_handler.py` | `pick_request` for finished goods silently dropped (never read) |
| B5 | Diverge | Medium | `mto_handler.py` | `covered_codes` suppresses orphan receipt/order variants not in PPBOM |
| C1 | Schema | **High** | `schema.sql` | No UNIQUE constraints on 6/7 cache tables — all `ON CONFLICT` clauses are inert |
| C2 | Schema | **High** | `sync_service.py` | All 7 old `_upsert_*` methods are non-transactional (DELETE + INSERT race) |
| C3 | Schema | Medium | `sync_service.py` | `_upsert_production_receipts` (old) omits `bill_no` |
| C4 | Schema | Medium | `sync_service.py` | `_upsert_sales_delivery` (old) omits `bill_no` |
| C5 | Schema | Medium | `sync_service.py` | Redundant DELETE + ON CONFLICT in all `_no_commit` methods (dead ON CONFLICT) |
| C6 | Schema | Medium | `sync_service.py` | Parallel chunks can overwrite data for overlapping MTOs |
| C7 | Schema | Low | `sync_service.py` | `_sync_date_range` swallows chunk exceptions — silent partial failures |
| C8 | Schema | Low | `sync_service.py` | SAL_SaleOrder dedup uses MAX qty, may pick row with wrong name |
| D1 | Field | **High** | `factory.py` | `SUB_SUBREQORDER` used instead of `SUB_POORDER` — wrong Kingdee form ID |
| D2 | Field | Low | `client.py` | `zip(field_keys, row)` silently truncates if API returns fewer columns |
| E1 | Fresh | Low | `cache_reader.py` | `check_freshness` only queries `production_orders`, ignores all other tables |
| E2 | Fresh | Low | `mto_handler.py` | Staleness warning omits `bom_joined_result` |

---

## Stages

### Stage 1: Schema — Add UNIQUE Constraints (Foundation)
**Goal**: Make `ON CONFLICT` clauses actually work; prevent duplicate rows at the DB level.
**Files**:
- `src/database/schema.sql` (modify)
- `src/sync/sync_service.py` (modify — migration logic)

**Changes**:
1. Add UNIQUE constraints to all 7 cache tables:
   - `cached_production_bom`: UNIQUE(mo_bill_no, material_code, aux_prop_id)
   - `cached_purchase_orders`: UNIQUE(bill_no, material_code, aux_prop_id)
   - `cached_subcontracting_orders`: UNIQUE(bill_no, material_code)
   - `cached_production_receipts`: UNIQUE(bill_no, mto_number, material_code, aux_prop_id)
   - `cached_purchase_receipts`: UNIQUE(bill_no, mto_number, material_code, aux_prop_id)
   - `cached_material_picking`: UNIQUE(bill_no, mto_number, material_code, aux_prop_id)
   - `cached_sales_delivery`: UNIQUE(bill_no, mto_number, material_code, aux_prop_id)
2. Add schema version / migration to recreate tables with constraints
3. Fix old `_upsert_*` methods to include `bill_no` (bugs C3, C4)

**Fixes**: C1, C3, C4, C5
**Success Criteria**: `sqlite3 data/quickpulse.db ".schema" | grep UNIQUE` shows constraints on all 7 tables
**Depends on**: —

---

### Stage 2: Fix SQL Aggregation in cache_reader.py
**Goal**: Eliminate wrong `MIN()` aggregations and fix the dual-JOIN double-counting.
**Files**:
- `src/query/cache_reader.py` (modify)

**Changes**:
1. Replace `MIN(bom.material_name)`, `MIN(bom.specification)`, `MIN(bom.aux_attributes)` with a subquery selecting from the row with the latest `synced_at` (bug A2)
2. Replace `MIN(bom.material_type)` with `MAX(bom.material_type)` or latest-synced subquery (bug A3 — MAX is safer: type 2/3 should not collapse to type 1)
3. Replace `MIN(bom.mo_bill_no)`, `MIN(bom.mto_number)` similarly (bug A4)
4. Fix the dual-JOIN `pr0` fallback to avoid double-counting when BOM has both aux=0 and aux>0 rows for the same material (bug B2)
5. Add `AND bom.material_code NOT LIKE '07.%'` to the BOM-joined query WHERE clause (bug A1, cache path)

**Fixes**: A1 (cache), A2, A3, A4, B2
**Success Criteria**: `pytest tests/ -k cache` passes; manual query with known MTO shows correct names and no duplicates
**Depends on**: Stage 1

---

### Stage 3: Fix mto_handler.py Live Path
**Goal**: Eliminate the 07.xx leak, fix cache/live divergence, and handle missing names.
**Files**:
- `src/query/mto_handler.py` (modify)

**Changes**:
1. Add `if bom.material_code.startswith("07."): continue` in primary PPBOM loop (bug A1, live path)
2. Fix `_get()` fallback to match SQL `pr0` behaviour — when `aux != 0` and no exact match, also check `_by_code` total (bug B1)
3. Fix `receipt_by_material` in `_try_cache` to correctly handle 07.xx (bug B3)
4. Remove or fix `pick_request`/`pick_actual` dead params in `_build_aggregated_sales_child` (bug B4)
5. Fix `covered_codes` to only skip if ALL aux variants are covered, not just any (bug B5)
6. Add `bom_joined_result` to staleness check (bug E2)

**Fixes**: A1 (live), B1, B3, B4, B5, E2
**Success Criteria**: Same MTO returns identical results from cache path and live path; `pytest tests/ -k mto` passes
**Depends on**: Stage 2

---

### Stage 4: Fix Reader Field Mappings & Models
**Goal**: Ensure all forms fetch `material_name`/`specification`; fix wrong form ID.
**Files**:
- `src/readers/factory.py` (modify)
- `src/readers/models.py` (modify)

**Changes**:
1. Fix `SUB_SUBREQORDER` → `SUB_POORDER` (bug D1) — **verify with user which form ID is correct first**
2. Add `FMaterialId.FName` and `FMaterialId.FSpecification` to:
   - `PURCHASE_RECEIPT_CONFIG` (STK_InStock) (bug A6)
   - `MATERIAL_PICKING_CONFIG` (PRD_PickMtrl) (bug A6)
   - `SALES_DELIVERY_CONFIG` (SAL_OUTSTOCK) (bug A6)
3. Add `material_name: str = ""` and `specification: str = ""` to:
   - `PurchaseReceiptModel` (bug A5)
   - `SubcontractingOrderModel` (bug A5)
   - `MaterialPickingModel` (bug A5)
   - `SalesDeliveryModel` (bug A5)
4. Add column-count validation in `client.py` after `zip()` to warn on mismatch (bug D2)

**Fixes**: D1, A5, A6, D2, A7 (partially — names now stored properly instead of JSON recovery)
**Success Criteria**: All forms return populated `material_name` fields; `pytest tests/ -k reader` passes
**Depends on**: —

---

### Stage 5: Fix Sync Service Integrity
**Goal**: Remove old unsafe upsert methods; fix parallel chunk races; handle errors properly.
**Files**:
- `src/sync/sync_service.py` (modify)
- `src/sync/scheduler.py` (modify)

**Changes**:
1. Remove or deprecate all 7 old `_upsert_*` methods — route all writes through `_no_commit` variants only (bug C2)
2. Remove redundant DELETE in `_no_commit` methods — let `ON CONFLICT` (now backed by UNIQUE constraints from Stage 1) handle upserts (bug C5)
3. Deduplicate MTO numbers across parallel chunks to prevent overwrite races (bug C6)
4. Propagate chunk exceptions instead of swallowing them — mark sync as partial failure (bug C7)
5. Fix SAL_SaleOrder dedup to prefer the row with the most complete data, not just highest qty (bug C8)
6. Fix scheduler TOCTOU race on `is_running()` check
7. Expand `check_freshness` to query all cache tables, not just `production_orders` (bug E1)

**Fixes**: C2, C5, C6, C7, C8, E1
**Success Criteria**: `pytest tests/ -k sync` passes; manual sync completes without silent failures
**Depends on**: Stage 1

---

## Test Cases

### Unit Tests
- [ ] Cache reader returns correct material_name when multiple BOM rows exist (not MIN)
- [ ] Cache reader returns correct material_type when rows disagree
- [ ] 07.xx items excluded from BOM child rows in both cache and live paths
- [ ] `_get()` fallback matches SQL `pr0` dual-JOIN behaviour
- [ ] No double-counting when BOM has aux=0 and aux>0 for same material
- [ ] `covered_codes` does not suppress orphan variants

### Integration Tests
- [ ] Same MTO returns identical `ChildItem` list from cache and live paths
- [ ] After sync, all receipt rows have non-empty `bill_no`
- [ ] Parallel chunk sync with overlapping MTOs produces correct data
- [ ] All forms return populated `material_name` from Kingdee API

### Manual Verification
1. Query MTO containing item `07.03.040` — verify description shows 潜水镜, not 外箱条码贴纸
2. Query MTO with 委外 items — verify subcontracting quantities appear (not zero)
3. Compare cache path vs live path results for 3 different MTOs — should be identical

## Acceptance Criteria
- [ ] No material code/name mismatches in dashboard display
- [ ] Cache and live paths return identical results for all MTOs
- [ ] All 7 cache tables have UNIQUE constraints
- [ ] No silent sync failures — errors are logged and status reflects partial failure
- [ ] All Kingdee forms fetch and store `material_name`/`specification`
