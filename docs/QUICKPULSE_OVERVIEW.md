# QuickPulse V2 功能说明

## 一、QuickPulse 能做什么？

| 功能 | 说明 |
|------|------|
| **MTO 状态查询** | 输入计划跟踪号（如 AK2510034），查看该订单下所有物料的订单、领料、入库状态 |
| **三类物料追踪** | 成品(07.xx)、自制(05.xx)、包材(03.xx) 各有独立的数据来源和显示逻辑 |
| **实时/缓存切换** | 默认使用缓存（<100ms），也可强制实时查询（1-5s） |
| **筛选排序** | 按物料类型筛选、按任意列排序、全文搜索 |
| **导出 Excel/CSV** | 一键导出当前查询结果 |
| **订单关联图** | 查看 MTO 关联的所有单据（销售订单、生产订单、采购订单等） |

---

## 二、UI 显示字段

### 表头信息（ParentItem）

| UI 字段 | 说明 | 数据来源 |
|---------|------|----------|
| **MTO** | 计划跟踪号 | 用户输入 |
| **客户** | 客户名称 | SAL_SaleOrder.FCustId.FName |
| **交期** | 交货日期 | SAL_SaleOrder.FDeliveryDate |
| **数据** | 缓存/实时 | 系统标识 |

### BOM 组件明细表（ChildItem）

#### 基础列（所有物料类型通用）

| UI 列名 | 说明 | 备注 |
|---------|------|------|
| **序号** | 行号 | 前端生成 |
| **物料编码** | 物料唯一标识 | 如 07.04.231、05.01.123、03.02.456 |
| **物料名称** | 物料中文名 | |
| **规格型号** | 物料规格 | |
| **BOM简称** | BOM 名称 | 仅成品(07.xx)显示 |
| **辅助属性** | 颜色/尺码等变体信息 | 从 BD_FLEXSITEMDETAILV 查询 |
| **物料类型** | 成品/自制/包材 | 根据编码前缀判断 |

#### 数量列（按物料类型显示不同数据）

| UI 列名 | 物料类型 | 含义 | 计算方式 |
|---------|----------|------|----------|
| **销售订单.数量** | 成品(07.xx) | 销售订单数量 | Σ SAL_SaleOrder.FQty |
| **生产入库单.应收数量** | 自制(05.xx) | 应该入库的数量 | Σ PRD_INSTOCK.FMustQty |
| **采购订单.数量** | 包材(03.xx) | 采购订单数量 | Σ PUR_PurchaseOrder.FQty 或 PPBOM.FMustQty |
| **生产领料单.实发数量** | 自制+包材 | 实际领出的数量 | Σ PRD_PickMtrl.FActualQty |
| **生产入库单.实收数量** | 成品+自制 | 实际入库的数量 | Σ PRD_INSTOCK.FRealQty |
| **采购订单.累计入库数量** | 包材(03.xx) | 采购已入库数量 | Σ PUR_PurchaseOrder.FStockInQty |

#### 列与物料类型对应关系

| UI 列 | 07.xx 成品 | 05.xx 自制 | 03.xx 包材 |
|-------|:----------:|:----------:|:----------:|
| 销售订单.数量 | ✅ | - | - |
| 生产入库单.应收数量 | - | ✅ | - |
| 采购订单.数量 | - | - | ✅ |
| 生产领料单.实发数量 | - | ✅ | ✅ |
| 生产入库单.实收数量 | ✅ | ✅ | - |
| 采购订单.累计入库数量 | - | - | ✅ |

---

## 三、取数逻辑

### 整体流程（BOM-first 架构，2026-03 重构后）

#### 缓存路径（默认，<100ms）

```
用户输入 MTO 号
    │
    ▼ 3 个 SQL 查询（SQLite JOIN）
    ├── SAL_SaleOrder      → 成品(07.xx)父项信息
    ├── PRD_MO             → 生产订单信息
    └── BOM JOIN 查询      → PPBOM LEFT JOIN 入库/领料/采购
    │                        一次 SQL JOIN 完成所有物料的数据关联
    │
    ▼ _bom_row_to_child() 统一转换
    │  （cache 和 live 路径共用同一方法）
    │
    ▼ 返回 UI 显示
```

#### 实时路径（`?source=live`，1-5s）

```
用户输入 MTO 号
    │
    ▼ 并行查询金蝶 API
    ├── SAL_SaleOrder      (销售订单)
    ├── PRD_MO             (生产订单)
    ├── PRD_PPBOM          (生产用料清单)
    ├── PRD_INSTOCK        (生产入库单)
    ├── STK_InStock        (采购入库单)
    ├── PUR_PurchaseOrder  (采购订单)
    ├── PRD_PickMtrl       (生产领料单)
    └── SAL_OUTSTOCK       (销售出库单)
    │
    ▼ 构造 synthetic BOMJoinedRow
    │
    ▼ _bom_row_to_child() 统一转换（同缓存路径）
    │
    ▼ 返回 UI 显示
```

> **`?source=cache|live` 参数**：可通过 API 查询参数强制指定数据路径，方便调试和对比。

### 分物料类型取数

> **BOM-first 架构要点**：所有物料都以 PRD_PPBOM 为起点，通过 SQL JOIN（缓存路径）或构造 synthetic row（实时路径）关联入库/领料/采购数据。这避免了旧架构中 Python 字典匹配导致的数据遗漏。

#### 成品 (07.xx)

| UI 字段 | 数据来源 | 聚合方式 |
|---------|----------|----------|
| 销售订单.数量 | SAL_SaleOrder | 按 (物料编码, 辅助属性) 汇总 FQty |
| 生产入库单.实收数量 | PRD_INSTOCK | 按 (物料编码, 辅助属性) 汇总 FRealQty |
| BOM简称 | SAL_SaleOrder | FBomId.FName |
| 完成率 | 计算字段 | 实收数量 / 销售订单数量 |

#### 自制 (05.xx)

| UI 字段 | 数据来源 | 聚合方式 |
|---------|----------|----------|
| 生产入库单.应收数量 | PRD_MO.FQty | 生产订单数量（非入库单的 FMustQty） |
| 生产入库单.实收数量 | PRD_INSTOCK | 按 (物料编码, 辅助属性) 汇总 FRealQty |
| 生产领料单.实发数量 | PRD_PickMtrl | 按 (物料编码, 辅助属性) 汇总 FActualQty |
| 完成率 | 计算字段 | 实收数量 / 应收数量 |

#### 包材 (03.xx)

| UI 字段 | 数据来源 | 聚合方式 |
|---------|----------|----------|
| 采购订单.数量 | PUR_PurchaseOrder | 按 (物料编码, 辅助属性) 汇总 FQty |
| 生产领料单.实发数量 | PRD_PickMtrl | 按 (物料编码, 辅助属性) 汇总 FActualQty |
| 采购订单.累计入库数量 | PUR_PurchaseOrder | FStockInQty |
| 完成率 | 计算字段 | 累计入库数量 / 采购订单数量 |

---

## 四、计算逻辑

### 聚合规则

所有数量字段都按 **(物料编码, 辅助属性ID)** 进行聚合，确保：
- 同一物料的不同颜色/尺码分别显示
- 同一 MTO 下多张单据的数量累加

```python
# 示例：汇总领料实发数量
pick_actual_qty = Σ PRD_PickMtrl.FActualQty
    WHERE material_code = '03.02.456'
    AND aux_prop_id = 12345
```

### 合计行

表格底部显示各列合计：

| UI 列 | 合计计算 |
|-------|----------|
| 销售订单.数量 | Σ 所有 07.xx 物料的 sales_order_qty |
| 生产入库单.应收数量 | Σ 所有 05.xx 物料的 prod_instock_must_qty |
| 采购订单.数量 | Σ 所有 03.xx 物料的 purchase_order_qty |
| 生产领料单.实发数量 | Σ 所有物料的 pick_actual_qty |
| 生产入库单.实收数量 | Σ 所有物料的 prod_instock_real_qty |
| 采购订单.累计入库数量 | Σ 所有 03.xx 物料的 purchase_stock_in_qty |

---

## 五、缓存策略

### 三级缓存

| 级别 | 存储 | 响应时间 | TTL |
|------|------|----------|-----|
| L1 | 内存 (TTLCache) | ~1-5ms | 5 分钟 |
| L2 | SQLite | ~100ms | 定时同步 |
| L3 | 金蝶 API | 1-5s | 实时 |

### 同步时间

每日 **07:00, 12:00, 16:00, 18:00** 自动从金蝶同步数据到 SQLite 缓存。

---

## 六、关键代码文件

| 文件 | 职责 |
|------|------|
| `src/query/mto_handler.py` | MTO 查询核心逻辑（~1077 行），BOM-first 架构的 `_bom_row_to_child()` 统一转换 |
| `src/query/cache_reader.py` | 缓存数据读取（~645 行），`get_mto_bom_joined()` SQL JOIN 查询 |
| `src/frontend/dashboard.html` | UI 表格定义，列显示逻辑 |
| `src/frontend/static/js/dashboard.js` | Alpine.js 前端状态管理，含聊天侧边栏 |
| `config/mto_config.json` | 物料类型路由配置 |
| `src/readers/factory.py` | 金蝶字段映射（实时路径） |
| `src/sync/sync_service.py` | 数据同步写入 SQLite |
| `src/models/mto_status.py` | Pydantic 响应模型 |
| `src/chat/` | DeepSeek LLM 聊天功能（client, context, prompts, sql_guard） |
| `src/agents/` | Agent 双代理管道（RetrievalAgent + ReasoningAgent） |
| `src/api/routers/admin.py` | 使用分析/IP 地理定位管理后台 |

---

## 七、注意事项

1. **UI 字段与金蝶字段解耦** - UI 显示的列名（如"采购订单.数量"）是业务语义，实际数据可能来自 PUR_PurchaseOrder.FQty、PRD_PPBOM.FMustQty 或 PRD_PickMtrl.FAppQty，取决于物料的数据来源

2. **辅助属性是关键** - 同一物料编码可能有多个颜色/尺码变体，系统按 (material_code, aux_prop_id) 分别显示，避免合并导致数据混淆

3. **三种包材数据来源** - 包材(03.xx)物料可能来自采购订单、BOM 领料清单或直接领料，系统会分别显示为独立行

---

## 八、部署环境

### CVM (共享阿里云 ECS)

| 环境 | 域名 (HTTPS) | 旧端口 | 分支 |
|------|-------------|--------|------|
| **生产** | `https://fltpulse.szfluent.cn` | `:8003` | `main` |
| **开发** | `https://dev.fltpulse.szfluent.cn` | `:8004` | `develop` |

- **部署命令**: `/opt/ops/scripts/deploy.sh quickpulse <prod|dev>`
- **CI/CD**: 推送到 `develop` 自动部署 dev；手动触发部署 prod
- **配置文件**: `/opt/ops/secrets/quickpulse/{prod,dev}.env` (KINGDEE_* 凭据)
- **详细文档**: `docs/CVM_INFRASTRUCTURE.md`
