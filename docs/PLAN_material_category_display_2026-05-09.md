# Plan: 物料分组列 (Phase 1)

**Date**: 2026-05-09
**Status**: ✅ COMPLETE (implementation done 2026-05-09 / 2026-05-11)

## 背景与现状

用户在 dashboard 看到的 **「物料类型」** 列显示 `自制 / 外购 / 委外`（来自 `PRD_PPBOM.FMaterialType`），已知**几乎永远是 1**，信息量低。
用户希望显示金蝶物料树里的细类名（"硅胶防水袋"、"泳镜"、"工衣"等），来源自截图所示的 **物料分组 (MaterialGroup)** 树。

经过 API 探查（见 `docs/MATERIAL_CLASSIFICATION_FIELDS_2026-05-09.md`），发现：

| 字段 | 真相 |
|---|---|
| `BD_MATERIAL.MaterialGroup.Number` | `07.41`（编码，截图里那棵树的 FNumber） |
| `BD_MATERIAL.MaterialGroup.Name` | **`硅胶防水袋`**（用户想看的） |
| `PPBOM` chained: `FMaterialId.FMaterialGroup` | **直接返回 group 名字字符串**（单层链，不能再 `.FName`） |
| `SAL_SaleOrder` chained: `FMaterialId.FMaterialGroup` | 同上，07.xx 成品走 SAL 取分组名 |
| `BD_MaterialCategory` 这个 FormId | **不是**截图里那棵树（它是 CHLB01_SYS 主料/辅料/包材 那套存货类别） |

## Phase 1 目标

新增一列「物料分组」显示 `MaterialGroup.Name`。**不动**老「物料类型」列、不动业务路由 (`material_class`)。

## 数据流

```
PRD_PPBOM API → +1 FieldKey: FMaterialId.FMaterialGroup → ProductionBOMModel.material_group_name
                                                              │
                                                              ▼
                                                  cached_production_bom.material_group_name (新列)
                                                              │
                                                              ▼
                                              CacheReader → BOMJoinedRow → mto_handler._bom_row_to_child
                                                              │
                                                              ▼
                                                       ChildItem.material_group_name
                                                              │
SAL_SaleOrder API → +1 FieldKey: FMaterialId.FMaterialGroup → SalesOrderModel.material_group_name
                                                              │  (07.xx 成品路径)
                                                              ▼
                                                  cached_sales_orders.material_group_name (新列)
                                                              │
                                                              ▼
                                              _build_aggregated_sales_child → ChildItem.material_group_name

                          前端 columns 加一项 → dashboard.html 表格 + BOM card 新列「物料分组」
```

## 已完成的改动

**Schema / Migration (2 files)**
- ✅ `src/database/schema.sql` — 两个表加 `material_group_name TEXT DEFAULT ''`
- ✅ `src/database/migrations/011_add_material_group_to_bom.sql`
- ✅ `src/database/migrations/012_add_material_group_to_sales_orders.sql`
- ✅ `src/database/connection.py` — `_column_guards` 加两条

**Readers (2 files)**
- ✅ `src/readers/factory.py` — PRODUCTION_BOM_CONFIG 和 SALES_ORDER_CONFIG 各加 `material_group_name` FieldMapping
- ✅ `src/readers/models.py` — ProductionBOMModel 和 SalesOrderModel 各加字段

**Cache + Sync (2 files)**
- ✅ `src/query/cache_reader.py` —
  - `BOMJoinedRow` 加字段
  - `get_production_bom` / `get_production_bom_by_mto` / `get_sales_orders` SELECTs 加列
  - `get_mto_bom_joined` 大 SQL 外层 SELECT 加 `br.material_group_name`（位置 27，synced_at 移到 28）
  - `_row_to_bom` / `_row_to_bom_joined` / `_row_to_sales_order` 读新列
- ✅ `src/sync/sync_service.py` — `_upsert_production_bom` 和 `_upsert_sales_orders_no_commit` INSERT 加列

**Domain + Handler (2 files)**
- ✅ `src/models/mto_status.py` — `ChildItem` 加 `material_group_name: str = ""`
- ✅ `src/query/mto_handler.py` — `_make_row` 加参数 + Step 1 call site 传值；`_bom_row_to_child` 4 个分支都populate；`_build_aggregated_sales_child` (07.xx 成品) 也populate

**Frontend (2 files)**
- ✅ `src/frontend/static/js/dashboard.js` — `columns` 数组加 `{ key: 'material_group_name', label: '物料分组', ... }` 在 material_type 之后
- ✅ `src/frontend/dashboard.html` — 新增 `<th>` + 表 `<td>` + 合计 `<td>` + BOM card item

**Tests (2 files)**
- ✅ `tests/unit/test_cache_reader.py` — `_row_to_bom` / `_row_to_sales_order` 测试 tuple 加列 + 断言
- ✅ `tests/unit/test_cache_reader_joined.py` — `_row_to_bom_joined` 3 个 row tuple 加列

## 验证

- ✅ 全套 unit tests 通过：`839 passed`（3 个失败是 main 上预先就有的 API endpoint 测试，跟本次改动无关）
- ⏳ 待做：smoke test in dev — 启动 dev server，查询 MTO，确认 UI 显示新列

## Phase 2（后续，看 Phase 1 反馈再做）

修复老「物料类型」列的假数据：从 `PRD_PPBOM.FMaterialType` 切到 `MaterialBase.ErpClsID`（真正的自制 / 外购 / 委外 / 成品）。需要先抽样验证 05.xx / 03.xx / 08.xx 各自的 ErpClsID 取值是否符合预期。

## 不做的事

- ❌ 同步独立的分类树字典（金蝶没暴露独立 FormId，且 group 名字已经能通过 PPBOM 单层链拿到）
- ❌ 引入 `MaterialBase.CategoryID`（CHLB07_SYS 那套，跟需求无关）
- ❌ 动 `material_class` 业务路由
- ❌ 合并 Phase 2（违反 "3 层缓存一致性" 风险）
