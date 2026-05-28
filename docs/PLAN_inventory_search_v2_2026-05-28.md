# Plan: Inventory Search v2 — Multi-Token + Aux + Shared Cache

## Status: Awaiting Approval

## v2 Architecture Decision (revised 2026-05-28 after user feedback)

**v1 was real-time-only. v2 introduces a cache layer.** Reason: multi-token AND
search + aux JOIN is expensive when each user keystroke triggers 2-4 Kingdee
API calls. The existing sync infrastructure (sync_service + SQLite + scheduler)
already has the scaffolding; v2 piggybacks on it.

| Concern | v1 (real-time) | v2 (cached) |
|---|---|---|
| Search latency | 0.3-3s | ~30-100ms |
| Multi-token AND | Hard (Kingdee FilterString limits) | Trivial SQL WHERE |
| Aux JOIN | 2 round trips | 1 SQL JOIN |
| Kingdee load per query | 1-4 calls | 0 |
| Data freshness | always live | up to ~4-6h stale (next sync) |
| Implementation effort | smaller | larger but more capable |

**User input "可以共用缓存"** = approved sharing the existing SQLite cache +
sync pipeline.

## Background

v1 (shipped 2026-05-28) searches BD_MATERIAL by single keyword across
{FNumber, FName, FSpecification}. User feedback: natural-language queries like

- `黑色网袋` — color + material name
- `黄色 2328泳镜` — color + material code/spec
- `K66 盒子` — packaging code + material name
- `巴西 Speedo 贴纸` — customer region + brand + material category

cannot be answered by v1 because (a) the query is multi-token, (b) "color" is
not on BD_MATERIAL — it lives on `BD_FLEXSITEMDETAILV` indexed by `FAuxPropId`
on inventory rows.

## Coverage Decision

This iteration covers **3 of 4 user examples**. The 4th (`巴西 Speedo`) requires
customer-master JOINs and is **explicitly deferred** to v3.

| Example | v2 Achievable? | Why |
|---|---|---|
| `黑色网袋` | ✅ | "黑色" matches aux; "网袋" matches BD_MATERIAL.FName |
| `黄色 2328泳镜` | ✅ | "黄色" matches aux; "2328" matches FNumber/FSpec; "泳镜" matches FName |
| `K66 盒子` | ✅ | "K66" matches FNumber/FSpec; "盒子" matches FName (no aux needed) |
| `巴西 Speedo 贴纸` | ❌ defer | "巴西" + "Speedo" require SAL_SaleOrder.FCustId JOIN — out of scope |

## Design — Cache-Backed Implementation

### Sync Pipeline Additions

Three new tables synced on the existing 07:00 / 12:00 / 16:00 / 18:00 schedule:

```sql
CREATE TABLE cached_materials (
    material_code     TEXT PRIMARY KEY,    -- BD_MATERIAL.FNumber
    material_name     TEXT NOT NULL,
    specification     TEXT,
    erp_class         TEXT,                -- "1"/"2"/"3"/"4"/"9"
    is_forbidden      INTEGER DEFAULT 0,
    synced_at         TEXT NOT NULL
);
-- Search indexes
CREATE INDEX idx_materials_name ON cached_materials(material_name);
CREATE INDEX idx_materials_spec ON cached_materials(specification);

CREATE TABLE cached_inventory_snapshot (
    -- Composite key — one row per (material × warehouse × lot × aux × org)
    material_code     TEXT NOT NULL,
    warehouse_code    TEXT NOT NULL,
    warehouse_name    TEXT NOT NULL,
    lot_number        TEXT DEFAULT '',
    aux_id            INTEGER DEFAULT 0,
    stock_org         TEXT DEFAULT '',
    base_qty          REAL NOT NULL,
    synced_at         TEXT NOT NULL,
    PRIMARY KEY (material_code, warehouse_code, lot_number, aux_id, stock_org)
);
CREATE INDEX idx_inv_aux ON cached_inventory_snapshot(aux_id);
CREATE INDEX idx_inv_material ON cached_inventory_snapshot(material_code);

CREATE TABLE cached_aux_descriptions (
    aux_id            INTEGER PRIMARY KEY,
    spec_text         TEXT,                -- FF100001
    color_name        TEXT,                -- FF100002.FName
    description       TEXT,                -- pre-joined "spec / color" for fuzzy match
    synced_at         TEXT NOT NULL
);
CREATE INDEX idx_aux_desc ON cached_aux_descriptions(description);
```

**Sync volume estimates** (verify with one-off probe before committing):
- BD_MATERIAL: ~60-100K rows, full reload per sync (~30s)
- STK_Inventory: ~50-200K rows, full reload (~60-120s)
- BD_FLEXSITEMDETAILV: ~5-15K rows, full reload (~10s)

Total: adds ~2-3 minutes to existing ~12-min sync. Acceptable.

### Live-API Fallback

If the cache is stale beyond a threshold (e.g., last_sync > 24h) or empty
(fresh deploy), the `/api/inventory/search` endpoint falls back to v1's
live-API code path. This keeps the feature functional during sync gaps.

### Search Strategy — SQL-Based AND-of-OR

For a query with N tokens, the SQL becomes:

```sql
SELECT DISTINCT m.material_code, m.material_name, m.specification, m.erp_class,
                a.aux_id, a.description AS aux_desc,
                SUM(i.base_qty) AS inventory_total
FROM cached_materials m
LEFT JOIN cached_inventory_snapshot i ON i.material_code = m.material_code
LEFT JOIN cached_aux_descriptions a ON a.aux_id = i.aux_id
WHERE m.is_forbidden = 0
  AND ( m.material_code LIKE ? OR m.material_name LIKE ?
        OR m.specification LIKE ? OR a.description LIKE ? )  -- token 1
  AND ( m.material_code LIKE ? OR m.material_name LIKE ?
        OR m.specification LIKE ? OR a.description LIKE ? )  -- token 2
  -- ... one block per token, joined by AND
GROUP BY m.material_code, a.aux_id
ORDER BY inventory_total DESC NULLS LAST
LIMIT 50;
```

This is far simpler than v1's parallel-Kingdee orchestration.

### Query Parsing

```python
def tokenize(q: str) -> list[str]:
    # Split by whitespace (including CJK full-width 　), drop empties.
    # Each token must individually pass sanitize_query().
    # Max 4 tokens (defensive — more tokens = exponential filter complexity).
```

### Search Strategy: AND-of-OR

For a query with N tokens, return materials where **every** token matches **at
least one** of: BD_MATERIAL.FNumber, FName, FSpecification, or aux description.

Implementation in 2 sub-queries (parallel):

#### Sub-query 1: BD_MATERIAL multi-token AND
```
FilterString:
  ((FNumber like '%T1%' OR FName like '%T1%' OR FSpecification like '%T1%'))
  AND
  ((FNumber like '%T2%' OR FName like '%T2%' OR FSpecification like '%T2%'))
  AND FForbidStatus = 'A'
```
Returns: candidate material set A (each material matches all tokens via material fields).

#### Sub-query 2: aux-mediated discovery (only if Sub-query 1 returns < user limit)
For each token, query `BD_FLEXSITEMDETAILV` where `FF100001 LIKE '%t%' OR FF100002.FName LIKE '%t%'` → aux_id list per token.

Then for materials that have inventory rows with ANY of those aux_ids,
intersect with the tokens that don't match material fields.

This is the tricky part. To avoid combinatorial blow-up:
- If ALL tokens match material fields → skip sub-query 2 entirely
- If exactly ONE token doesn't match material fields → that's the "aux candidate token"; find aux_ids for it, then query STK_Inventory for materials with those aux_ids AND filter by Sub-query 1's material set (if non-empty) or by remaining tokens
- If >1 tokens don't match material fields → user query is too ambiguous; return Sub-query 1 results only with a note

### SKU-Level Result Panel (UI)

When the query involves aux matching, return **(material_code × aux_id)**
combinations, NOT just material codes:

```python
class SkuMatch(BaseModel):
    material_code: str
    material_name: str
    specification: str
    erp_class_label: str
    aux_id: int = 0           # 0 means "no aux dimension matched"
    aux_desc: str = ""
    matched_tokens: list[str] # which query tokens this SKU matched, for transparency
    inventory_total: Decimal  # total qty across all warehouses for this SKU
```

Frontend renders each SkuMatch as one row showing:
`[code] name | spec | aux_desc (chip) | total qty | matched: 黑色,网袋`

Clicking a row drills into the warehouse breakdown (existing v1 behavior).

### Performance Budget (cache-backed)

| Sub-step | Latency | Notes |
|---|---|---|
| Tokenize + sanitize | <1ms | Pure Python |
| SQL JOIN + GROUP BY | 20-80ms | aiosqlite, indexed columns |
| Pydantic serialization | 10-20ms | 50-row response |
| **Total end-to-end** | **30-100ms** | 30× faster than v1 |

If cache is stale → fallback to live: 1-3s (v1 budget retained).

### Files to Modify / Create

```
src/database/schema.sql                          (modify)  — 3 new tables + indexes
src/database/migrations/014_inventory_cache.sql  (create)  — migration script
src/sync/sync_service.py                         (modify)  — add 3 sync stages
src/sync/inventory_sync.py                       (create)  — dedicated sync logic
src/query/inventory_cache_reader.py              (create)  — SQL-based search reader
src/readers/inventory.py                         (modify)  — tokenize helpers, route to cache or live
src/models/inventory.py                          (modify)  — add SkuMatch
src/api/routers/inventory.py                    (modify)  — wire cache reader
src/frontend/inventory.html                      (modify)  — SKU rows + aux chip + freshness indicator
tests/unit/test_inventory_sync.py                (create)  — sync stage tests
tests/unit/test_inventory_cache_reader.py        (create)  — SQL search tests
tests/unit/test_inventory_reader.py              (modify)  — multi-token + tokenize tests
tests/unit/test_inventory_models.py              (modify)  — SkuMatch tests
tests/unit/test_inventory_router.py              (modify)  — response shape changes
```

Scope is materially larger than v1: ~9 files touched (vs 6 in v1), ~3-4 hours
of agent work split across 4 waves.

### Backward Compatibility

`InventorySearchResponse.items` was `list[MaterialMatch]` in v1; v2 makes it
`list[SkuMatch]`. Frontend rendering must update. Since the feature is 2 hours
old and used by one developer, **no migration / dual-shape support** is needed
— hard cut over.

## Test Cases

### Tokenization
- [ ] `test_tokenize_splits_ascii_space`: `"GT38 黑色"` → `["GT38", "黑色"]`
- [ ] `test_tokenize_splits_cjk_fullwidth_space`: `"GT38　黑色"` → `["GT38", "黑色"]`
- [ ] `test_tokenize_single_token_no_split`: `"黑色网袋"` → `["黑色网袋"]` (no internal split — Chinese has no spaces)
- [ ] `test_tokenize_caps_at_four`: `"a b c d e"` → ValueError
- [ ] `test_tokenize_each_token_sanitized`: `"a';DROP b"` → ValueError

### Multi-Token Material-Only Search
- [ ] `test_multi_token_and_across_three_fields`: `"K66 盒子"` → filter contains 2 paren groups joined by AND
- [ ] `test_multi_token_single_match_excluded`: material matches only one token → not in results

### Aux-Mediated Discovery
- [ ] `test_aux_token_discovers_materials`: `"黑色 网袋"` → 网袋 finds material set via BD_MATERIAL; 黑色 finds aux_ids; intersect via STK_Inventory
- [ ] `test_aux_only_no_material_token`: `"黑色"` (single aux token, no material fields hit) → returns all materials with that aux, ranked by inventory qty desc, cap 50
- [ ] `test_aux_unresolved_returns_material_only`: `"巴西 贴纸"` → "巴西" matches nothing → return material-only results matching "贴纸" with a `unresolved_tokens: ["巴西"]` field

### SKU-Level Result Structure
- [ ] `test_sku_match_includes_aux_when_resolved`: result row has aux_id, aux_desc populated
- [ ] `test_sku_match_aux_zero_when_material_only`: query like `"K66 盒子"` → aux_id=0, aux_desc=""
- [ ] `test_sku_match_inventory_total_populated`: includes sum of FBaseQty across warehouses

### End-to-End Example Coverage
- [ ] `test_e2e_黑色网袋`: returns 网袋-class materials with 黑色 aux variants only
- [ ] `test_e2e_黄色_2328泳镜`: returns 泳镜 materials with code matching 2328 and 黄色 aux
- [ ] `test_e2e_K66_盒子`: pure material search, no aux call

## Open Questions

1. **Result ordering**: when a material has 5 colors and the user searches only "网袋"
   (no aux token), should we return one row per material (collapsed) or one row per
   (material × aux)? **Default proposal**: collapsed (aux_id=0) — matches v1 behavior.
2. **Highlighting**: should matched tokens be highlighted in the UI? Adds polish but
   complicates the renderer. **Default**: skip for v2.
3. **Cache freshness indicator**: should we show "数据更新于 X 小时前" in the UI?
   **Default proposal**: yes — a small timestamp chip on the search panel, sourced
   from `MAX(synced_at)` on `cached_inventory_snapshot`. Builds user trust.
4. **First-deploy behavior**: cache will be empty until first sync runs. Until then
   the endpoint falls back to v1 live-API. Do we want a manual "rebuild inventory
   cache" button (like the existing `/api/sync/trigger`), or wait for the next
   scheduled sync? **Default**: leverage existing sync trigger — no new button.

## Out of Scope (Defer to v3+)

- 客户 / 地区 / 品牌 search (`巴西 Speedo`) — requires SAL_SaleOrder + BD_CUSTOMER JOIN
- Synonym expansion (`镜片` ↔ `lens` ↔ `kraal`) — needs a vocabulary file
- Fuzzy/typo tolerance (`K66` → `K-66`) — would need full-text indexing
- Negative tokens (`不要黑色`) — niche
- Range queries (`库存 > 1000`) — different problem class

## Acceptance Criteria

- [ ] All 3 in-scope user examples return non-empty, relevant results
- [ ] 4th example (`巴西 Speedo 贴纸`) returns "巴西" "Speedo" in unresolved_tokens
  but still surfaces `贴纸` results
- [ ] End-to-end latency <3s p95
- [ ] All v1 test cases still pass (no regressions on single-token search)
- [ ] New test count ≥ 12
- [ ] Frontend SKU panel renders aux chips + matched-tokens hint legibly
