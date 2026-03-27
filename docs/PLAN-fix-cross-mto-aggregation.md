# Plan: Fix Cross-MTO Aggregation for 自制 prod_instock_must_qty

## Status: Complete (addressed by commits 265303a + 3-tier aux fallback fix 2026-03-27)

## Design Spec

### Problem

For 自制 (self-made) items, `prod_instock_must_qty` shows inflated values because it sums PRD_MO quantities across **all MTO variants** (e.g., DS263039S, DS263039S-1, DS263039S-2) instead of scoping to the BOM row's specific production order.

**Example**: MTO DS263039S, parent order qty = 4,763
- 外框 WK-GL16 shows `prod_instock_must_qty = 45,248.50` (should be ~4,763)
- 镜片 FM-GL16 shows `76,208` (should be ~4,763)
- The same material appears in multiple sub-MTOs, and all their PRD_MO `qty` values get summed

### Root Cause

In `mto_handler.py` (both cache and live paths, lines ~419-423 and ~510-513):

```python
prd_mo_qty_by_key: dict[tuple[str, int], Decimal] = {}
for po in prod_orders:
    key = (po.material_code, aux_prop_id)
    prd_mo_qty_by_key[key] += po.qty  # sums ALL variant MTOs
```

`prod_orders` is fetched via `LIKE 'DS263039S%'` which returns PRD_MO records for all variants. The aggregation groups only by `(material_code, aux_prop_id)`, losing the MTO/bill_no granularity.

Then in `_bom_row_to_child()` (line ~860-867), for `effective_type == 1`:
```python
demand_qty = prd_mo_qty_by_key.get((material_code, aux_prop_id))  # gets inflated sum
prod_instock_must_qty = demand_qty  # BUG: too high
```

### Solution

**Stop using `prd_mo_qty_by_key` for `prod_instock_must_qty`.** Instead, use the BOM's own `need_qty` from PPBOM, which is already correctly scoped per BOM row.

The `need_qty` from PPBOM represents "how many units of this material are needed for this specific production order," which is exactly what 生产入库单.应收数量 should show.

**Why this is correct:**
- PPBOM `need_qty` is defined per `mo_bill_no` — it's already scoped to one production order
- The BOM query already aggregates across the MTO group correctly via `SUM(need_qty) GROUP BY material_code, aux_prop_id`
- PRD_MO `qty` is the finished product quantity, not the component quantity — using it as `prod_instock_must_qty` for a component is semantically wrong

**What changes:**
- In `_bom_row_to_child()`, for `effective_type == 1`: use `row.need_qty` instead of `prd_mo_qty_by_key` lookup
- Remove the now-unused `prd_mo_qty_by_key` parameter and its construction

### Files to Modify

1. `src/query/mto_handler.py` — Change `_bom_row_to_child()` for type==1 to use `row.need_qty`, remove `prd_mo_qty_by_key` construction and parameter
2. `tests/unit/test_mto_handler.py` — Update tests that verify `prd_mo_qty_by_key` behavior

## Test Cases

### Unit Tests
- [ ] Test that 自制 `prod_instock_must_qty` equals BOM `need_qty` (not PRD_MO qty sum)
- [ ] Test with multiple MTO variants (DS263039S, DS263039S-1) that quantities don't cross-aggregate
- [ ] Test fallback: if `need_qty` is 0/None, verify behavior (should show 0, not PRD_MO sum)
- [ ] Test 包材 and 委外 paths are unaffected

### Manual Verification
1. Query MTO DS263039S on prod after deploy
2. Verify 自制 items show reasonable `prod_instock_must_qty` values (close to ~4,763 per component, not 45k+)
3. Compare cache vs live path results

## Acceptance Criteria
- [ ] 自制 items show `need_qty` from BOM as `prod_instock_must_qty`, not cross-MTO PRD_MO sums
- [ ] All existing unit tests pass
- [ ] Cache path and live path produce same results
- [ ] No regression for 包材/委外/成品 item types
