# 物料分类字段调研与推荐 (2026-05-09)

> **2026-05-22 OBSOLETE NOTICE**: This doc recommended `MaterialBase.ErpClsID` for the 自制/包材/委外 routing. Live probe (`docs/probes/probe_erp_cls_routing.py`, 23 codes) on 2026-05-22 found ErpClsID is ALSO flat in this tenant (22/23 = `"2"`, including outer cartons and outsourced caps). The correct routing field is `MaterialBase.CategoryID.FName`. See `docs/PLAN_fix_baocai_routing_2026-05-22.md` for the implemented fix.

## 背景

用户在 dashboard 看到的「物料类型」列显示 `自制/外购/委外`（来自 `PRD_PPBOM.FMaterialType`，已知**几乎永远是 1**，信息量低）。
用户希望显示截图里那种细类名，例如 `07.41 硅胶防水袋`。
经过对金蝶 API 的实际探查，发现**与 memory 里记录的不完全一致**，且金蝶有**多个相近字段**容易混淆。本文梳理事实，给出推荐方案。

## 实地探查结果（07.41.001 硅胶防水袋）

通过 `View("BD_MATERIAL", {"Number": "07.41.001"})` 拿到的实际字段：

| 字段路径 | 实际值 | 中文含义 | 备注 |
|---|---|---|---|
| **`MaterialGroup.Number`** | `07.41` | 物料分组**编码** | 截图里那棵树，2 段编码 |
| **`MaterialGroup.Name`** | `硅胶防水袋` | 物料分组**名称** | 用户想显示的细类名 |
| `MaterialGroup.Id` | 1457370 | 内部 ID | 同步时可不要 |
| **`MaterialBase.ErpClsID`** | `"9"` | ERP 大类 | **真正的「自制/外购/委外」分类**，但**字符串**不是整数 |
| `MaterialBase.CategoryID.Number` | `CHLB07_SYS` | 存货类别**编码** | 财务/库存视角 |
| `MaterialBase.CategoryID.Name` | `包装成品` | 存货类别**名称** | 不是树，扁平 ~6-10 个 |
| `MaterialSRC` | `B` | 物料来源 | 字典含义未明 |
| `Number` | `07.41.001` | 物料编码 | 已有 |
| `Name` (MultiLanguageText) | （物料名） | 物料名称 | 已有 |

### ErpClsID 编码字典（与 memory 一致）
| ErpClsID 值 | 含义 |
|---|---|
| `"1"` | 外购 |
| `"2"` | 自制 |
| `"3"` | 委外 |
| `"9"` | Fluent 自定义 — 成品 |

> 备注：**`07.41.001` 的 ErpClsID = "9"（成品）**，跟 memory 里说的"成品/半成品都是 ErpClsID=2 自制"对不上 —— 看来福伦特实际把成品标成了 9。需要后续验证 05.xx 半成品到底是 2 还是有别的代码。

## 字段差异澄清（重点！）

用户提到"很多字段看起来很相近"，下面是关键差异：

### 1. `MaterialGroup` ≠ `MaterialBase.CategoryID` ≠ `ErpClsID`

| 维度 | `MaterialGroup` | `MaterialBase.CategoryID` | `MaterialBase.ErpClsID` |
|---|---|---|---|
| **是什么** | 物料分组（**自定义树**） | 存货类别（K3Cloud 系统字典） | ERP 大类（**采购/生产路由**） |
| **编码格式** | `07.41`（层级，福伦特自定义） | `CHLB07_SYS`（系统枚举） | `"9"`（单字符） |
| **数量级** | ~几百个细类 + 5-10 个根 | 大概 10 个左右扁平类别 | 4 个值 (1/2/3/9) |
| **业务含义** | "这是什么东西"（按品类分） | "怎么管"（主料/辅料/包材/成品...） | "怎么来"（自制/外购/委外） |
| **用户截图所指** | ✅ 就是这个 | ❌ | ❌ |
| **决定路由** | ❌ | ❌ | ✅ |

### 2. `BD_MaterialCategory` (FormId) ≠ "物料分组"
- `BD_MaterialCategory` 是**存货类别字典**（CHLB01_SYS 主料、CHLB02_SYS 辅料等）—— **不是**用户截图里那棵树
- "物料分组"目前**没有发现独立的 FormId**——只能通过 `BD_MATERIAL.MaterialGroup` 反向收集，或者按编码前缀分组

### 3. memory 中需要修正的几条
- ❌ memory: "BD_MATERIAL.FErpClsID 是顶层字段" → ✅ 实际：在 `MaterialBase.ErpClsID`（子表）
- ❌ memory: "9=Fluent-custom 成品（成品/半成品 都是自制 2）" → ❓ 实际样本 (07.41.001) ErpClsID="9"，需要验证 05.xx 半成品才能定论
- ⚠️ ErpClsID 是 **string** 类型 (`"9"`) 不是 int

## 三个候选显示方案

### 方案 A — 单列拼接：`大类 - 细类`
```
成品 - 硅胶防水袋
```
- ✅ 简洁
- ❌ 丢失"自制/外购/委外"的源信息，但其实 ErpClsID 已经隐含了大类（9=成品）
- ❌ 大类名（"成品"/"半成品"）需要硬编码字典或单独同步根节点

### 方案 B — 单列拼接：`来源 · 大类 - 细类`
```
成品 · 成品 - 硅胶防水袋    ← 重复
自制 · 半成品 - 模具         ← OK
外购 · 外购 - 拉链          ← 重复
```
- ❌ 经常重复（ErpClsID 跟 MaterialGroup 根经常等价）
- ❌ 字符长

### 方案 C — 两列分开（推荐 ⭐）
| 列 1（重命名为「来源」） | 列 2（新增「物料分组」） |
|---|---|
| 来自 `MaterialBase.ErpClsID`：自制 / 外购 / 委外 / 成品（用 badge 颜色） | 来自 `MaterialGroup.Name`：硅胶防水袋 |

- ✅ 信息维度分开，独立排序/筛选
- ✅ 老列从**假数据 (FMaterialType)** 切到**真数据 (ErpClsID)**，是净改善
- ✅ 用户可以通过列开关只显示其中一列
- ✅ 符合现有 dashboard 的列结构（`columns[N].visible`）
- ❌ 表格更宽 — 但 BOM card 视图可以并排展示

## 推荐：方案 C

### 数据流
```
BD_MATERIAL (per material, 同步时取)
  ├── MaterialBase.ErpClsID   → erp_class (存到 cache)
  ├── MaterialGroup.Number    → group_number (存到 cache)
  └── MaterialGroup.Name      → group_name (存到 cache)
        │
        ▼
sync_service.py 写入 cached_production_bom（加 3 列）
        │
        ▼
mto_handler.py / cache_reader.py 透传给 ChildItem
        │
        ▼
前端列：
  「来源」      = erp_class_to_label[erp_class]   (自制/外购/委外/成品)
  「物料分组」  = group_name                       (硅胶防水袋)
```

### 改动清单
- `src/readers/factory.py` — BD_MATERIAL FieldMapping 加 3 字段
- `src/readers/models.py` — ProductionBOMModel 加 3 字段（or 单独的 MaterialModel）
- `src/sync/sync_service.py` — INSERT 列加 3 个
- `src/query/cache_reader.py` — SELECT + `_row_to_*` 加 3 列
- `src/models/mto_status.py` — ChildItem 加 `erp_class_label`, `material_group_name`
- `src/api/routers/mto.py` — 序列化包含新字段
- `src/frontend/dashboard.html` + `dashboard.js` — 列开关、表头、单元格、BOM card、过滤器
- 一次性数据回填脚本（已有数据需要补 3 字段）

### 待办验证（实施前先确认）
- [ ] 05.xx 半成品的 ErpClsID 真的是 "2"（自制）吗？还是别的代码？跑 `BD_MATERIAL` 抽样
- [ ] 03.xx 外购 ErpClsID = "1" ?
- [ ] 08.xx 委外加工 ErpClsID = "3" ?
- [ ] 是否所有物料都有 MaterialGroup？(有些虚拟件可能没分组)
- [ ] sync 增加 BD_MATERIAL 拉取的性能影响（多少行？）

## 数量探查待办

用户最初问"有多少种"。已知：
- ErpClsID: **4 种** (1/2/3/9)
- BD_MaterialCategory（存货类别）: 至少 5 种 (CHLB01-05_SYS)，估计 6-10 种
- MaterialGroup（截图里那棵树）: **未知** —— 需要遍历 BD_MATERIAL 收集所有不同的 `MaterialGroup.Number`

下一步如果你同意方案 C，我会做一次性扫描 BD_MATERIAL 把所有 (ErpClsID, MaterialGroup.Number, MaterialGroup.Name) 三元组的去重列表打出来给你看。
