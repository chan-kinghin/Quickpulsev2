# Plan: Resolve 辅助属性 for PUR-only packaging children (cache path)

## Status: Not Started

## Design Spec

### Problem

Purchase-only packaging materials (e.g. `03.23.009 贴纸`) that have no PPBOM line currently render with empty `辅助属性` ("-") on the dashboard, even though Kingdee carries rich descriptions for each variant in `BD_FLEXSITEMDETAILV` (e.g. *"JSC儿童款泳帽可移动价格贴纸,UK24×26MM/Pantone 485C,3.99,水胶不干胶材质"*).

Concrete evidence — MTO `AK2508006`, material `03.23.009 贴纸`:
- 25+ rows in `cached_purchase_orders`, each with a distinct `aux_prop_id` (e.g. 107578, 114367, 114443, …)
- `lookup_aux_properties()` resolves **25 / 25** of those IDs to full Chinese descriptions
- Dashboard nevertheless shows `辅助属性 = "-"` for every row

### Root cause

`src/query/mto_handler.py::get_mto_status` (cache path) collects `aux_prop_id`s from only two sources before calling `lookup_aux_properties`:

```python
# Lines 414-424
aux_prop_ids = set()
for so in sales_orders:                                    # ← SAL only
    if hasattr(so, "aux_prop_id") and so.aux_prop_id:
        aux_prop_ids.add(so.aux_prop_id)
for row in bom_rows:                                       # ← PPBOM only
    if row.aux_prop_id:
        aux_prop_ids.add(row.aux_prop_id)

aux_descriptions = await self._client.lookup_aux_properties(list(aux_prop_ids))
```

The **synthetic PUR-only child builder** (lines 495-538, added 2026-05-22 per colleague feedback) runs *after* the lookup and consults `aux_descriptions.get(aux, "")`. Its source IDs were never added to the set → cache miss → silent fall-back to `""` → UI shows `-`.

The **live path** (lines 610-615) already iterates over `purchase_orders` (plus 4 more sources). Only the cache path is broken — classic "3-tier consistency drift" pattern called out in `CLAUDE.md` (Pre-Change Checklist).

### Solution

Two surgical changes in `src/query/mto_handler.py::get_mto_status`:

1. **Move** the `purchase_orders_result = await self._cache_reader.get_purchase_orders(mto_number)` fetch from line ~507 up to **before** the aux-id collection block (~line 413). The cache reader is cheap (single indexed SELECT) and the data is already needed later.
2. **Add** a third loop:
   ```python
   for po in (purchase_orders_result.data or []):
       if getattr(po, "aux_prop_id", 0):
           aux_prop_ids.add(po.aux_prop_id)
   ```
3. Reuse the already-fetched `purchase_orders_result` at the synthetic-PUR section (delete the duplicate fetch at line ~507).

No schema change, no sync change, no live-path change, no frontend change. ~6 lines moved + 3 lines added.

### Files to Modify

| File | Change |
|---|---|
| `src/query/mto_handler.py` | Reorder `get_purchase_orders` fetch; extend aux-id collection loop |
| `tests/unit/test_mto_handler.py` | New test: PUR-only child with non-zero aux_prop_id gets resolved `aux_attributes` |

### Data flow (after fix)

```
cache: sales_orders + bom_rows + purchase_orders
   ↓
collect aux_prop_id from ALL THREE
   ↓
lookup_aux_properties(BD_FLEXSITEMDETAILV) → aux_descriptions dict
   ↓
build_aggregated_sales_child   (07.xx)        uses aux_descriptions ✓
_bom_row_to_child              (BOM children) uses aux_descriptions ✓
synthetic-PUR child builder    (PUR-only)     uses aux_descriptions ✓ ← FIXED
```

## Test Cases

### Unit Tests
- [ ] **`test_pur_only_child_resolves_aux_attributes`** — Mock `cache_reader.get_purchase_orders` to return rows with `aux_prop_id=999`, mock `client.lookup_aux_properties` to return `{999: "贴纸变体A"}`, assert the synthetic child has `aux_attributes == "贴纸变体A"`.
- [ ] **`test_pur_only_child_handles_missing_aux_description`** — Same setup but `lookup_aux_properties` returns `{}`. Child should fall back to `""` (no crash, no fabricated string).
- [ ] **`test_pur_only_child_with_aux_zero_unchanged`** — `aux_prop_id=0` rows should not be added to the lookup set and still render with `aux_attributes=""`.
- [ ] **Regression**: existing `bom_rows` and `sales_orders` aux paths still resolve (lift one assertion from current tests).

### Manual Verification
1. Run dev server locally with the patched code: `uvicorn src.main:app --reload --port 8000`.
2. Query MTO `AK2508006` from the dashboard.
3. Confirm the 25 `03.23.009 贴纸` rows now show distinct, descriptive `辅助属性` values matching the IDs from the diagnosis probe (e.g. row with `aux_prop_id=114367` should display *"JSC儿童款泳帽可移动价格贴纸,UK24×26MM/Pantone 485C,3.99,水胶不干胶材质"*).
4. Pick another MTO with PUR-only items (`AK2509xxx` series likely candidates) — confirm same behaviour.
5. Pick a 07.xx-heavy MTO (e.g. `DK251003S`) — confirm finished-goods aux still resolves (regression check).

## Acceptance Criteria

- [ ] `tests/unit/test_mto_handler.py` passes including new tests
- [ ] `pytest --ignore=tests/e2e --ignore=tests/integration` exits 0 (no other tests broken)
- [ ] AK2508006 → 03.23.009 rows show resolved Chinese descriptions on the dashboard
- [ ] BOM-child rows and 07.xx finished-goods rows still show their aux_attributes (no regression)
- [ ] `lookup_aux_properties` is still called **exactly once per MTO query** (not multiple times) — verified by log line `"Looked up N aux properties"`
- [ ] No new warnings in `aux_lookup_failed` / `aux_lookup_sparse` Loki metrics after deploy

## Out of scope

- Live path (already correct)
- Sync writer (the aux_prop_id is already in `cached_purchase_orders`)
- Schema migrations
- Frontend changes (column already exists at `dashboard.js:32`)
- Caching the BD_FLEXSITEMDETAILV lookup results (a future optimisation — current call is one batched query per MTO, acceptable)
