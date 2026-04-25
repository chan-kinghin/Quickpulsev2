# Plan: Surface aux_prop_id match quality (stop the silent fallback)

**Created**: 2026-04-25
**Status**: Complete (all 7 stages implemented; 699 unit tests pass)
**Author**: King + Claude
**Inspiration**: QuickPulse Lite's per-customer `MANUAL_MAP` workflow — Lite assumes aux mismatches need human attention; V2 silently papers over them.

---

## Problem

V2's storage layer already keys correctly on `(material_code, aux_prop_id)` — schema UNIQUE constraints, sync writers, and most lookups are aligned. But `cache_reader.get_mto_bom_joined()` (`src/query/cache_reader.py:282-385`) implements a **3-tier silent fallback** for every receipt/pick/order JOIN:

- **Tier 1**: exact `(material_code, aux_prop_id)` match
- **Tier 2**: BOM has aux≠0, fall back to `aux=0` receipts (different variant)
- **Tier 3**: BOM has aux=0, sum ALL aux variants for that material

The fallback is encoded with `COALESCE(...)` and `CASE WHEN` so the caller can't tell *which* tier fired. The MTO query returns the same shape whether the match was clean or estimated, and the UI displays both identically.

**Concrete consequences**:
1. The `aux_prop_id=0` "Cache path blind spot" (MEMORY.md, 2026-02-24) — bugs in this region take long to diagnose because data looks plausible.
2. There is no signal in logs, metrics, or the UI when fallback fires. Every "fix doesn't work" thread eventually reduces to "the fallback was hiding the real mismatch."
3. One lookup in the live path (`mto_handler.py:506` — `pick_request = _sum_by_material(material_picks, "app_qty")`) is **material-only**, inconsistent with the `_sum_by_material_and_aux` pattern used everywhere else. Either it's intentional (and needs justification) or it's a leftover (and should be aux-aware).
4. `lookup_aux_properties` (BD_FLEXSITEMDETAILV second pass) is best-effort — failure silently leaves `aux_attributes=""`. Lite treats this lookup as mandatory.

This plan does **not** propose removing the fallback — it encodes legitimate Kingdee data realities (operators sometimes record receipts against generic SKU even when BOM specifies variant). It proposes **making the fallback observable** so users see when their answer is estimated vs exact.

---

## Solution

Add a `match_quality` enum that travels from the SQL JOIN through the model into the API response and the UI.

```
match_quality ∈ {
  "exact",              # Tier 1: aux_prop_id matched
  "aux_zero_fallback",  # Tier 2: BOM aux≠0 but only aux=0 receipts found
  "all_aux_rollup",     # Tier 3: BOM aux=0, summed across all variants
  "no_match",           # Fallback returned 0 — no receipts at all
}
```

The cache SQL already has the COALESCE branches. Add a parallel `CASE` expression that emits a string label per source (receipt, pick, purchase, etc.). Surface in the API as `match_quality_breakdown` per child, and add a UI badge ("⚠ aux fallback") on rows where any source is non-exact.

Plus: a `?strict_aux=true` query param that *disables* the Tier 2/3 fallbacks, so power users can see raw data quality. And: convert the lone material-only lookup at `mto_handler.py:506` to aux-aware (or document why it must stay material-only).

---

## Files to Modify

| File | Change |
|---|---|
| `src/query/cache_reader.py` | Add `match_quality` `CASE` expressions next to each `COALESCE`; emit per-source labels. Honor `strict_aux` flag. |
| `src/query/cache_reader.py` (BOMJoinedRow dataclass) | Add `match_quality_*` fields per source (receipt, pick, purchase, sub, delivery). |
| `src/query/mto_handler.py:506` | Convert `_sum_by_material(material_picks, "app_qty")` → `_sum_by_material_and_aux`, OR add a comment with the documented reason it must stay material-only. |
| `src/query/mto_handler.py` (`_bom_row_to_child`) | Propagate `match_quality_breakdown` into `ChildItem`. |
| `src/query/mto_handler.py` (`get_mto_status`) | Accept `strict_aux: bool = False` param, plumb to cache + live paths. |
| `src/readers/models.py` (ChildItem) | Add `match_quality_breakdown: dict[str, str]` field (default empty). |
| `src/api/routers/mto.py` | Accept `?strict_aux=true` query param, pass to handler. |
| `src/frontend/dashboard.html` + `dashboard.js` | Add tooltip badge on rows with non-exact match_quality. No new column. |
| `src/kingdee/client.py` (`lookup_aux_properties`) | Log a WARNING when lookup fails; do not silently swallow. |
| `tests/unit/test_cache_reader.py` | Update row tuples (positional — order matters per MEMORY.md pre-change checklist). |
| `tests/golden/` | Regenerate fixtures with `match_quality_breakdown` populated. |
| `tests/integration/test_cache_live_parity.py` | Extend parity check to compare match_quality between cache and live paths. |

---

## Stages

### Stage 1: Diagnose — instrument current fallback (read-only)
**Goal**: Quantify how often each fallback tier fires in real production traffic before changing anything.
**Files**: `src/query/cache_reader.py` (add Prometheus counters), `src/observability/metrics.py` (new counter `mto_aux_fallback_total{tier="..."}`)
**Depends on**: —
**Tests**: Unit test that fires each fallback tier and verifies counter increments.
**Success Criteria**:
- Counters wired up on prod for ≥48h
- Report: % of MTO queries where any tier-2 or tier-3 fallback fires
- If <1%, this plan is over-engineered — pause and reassess
- If >5%, this is a real signal worth surfacing
**Status**: Not Started

### Stage 2: Add match_quality field to BOMJoinedRow + ChildItem
**Goal**: Add the per-source enum field everywhere it needs to flow, default to `"exact"` so existing behavior is preserved.
**Files**: `src/query/cache_reader.py` (dataclass), `src/readers/models.py` (ChildItem), `tests/unit/test_cache_reader.py` (row tuples)
**Depends on**: —
**Tests**: Pydantic validation, default value behavior, serialization round-trip.
**Success Criteria**:
- `pytest tests/unit/test_cache_reader.py tests/unit/test_readers_models.py` passes
- API JSON includes `match_quality_breakdown` field, defaulting to `{}` for now
- No behavior change end-to-end yet
**Status**: Not Started

### Stage 3: Emit match_quality from SQL
**Goal**: Add `CASE` expressions to the cache JOIN that label which tier fired per source. Populate `match_quality_breakdown` in `_row_to_bom_joined`.
**Files**: `src/query/cache_reader.py:282-500`, `tests/unit/test_cache_reader.py`, `tests/golden/`
**Depends on**: Stage 2
**Tests**:
- Fixture with BOM `(M001, aux=5001)` + receipt `(M001, aux=5001)` → match_quality = exact
- Fixture with BOM `(M001, aux=5001)` + only `(M001, aux=0)` receipt → match_quality = aux_zero_fallback
- Fixture with BOM `(M001, aux=0)` + `(M001, aux=5001)` + `(M001, aux=5002)` receipts → match_quality = all_aux_rollup
- Fixture with no receipt → match_quality = no_match
**Success Criteria**:
- Every receipt/pick/order source in the JOIN emits a `match_quality_*` column
- Golden tests show populated `match_quality_breakdown` for each child
- Numeric quantities unchanged from current behavior (parity check on real MTO queries)
**Status**: Not Started

### Stage 4: Mirror match_quality in the live path
**Goal**: `_build_bom_joined_rows_from_live` in `mto_handler.py` should produce the same `match_quality_breakdown` shape so cache and live results stay shape-compatible.
**Files**: `src/query/mto_handler.py:554-700` (live BOM join), `src/query/mto_handler.py:506` (material-only lookup)
**Depends on**: Stage 3
**Tests**: Live-vs-cache parity test (`tests/integration/test_cache_live_parity.py`) — match_quality breakdown must agree.
**Success Criteria**:
- Live and cache paths emit identical `match_quality_breakdown` for the same MTO
- Lone `_sum_by_material(material_picks, "app_qty")` either converted to aux-aware OR has an inline comment documenting why
**Status**: Not Started

### Stage 5: Surface in UI
**Goal**: Show a small ⚠ badge with tooltip on rows where any source's match_quality ≠ "exact". No new column — just a visual marker.
**Files**: `src/frontend/dashboard.html`, `src/frontend/static/js/dashboard.js`
**Depends on**: Stage 3
**Tests**: Playwright E2E — query a fixture MTO with known fallbacks, screenshot shows badges on the right rows.
**Success Criteria**:
- Tooltip text: "实收数量为按辅助属性=0回落估算" or similar
- Badge does not affect column layout or sort order
- Existing `STORAGE_VERSION` does NOT bump (no column structure change, per MEMORY.md gotcha)
**Status**: Not Started

### Stage 6: Add `?strict_aux=true` opt-in
**Goal**: Power-user query param that disables Tier 2/3 fallbacks. Returns `match_quality=no_match` and `qty=0` instead of estimating.
**Files**: `src/api/routers/mto.py`, `src/query/mto_handler.py`, `src/query/cache_reader.py`
**Depends on**: Stage 4
**Tests**:
- API: `GET /api/mto/AK2510034?strict_aux=true` — fixture with mismatched aux returns explicit zero quantities
- Unit: `get_mto_bom_joined(strict=True)` skips Tier 2/3 JOINs entirely
**Success Criteria**:
- Default behavior unchanged (`strict_aux` defaults to false)
- With `strict_aux=true`, output exposes data quality issues directly
**Status**: Not Started

### Stage 7: Make BD_FLEXSITEMDETAILV lookup loud on failure
**Goal**: `lookup_aux_properties` currently returns `{}` silently on error. Add a WARNING log + bump a metric `aux_lookup_failures_total`.
**Files**: `src/kingdee/client.py:368-410`
**Depends on**: —
**Tests**: Unit — mock SDK to return an error response, verify warning logged and metric incremented.
**Success Criteria**:
- Failed lookups appear in logs with MTO context
- Existing callers do not break (return value shape unchanged)
**Status**: Not Started

---

## Test Cases

### Unit Tests
- [ ] `test_match_quality_exact` — BOM aux matches receipt aux
- [ ] `test_match_quality_aux_zero_fallback` — BOM aux≠0, only aux=0 receipts
- [ ] `test_match_quality_all_aux_rollup` — BOM aux=0, multiple variant receipts
- [ ] `test_match_quality_no_match` — no receipts at all
- [ ] `test_strict_aux_disables_fallback` — `strict_aux=true` returns zero qty for non-exact rows
- [ ] `test_aux_lookup_failure_logs_warning` — BD_FLEXSITEMDETAILV failure emits warning
- [ ] `test_pick_request_aux_aware` — `pick_request` lookup keyed on `(material, aux)` (or test asserts intentional material-only with rationale)

### Integration Tests
- [ ] `test_cache_live_parity_match_quality` — same MTO, same match_quality breakdown from both paths
- [ ] `test_strict_aux_e2e` — full HTTP request → response with `?strict_aux=true`

### Manual Verification
1. Pick an MTO with known aux mismatches from prod (use Stage 1 metrics to identify candidates)
2. Query without strict mode — verify badge appears on affected rows
3. Hover badge — verify tooltip explains the fallback tier
4. Query with `?strict_aux=true` — verify affected rows show zero qty + "no_match"
5. Compare to Kingdee directly — confirm strict-mode zeroes match raw data reality

---

## Acceptance Criteria

- [ ] Stage 1 metrics show fallback rate quantified for ≥48h before any code change ships
- [ ] All 7 stages' Success Criteria met
- [ ] No regression in numeric quantities for default queries (cache vs current main)
- [ ] `pytest --ignore=tests/e2e --ignore=tests/integration` passes
- [ ] Live-vs-cache parity test passes (match_quality must agree)
- [ ] Frontend Playwright tests pass; sticky-header tests still green
- [ ] Deployed to dev with full sync rebuild; verified on at least 5 MTOs covering different fallback scenarios
- [ ] CLAUDE.md "Cache path blind spot" memory is updated with a pointer to this remediation

---

## Non-Goals (explicitly NOT in this plan)

- Removing the fallback entirely (it encodes real Kingdee operator behavior)
- Customer-centric dashboard view (separate plan, would build on this)
- Excel export (separate plan)
- Schema migration (already done; primary keys are correct)
- Aux-mapping admin UI (Lite-style `MANUAL_MAP` editor) — could be a follow-up if Stage 1 metrics show it's needed

---

## Risks

| Risk | Mitigation |
|---|---|
| Match-quality field bloats response size | Use short enum strings; only emit non-default per-source labels |
| Parallel SQL `CASE` expressions slow the JOIN | Benchmark in Stage 3; if >10% slower, push label computation to Python post-processing |
| Frontend badge clashes with existing column visibility prefs | Don't add columns; use absolute-positioned tooltip on existing material_code cell |
| Stage 1 metrics show fallback rate <1% | Pause plan — the silent fallback may not be worth surfacing if it's rare |
