# Plan: 修复数据源标签不匹配问题

## Status: Complete (Stages 1-4 done, Stage 5 deferred pending user decision)

## 背景

审计发现 14 个问题，核心根因是两个：
1. **PPBOM 数据被当作其他表单数据使用** — `need_qty`(PPBOM.FMustQty) 被赋给了 `prod_instock_must_qty`，还作为采购/委外的 fallback
2. **aux_prop_id fallback 太宽松** — 精确匹配失败时混入不同变体数据

## Design Spec

### 问题清单

| # | 严重度 | 问题 | 文件:行 |
|---|--------|------|---------|
| 1 | 🔴 | prod_instock_must_qty 取 PPBOM 而非 PRD_INSTOCK | mto_handler.py:867 |
| 2 | 🔴 | 外购 fallback 到 PPBOM.need_qty | mto_handler.py:879 |
| 3 | 🔴 | 委外 fallback 到 PPBOM.need_qty | mto_handler.py:891 |
| 4 | 🔴 | aux fallback 双重计数 | cache_reader.py:321-350 |
| 5 | 🔴 | 成品 aux fallback 不汇总变体 | mto_handler.py:814-821 |
| 6 | 🟡 | fulfillment_rate 分母用错 | semantic/metrics.py |
| 7 | 🟡 | 外购 pick_actual_qty fallback 到 PPBOM | mto_handler.py:881 |
| 8 | 🟡 | 委外列名不区分 | dashboard.js |
| 9 | 🟡 | mo_bill_no 与 SUM 不匹配 | cache_reader.py:301-308 |
| 10 | 🟡 | mto_config provenance 文档失实 | mto_config.json:139 |
| 11 | 🟢 | materialTypeFilter 死代码 | dashboard.js |
| 12 | 🟢 | config 定义了不存在的列 | mto_config.json |
| 13 | 🟢 | SAL_OUTSTOCK 数据取了没用 | mto_handler.py |
| 14 | 🟢 | 成品 material_type=1 与自制冲突 | mto_handler.py:829 |

---

## Stage 1: 修复自制件数据源 (#1, #6)

**Goal**: `prod_instock_must_qty` 用 PRD_INSTOCK.FMustQty，不再用 PPBOM.FMustQty

**前置确认**: `prod_receipt_must_qty` 已在 BOMJoinedRow 中存在（cache: column index 12, live: 已实现）

**Changes**:

### 1a. mto_handler.py:867
```python
# Before:
prod_instock_must_qty=row.need_qty,

# After:
prod_instock_must_qty=row.prod_receipt_must_qty,
```

### 1b. mto_handler.py:908 (unknown type fallback)
```python
# Before:
prod_instock_must_qty=row.need_qty,

# After:
prod_instock_must_qty=row.prod_receipt_must_qty,
```

### 1c. 更新注释 (mto_handler.py:904-907)
删除 "Despite the field name" 的警告注释，因为修复后 field name 和数据源一致了。

**Success Criteria**:
- `pytest tests/unit/test_mto_handler.py -v` 通过（更新相关 assertions）
- 查询 DS263039S，自制件的"生产入库单.应收数量"显示整数（如 4,763），不再是小数（45,248.5）

**Files**:
- `src/query/mto_handler.py` (modify)
- `tests/unit/test_mto_handler.py` (modify)

---

## Stage 2: 移除 PPBOM fallback (#2, #3, #7)

**Goal**: 外购/委外没有订单数据时显示 0，不再用 PPBOM 数据冒充

**Changes**:

### 2a. mto_handler.py:879 (外购)
```python
# Before:
purchase_order_qty=row.purchase_order_qty if row.purchase_order_qty else row.need_qty,

# After:
purchase_order_qty=row.purchase_order_qty,
```

### 2b. mto_handler.py:891 (委外)
```python
# Before:
purchase_order_qty=row.subcontract_order_qty if row.subcontract_order_qty else row.need_qty,

# After:
purchase_order_qty=row.subcontract_order_qty,
```

### 2c. mto_handler.py:881 (外购 pick fallback)
```python
# Before:
pick_actual_qty=row.pick_actual_qty if row.pick_actual_qty else row.picked_qty,

# After:
pick_actual_qty=row.pick_actual_qty,
```

**Impact 评估**:
- 如果某个外购物料没有创建采购订单，该列会显示 0 而非 PPBOM 需求量
- 这是正确行为：没有采购订单就应该显示 0，不应该静默替换
- fulfillment_rate 计算：分母为 0 时，前端已有保护（显示 "-"）

**Success Criteria**:
- `pytest tests/unit/test_mto_handler.py -v` 通过
- 外购物料无 PO 时，"采购订单.数量"显示 0 或 "-"，不再显示 BOM 数量

**Files**:
- `src/query/mto_handler.py` (modify)
- `tests/unit/test_mto_handler.py` (modify)

---

## Stage 3: 更新配置文档 (#10, #12)

**Goal**: mto_config.json 的 provenance 与实际代码一致

**Changes**:

### 3a. mto_config.json provenance 修正
```json
// Before:
"prod_instock_must_qty": { "source_form": "PRD_INSTOCK", "kingdee_field": "FMustQty" }

// After (Stage 1 修复后这就是对的了，只需确认)
"prod_instock_must_qty": { "source_form": "PRD_INSTOCK", "kingdee_field": "FMustQty" }
```

### 3b. 清理 config 中不存在的列定义
移除 `required_qty`、`picked_qty`、`unpicked_qty`、`order_qty`、`receipt_qty`、`unreceived_qty` 等在 ChildItem 中不存在的字段。

**Success Criteria**:
- config 中每个 provenance 条目都能在代码中找到对应的数据流
- 无残留的死配置

**Files**:
- `config/mto_config.json` (modify)

---

## Stage 4: 修复 aux_prop_id fallback (#4, #5)

**Goal**: fallback 不再混入不同变体数据

**⚠️ 风险评估**: 这是影响最大的修改，改变了 cache SQL JOIN 逻辑，需要充分测试

**Changes**:

### 4a. cache_reader.py — 收紧 fallback 条件
当前逻辑：精确匹配失败 → 按 material_code 汇总所有 aux
改为：精确匹配失败 → 只 fallback 到 aux=0 的记录（金蝶"未指定变体"的标志）

```sql
-- Before (pr0):
LEFT JOIN (
    SELECT material_code, SUM(real_qty)...
    FROM cached_production_receipts WHERE mto_number LIKE ?
    GROUP BY material_code
) pr0 ON br.material_code = pr0.material_code

-- After: fallback 只匹配 aux_prop_id=0
LEFT JOIN (
    SELECT material_code, SUM(real_qty)...
    FROM cached_production_receipts WHERE mto_number LIKE ? AND aux_prop_id = 0
    GROUP BY material_code
) pr0 ON br.material_code = pr0.material_code
```

对所有 fallback JOIN 做同样的修改（pr0, pk0, po0, pur0, sub0）。

### 4b. mto_handler.py — live path fallback 对齐
更新 `_get()` 函数的 fallback 逻辑，只 fallback 到 aux=0，与 SQL 一致。

### 4c. 成品 aux fallback
修改 `_build_aggregated_sales_child` 中的 fallback，从只查 `(code, 0)` 改为汇总同 code 的所有 aux 变体。

**Success Criteria**:
- `pytest tests/unit/test_cache_reader_joined.py -v` 通过
- `pytest tests/unit/test_mto_handler.py -v` 通过
- 多变体物料的数量不再膨胀

**Files**:
- `src/query/cache_reader.py` (modify)
- `src/query/mto_handler.py` (modify)
- `tests/unit/test_cache_reader_joined.py` (modify)
- `tests/unit/test_mto_handler.py` (modify)

**Depends on**: Stage 1, Stage 2 (先改赋值逻辑，再改 JOIN 逻辑)

---

## Stage 5: 前端标签清理 (#8, #11)

**Goal**: 委外列名区分、清理死代码

**Changes**:

### 5a. 委外件列名区分
考虑方案：
- **方案A**: 后端给委外件的 ChildItem 加标记，前端根据 material_type 动态显示不同列名
- **方案B**: 保持现有列名不变（采购订单.数量），因为用户已习惯

**待确认**: 需要与用户确认是否需要区分委外/采购的列名

### 5b. 移除 materialTypeFilter 死代码
删除 dashboard.js columns 中未使用的 `materialTypeFilter` 属性。

**Success Criteria**:
- 前端正常渲染
- 无死代码

**Files**:
- `src/frontend/static/js/dashboard.js` (modify)
- `src/frontend/dashboard.html` (可能 modify)

**Depends on**: 无依赖，可与其他 Stage 并行

---

## 不修复的项目

| # | 问题 | 原因 |
|---|------|------|
| 9 | mo_bill_no 与 SUM 不匹配 | 设计如此：显示的是 MTO 级汇总，mo_bill_no 仅做参考 |
| 13 | SAL_OUTSTOCK 数据没用 | 当前产品不需要显示销售出库，留作未来扩展 |
| 14 | 成品 material_type=1 | is_finished_goods 已正确区分，改 type 值风险大收益小 |

---

## 执行顺序

```
Stage 1 (自制件数据源) ──→ Stage 2 (移除 fallback) ──→ Stage 4 (aux fallback)
                                                           │
Stage 3 (config 文档) ─────────────────────────────────────┘ (Stage 1 完成后即可)
Stage 5 (前端清理) ────────────────────────────────────────── (独立，随时可做)
```

## Test Cases

### Unit Tests
- [ ] 自制件 prod_instock_must_qty 取自 prod_receipt_must_qty，不是 need_qty
- [ ] 外购件无 PO 时 purchase_order_qty = 0，不是 PPBOM need_qty
- [ ] 委外件无 SO 时 purchase_order_qty = 0，不是 PPBOM need_qty
- [ ] 外购件无领料时 pick_actual_qty = 0，不是 PPBOM picked_qty
- [ ] aux fallback 只匹配 aux=0，不汇总所有 aux
- [ ] 成品多变体时 prod_instock_real_qty 正确汇总

### Manual Verification
1. 查询 DS263039S — 自制件"应收数量"应为整数（如 4,763）
2. 查询一个有外购但无 PO 的 MTO — "采购订单.数量"应显示 0 或 "-"
3. 查询一个多变体物料的 MTO — 检查各变体数量不膨胀

## Acceptance Criteria
- [ ] 所有列的数据来源与标签名称一致
- [ ] 无 PPBOM 数据被静默替换到其他列
- [ ] aux_prop_id 不同的变体不会互相污染
- [ ] 718 个现有测试通过（更新 assertions 后）
- [ ] 本地 `uvicorn` 启动后查询 DS263039S 正常
