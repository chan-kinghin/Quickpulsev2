# Kingdee API Field Analysis

> Comprehensive analysis of fields across 9 Kingdee Cloud APIs for QuickPulse V2

---

## 1. Executive Summary

### APIs Covered

| API Code | Chinese Name | English Name | Header Fields | Detail Fields | Total |
|----------|-------------|--------------|---------------|---------------|-------|
| PRD_MO | 生产订单 | Production Order | 17 | 29 | 46 |
| PRD_INSTOCK | 生产入库单 | Production Receipt | 20 | 58 | 78 |
| PRD_PPBOM | 生产用料清单 | Production BOM | 27 | 106 | 133 |
| PRD_PickMtrl | 生产领料单 | Material Picking | 23 | 89 | 112 |
| SAL_SaleOrder | 销售订单 | Sales Order | 52 | 182 | 234 |
| SAL_OUTSTOCK | 销售出库单 | Sales Delivery | 52 | 150 | 202 |
| PUR_PurchaseOrder | 采购订单 | Purchase Order | 46 | 165 | 211 |
| STK_InStock | 采购入库单 | Purchase Receipt | 43 | 135 | 178 |
| SUB_SUBREQORDER | 委外申请订单 | Subcontracting Request | 12 | 92 | 104 |

### Field Categories

| Category | Description | Count |
|----------|-------------|-------|
| Common Fields | Present in all/most APIs | ~25 |
| Linkage Fields | Cross-document references | ~15 |
| Quantity Fields | Tracking quantities | ~40 |
| Status Fields | Document/process status | ~20 |
| Custom Fields (F_QWJI_*) | Company-specific | ~30 |

---

## 2. Cross-API Linkage Fields

### Primary Linkage: 计划跟踪号 (MTO Number)

The **MTO Number** is the most important field for cross-document traceability.

| API | Field Name | Description |
|-----|------------|-------------|
| PRD_MO | `FMTONo` | 计划跟踪号 (Detail) |
| PRD_INSTOCK | `FEntity_FMtoNo` | 计划跟踪号 |
| PRD_PPBOM | `FPPBomEntry_FMTONO` | 计划跟踪号 |
| PRD_PickMtrl | `FEntity_FMTONO` | 计划跟踪号 |
| SAL_SaleOrder | `FSaleOrderEntry_FMtoNo` | 计划跟踪号 |
| SAL_OUTSTOCK | `FSAL_OUTSTOCKENTRY_FMTONO` | 计划跟踪号 |
| PUR_PurchaseOrder | `FPOOrderEntry_FMtoNo` | 计划跟踪号 |
| STK_InStock | `FInStockEntry_FMtoNo` | 计划跟踪号 |
| SUB_SUBREQORDER | `FTreeEntity_Fmtono` | 计划跟踪号 |

**Query Example:**
```python
# Find all documents related to MTO number "AK2412023"
apis = ["PRD_MO", "SAL_SaleOrder", "PUR_PurchaseOrder", "PRD_INSTOCK"]
for api in apis:
    query = {
        "FormId": api,
        "FieldKeys": "FBillNo,FId",
        "FilterString": f"FMTONo='AK2412023'"  # Adjust field name per API
    }
```

### Document Reference Fields

#### Sales Order References

| Field | Found In | Purpose |
|-------|----------|---------|
| `FSaleOrderNo` | PRD_MO, PRD_PPBOM | Link to sales order number |
| `FSaleOrderId` | PRD_MO, PRD_PPBOM, SUB_SUBREQORDER | Link to sales order ID |
| `FSaleOrderEntryId` | PRD_PPBOM, SUB_SUBREQORDER | Link to sales order line |
| `FSALEORDERNO` | PRD_PPBOM, SUB_SUBREQORDER | Sales order number |

#### Production Order References

| Field | Found In | Purpose |
|-------|----------|---------|
| `FMoBillNo` | PRD_INSTOCK, PRD_PPBOM, PRD_PickMtrl | Production order number |
| `FMoId` | PRD_INSTOCK, PRD_PPBOM, PRD_PickMtrl | Production order ID |
| `FMoEntryId` | PRD_INSTOCK, PRD_PPBOM, PRD_PickMtrl | Production order line ID |
| `FMoEntrySeq` | PRD_INSTOCK, PRD_PPBOM, PRD_PickMtrl | Production order line number |

#### Purchase Order References

| Field | Found In | Purpose |
|-------|----------|---------|
| `FPOOrderNo` | STK_InStock | Purchase order number |
| `FPOORDERENTRYID` | STK_InStock | Purchase order line ID |
| `FPurOrderNo` | SUB_SUBREQORDER | Purchase order reference |
| `FPurOrderId` | SUB_SUBREQORDER | Purchase order ID |

#### BOM/Material List References

| Field | Found In | Purpose |
|-------|----------|---------|
| `FPPBomEntryId` | PRD_PickMtrl | Link to PPBOM line |
| `FPPBomBillNo` | PRD_PickMtrl | Link to PPBOM number |
| `FBomId` | All APIs | BOM version reference |

#### Source Document References (Generic)

| Field | Found In | Purpose |
|-------|----------|---------|
| `FSrcBillNo` | All APIs | Source document number |
| `FSrcBillType` | All APIs | Source document type |
| `FSrcInterId` | PRD_INSTOCK, PRD_PickMtrl | Source document internal ID |
| `FSrcEntryId` | PRD_INSTOCK, PRD_PickMtrl | Source document line ID |

### Linkage Diagram

```
SAL_SaleOrder (销售订单)
    │
    ├──> PRD_MO (生产订单) ──────────────────────┐
    │        │                                    │
    │        ├──> PRD_PPBOM (生产用料清单)       │
    │        │        │                           │
    │        │        └──> PRD_PickMtrl (生产领料单)
    │        │                                    │
    │        └──> PRD_INSTOCK (生产入库单)       │
    │                                             │
    └──> PUR_PurchaseOrder (采购订单) ───────────┤
             │                                    │
             └──> STK_InStock (采购入库单)       │
                                                  │
    SUB_SUBREQORDER (委外申请订单) ──────────────┘
             │
             └──> PUR_PurchaseOrder ──> STK_InStock
```

---

## 3. Quantity/Status Fields Matrix

### Quantity Fields by Category

#### A. Planning/Required Quantities

| Field | API | Description |
|-------|-----|-------------|
| `FQty` | PRD_MO, SAL_SaleOrder, SUB | 数量 (Primary quantity) |
| `FMustQty` | PRD_INSTOCK, PRD_PPBOM, SAL_OUTSTOCK, STK_InStock | 应收/应发数量 |
| `FNeedQty` | PRD_PPBOM | 需求数量 |
| `FStdQty` | PRD_PPBOM | 标准用量 |
| `FAppQty` | PRD_PickMtrl | 申请数量 |
| `FBaseUnitQty` | All APIs | 基本单位数量 |

#### B. Actual/Executed Quantities

| Field | API | Description |
|-------|-----|-------------|
| `FRealQty` | PRD_INSTOCK, PRD_PickMtrl, SAL_OUTSTOCK, STK_InStock | 实收/实发数量 |
| `FActualQty` | PRD_PickMtrl | 实际领料数量 |
| `FPickedQty` | PRD_PPBOM | 已领数量 |
| `FReceiveQty` | PUR_PurchaseOrder | 已收货数量 |
| `FStockInQty` | PUR_PurchaseOrder, SUB_SUBREQORDER | 已入库数量 |
| `FStockOutQty` | SAL_SaleOrder | 已出库数量 |
| `FDeliQty` | SAL_SaleOrder | 已发货数量 |
| `FConsumeQty` | PRD_PPBOM | 消耗数量 |

#### C. Remaining/Outstanding Quantities

| Field | API | Description |
|-------|-----|-------------|
| `FNoStockInQty` | PRD_MO, SUB_SUBREQORDER | 未入库数量 |
| `FRemainOutQty` | SAL_SaleOrder | 未出库数量 |
| `FRemainReceiveQty` | PUR_PurchaseOrder | 未收货数量 |
| `FRemainStockInQty` | PUR_PurchaseOrder | 未入库数量 |
| `FNoPickedQty` | PRD_PPBOM | 未领数量 |
| `FCanOutQty` | SAL_SaleOrder | 可出库数量 |

#### D. Return/Scrap Quantities

| Field | API | Description |
|-------|-----|-------------|
| `FReturnQty` | SAL_SaleOrder, SAL_OUTSTOCK | 退货数量 |
| `FGoodReturnQty` | PRD_PPBOM | 良品退料数量 |
| `FProcessDefectReturnQty` | PRD_PPBOM | 工废退料数量 |
| `FINCDefectReturnQty` | PRD_PPBOM | 来料不良退料数量 |
| `FScrapQty` | PRD_PPBOM | 报废数量 |
| `FScrapRate` | PRD_PPBOM | 损耗率 |

#### E. Invoice/Payment Quantities

| Field | API | Description |
|-------|-----|-------------|
| `FInvoiceQty` | SAL_SaleOrder, PUR_PurchaseOrder | 已开票数量 |
| `FInvoicedQty` | SAL_OUTSTOCK, STK_InStock | 已开票数量 |
| `FPayAmount` | PUR_PurchaseOrder | 已付款金额 |
| `FReceiveAmount` | SAL_SaleOrder | 已收款金额 |

### Status Fields

#### A. Document Status (FDocumentStatus) - All APIs

| Value | Chinese | English |
|-------|---------|---------|
| A | 创建 | Created |
| B | 审核中 | Pending Approval |
| C | 已审核 | Approved |
| Z | 暂存 | Draft |

#### B. Production Status (FStatus) - PRD_MO

| Value | Chinese | English |
|-------|---------|---------|
| 1 | 计划 | Planned |
| 2 | 计划确认 | Plan Confirmed |
| 3 | 下达 | Released |
| 4 | 开工 | Started |
| 5 | 完工 | Completed |
| 6 | 结案 | Closed |

#### C. Close/Cancel Status Fields

| Field | API | Values | Description |
|-------|-----|--------|-------------|
| `FCloseStatus` | SAL_SaleOrder, PUR_PurchaseOrder | A/B | 关闭状态 |
| `FCancelStatus` | All APIs | A | 作废状态 |
| `FMrpCloseStatus` | SAL_SaleOrder | A/B | MRP关闭状态 |
| `FMrpFreezeStatus` | SAL_SaleOrder | A | MRP冻结状态 |
| `FMrpTerminateStatus` | SAL_SaleOrder | A | MRP终止状态 |

#### D. Business Process Status Fields

| Field | API | Description |
|-------|-----|-------------|
| `FDeliveryStatus` | SAL_SaleOrder | 交货状态 |
| `FARStatus` | SAL_OUTSTOCK | 应收状态 |
| `FAPSTATUS` | STK_InStock | 应付状态 |
| `FPayableCloseStatus` | STK_InStock | 应付关闭状态 |
| `FInvoicedStatus` | STK_InStock | 开票状态 |
| `FPickMtrlStatus` | SUB_SUBREQORDER | 领料状态 |
| `FConfirmStatus` | PUR_PurchaseOrder, STK_InStock | 确认状态 |

---

## 4. Unique Fields by API

### PRD_MO (生产订单) - Unique Fields

#### Header
| Field | Description |
|-------|-------------|
| `FPrdOrgId` | 生产组织 |
| `FPlannerID` | 计划员 |
| `FWorkShopID` | 生产车间(表头) |
| `FBusinessType` | 业务类型 |
| `FIsRework` | 是否返工 |
| `FIsEntrust` | 是否委外 |

#### Detail
| Field | Description |
|-------|-------------|
| `FMTONo` | 计划跟踪号 (Primary identifier) |
| `FPlanStartDate` | 计划开工日期 |
| `FPlanFinishDate` | 计划完工日期 |
| `FStatus` | 生产状态 (1-6) |
| `FYieldRate` | 合格率 |
| `FStockInQuaQty` | 良品入库数量 |
| `FNoStockInQty` | 未入库数量 |
| `FRequestOrgId` | 需求组织 |
| `FPlanConfirmDate` | 计划确认日期 |
| `FConveyDate` | 下达日期 |

---

### PRD_INSTOCK (生产入库单) - Unique Fields

#### Header
| Field | Description |
|-------|-------------|
| `FStockOrgId` | 库存组织 |
| `FWorkShopId` | 车间 |
| `FIOSBizTypeId` | 跨组织业务类型 |
| `FIsEntrust` | 是否委外 |
| `FEntrustInStockId` | 委外入库单ID |

#### Detail
| Field | Description |
|-------|-------------|
| `FProductType` | 产品类型 |
| `FInStockType` | 入库类型 |
| `FMustQty` / `FRealQty` | 应收/实收数量 |
| `FMoBillNo` | 生产订单编号 |
| `FMoEntryId` | 生产订单分录内码 |
| `FCheckProduct` | 检验产品 |
| `FQAIP` | 质检状态 (A) |
| `FCOSTRATE` | 成本率 |
| `FISBACKFLUSH` | 是否倒冲 |
| `FIsFinished` | 是否完工 |
| `FMoMainEntryId` | 生产订单主分录ID |

---

### PRD_PPBOM (生产用料清单) - Unique Fields

#### Header
| Field | Description |
|-------|-------------|
| `FMaterialID` | 产品物料 |
| `FWorkshopID` | 车间 |
| `FBOMID` | BOM版本 |
| `FMOBillNO` | 生产订单编号 |
| `FMOEntrySeq` | 生产订单行号 |
| `FMOStatus` | 生产订单状态 |
| `FMOType` | 生产订单类型 |
| `FInventoryDate` | 盘点日期 |
| `FGeneRateDate` | 生成日期 |

#### Detail (Extensive - 106 fields)
| Field | Description |
|-------|-------------|
| `FBOMEntryID` | BOM分录ID |
| `FReplaceGroup` | 替代组 |
| `FMaterialType` | 物料类型 |
| `FDosageType` | 用量类型 |
| `FUseRate` | 使用率 |
| `FScrapRate` | 损耗率 |
| `FOperID` | 工序ID |
| `FNeedDate` | 需求日期 |
| `FStdQty` | 标准用量 |
| `FNeedQty` | 需求数量 |
| `FMustQty` | 应发数量 |
| `FPickedQty` | 已领数量 |
| `FRePickedQty` | 补领数量 |
| `FScrapQty` | 报废数量 |
| `FGoodReturnQty` | 良品退料数量 |
| `FINCDefectReturnQty` | 来料不良退料 |
| `FProcessDefectReturnQty` | 工废退料 |
| `FConsumeQty` | 消耗数量 |
| `FWipQty` | 在制数量 |
| `FIssueType` | 发料方式 |
| `FBackFlushType` | 倒冲类型 |
| `FOverRate` | 超发比例 |
| `FIsKeyItem` | 是否关键件 |
| `FIsKeyComponent` | 是否关键组件 |
| `FNoPickedQty` | 未领数量 |

---

### PRD_PickMtrl (生产领料单) - Unique Fields

#### Header
| Field | Description |
|-------|-------------|
| `FTransferBizType` | 调拨业务类型 |
| `FPickerId` | 领料员 |
| `FIsCrossTrade` | 是否跨法人交易 |
| `FVmiBusiness` | VMI业务 |
| `FSourceType` | 来源类型 |
| `FIsOwnerTInclOrg` | 货主包含组织 |

#### Detail
| Field | Description |
|-------|-------------|
| `FPPBomEntryId` | PPBOM分录ID |
| `FOperId` | 工序ID |
| `FAppQty` | 申请数量 |
| `FActualQty` | 实际数量 |
| `FStockAppQty` | 库存申请数量 |
| `FStockActualQty` | 库存实际数量 |
| `FAllowOverQty` | 允许超发数量 |
| `FPPBomBillNo` | PPBOM单号 |
| `FParentOwnerTypeId` | 父项货主类型 |
| `FParentOwnerId` | 父项货主 |
| `FParentMaterialId` | 父项物料 |
| `FPickingStatus` | 领料状态 |
| `FReqSrc` | 需求来源 |
| `FReqBillNo` | 需求单号 |

---

### SAL_SaleOrder (销售订单) - Unique Fields

#### Header
| Field | Description |
|-------|-------------|
| `FSaleOrgId` | 销售组织 |
| `FCustId` | 客户 |
| `FSaleDeptId` | 销售部门 |
| `FSalerId` | 销售员 |
| `FReceiveId` | 收货方 |
| `FSettleId` | 结算方 |
| `FChargeId` | 付款方 |
| `FReceiveAddress` | 收货地址 |
| `FCreditCheckResult` | 信用检查结果 |
| `FNetOrderBillNo` | 网络订单号 |
| `FLinkMan` | 联系人 |
| `FLinkPhone` | 联系电话 |
| `FContractType` | 合同类型 |
| `FContractId` | 合同ID |

#### Detail (Extensive - 182 fields)
| Field | Description |
|-------|-------------|
| `FPrice` / `FTaxPrice` | 单价/含税单价 |
| `FTaxRate` / `FTaxAmount` | 税率/税额 |
| `FAllAmount` | 价税合计 |
| `FDiscountRate` / `FDiscount` | 折扣率/折扣额 |
| `FDeliveryDate` | 交货日期 |
| `FDeliveryControl` | 发货控制 |
| `FDeliveryMaxQty` / `FDeliveryMinQty` | 发货上限/下限 |
| `FMrpCloseStatus` | MRP关闭状态 |
| `FMrpFreezeStatus` | MRP冻结状态 |
| `FMrpTerminateStatus` | MRP终止状态 |
| `FDeliQty` | 已发货数量 |
| `FStockOutQty` | 已出库数量 |
| `FRemainOutQty` | 未出库数量 |
| `FRetNoticeQty` | 退货通知数量 |
| `FReturnQty` | 已退货数量 |
| `FInvoiceQty` | 已开票数量 |
| `FReceiveAmount` | 已收款金额 |
| `FPurReqQty` / `FPurOrderQty` | 采购申请/订单数量 |
| `FReserveType` | 预留类型 |
| `FPriority` | 优先级 |
| `FMinPlanDeliveryDate` | 最小计划发货日期 |
| `FDeliveryStatus` | 交货状态 |
| `FCanOutQty` | 可出库数量 |
| `FCanReturnQty` | 可退货数量 |
| `FAvailableQty` | 可用库存数量 |
| `FInventoryQty` | 库存数量 |
| `FCurrentInventory` | 当前库存 |
| `FRowType` | 行类型 |
| `FParentMatId` | 父项物料 |

---

### SAL_OUTSTOCK (销售出库单) - Unique Fields

#### Header
| Field | Description |
|-------|-------------|
| `FCustomerID` | 客户 |
| `FDeliveryDeptID` | 发货部门 |
| `FStockerGroupID` / `FStockerID` | 仓管组/仓管员 |
| `FSalesGroupID` / `FSalesManID` | 销售组/销售员 |
| `FCarrierID` / `FCarriageNO` | 承运商/运输单号 |
| `FReceiverID` | 收货方 |
| `FPayerID` | 付款方 |
| `FBussinessType` | 业务类型 |
| `FTransferBizType` | 调拨业务类型 |
| `FIsInterLegalPerson` | 是否内部法人 |
| `FPlanRecAddress` | 计划收货地址 |
| `FARStatus` | 应收状态 |
| `FLogisticsNos` | 物流单号 |

#### Detail
| Field | Description |
|-------|-------------|
| `FCustMatID` | 客户物料 |
| `FMustQty` / `FRealQty` | 应发/实发数量 |
| `FCostPrice` / `FCostAmount` | 成本单价/金额 |
| `FReturnQty` | 退货数量 |
| `FSumRetNoticeQty` | 累计退货通知数量 |
| `FSumRetStockQty` | 累计退货入库数量 |
| `FInvoicedQty` | 已开票数量 |
| `FSumInvoicedQty` / `FSumInvoicedAMT` | 累计开票数量/金额 |
| `FSumReceivedAMT` | 累计收款金额 |
| `FArrivalStatus` / `FArrivalDate` | 到货状态/日期 |
| `FValidateStatus` / `FValidateDate` | 验收状态/日期 |
| `FSignQty` | 签收数量 |
| `FRefuseQty` | 拒收数量 |
| `FRepairQty` | 维修数量 |

---

### PUR_PurchaseOrder (采购订单) - Unique Fields

#### Header
| Field | Description |
|-------|-------------|
| `FPurchaseOrgId` | 采购组织 |
| `FSupplierId` | 供应商 |
| `FPurchaserGroupId` | 采购员组 |
| `FPurchaseDeptId` | 采购部门 |
| `FPurchaserId` | 采购员 |
| `FSettleId` | 结算供应商 |
| `FChargeId` | 付款供应商 |
| `FProviderId` | 供货方 |
| `FProviderAddress` | 供货地址 |
| `FProviderContact` | 供货联系人 |
| `FAssignSupplierId` | 指定供应商 |
| `FConfirmStatus` | 确认状态 |
| `FSourceBillNo` | 来源单号 |
| `FACCTYPE` | 应计类型 |
| `FRelReqStatus` | 关联请购状态 |

#### Detail (Extensive - 165 fields)
| Field | Description |
|-------|-------------|
| `FPrice` / `FTaxPrice` | 单价/含税单价 |
| `FTaxRate` / `FTaxNetPrice` | 税率/不含税单价 |
| `FAmount` / `FAllAmount` | 金额/价税合计 |
| `FDiscountRate` / `FDiscount` | 折扣率/折扣额 |
| `FReceiveQty` | 已收货数量 |
| `FStockInQty` | 已入库数量 |
| `FInvoiceQty` / `FInvoiceAmount` | 已开票数量/金额 |
| `FPayAmount` | 已付款金额 |
| `FRemainReceiveQty` | 未收货数量 |
| `FRemainStockInQty` | 未入库数量 |
| `FReceiveOrgId` | 收料组织 |
| `FRequireOrgId` | 需求组织 |
| `FRequireDeptId` / `FRequireStaffId` | 需求部门/员工 |
| `FSupplierLot` | 供应商批号 |
| `FDeliveryControl` | 交货控制 |
| `FDeliveryBeforeDays` / `FDeliveryDelayDays` | 提前/延迟天数 |
| `FDeliveryMaxQty` / `FDeliveryMinQty` | 交货上限/下限 |
| `FDeliveryDate` / `FDeliveryLastDate` / `FDeliveryEarlyDate` | 交货日期 |
| `FContractNo` | 合同号 |
| `FReqTraceNo` | 请购追溯号 |
| `FAPJoinAmount` | 应付关联金额 |
| `FMrbQty` | 退料数量 |
| `FGiveAway` | 是否赠品 |
| `FIsStock` | 是否入库 |
| `FRowType` | 行类型 |

---

### STK_InStock (采购入库单) - Unique Fields

#### Header
| Field | Description |
|-------|-------------|
| `FDemandOrgId` | 需求组织 |
| `FPurchaseOrgId` | 采购组织 |
| `FSupplierId` | 供应商 |
| `FSupplyId` | 供货方 |
| `FSettleId` / `FChargeId` | 结算/付款供应商 |
| `FBusinessType` | 业务类型 |
| `FSupplyAddress` | 供货地址 |
| `FAPSTATUS` | 应付状态 |
| `FDeliveryBill` / `FTakeDeliveryBill` | 送货单/收货单 |
| `FConfirmStatus` | 确认状态 |
| `FSplitBillType` | 拆分单据类型 |
| `FSalOutStockOrgId` | 销售出库组织 |

#### Detail
| Field | Description |
|-------|-------------|
| `FMustQty` / `FRealQty` | 应收/实收数量 |
| `FSupplierLot` | 供应商批号 |
| `FGrossWeight` / `FNetWeight` | 毛重/净重 |
| `FContractNO` / `FDemandNo` | 合同号/需求号 |
| `FTaxPrice` / `FCostPrice` | 含税单价/成本单价 |
| `FTaxRate` / `FTaxAmount` | 税率/税额 |
| `FCostAmount` / `FAllAmount` | 成本金额/价税合计 |
| `FPOOrderNo` | 采购订单号 |
| `FPOORDERENTRYID` | 采购订单分录ID |
| `FReceiveStockStatus` / `FReceiveStockFlag` | 收料状态/标志 |
| `FInvoicedQty` / `FInvoicedStatus` | 已开票数量/状态 |
| `FProcessFee` / `FMaterialCosts` | 加工费/材料费 |
| `FGiveAway` | 是否赠品 |
| `FCheckInComing` | 来料检验 |
| `FPayableCloseStatus` / `FPayableCloseDate` | 应付关闭状态/日期 |
| `FAPNotJoinQty` | 应付未关联数量 |
| `FAPJoinAmount` | 应付关联金额 |
| `FRemainInStockQty` | 剩余入库数量 |
| `FBILLINGCLOSE` | 开票关闭 |
| `FWWInType` | 委外入库类型 |

---

### SUB_SUBREQORDER (委外申请订单) - Unique Fields

#### Header
| Field | Description |
|-------|-------------|
| `FSubOrgId` | 委外组织 |
| `FPlannerID` | 计划员 |
| `FWorkGroupId` | 工作组 |
| `FIsRework` | 是否返工 |
| `FIsQCSub` | 是否质检委外 |
| `FPPBOMType` | PPBOM类型 |

#### Detail
| Field | Description |
|-------|-------------|
| `FProductType` | 产品类型 |
| `FPlanStartDate` / `FPlanFinishDate` | 计划开始/完成日期 |
| `FSupplierId` | 供应商 |
| `FStatus` | 状态 |
| `FRequestOrgId` | 需求组织 |
| `FRoutingId` | 工艺路线 |
| `FYieldRate` / `FYieldQty` | 合格率/合格数量 |
| `FStockInLimitH` / `FStockInLimitL` | 入库上限/下限 |
| `FStockInQty` / `FNoStockInQty` | 已入库/未入库数量 |
| `FPurSelQty` / `FPurQty` | 采购选择/数量 |
| `FPurOrderNo` / `FPurOrderId` | 采购订单号/ID |
| `FPurorgId` | 采购组织 |
| `FStockInOrgId` | 入库组织 |
| `FSettleOrgId` | 结算组织 |
| `FInStockOwnerTypeId` / `FInStockOwnerId` | 入库货主类型/ID |
| `FSampleDamageQty` | 检验损耗数量 |
| `FStockReadyqty` | 备料数量 |
| `FPickMtlQty` / `FPickMtrlStatus` | 领料数量/状态 |
| `FIsSuspend` | 是否挂起 |
| `FCreateType` | 创建类型 |
| `FCloseType` | 关闭类型 |
| `FScheduleStatus` | 排程状态 |
| `FMatchQty` / `FInvMatchQty` | 匹配数量/库存匹配 |

---

## 5. Custom Fields Analysis (F_QWJI_*)

### Complete Inventory

| Field | Found In APIs | Inferred Purpose |
|-------|---------------|------------------|
| **Customer/Partner Fields** | | |
| `F_QWJI_KHMC` | PRD_MO, PRD_INSTOCK, PRD_PickMtrl | 客户名称 (Customer Name) |
| `F_QWJI_KHMC1` | PRD_MO | 客户名称 (Header) |
| `F_QWJI_DDH` | SAL_SaleOrder | 订单号 (Order Number) |
| **Contract/Document Fields** | | |
| `F_QWJI_HTH` | PUR_PurchaseOrder, STK_InStock | 合同号 (Contract Number) |
| `F_QWJI_JHGZH` | SAL_SaleOrder | 计划跟踪号 (Plan Tracking) |
| `F_QWJI_JHZT` | PUR_PurchaseOrder | 交货状态 (Delivery Status) |
| **Inventory Fields** | | |
| `F_QWJI_JSKC` | PRD_INSTOCK, PRD_PickMtrl, SAL_OUTSTOCK, STK_InStock, PUR_PurchaseOrder | 即时库存 (Real-time Inventory) |
| `F_QWJI_SCCL` | PRD_INSTOCK | 生产产量 (Production Output) |
| `F_QWJI_ZP` | STK_InStock | 赠品 (Free Gift) |
| **Supplier/Source Fields** | | |
| `F_QWJI_SCCS` | PUR_PurchaseOrder | 生产厂商 (Manufacturer) |
| `F_QWJI_FKTJ2` | PUR_PurchaseOrder | 付款条件 (Payment Terms) |
| `F_QWJI_JHRQ` | STK_InStock | 交货日期 (Delivery Date) |
| **Packaging Fields** | | |
| `F_QWJI_WK` | SAL_SaleOrder | 外箱 (Outer Carton) |
| `F_QWJI_WLTP` | SAL_SaleOrder | 物料图片 (Material Picture) |
| `F_QWJI_PACKAGE` | SAL_SaleOrder | 包装 (Package) |
| `F_QWJI_CARTON` | SAL_SaleOrder | 箱规 (Carton Spec) |
| `F_QWJI_BARCODE` | SAL_SaleOrder | 条码 (Barcode) |
| `F_QWJI_CTNQTY` | SAL_SaleOrder | 每箱数量 (Qty per Carton) |
| `F_QWJI_CTNS` | SAL_SaleOrder | 箱数 (Number of Cartons) |
| `F_QWJI_CBM` | SAL_SaleOrder | 立方米 (Cubic Meters) |
| **Price Fields** | | |
| `F_QWJI_DJ` | SAL_OUTSTOCK | 单价 (Unit Price) |
| `F_QWJI_KJDJ` | SAL_SaleOrder | 客价单价 (Customer Price) |
| `F_QWJI_JJDJ` | SAL_SaleOrder | 加价单价 (Markup Price) |
| `F_QWJI_WXDJ` | SAL_SaleOrder | 维修单价 (Repair Price) |
| `F_QWJI_Qty_qtr` | SAL_SaleOrder | 季度数量 (Quarterly Qty) |
| **BOM/Material Fields** | | |
| `F_QWJI_XSWLBM` | PRD_PPBOM | 销售物料编码 (Sales Material Code) |
| `F_QWJI_MS` / `F_QWJI_MS2` | PRD_PPBOM | 描述 (Description) |
| `F_QWJI_YSTP` / `F_QWJI_YSTP2` / `F_QWJI_YSTP3` | PRD_PPBOM | 原始图片 (Original Picture) |
| `F_QWJI_FJ` | PRD_PPBOM | 附件 (Attachment) |
| **Purchase Order Fields** | | |
| `F_QWJI_Remarks_qtr` / `F_QWJI_Remarks_83g` | PUR_PurchaseOrder | 备注 (Remarks) |
| `F_QWJI_Picture_re5` / `F_QWJI_Picture_apv` / `F_QWJI_Picture_tzk` | PUR_PurchaseOrder | 图片 (Pictures) |
| `F_QWJI_Attachments_ca9` | PUR_PurchaseOrder | 附件 (Attachments) |
| `F_QWJI_GGBC` | PUR_PurchaseOrder | 规格包材 (Spec/Packaging) |
| **Other Fields** | | |
| `F_QWJI_Base_qtr` | PRD_PickMtrl | 基地/车间 (Base/Workshop) |

### Custom Fields by API

| API | Custom Fields Count | Key Fields |
|-----|---------------------|------------|
| PRD_MO | 1 | KHMC1 (客户名称) |
| PRD_INSTOCK | 3 | SCCL, JSKC, KHMC |
| PRD_PPBOM | 8 | MS, YSTP, FJ, XSWLBM |
| PRD_PickMtrl | 3 | JSKC, KHMC, Base_qtr |
| SAL_SaleOrder | 15 | WK, PACKAGE, CARTON, CBM, DDH, 价格字段 |
| SAL_OUTSTOCK | 3 | ddh, DJ, JSKC |
| PUR_PurchaseOrder | 10 | SCCS, FKTJ2, HTH, JHZT, Pictures |
| STK_InStock | 4 | SCCS1, hth, JSKC, ZP, JHRQ |
| SUB_SUBREQORDER | 0 | (none) |

---

## 6. Field Naming Conventions

### Standard Prefixes

| Prefix | Meaning | Example |
|--------|---------|---------|
| `F` | Field (基础字段) | `FBillNo`, `FDate` |
| `FBase` | Base unit (基本单位) | `FBaseUnitQty`, `FBaseUnitId` |
| `FStock` | Stock/Inventory (库存) | `FStockId`, `FStockQty` |
| `FSrc` | Source (源单) | `FSrcBillNo`, `FSrcBillType` |
| `FMust` | Required/Planned (应收/应发) | `FMustQty` |
| `FReal` | Actual (实收/实发) | `FRealQty` |
| `FRemain` | Remaining (剩余) | `FRemainOutQty` |
| `FSal` / `FPur` | Sales/Purchase (销售/采购) | `FSalUnitId`, `FPurQty` |
| `FSec` | Secondary unit (辅助单位) | `FSecUnitId`, `FSecQty` |
| `F_QWJI_` | Custom field (自定义) | `F_QWJI_KHMC` |

### Entry Prefixes by API

| API | Entry Prefix | Example |
|-----|--------------|---------|
| PRD_MO | `FTreeEntity_` | `FTreeEntity_FSeq` |
| PRD_INSTOCK | `FEntity_` | `FEntity_FMaterialId` |
| PRD_PPBOM | `FPPBomEntry_` | `FPPBomEntry_FMaterialID` |
| PRD_PickMtrl | `FEntity_` | `FEntity_FActualQty` |
| SAL_SaleOrder | `FSaleOrderEntry_` | `FSaleOrderEntry_FQty` |
| SAL_OUTSTOCK | `FSAL_OUTSTOCKENTRY_` | `FSAL_OUTSTOCKENTRY_FRealQty` |
| PUR_PurchaseOrder | `FPOOrderEntry_` | `FPOOrderEntry_FPrice` |
| STK_InStock | `FInStockEntry_` | `FInStockEntry_FRealQty` |
| SUB_SUBREQORDER | `FTreeEntity_` | `FTreeEntity_FQty` |

### ID vs Number vs No Patterns

| Pattern | Usage | Example |
|---------|-------|---------|
| `*Id` | Internal numeric ID | `FId`, `FMoId`, `FSaleOrderId` |
| `*No` | Business document number | `FBillNo`, `FMTONo`, `FSaleOrderNo` |
| `*BillNo` | Full document reference | `FMoBillNo`, `FPOOrderNo` |
| `*EntryId` | Line item internal ID | `FMoEntryId`, `FSaleOrderEntryId` |
| `*EntrySeq` | Line item sequence number | `FMoEntrySeq`, `FSeq` |

---

## Appendix: Quick Reference Query Examples

### Find Documents by MTO Number
```python
# Sales Order
{"FormId": "SAL_SaleOrder", "FilterString": "FSaleOrderEntry_FMtoNo='AK2412023'"}

# Production Order
{"FormId": "PRD_MO", "FilterString": "FMTONo='AK2412023'"}

# Purchase Order
{"FormId": "PUR_PurchaseOrder", "FilterString": "FPOOrderEntry_FMtoNo='AK2412023'"}

# Production Receipt
{"FormId": "PRD_INSTOCK", "FilterString": "FEntity_FMtoNo='AK2412023'"}
```

### Find Related Documents
```python
# Find PPBOM by Production Order
{"FormId": "PRD_PPBOM", "FilterString": "FMOBillNO='MO25010001'"}

# Find Pick List by PPBOM
{"FormId": "PRD_PickMtrl", "FilterString": "FEntity_FPPBomBillNo='PPBOM25010001'"}

# Find Purchase Receipt by PO
{"FormId": "STK_InStock", "FilterString": "FInStockEntry_FPOOrderNo='F2412390'"}
```

### Query Outstanding Quantities
```python
# Unreceived PO lines
{"FormId": "PUR_PurchaseOrder", "FilterString": "FPOOrderEntry_FRemainReceiveQty>0"}

# Undelivered SO lines
{"FormId": "SAL_SaleOrder", "FilterString": "FSaleOrderEntry_FRemainOutQty>0"}

# Unpicked PPBOM materials
{"FormId": "PRD_PPBOM", "FilterString": "FPPBomEntry_FNoPickedQty>0"}
```
