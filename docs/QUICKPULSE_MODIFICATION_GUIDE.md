# QuickPulse V2 修改指南 (AI 提示词)

> 把这个文档放到 CLAUDE.md 或作为上下文提供给 AI，可以快速帮你修改取数逻辑和 UI 显示。

---

## 一、项目架构概述

### 数据流
```
MTO 单号 → 7个并行查询 → 按物料聚合 → 按类型构建 ChildItem → UI 显示
```

### 关键文件
| 文件 | 作用 | 修改频率 |
|-----|------|---------|
| `config/mto_config.json` | 物料类型路由 + 列计算配置 | ⭐ 高 |
| `src/readers/factory.py` | 金蝶字段映射 (Python) | ⭐⭐ 中 |
| `src/readers/models.py` | Pydantic 数据模型 | ⭐⭐ 中 |
| `src/query/mto_handler.py` | 数据聚合逻辑 | ⭐⭐⭐ 低 |
| `src/frontend/dashboard.html` | UI 表格显示 | ⭐⭐ 中 |

### 物料类型路由规则
| 物料编码前缀 | 类型 | 源单 | MTO 字段 |
|-------------|------|------|----------|
| `07.xx.xxx` | 成品 | `SAL_SaleOrder` | `FMtoNo` |
| `05.xx.xxx` | 自制 | `PRD_MO` | `FMTONo` |
| `03.xx.xxx` | 外购 | `PUR_PurchaseOrder` | `FMtoNo` |

---

## 二、当前使用的字段映射

### 1. 销售订单 SAL_SaleOrder (成品 07.xx)

**当前使用字段**:
```python
"bill_no": "FBillNo"
"mto_number": "FMtoNo"
"material_code": "FMaterialId.FNumber"
"material_name": "FMaterialId.FName"
"specification": "FMaterialId.FSpecification"
"aux_prop_id": "FAuxPropId"
"customer_name": "FCustId.FName"
"delivery_date": "FDeliveryDate"
"qty": "FQty"
```

**可用但未使用的字段**:
- `FSaleOrderEntry_FPrice` - 单价
- `FSaleOrderEntry_FTaxPrice` - 含税单价
- `FSaleOrderEntry_FAllAmount` - 金额
- `FSaleOrderEntry_FRemainOutQty` - 未出库数量
- `FSaleOrderEntry_FStockOutQty` - 已出库数量
- `FSaleDeptId` - 销售部门
- `FSalerId` - 销售员

---

### 2. 生产订单 PRD_MO (自制 05.xx)

**当前使用字段**:
```python
"bill_no": "FBillNo"
"mto_number": "FMTONo"
"workshop": "FWorkShopID.FName"
"material_code": "FMaterialId.FNumber"
"material_name": "FMaterialId.FName"
"specification": "FMaterialId.FSpecification"
"qty": "FQty"
"status": "FStatus"
"create_date": "FCreateDate"
```

**可用但未使用的字段**:
- `FPlanStartDate` - 计划开工日期
- `FPlanFinishDate` - 计划完工日期
- `FNoStockInQty` - 未入库数量
- `FStockInQuaQty` - 良品入库数量
- `FSaleOrderNo` - 销售订单号
- `FBomId` - BOM版本
- `FAuxPropId` - 辅助属性

**状态值 FStatus**:
- 1=计划, 2=计划确认, 3=下达, 4=开工, 5=完工, 6=结案

---

### 3. 采购订单 PUR_PurchaseOrder (外购 03.xx)

**当前使用字段**:
```python
"bill_no": "FBillNo"
"mto_number": "FMtoNo"
"material_code": "FMaterialId.FNumber"
"material_name": "FMaterialId.FName"
"specification": "FMaterialId.FSpecification"
"aux_prop_id": "FAuxPropId"
"order_qty": "FQty"
"stock_in_qty": "FStockInQty"         # 累计入库数量
"remain_stock_in_qty": "FRemainStockInQty"  # 未入库数量
```

**可用但未使用的字段**:
- `FPOOrderEntry_FPrice` - 单价
- `FPOOrderEntry_FTaxPrice` - 含税单价
- `FPOOrderEntry_FAllAmount` - 金额
- `FPOOrderEntry_FDeliveryDate` - 交货日期
- `FSupplierId` - 供应商
- `FPurchaserId` - 采购员

---

### 4. 生产入库单 PRD_INSTOCK

**当前使用字段**:
```python
"mto_number": "FMtoNo"
"material_code": "FMaterialId.FNumber"
"real_qty": "FRealQty"        # 实收数量
"must_qty": "FMustQty"        # 应收数量
"aux_prop_id": "FAuxPropId"
"mo_bill_no": "FMoBillNo"     # 关联生产订单号
```

**可用但未使用的字段**:
- `FEntity_FLot` - 批号
- `FEntity_FStockId` - 仓库
- `FEntity_FPrice` - 单价
- `FEntity_FAmount` - 金额
- `FEntity_FWorkShopId` - 车间

---

### 5. 生产领料单 PRD_PickMtrl

**当前使用字段**:
```python
"mto_number": "FMTONO"
"material_code": "FMaterialId.FNumber"
"app_qty": "FAppQty"          # 申请领料数量
"actual_qty": "FActualQty"    # 实际领料数量
"ppbom_bill_no": "FPPBomBillNo"
```

**可用但未使用的字段**:
- `FEntity_FMoBillNo` - 生产订单编号
- `FEntity_FStockId` - 仓库
- `FEntity_FLot` - 批号
- `FEntity_FPrice` - 单价
- `FEntity_FAmount` - 金额

---

### 6. 销售出库单 SAL_OUTSTOCK

**当前使用字段**:
```python
"mto_number": "FMTONO"
"material_code": "FMaterialId.FNumber"
"real_qty": "FRealQty"        # 实发数量
"must_qty": "FMustQty"        # 应发数量
"aux_prop_id": "FAuxPropId"
```

**可用但未使用的字段**:
- `FSAL_OUTSTOCKENTRY_FLot` - 批号
- `FSAL_OUTSTOCKENTRY_FStockID` - 仓库
- `FSAL_OUTSTOCKENTRY_FPrice` - 单价
- `FSAL_OUTSTOCKENTRY_FAllAmount` - 金额
- `FCustomerID` - 客户

---

### 7. 采购入库单 STK_InStock

**当前使用字段**:
```python
"mto_number": "FMtoNo"
"material_code": "FMaterialId.FNumber"
"real_qty": "FRealQty"        # 实收数量
"must_qty": "FMustQty"        # 应收数量
"bill_type_number": "FBillTypeID.FNumber"  # RKD01_SYS/RKD02_SYS
```

**可用但未使用的字段**:
- `FInStockEntry_FLot` - 批号
- `FInStockEntry_FStockId` - 仓库
- `FInStockEntry_FTaxPrice` - 含税单价
- `FInStockEntry_FAllAmount` - 金额
- `FSupplierId` - 供应商

---

### 8. 生产用料清单 PRD_PPBOM

**当前使用字段**:
```python
"mo_bill_no": "FMOBillNO"
"mto_number": "FMTONO"
"material_code": "FMaterialId.FNumber"
"material_name": "FMaterialId.FName"
"specification": "FMaterialId.FSpecification"
"aux_prop_id": "FAuxPropId"
"material_type": "FMaterialType"   # 1=自制, 2=外购, 3=委外
"need_qty": "FMustQty"
"picked_qty": "FPickedQty"
"no_picked_qty": "FNoPickedQty"
```

---

## 三、UI 列与数据字段映射

| UI 列名 | JSON 字段 | 数据来源 | 条件格式 |
|--------|----------|---------|---------|
| 序号 | - | 自动生成 | - |
| 物料编码 | `material_code` | 源单 | 等宽字体 |
| 物料名称 | `material_name` | 源单 | - |
| 规格型号 | `specification` | 源单 | 空值显示"-" |
| BOM简称 | `bom_short_name` | SAL_SaleOrder | 仅成品(07.xx)显示 |
| 辅助属性 | `aux_attributes` | BD_FLEXSITEMDETAILV | 空值显示"-" |
| 物料类型 | `material_type` | 代码判断 | 徽章颜色 |
| **销售订单.数量** | `sales_order_qty` | SAL_SaleOrder.FQty | 成品(07.xx)显示 |
| **生产入库单.应收数量** | `prod_instock_must_qty` | PRD_INSTOCK.FMustQty | 自制(05.xx)显示 |
| **采购订单.数量** | `purchase_order_qty` | PUR_PurchaseOrder.FQty | 包材(03.xx)显示 |
| **生产领料单.实发数量** | `pick_actual_qty` | PRD_PickMtrl.FActualQty | 05.xx/03.xx显示 |
| **生产入库单.实收数量** | `prod_instock_real_qty` | PRD_INSTOCK.FRealQty | 07.xx/05.xx显示 |
| **采购订单.累计入库数量** | `purchase_stock_in_qty` | PUR_PurchaseOrder.FStockInQty | 03.xx显示 |

---

## 四、修改示例

### 示例1: 添加新字段到 UI

**需求**: 在 UI 显示采购订单的"交货日期"

**步骤**:

1. **修改 factory.py** - 添加字段映射:
```python
PURCHASE_ORDER_CONFIG = ReaderConfig(
    # ... 现有配置 ...
    field_mappings={
        # ... 现有字段 ...
        "delivery_date": FieldMapping("FDeliveryDate", _optional_str),  # 新增
    },
)
```

2. **修改 models.py** - 添加模型字段:
```python
class PurchaseOrderModel(BaseModel):
    # ... 现有字段 ...
    delivery_date: Optional[str] = None  # 新增
```

3. **修改 mto_handler.py** - 传递到 ChildItem:
```python
def _build_purchase_child(...):
    return ChildItem(
        # ... 现有字段 ...
        delivery_date=record.delivery_date,  # 新增
    )
```

4. **修改 dashboard.html** - 添加列:
```html
<th>交货日期</th>
...
<td x-text="formatDate(item.delivery_date)"></td>
```

---

### 示例2: 修改计算逻辑

**需求**: 未领量改为 "申请量 - 实领量" (而不是 "需求量 - 已领量")

**修改 mto_config.json**:
```json
"unpicked_qty": {
  "source": "PRD_PickMtrl",
  "field": "app_qty",
  "subtract": "actual_qty",
  "match_by": ["material_code"]
}
```

---

### 示例3: 添加新的物料类型

**需求**: 支持 04.xx.xxx 委外件

**修改 mto_config.json** - 添加到 `material_classes`:
```json
{
  "id": "subcontracted",
  "pattern": "^04\\.",
  "display_name": "委外",
  "material_type": 3,
  "source_form": "SUB_POORDER",
  "mto_field": "FMtoNo",
  "columns": {
    "required_qty": { "source": "SUB_POORDER", "field": "order_qty" },
    "receipt_qty": { "source": "STK_InStock", "field": "real_qty", "match_by": ["material_code"] }
  }
}
```

---

## 五、金蝶 MTO 字段名速查表

| 表单 | MTO 字段名 | 查询示例 |
|-----|-----------|---------|
| SAL_SaleOrder | `FMtoNo` | `FMtoNo='AK2510034'` |
| PRD_MO | `FMTONo` | `FMTONo='AK2510034'` |
| PUR_PurchaseOrder | `FMtoNo` | `FMtoNo='AK2510034'` |
| PRD_INSTOCK | `FMtoNo` | `FMtoNo='AK2510034'` |
| STK_InStock | `FMtoNo` | `FMtoNo='AK2510034'` |
| PRD_PickMtrl | `FMTONO` | `FMTONO='AK2510034'` |
| SAL_OUTSTOCK | `FMTONO` | `FMTONO='AK2510034'` |
| PRD_PPBOM | `FMTONO` | `FMTONO='AK2510034'` |

**注意**: MTO 字段名在不同表单中大小写不一致！

---

## 六、数量字段速查表

| 用途 | 字段名 | 表单 |
|-----|-------|------|
| 需求/订单数量 | `FQty` | 几乎所有源单 |
| 实收/实发数量 | `FRealQty` | 入库单/出库单 |
| 应收/应发数量 | `FMustQty` | 入库单/出库单 |
| 申请领料数量 | `FAppQty` | PRD_PickMtrl |
| 实际领料数量 | `FActualQty` | PRD_PickMtrl |
| 累计入库数量 | `FStockInQty` | PUR_PurchaseOrder |
| 未入库数量 | `FRemainStockInQty` | PUR_PurchaseOrder |
| 已出库数量 | `FStockOutQty` | SAL_SaleOrder |
| 未出库数量 | `FRemainOutQty` | SAL_SaleOrder |

---

## 七、探索新字段

运行以下命令获取表单的完整字段:
```bash
python scripts/explore_all_api_fields.py
```

输出保存在 `field_data/` 目录。

---

## 八、测试修改

### 本地测试
1. 重启服务: `uvicorn src.main:app --reload`
2. 访问 `http://localhost:8000`
3. 输入测试 MTO 号: `AK2510034`
4. 检查新字段是否正确显示

### CVM 测试 (远程部署)
1. 推送到 `develop` 分支 → 自动部署到 dev 环境
2. 访问 `http://121.41.81.36:8004` (dev)
3. 手动部署 prod: `/opt/ops/scripts/deploy.sh quickpulse prod`
4. 访问 `http://121.41.81.36:8003` (prod)

> 详细 CVM 信息见 `docs/CVM_INFRASTRUCTURE.md`
