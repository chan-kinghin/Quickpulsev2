# Plan: Fix Bidirectional aux_prop_id Fallback

## Status: Stage 1-2 Complete, Stage 3 Pending

## Design Spec

### Problem

MTO AS2602037 shows **0 receipt quantities for all self-made items** except one (05.20.03.02.056). Kingdee ERP shows real receipt data (e.g., 20,130 for 水阀, 吊环, etc.).

**Root cause**: The BOM items have `aux_prop_id=0` (generic, no variant specified), but their PRD_INSTOCK receipts have **specific** `aux_prop_id` values (105726, 107962, 106077, etc.).

| BOM material | BOM aux | Receipt aux | Exact match? | aux=0 fallback? | Result |
|---|---|---|---|---|---|
| 05.06.02.20 水阀 | 0 | 105726 | NO | NO (no aux=0 receipts) | **0** |
| 05.06.02.21 水阀 | 0 | 107962 | NO | NO | **0** |
| 05.06.05.029 长管 | 0 | 106077 | NO | NO | **0** |
| 05.20.03.02.056 长管印刷 | 106077 | 106077 | YES | — | **Works** |

The current 2-tier matching:
1. **Exact**: `(material_code, aux_prop_id)` — works only when both sides agree
2. **Fallback**: sum receipts with `aux_prop_id=0` — handles "receipt has no variant"

**Missing**: A third tier for when BOM has `aux_prop_id=0` (meaning "any variant") but receipts have specific variants. This is the **reverse direction** of the existing fallback.

### Solution

Add a **bidirectional fallback** — a third tier that sums ALL receipts for a `material_code` regardless of `aux_prop_id`, used when:
- Exact match fails, AND
- BOM row has `aux_prop_id=0` (meaning "any variant")

**3-tier matching strategy**:
```
Tier 1: Exact match on (material_code, aux_prop_id)
Tier 2: BOM has specific aux, receipt has aux=0  → use aux=0 sum  [EXISTING]
Tier 3: BOM has aux=0, receipt has specific aux  → use material-code sum  [NEW]
```

**Why Tier 3 only for BOM aux=0**: If BOM has a specific `aux_prop_id` and we fell through to summing ALL receipts, we'd risk double-counting when another BOM row for the same material gets the exact match. Restricting Tier 3 to `BOM aux=0` is safer because aux=0 means "I represent all variants of this material."

### Files to Modify

1. `src/query/cache_reader.py` — Add `pr_all` subquery (and analogous for pk, po, pur, sub, sd), update COALESCE to 3-tier
2. `src/query/mto_handler.py` — Add `_by_code_all` dict (sums all aux variants), update `_get()` to 3-tier
3. `tests/unit/test_cache_reader_joined.py` — Add test for BOM aux=0 + receipt aux=specific
4. `tests/unit/test_mto_handler.py` — Add test for live path 3-tier fallback

### Data Flow (Cache Path)

```sql
-- Tier 1: Exact match (existing)
LEFT JOIN (
    SELECT material_code, aux_prop_id, SUM(real_qty)...
    FROM cached_production_receipts WHERE mto_number LIKE ?
    GROUP BY material_code, aux_prop_id
) pr ON br.material_code = pr.material_code
     AND br.aux_prop_id = pr.aux_prop_id

-- Tier 2: Receipt aux=0 fallback (existing)
LEFT JOIN (
    SELECT material_code, SUM(real_qty)...
    FROM cached_production_receipts
    WHERE mto_number LIKE ? AND aux_prop_id = 0
    GROUP BY material_code
) pr0 ON br.material_code = pr0.material_code

-- Tier 3: Material-code-only sum (NEW)
LEFT JOIN (
    SELECT material_code, SUM(real_qty)...
    FROM cached_production_receipts WHERE mto_number LIKE ?
    GROUP BY material_code
) pr_all ON br.material_code = pr_all.material_code

-- COALESCE: 3-tier resolution
COALESCE(
    pr.real_qty,                                                              -- Tier 1
    CASE WHEN pr.material_code IS NULL AND br.aux_prop_id != 0
         THEN pr0.real_qty END,                                               -- Tier 2
    CASE WHEN pr.material_code IS NULL AND br.aux_prop_id = 0
         THEN pr_all.real_qty END,                                            -- Tier 3
    0
)
```

### Data Flow (Live Path)

```python
# Existing: _by_code sums only aux=0 entries (Tier 2)
# NEW: _by_code_all sums ALL entries regardless of aux (Tier 3)

_by_code_all: dict[str, dict[str, Decimal]] = {}
for label, aux_dict in [...]:
    code_totals = {}
    for (code, _aux), val in aux_dict.items():
        code_totals[code] = code_totals.get(code, ZERO) + val
    _by_code_all[label] = code_totals

def _get(lookup, lookup_label, code, aux):
    # Tier 1: exact (code, aux)
    exact = lookup.get((code, aux))
    if exact is not None:
        return exact
    # Tier 2: BOM has specific aux → try aux=0 receipts
    if aux != 0:
        fallback = _by_code.get(lookup_label, {}).get(code)
        if fallback is not None:
            return fallback
    # Tier 3: BOM has aux=0 → sum all receipts for material
    if aux == 0:
        all_sum = _by_code_all.get(lookup_label, {}).get(code)
        if all_sum is not None:
            return all_sum
    return ZERO
```

### Edge Case: Double-Counting Risk

If BOM has **both** `(material_X, aux=0)` and `(material_X, aux=106077)` rows:
- Row (aux=106077): Tier 1 exact match → gets receipts for aux=106077
- Row (aux=0): Tier 3 → gets ALL receipts including aux=106077 → **double-count**

**Mitigation**: This pattern is rare in practice (BOM typically has one row per material per MTO). In the AS2602037 data, each self-made material has exactly ONE BOM row. If this becomes an issue, a future fix can subtract already-matched receipts.

### Scope

This fix applies to ALL 6 receipt/order table JOINs in `cache_reader.py`:
- `pr/pr0/pr_all` — Production receipts (PRD_INSTOCK)
- `pk/pk0/pk_all` — Material picking (PRD_PickMtrl)
- `po/po0/po_all` — Purchase orders (PUR_PurchaseOrder)
- `pur/pur0/pur_all` — Purchase receipts (STK_InStock)
- `sub/sub0/sub_all` — Subcontracting orders (SUB_POORDER)
- `sd/sd0/sd_all` — Sales delivery (SAL_OUTSTOCK)

And the corresponding `_get()` function in `mto_handler.py` live path.

---

## Stage 1: Cache Path — Add Tier 3 Fallback JOINs

**Goal**: Add `*_all` subqueries and 3-tier COALESCE to `cache_reader.py`

**Changes**:
- Add 6 new LEFT JOIN subqueries (one per table) that GROUP BY material_code only (no aux filter)
- Update 12 COALESCE expressions (2 per table: real_qty and must_qty/order_qty/etc.) to 3-tier logic
- Total: ~36 new lines of SQL + 12 modified COALESCE lines

**Success Criteria**:
- `pytest tests/unit/test_cache_reader_joined.py -v` passes
- New test: BOM aux=0 + receipt aux=specific → receipt data appears

**Files**:
- `src/query/cache_reader.py` (modify)
- `tests/unit/test_cache_reader_joined.py` (modify)

---

## Stage 2: Live Path — Add Tier 3 Fallback

**Goal**: Update `_get()` and `_by_code_all` in `mto_handler.py` live path

**Changes**:
- Add `_by_code_all` dict construction (sums all aux variants per material_code)
- Update `_get()` to branch: aux≠0 → Tier 2 (aux=0 only), aux=0 → Tier 3 (all variants)

**Success Criteria**:
- `pytest tests/unit/test_mto_handler.py -v` passes
- New test: live path with BOM aux=0 + receipt aux=specific → receipt data appears

**Files**:
- `src/query/mto_handler.py` (modify)
- `tests/unit/test_mto_handler.py` (modify)

**Depends on**: Stage 1 (for consistency verification, but can be coded in parallel)

---

## Stage 3: Integration Verification

**Goal**: Verify fix works on real data

**Steps**:
1. Run full unit test suite: `pytest --ignore=tests/e2e --ignore=tests/integration`
2. Start local server, query AS2602037 via cache path → verify self-made items show receipt data
3. Deploy to dev, verify on https://dev.fltpulse.szfluent.cn

**Success Criteria**:
- All unit tests pass
- AS2602037 self-made items show non-zero receipt quantities matching Kingdee
- No regression on other MTOs (spot check DS263039S, AK2510034)

---

## Relationship to Existing Plans

| Existing Plan | Status | Overlap |
|---|---|---|
| `PLAN-fix-cross-mto-aggregation.md` | Not Started | Partially superseded — Stage 1 (use need_qty) was already applied in commit 265303a. Remaining issue about cross-MTO summing is separate. |
| `PLAN-fix-data-source-mismatches.md` | Stage 1-2 done (commit 265303a) | Stage 4 (aux fallback) is **expanded** by this plan. This plan replaces Stage 4 with a more complete bidirectional approach. |

---

## Test Cases

### Unit Tests
- [ ] Cache: BOM aux=0, receipt aux=105726 → receipt qty shows correctly (Tier 3)
- [ ] Cache: BOM aux=106077, receipt aux=106077 → exact match works (Tier 1)
- [ ] Cache: BOM aux=106077, receipt aux=0 → fallback works (Tier 2)
- [ ] Cache: BOM aux=0, no receipts at all → shows 0
- [ ] Live: same 4 scenarios via `_get()` function
- [ ] All 6 tables (pr, pk, po, pur, sub, sd) tested

### Manual Verification
1. Query AS2602037 → self-made items show receipt quantities matching Kingdee
2. Query DS263039S → no regression, self-made items still correct
3. Compare cache vs live path results for AS2602037

## Acceptance Criteria
- [ ] Self-made items with BOM aux=0 match receipts with specific aux values
- [ ] No regression for items where aux already matches exactly
- [ ] Cache path and live path produce identical results
- [ ] All existing unit tests pass (updated assertions as needed)
- [ ] Deployed to dev and verified with real data
