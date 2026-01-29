# MTO 配置文档 - 数量字段设置与金蝶字段映射

## 配置文件位置

**`config/mto_config.json`** - 可配置的数量字段设置文件

---

## 一、系统架构概述

### 物料分类识别规则

系统根据 **物料编码前缀** 自动识别物料类型，并路由到对应的金蝶表单查询：

| 分类ID | 编码规则 (`pattern`) | 显示名称 | 数据来源表单 | MTO字段 |
|--------|---------------------|----------|-------------|---------|
| `finished_goods` | `^07\.` (07开头) | 成品 | `SAL_SaleOrder` 销售订单 | `FMtoNo` |
| `self_made` | `^05\.` (05开头) | 自制 | `PRD_MO` 生产订单 | `FMTONo` |
| `purchased` | `^03\.` (03开头) | 外购 | `PUR_PurchaseOrder` 采购订单 | `FMtoNo` |

---

## 二、UI 列与数据源映射

### 成品 (07.xx.xxx) - 销售订单流程

| UI 列名 | 配置字段 | 数据来源表单 | 金蝶字段 | 中文说明 | 匹配方式 |
|---------|---------|-------------|----------|---------|---------|
| **需求数量** | `required_qty` | `SAL_SaleOrder` | `FQty` | 数量 | - |
| **已领数量** | `picked_qty` | `SAL_OUTSTOCK` | `FRealQty` | 实收/实发数量 | 物料编码 + 辅助属性 |
| **未领数量** | `unpicked_qty` | 计算 | - | `需求数量 - 已领数量` | - |
| **订单数量** | `order_qty` | `SAL_SaleOrder` | `FQty` | 数量 | - |
| **入库数量** | `receipt_qty` | `PRD_INSTOCK` | `FRealQty` | 实收/实发数量 | 物料编码 + 辅助属性 |
| **未入数量** | `unreceived_qty` | 计算 | - | `订单数量 - 入库数量` | - |

### 自制件 (05.xx.xxx) - 生产订单流程

| UI 列名 | 配置字段 | 数据来源表单 | 金蝶字段 | 中文说明 | 匹配方式 |
|---------|---------|-------------|----------|---------|---------|
| **需求数量** | `required_qty` | `PRD_MO` | `FQty` | 数量 | - |
| **已领数量** | `picked_qty` | `PRD_PickMtrl` | `FActualQty` | 实领数量 | 物料编码 |
| **未领数量** | `unpicked_qty` | `PRD_PickMtrl` | `FAppQty - FActualQty` | 申请数量 - 实领数量 | 物料编码 |
| **订单数量** | `order_qty` | `PRD_MO` | `FQty` | 数量 | - |
| **入库数量** | `receipt_qty` | `PRD_INSTOCK` | `FRealQty` | 实收/实发数量 | 物料编码 |
| **未入数量** | `unreceived_qty` | 计算 | - | `订单数量 - 入库数量` | - |

### 外购件 (03.xx.xxx) - 采购订单流程

| UI 列名 | 配置字段 | 数据来源表单 | 金蝶字段 | 中文说明 | 匹配方式 |
|---------|---------|-------------|----------|---------|---------|
| **需求数量** | `required_qty` | `PUR_PurchaseOrder` | `FQty` | 数量 | - |
| **已领数量** | `picked_qty` | `PRD_PickMtrl` | `FActualQty` | 实领数量 | 物料编码 |
| **未领数量** | `unpicked_qty` | 计算 | - | `需求数量 - 已领数量` | - |
| **订单数量** | `order_qty` | `PUR_PurchaseOrder` | `FQty` | 数量 | - |
| **入库数量** | `receipt_qty` | `PUR_PurchaseOrder` | `FStockInQty` | 累计入库数量 | 直接从采购订单 |
| **未入数量** | `unreceived_qty` | `PUR_PurchaseOrder` | `FRemainStockInQty` | 未入库数量 | 直接从采购订单 |

---

## 三、金蝶表单字段清单

### 3.1 生产订单 PRD_MO (生产订单)

| 金蝶字段 | 中文说明 | 示例值 | 用途 |
|---------|---------|--------|------|
| `FBillNo` | 单据编号 | MO25010001 | 生产订单号 |
| `FMTONo` | **计划跟踪号** | AK2412023 | MTO查询主键 |
| `FMaterialId.FNumber` | 物料编码 | 06.04.087 | 物料匹配 |
| `FMaterialId.FName` | 物料名称 | 未包装呼吸管 | 显示 |
| `FMaterialId.FSpecification` | 规格型号 | SN9871-成人咬嘴 | 显示 |
| `FQty` | **数量** | 1300 | 需求数量/订单数量 |
| `FStatus` | 生产状态 | 3 | 状态判断 |
| `FWorkShopID.FName` | 生产车间 | 包装工段 | 显示 |
| `FNoStockInQty` | 未入库数量 | 1300 | 未入数量 |
| `FAuxPropId` | 辅助属性 | 客户型号:6001292 | 变体匹配 |

**生产状态 (FStatus) 值说明:**
| 值 | 说明 |
|----|------|
| 1 | 计划 |
| 2 | 计划确认 |
| 3 | 下达 |
| 4 | 开工 |
| 5 | 完工 |
| 6 | 结案 |

---

### 3.2 生产入库单 PRD_INSTOCK (生产入库单)

| 金蝶字段 | 中文说明 | 示例值 | 用途 |
|---------|---------|--------|------|
| `FBillNo` | 单据编号 | CP25020001 | 入库单号 |
| `FMtoNo` | **计划跟踪号** | AK2412053 | MTO查询 |
| `FMaterialId.FNumber` | 物料编码 | 05.02.27.022 | 物料匹配 |
| `FMustQty` | **应收数量** | 9072.0 | 应入库数量 |
| `FRealQty` | **实收数量** | 1365.0 | 实际入库数量 |
| `FMoBillNo` | 生产订单编号 | MO250110899 | 关联生产订单 |
| `FAuxPropId` | 辅助属性 | (object) | 变体匹配 |
| `FLot` | 批号 | AK2412053 | 批次追溯 |
| `FWorkShopId` | 车间 | 03 | 车间信息 |

---

### 3.3 采购订单 PUR_PurchaseOrder (采购订单)

| 金蝶字段 | 中文说明 | 示例值 | 用途 |
|---------|---------|--------|------|
| `FBillNo` | 单据编号 | F2412390 | 采购单号 |
| `FMtoNo` | **计划跟踪号** | 2406192-A2 | MTO查询 |
| `FMaterialId.FNumber` | 物料编码 | 21.11.020.04 | 物料匹配 |
| `FMaterialId.FName` | 物料名称 | - | 显示 |
| `FQty` | **数量** | 150.0 | 订单数量 |
| `FStockInQty` | **累计入库数量** | 150.0 | 已入库数量 |
| `FRemainStockInQty` | **未入库数量** | 0.0 | 待入库数量 |
| `FAuxPropId` | 辅助属性 | - | 变体匹配 |
| `FDeliveryDate` | 交货日期 | 2024-12-23 | 交期信息 |
| `FSupplierId` | 供应商 | 03.0827 | 供应商信息 |

---

### 3.4 生产领料单 PRD_PickMtrl (生产领料单)

| 金蝶字段 | 中文说明 | 示例值 | 用途 |
|---------|---------|--------|------|
| `FBillNo` | 单据编号 | LL25040001 | 领料单号 |
| `FMTONO` | **计划跟踪号** | DS252019S | MTO查询 |
| `FMaterialId.FNumber` | 物料编码 | 05.20.01.01.027 | 物料匹配 |
| `FAppQty` | **申请数量** | 2000.0 | 申请领料数量 |
| `FActualQty` | **实领数量** | 1000.0 | 实际领料数量 |
| `FMoBillNo` | 生产订单编号 | MO250302174 | 关联生产订单 |
| `FPPBomBillNo` | 生产用料清单 | PPBOM250301013 | 关联BOM |
| `FAuxPropId` | 辅助属性 | (object) | 变体匹配 |
| `FWorkShopId` | 车间 | 20 | 车间信息 |

**领料数量计算:**
- **已领数量** = `FActualQty` (实领数量)
- **未领数量** = `FAppQty` - `FActualQty` (申请数量 - 实领数量)

---

### 3.5 销售出库单 SAL_OUTSTOCK (销售出库单)

| 金蝶字段 | 中文说明 | 示例值 | 用途 |
|---------|---------|--------|------|
| `FBillNo` | 单据编号 | XSCKD000001 | 出库单号 |
| `FMTONO` | **计划跟踪号** | 2411294 | MTO查询 |
| `FMaterialId.FNumber` | 物料编码 | 27.09.02.03.01 | 物料匹配 |
| `FMustQty` | **应发数量** | 0.0 | 应出库数量 |
| `FRealQty` | **实发数量** | 133.0 | 实际出库数量 |
| `FAuxPropId` | 辅助属性 | - | 变体匹配 |
| `FCustomerID` | 客户 | 09.048 | 客户信息 |
| `FLot` | 批号 | 2411294 | 批次追溯 |
| `FStockID` | 仓库 | 07.01 | 仓库信息 |

---

### 3.6 销售订单 SAL_SaleOrder (销售订单)

| 金蝶字段 | 中文说明 | 示例值 | 用途 |
|---------|---------|--------|------|
| `FBillNo` | 单据编号 | XSDD2501001 | 销售单号 |
| `FMtoNo` | **计划跟踪号** | AK2501001 | MTO查询 |
| `FMaterialId.FNumber` | 物料编码 | 07.04.231 | 物料匹配 |
| `FMaterialId.FName` | 物料名称 | - | 显示 |
| `FMaterialId.FSpecification` | 规格型号 | - | 显示 |
| `FQty` | **数量** | 1000.0 | 订单数量 |
| `FCustId.FName` | 客户名称 | 法国ITS | 显示 |
| `FDeliveryDate` | 交货日期 | 2025-02-15 | 交期信息 |
| `FAuxPropId` | 辅助属性 | - | 变体匹配 |

---

### 3.7 采购入库单 STK_InStock (采购入库单)

| 金蝶字段 | 中文说明 | 示例值 | 用途 |
|---------|---------|--------|------|
| `FBillNo` | 单据编号 | RK25010001 | 入库单号 |
| `FMtoNo` | **计划跟踪号** | AK2501001 | MTO查询 |
| `FMaterialId.FNumber` | 物料编码 | 03.01.001 | 物料匹配 |
| `FMustQty` | **应收数量** | 100.0 | 应入库数量 |
| `FRealQty` | **实收数量** | 100.0 | 实际入库数量 |
| `FBillTypeID.FNumber` | **单据类型编码** | RKD01_SYS / RKD02_SYS | 区分外购/委外 |
| `FPOOrderNo` | 采购订单号 | F2501001 | 关联采购订单 |

**单据类型说明:**
| 类型编码 | 说明 |
|---------|------|
| `RKD01_SYS` | 外购入库 (采购入库) |
| `RKD02_SYS` | 委外入库 (委外加工入库) |

---

## 四、入库数据源配置 (receipt_sources)

配置文件中 `receipt_sources` 定义了各类单据的字段映射：

```json
{
  "receipt_sources": {
    "PRD_INSTOCK": {
      "form_id": "PRD_INSTOCK",
      "mto_field": "FMtoNo",
      "qty_field": "FRealQty",
      "material_field": "FMaterialId.FNumber",
      "link_field": "FMoBillNo"
    },
    "STK_InStock": {
      "form_id": "STK_InStock",
      "mto_field": "FMtoNo",
      "qty_field": "FRealQty",
      "material_field": "FMaterialId.FNumber",
      "link_field": "FPOOrderNo"
    },
    "SAL_OUTSTOCK": {
      "form_id": "SAL_OUTSTOCK",
      "mto_field": "FMTONO",
      "qty_field": "FRealQty",
      "material_field": "FMaterialId.FNumber"
    },
    "PRD_PickMtrl": {
      "form_id": "PRD_PickMtrl",
      "mto_field": "FMTONO",
      "qty_field": "FActualQty",
      "app_qty_field": "FAppQty",
      "material_field": "FMaterialId.FNumber"
    }
  }
}
```

---

## 五、匹配逻辑说明

### 5.1 match_by 配置

`match_by` 字段决定如何汇总入库/出库数量：

| 配置值 | 说明 | 适用场景 |
|--------|------|---------|
| `["material_code"]` | 仅按物料编码匹配汇总 | 自制件、无变体物料 |
| `["material_code", "aux_attributes"]` | 按物料编码 + 辅助属性匹配 | 成品、有颜色/尺寸等变体的物料 |

### 5.2 物料类型 (FMaterialType) - PRD_PPBOM

生产用料清单中的物料类型决定后续查询路径：

| 值 | 说明 | 入库查询表单 | 入库类型过滤 |
|----|------|-------------|-------------|
| 1 | 自制件 | `PRD_INSTOCK` | - |
| 2 | 外购件 | `STK_InStock` | `FBillTypeID.FNumber='RKD01_SYS'` |
| 3 | 委外件 | `STK_InStock` | `FBillTypeID.FNumber='RKD02_SYS'` |

---

## 六、常用单据状态

### 单据状态 (FDocumentStatus)

所有单据通用的状态值：

| 值 | 说明 |
|----|------|
| A | 创建 |
| B | 审核中 |
| C | 已审核 |
| Z | 暂存 |

---

## 七、MTO字段命名差异

不同金蝶表单中 MTO 字段的命名略有差异：

| 表单 | MTO字段名 | 说明 |
|------|----------|------|
| `PRD_MO` | `FMTONo` | 大写 |
| `PRD_INSTOCK` | `FMtoNo` | 混合大小写 |
| `PUR_PurchaseOrder` | `FMtoNo` | 混合大小写 |
| `PRD_PPBOM` | `FMTONO` | 全大写 |
| `PRD_PickMtrl` | `FMTONO` | 全大写 |
| `SAL_OUTSTOCK` | `FMTONO` | 全大写 |
| `SAL_SaleOrder` | `FMtoNo` | 混合大小写 |
| `STK_InStock` | `FMtoNo` | 混合大小写 |
| `SUB_POORDER` | `FMtoNo` | 混合大小写 |

---

## 八、数据流示意图

### 8.1 简洁版 - 按物料类型路由

```
用户输入: MTO Number (例如: AK2510034)
    │
    ├─► 成品 (07.xx.xxx)
    │   └─► SAL_SaleOrder (销售订单) ─► 需求数量/订单数量
    │       └─► SAL_OUTSTOCK (销售出库) ─► 已领数量 (按物料+辅助属性匹配)
    │       └─► PRD_INSTOCK (生产入库) ─► 入库数量 (按物料+辅助属性匹配)
    │
    ├─► 自制件 (05.xx.xxx)
    │   └─► PRD_MO (生产订单) ─► 需求数量/订单数量
    │       └─► PRD_PickMtrl (生产领料) ─► 已领数量/未领数量
    │       └─► PRD_INSTOCK (生产入库) ─► 入库数量
    │
    └─► 外购件 (03.xx.xxx)
        └─► PUR_PurchaseOrder (采购订单) ─► 需求数量/订单数量/入库数量/未入数量
            └─► PRD_PickMtrl (生产领料) ─► 已领数量
```

### 8.2 详细版 - 完整查询流程

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        用户输入 MTO Number                                   │
│                        (例如: AK2510034)                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │     检查缓存 (L1 → L2)         │
                    │     命中? 直接返回             │
                    └───────────────┬───────────────┘
                                    │ 未命中
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     并行查询 7 个金蝶表单 (asyncio.gather)                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐                │
│  │SAL_Sale   │  │PRD_MO     │  │PUR_       │  │PRD_       │                │
│  │Order      │  │           │  │Purchase   │  │INSTOCK    │                │
│  │销售订单    │  │生产订单    │  │Order      │  │生产入库    │                │
│  │           │  │           │  │采购订单    │  │           │                │
│  │FMtoNo     │  │FMTONo     │  │FMtoNo     │  │FMtoNo     │                │
│  └───────────┘  └───────────┘  └───────────┘  └───────────┘                │
│                                                                             │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐                               │
│  │STK_       │  │PRD_       │  │SAL_       │                               │
│  │InStock    │  │PickMtrl   │  │OUTSTOCK   │                               │
│  │采购入库    │  │生产领料    │  │销售出库    │                               │
│  │           │  │           │  │           │                               │
│  │FMtoNo     │  │FMTONO     │  │FMTONO     │                               │
│  └───────────┘  └───────────┘  └───────────┘                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           数据聚合处理                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. 构建聚合字典:                                                            │
│     ├─ delivered_by_material = {(物料编码, 辅助属性): 出库数量}               │
│     ├─ receipt_by_material = {(物料编码, 辅助属性): 入库数量}                 │
│     ├─ pick_request = {物料编码: 申请领料数量}                               │
│     └─ pick_actual = {物料编码: 实际领料数量}                                │
│                                                                             │
│  2. 按物料编码前缀路由:                                                       │
│     ├─ 07.* → 成品流程 (SAL_SaleOrder 为主)                                  │
│     ├─ 05.* → 自制流程 (PRD_MO 为主)                                         │
│     └─ 03.* → 外购流程 (PUR_PurchaseOrder 为主)                              │
│                                                                             │
│  3. 计算派生数量:                                                            │
│     ├─ unpicked_qty = required_qty - picked_qty                             │
│     └─ unreceived_qty = order_qty - receipt_qty                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         返回 MTOStatusResponse                               │
├─────────────────────────────────────────────────────────────────────────────┤
│  {                                                                          │
│    "mto_number": "AK2510034",                                               │
│    "parent": { "customer_name": "...", "delivery_date": "..." },            │
│    "children": [                                                            │
│      {                                                                      │
│        "material_code": "07.04.231",                                        │
│        "required_qty": 1000,                                                │
│        "picked_qty": 800,                                                   │
│        "unpicked_qty": 200,                                                 │
│        ...                                                                  │
│      }                                                                      │
│    ],                                                                       │
│    "data_source": "live",                                                   │
│    "query_time": "2025-01-25T10:30:00"                                      │
│  }                                                                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 九、相关文件

| 文件路径 | 说明 |
|---------|------|
| `config/mto_config.json` | 数量字段配置主文件 |
| `src/mto_config/mto_config.py` | 配置加载器类 |
| `src/readers/factory.py` | 金蝶表单读取器配置 |
| `src/models/mto_status.py` | MTO响应数据模型 |
| `docs/fields/*.md` | 各表单完整字段文档 |

---

## 十、系统查询架构

### 10.1 三层缓存架构

系统采用三层缓存策略，平衡查询速度和数据新鲜度：

```
┌─────────────────────────────────────────────────────────────────┐
│                     用户请求 MTO 查询                            │
│                   GET /api/mto/{mto_number}                     │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  L1: 内存缓存 (TTLCache)                                         │
│  ├─ 容量: ~300 条热门 MTO                                        │
│  ├─ TTL: 5 分钟                                                  │
│  ├─ 响应时间: < 10ms                                             │
│  └─ 实现: cachetools.TTLCache                                    │
└─────────────────────────────────────────────────────────────────┘
                │ (未命中)
                ▼
┌─────────────────────────────────────────────────────────────────┐
│  L2: SQLite 持久缓存                                             │
│  ├─ 存储: 全量同步数据 (7天滚动)                                  │
│  ├─ TTL: 60 分钟 (可配置)                                        │
│  ├─ 响应时间: ~100ms                                             │
│  └─ 实现: aiosqlite + WAL 模式                                   │
└─────────────────────────────────────────────────────────────────┘
                │ (未命中/过期)
                ▼
┌─────────────────────────────────────────────────────────────────┐
│  L3: Kingdee API 实时查询                                        │
│  ├─ 数据源: 金蝶 K3Cloud WebAPI                                  │
│  ├─ 响应时间: 1-5 秒                                             │
│  └─ 实现: 7 个并行 API 调用 (asyncio.gather)                      │
└─────────────────────────────────────────────────────────────────┘
```

### 10.2 并行查询流程图

当触发 L3 实时查询时，系统同时发起 7 个 API 调用：

```
MTO 查询触发 (L3 实时)
       │
       │ asyncio.gather() 并行执行
       │
       ├──────────┬──────────┬──────────┬──────────┬──────────┬──────────┐
       │          │          │          │          │          │          │
       ▼          ▼          ▼          ▼          ▼          ▼          ▼
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│ SAL_     │ │ PRD_MO   │ │ PUR_     │ │ PRD_     │ │ STK_     │ │ PRD_     │ │ SAL_     │
│ SaleOrder│ │ 生产订单  │ │ Purchase │ │ INSTOCK  │ │ InStock  │ │ PickMtrl │ │ OUTSTOCK │
│ 销售订单  │ │          │ │ Order    │ │ 生产入库  │ │ 采购入库  │ │ 生产领料  │ │ 销售出库  │
│          │ │          │ │ 采购订单  │ │          │ │          │ │          │ │          │
└──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘
       │          │          │          │          │          │          │
       └──────────┴──────────┴──────────┴──────────┴──────────┴──────────┘
                                        │
                                        ▼
                          ┌───────────────────────────┐
                          │  数据聚合 & 数量计算        │
                          │  ├─ 按物料类型路由         │
                          │  ├─ 构建聚合字典           │
                          │  └─ 计算派生数量           │
                          └───────────────────────────┘
                                        │
                                        ▼
                          ┌───────────────────────────┐
                          │  MTOStatusResponse        │
                          │  ├─ parent: 订单信息       │
                          │  ├─ children: BOM明细     │
                          │  └─ data_source: 数据来源 │
                          └───────────────────────────┘
```

### 10.3 查询耗时对比

| 缓存层 | 典型耗时 | 适用场景 |
|--------|----------|---------|
| L1 内存 | < 10ms | 高频查询的热门 MTO |
| L2 SQLite | ~100ms | 已同步但非热门的 MTO |
| L3 API | 1-5s | 新 MTO 或强制刷新 |

---

## 十一、完整字段映射表 (代码实现)

以下是 `src/readers/factory.py` 中定义的 9 个 Reader 配置，展示金蝶字段到 Python 模型的完整映射。

### 11.1 生产订单 PRODUCTION_ORDER_CONFIG

| 金蝶表单 | `PRD_MO` |
|---------|----------|
| MTO字段 | `FMTONo` |
| 日期字段 | `FCreateDate` |

| Python 字段 | 金蝶字段 | 类型转换 | 说明 |
|------------|---------|---------|------|
| `bill_no` | `FBillNo` | str | 生产订单号 |
| `mto_number` | `FMTONo` | str | 计划跟踪号 |
| `workshop` | `FWorkShopID.FName` | str | 生产车间名称 |
| `material_code` | `FMaterialId.FNumber` | str | 物料编码 |
| `material_name` | `FMaterialId.FName` | str | 物料名称 |
| `specification` | `FMaterialId.FSpecification` | str | 规格型号 |
| `qty` | `FQty` | Decimal | 生产数量 |
| `status` | `FStatus` | str | 生产状态 (1-6) |
| `create_date` | `FCreateDate` | Optional[str] | 创建日期 |

### 11.2 生产用料清单 PRODUCTION_BOM_CONFIG

| 金蝶表单 | `PRD_PPBOM` |
|---------|------------|
| MTO字段 | `FMTONO` |
| 单据字段 | `FMOBillNO` |

| Python 字段 | 金蝶字段 | 类型转换 | 说明 |
|------------|---------|---------|------|
| `mo_bill_no` | `FMOBillNO` | str | 关联生产订单号 |
| `mto_number` | `FMTONO` | str | 计划跟踪号 |
| `material_code` | `FMaterialId.FNumber` | str | 物料编码 |
| `material_name` | `FMaterialId.FName` | str | 物料名称 |
| `specification` | `FMaterialId.FSpecification` | str | 规格型号 |
| `aux_prop_id` | `FAuxPropId` | int | 辅助属性ID |
| `material_type` | `FMaterialType` | int | 物料类型 (1=自制, 2=外购, 3=委外) |
| `need_qty` | `FMustQty` | Decimal | 需求数量 |
| `picked_qty` | `FPickedQty` | Decimal | 已领数量 |
| `no_picked_qty` | `FNoPickedQty` | Decimal | 未领数量 (负值=超领) |

### 11.3 生产入库单 PRODUCTION_RECEIPT_CONFIG

| 金蝶表单 | `PRD_INSTOCK` |
|---------|--------------|
| MTO字段 | `FMtoNo` |

| Python 字段 | 金蝶字段 | 类型转换 | 说明 |
|------------|---------|---------|------|
| `mto_number` | `FMtoNo` | str | 计划跟踪号 |
| `material_code` | `FMaterialId.FNumber` | str | 物料编码 |
| `real_qty` | `FRealQty` | Decimal | 实收数量 |
| `must_qty` | `FMustQty` | Decimal | 应收数量 |
| `aux_prop_id` | `FAuxPropId` | int | 辅助属性ID |
| `mo_bill_no` | `FMoBillNo` | str | 关联生产订单号 |

### 11.4 采购订单 PURCHASE_ORDER_CONFIG

| 金蝶表单 | `PUR_PurchaseOrder` |
|---------|---------------------|
| MTO字段 | `FMtoNo` |

| Python 字段 | 金蝶字段 | 类型转换 | 说明 |
|------------|---------|---------|------|
| `bill_no` | `FBillNo` | str | 采购订单号 |
| `mto_number` | `FMtoNo` | str | 计划跟踪号 |
| `material_code` | `FMaterialId.FNumber` | str | 物料编码 |
| `material_name` | `FMaterialId.FName` | str | 物料名称 |
| `specification` | `FMaterialId.FSpecification` | str | 规格型号 |
| `aux_prop_id` | `FAuxPropId` | int | 辅助属性ID |
| `order_qty` | `FQty` | Decimal | 采购数量 |
| `stock_in_qty` | `FStockInQty` | Decimal | 累计入库数量 |
| `remain_stock_in_qty` | `FRemainStockInQty` | Decimal | 未入库数量 |

### 11.5 采购入库单 PURCHASE_RECEIPT_CONFIG

| 金蝶表单 | `STK_InStock` |
|---------|--------------|
| MTO字段 | `FMtoNo` |

| Python 字段 | 金蝶字段 | 类型转换 | 说明 |
|------------|---------|---------|------|
| `mto_number` | `FMtoNo` | str | 计划跟踪号 |
| `material_code` | `FMaterialId.FNumber` | str | 物料编码 |
| `real_qty` | `FRealQty` | Decimal | 实收数量 |
| `must_qty` | `FMustQty` | Decimal | 应收数量 |
| `bill_type_number` | `FBillTypeID.FNumber` | str | 单据类型 (RKD01_SYS/RKD02_SYS) |

### 11.6 委外订单 SUBCONTRACTING_ORDER_CONFIG

| 金蝶表单 | `SUB_POORDER` |
|---------|--------------|
| MTO字段 | `FMtoNo` |

| Python 字段 | 金蝶字段 | 类型转换 | 说明 |
|------------|---------|---------|------|
| `bill_no` | `FBillNo` | str | 委外订单号 |
| `mto_number` | `FMtoNo` | str | 计划跟踪号 |
| `material_code` | `FMaterialId.FNumber` | str | 物料编码 |
| `order_qty` | `FQty` | Decimal | 委外数量 |
| `stock_in_qty` | `FStockInQty` | Decimal | 累计入库数量 |
| `no_stock_in_qty` | `FNoStockInQty` | Decimal | 未入库数量 |

### 11.7 生产领料单 MATERIAL_PICKING_CONFIG

| 金蝶表单 | `PRD_PickMtrl` |
|---------|---------------|
| MTO字段 | `FMTONO` |

| Python 字段 | 金蝶字段 | 类型转换 | 说明 |
|------------|---------|---------|------|
| `mto_number` | `FMTONO` | str | 计划跟踪号 |
| `material_code` | `FMaterialId.FNumber` | str | 物料编码 |
| `app_qty` | `FAppQty` | Decimal | 申请领料数量 |
| `actual_qty` | `FActualQty` | Decimal | 实际领料数量 |
| `ppbom_bill_no` | `FPPBomBillNo` | str | 关联生产用料清单 |

### 11.8 销售出库单 SALES_DELIVERY_CONFIG

| 金蝶表单 | `SAL_OUTSTOCK` |
|---------|---------------|
| MTO字段 | `FMTONO` |

| Python 字段 | 金蝶字段 | 类型转换 | 说明 |
|------------|---------|---------|------|
| `mto_number` | `FMTONO` | str | 计划跟踪号 |
| `material_code` | `FMaterialId.FNumber` | str | 物料编码 |
| `real_qty` | `FRealQty` | Decimal | 实发数量 |
| `must_qty` | `FMustQty` | Decimal | 应发数量 |
| `aux_prop_id` | `FAuxPropId` | int | 辅助属性ID |

### 11.9 销售订单 SALES_ORDER_CONFIG

| 金蝶表单 | `SAL_SaleOrder` |
|---------|----------------|
| MTO字段 | `FMtoNo` |

| Python 字段 | 金蝶字段 | 类型转换 | 说明 |
|------------|---------|---------|------|
| `bill_no` | `FBillNo` | str | 销售订单号 |
| `mto_number` | `FMtoNo` | str | 计划跟踪号 |
| `material_code` | `FMaterialId.FNumber` | str | 物料编码 |
| `material_name` | `FMaterialId.FName` | str | 物料名称 |
| `specification` | `FMaterialId.FSpecification` | str | 规格型号 |
| `aux_prop_id` | `FAuxPropId` | int | 辅助属性ID |
| `customer_name` | `FCustId.FName` | str | 客户名称 |
| `delivery_date` | `FDeliveryDate` | Optional[str] | 交货日期 |
| `qty` | `FQty` | Decimal | 订单数量 |

---

## 十二、物料类型数量计算详解

系统根据物料编码前缀路由到不同的计算逻辑，使用不同的匹配键进行数量聚合。

### 12.1 成品 (07.xx.xxx) - 销售订单流程

**数据源**: `SAL_SaleOrder` (销售订单)

| UI 字段 | 计算公式 | 数据源 | 匹配键 |
|--------|---------|--------|-------|
| `required_qty` | `SAL_SaleOrder.FQty` | 直接取值 | - |
| `picked_qty` | `Σ SAL_OUTSTOCK.FRealQty` | 聚合求和 | `(material_code, aux_prop_id)` |
| `unpicked_qty` | `required_qty - picked_qty` | 计算 | - |
| `order_qty` | `SAL_SaleOrder.FQty` | 直接取值 | - |
| `receipt_qty` | `Σ PRD_INSTOCK.FRealQty` | 聚合求和 | `(material_code, aux_prop_id)` |
| `unreceived_qty` | `order_qty - receipt_qty` | 计算 | - |

**关键点**: 成品使用 `(material_code, aux_prop_id)` 元组匹配，支持颜色、尺寸等变体区分。

### 12.2 自制件 (05.xx.xxx) - 生产订单流程

**数据源**: `PRD_MO` (生产订单)

| UI 字段 | 计算公式 | 数据源 | 匹配键 |
|--------|---------|--------|-------|
| `required_qty` | `PRD_MO.FQty` | 直接取值 | - |
| `picked_qty` | `Σ PRD_PickMtrl.FActualQty` | 聚合求和 | `material_code` |
| `unpicked_qty` | `Σ (FAppQty - FActualQty)` | 聚合计算 | `material_code` |
| `order_qty` | `PRD_MO.FQty` | 直接取值 | - |
| `receipt_qty` | `Σ PRD_INSTOCK.FRealQty` | 聚合求和 | `material_code` |
| `unreceived_qty` | `order_qty - receipt_qty` | 计算 | - |

**关键点**: 自制件只用 `material_code` 匹配，`unpicked_qty` 可能为负值表示超领。

### 12.3 外购件 (03.xx.xxx) - 采购订单流程

**数据源**: `PUR_PurchaseOrder` (采购订单)

| UI 字段 | 计算公式 | 数据源 | 匹配键 |
|--------|---------|--------|-------|
| `required_qty` | `PUR_PurchaseOrder.FQty` | 直接取值 | - |
| `picked_qty` | `Σ PRD_PickMtrl.FActualQty` | 聚合求和 | `material_code` |
| `unpicked_qty` | `required_qty - picked_qty` | 计算 | - |
| `order_qty` | `PUR_PurchaseOrder.FQty` | 直接取值 | - |
| `receipt_qty` | `PUR_PurchaseOrder.FStockInQty` | 直接取值 | - |
| `unreceived_qty` | `PUR_PurchaseOrder.FRemainStockInQty` | 直接取值 | - |

**关键点**: 外购件的入库数量直接从采购订单读取 (`FStockInQty`、`FRemainStockInQty`)，无需额外聚合。

### 12.4 匹配键说明

| 匹配键类型 | 格式 | 适用场景 | 示例 |
|-----------|------|---------|------|
| 单键匹配 | `material_code` | 自制件、外购件 | `"05.02.27.022"` |
| 双键匹配 | `(material_code, aux_prop_id)` | 成品 (有变体) | `("07.04.231", 12345)` |

**双键匹配原理**:
```python
# 构建聚合字典
delivered_by_material = {}
for delivery in sales_deliveries:
    key = (delivery.material_code, delivery.aux_prop_id)
    delivered_by_material[key] = delivered_by_material.get(key, 0) + delivery.real_qty
```

### 12.5 超领检测

当 `unpicked_qty` 或 `no_picked_qty` 为**负值**时，表示实际领料超过申请数量：

```python
# 超领判断
if child.unpicked_qty < 0:
    # 标记为红色警告
    status = "over_picked"
```

**UI 显示**: 超领数量以红色显示，提醒用户关注。

---

## 附录A: 代码关联参考

> **重要**: 本节的所有配置字段都与实际代码直接关联。修改 `config/mto_config.json` 会影响系统行为。

### A.1 配置文件与代码调用链

```
config/mto_config.json              ◄─── 你修改这个文件
        │
        ▼ 加载于
src/main.py:77-78
│   mto_config = MTOConfig("config/mto_config.json")
│   logger.info("Loaded MTO config with %d material classes", len(mto_config.material_classes))
        │
        ▼ 传递到 MTOQueryHandler
src/main.py:82-97
│   mto_handler = MTOQueryHandler(
│       ...
│       mto_config=mto_config,  ◄─── 参数传递
│       ...
│   )
        │
        ▼ 存储于
src/query/mto_handler.py:97
│   self._mto_config = mto_config or MTOConfig()
        │
        ▼ 使用于物料分类判断
src/query/mto_handler.py:122-136
│   def _get_material_class(self, material_code: str):
│       class_config = self._mto_config.get_class_for_material(material_code)
│       if class_config:
│           return class_config.id, class_config
│       return None, None
```

### A.2 代码行号快速索引

| 功能 | 文件 | 行号 |
|------|------|------|
| **配置加载** | `src/main.py` | 77-78 |
| **配置类定义** | `src/mto_config/mto_config.py` | 33-63 |
| **配置解析** | `src/mto_config/mto_config.py` | 109-123 |
| **物料匹配** | `src/mto_config/mto_config.py` | 129-141 |
| **获取物料类型** | `src/query/mto_handler.py` | 122-136 |
| **缓存路由 (成品)** | `src/query/mto_handler.py` | 246-252 |
| **缓存路由 (自制)** | `src/query/mto_handler.py` | 254-261 |
| **缓存路由 (外购)** | `src/query/mto_handler.py` | 264-270 |
| **实时路由 (成品)** | `src/query/mto_handler.py` | 350-357 |
| **实时路由 (自制)** | `src/query/mto_handler.py` | 359-366 |
| **实时路由 (外购)** | `src/query/mto_handler.py` | 369-375 |
| **构建成品子项** | `src/query/mto_handler.py` | 392-439 |
| **构建自制子项** | `src/query/mto_handler.py` | 441-498 |
| **构建外购子项** | `src/query/mto_handler.py` | 500-542 |

### A.3 如何添加新物料分类

**例如**: 添加 "委外件" (06.xx.xxx)

1. **编辑 `config/mto_config.json`**:

```json
{
  "material_classes": [
    // ... 现有配置 ...
    {
      "id": "subcontracted",           // 新的唯一标识符
      "pattern": "^06\\.",             // 匹配 06 开头
      "display_name": "委外",
      "material_type": 3,
      "source_form": "SUB_POORDER",    // 委外订单表单
      "mto_field": "FMtoNo",
      "columns": {
        "required_qty": { "source": "SUB_POORDER", "field": "qty" }
        // ... 其他列定义
      }
    }
  ]
}
```

2. **需要修改代码** (`mto_handler.py`):

目前代码只处理三种类型，添加新类型需要:
- 添加新的 `_build_*_child()` 方法
- 在 `_try_cache()` 和 `_fetch_live()` 添加路由逻辑

### A.4 测试验证

**验证配置生效**:

1. **启动服务**:
```bash
uvicorn src.main:app --reload --port 8000
```

2. **查看日志确认配置加载**:
```
INFO: Loaded MTO config with 3 material classes
```

3. **运行单元测试**:
```bash
pytest tests/ -v -k "mto"
```

---

*文档版本: 2026-01-29*
*合并自: MTO_CONFIG_CODE_REFERENCE.md*
