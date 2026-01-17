# 采购入库单 (STK_InStock) 字段清单

## 一、单据头字段

| 查询字段名 | 说明 | 示例值 |
|-----------|------|--------|
| `FId` | 单据内码 | 100007 |
| `FSrcEntityDisa` | SrcEntityDisa |   |
| `FBillNo` | 单据编号 | CGRK00002 |
| `FDocumentStatus` | 单据状态 | C |
| `FStockOrgId` | 库存组织 | 102 |
| `FDate` | 日期 | 2024-12-13T00:00:00 |
| `FBillTypeID_Id` | FBillTypeID_Id | a1ff32276cd9469dad3bf2494366fa4f |
| `FBillTypeID` | FBillTypeID | RKD01_SYS |
| `FOwnerTypeIdHead` | OwnerTypeIdHead | BD_OwnerOrg |
| `FOwnerIdHead` | 货主(表头) | 102 |
| `FDemandOrgId` | DemandOrgId | 102 |
| `FPurchaseOrgId` | 采购组织 | 102 |
| `FSupplierId` | 供应商 | 07.0005 |
| `FStockerGroupId` | StockerGroupId | - |
| `FStockDeptId` | StockDeptId | - |
| `FStockerId` | StockerId | - |
| `FCreatorId` | 创建人 | (object) |
| `FCreateDate` | 创建日期 | 2024-12-13T09:18:04.96 |
| `FModifierId_Id` | 修改人 | 183832 |
| `FModifierId` | 修改人 | (object) |
| `FModifyDate` | 修改日期 | 2024-12-13T09:18:05.32 |
| `FApproverId` | 审核人 | (object) |
| `FCancelDate` | 作废日期 | - |
| `FDeliveryBill` | DeliveryBill |   |
| `FTakeDeliveryBill` | TakeDeliveryBill |   |
| `FCancellerId` | CancellerId | - |
| `FApproveDate` | 审核日期 | 2024-12-14T16:21:22.96 |
| `FCancelStatus` | CancelStatus | A |
| `FPurchaseDeptId` | PurchaseDeptId | - |
| `FPurchaserGroupId` | PurchaserGroupId | - |
| `FPurchaserId` | 采购员 | - |
| `FSupplyId` | SupplyId | 07.0005 |
| `FSettleId` | SettleId | 07.0005 |
| `FChargeId` | ChargeId | 07.0005 |
| `FBusinessType` | BusinessType | CG |
| `FSupplyAddress` | SupplyAddress |   |
| `FAPSTATUS` | APSTATUS | Y |
| `FTransferBizType` | TransferBizType | OverOrgPur |
| `FCorrespondOrgId` | CorrespondOrgId | 105 |
| `FIsInterLegalPerson` | IsInterLegalPerson | false |
| `FScanBox` | ScanBox | - |
| `FCDateOffsetUnit` | FCDateOffsetUnit | - |
| `FCDateOffsetValue` | CDateOffsetValue | 0 |
| `FDisassemblyFlag` | DisassemblyFlag | false |
| `FConfirmerId` | ConfirmerId | - |
| `FConfirmDate` | ConfirmDate | - |
| `FConfirmStatus` | ConfirmStatus | A |
| `FProviderContactID` | ProviderContactID | - |
| `FSplitBillType` | SplitBillType | A |
| `FSupplyEMail` | FSupplyEMail |   |
| `FSalOutStockOrgId` | SalOutStockOrgId | - |
| `F_QWJI_SCCS1_Id` | F_QWJI_SCCS1_Id | 0 |
| `F_QWJI_SCCS1` | F_QWJI_SCCS1 | - |
| `F_QWJI_hth` | F_QWJI_hth | - |
| `FBOS_ConvertTakeDataInfo` | BOS_ConvertTakeDataInfo | - |

## 二、明细行字段 (InStockEntry)

| 查询字段名 | 说明 | 示例值 |
|-----------|------|--------|
| `FInStockEntry_FId` | 单据内码 | 100009 |
| `FInStockEntry_FSeq` | 行号 | 1 |
| `FInStockEntry_FSrcEntityDisa` | SrcEntityDisa |   |
| `FInStockEntry_FMaterialId` | 物料 | 21.05.183 |
| `FInStockEntry_FStockId` | 仓库 | 01.01 |
| `FInStockEntry_FProduceDate` | 生产日期 | - |
| `FInStockEntry_FNote` | 备注 |   |
| `FInStockEntry_FSupplierLot` | SupplierLot |   |
| `FInStockEntry_FGrossWeight` | GrossWeight | 0.0 |
| `FInStockEntry_FNetWeight` | NetWeight | 0.0 |
| `FInStockEntry_FContractNO` | ContractNO |   |
| `FInStockEntry_FDemandNo` | DemandNo |   |
| `FInStockEntry_FMustQty` | 应收/应发数量 | 60.0 |
| `FInStockEntry_FRealQty` | 实收/实发数量 | 60.0 |
| `FInStockEntry_FAuxUnitQty` | AuxUnitQty | 0.0 |
| `FInStockEntry_FSRCRowId` | SRCRowId | 0 |
| `FInStockEntry_FEXPIRYDATE` | EXPIRYDATE | - |
| `FInStockEntry_FIsFree` | IsFree | false |
| `FInStockEntry_FStockStatusId` | 库存状态 | KCZT01_SYS |
| `FInStockEntry_FBOMId` | BOMId | - |
| `FInStockEntry_FTaxPrice` | 含税单价 | 295.0 |
| `FInStockEntry_FCostPrice` | CostPrice | 261.062 |
| `FInStockEntry_FTaxRate` | 税率 | 13.0 |
| `FInStockEntry_FTaxAmount` | TaxAmount | 2036.28 |
| `FInStockEntry_FDiscountRate` | DiscountRate | 0.0 |
| `FInStockEntry_FPriceCoefficient` | PriceCoefficient | 1.0 |
| `FInStockEntry_FPriceUnitQty` | PriceUnitQty | 60.0 |
| `FInStockEntry_FTaxNetPrice` | FTaxNetPrice | 295.0 |
| `FInStockEntry_FCostAmount` | FCostAmount | 15663.72 |
| `FInStockEntry_FAllAmount` | AllAmount | 17700.0 |
| `FInStockEntry_FTaxAmount_LC` | TaxAmount_LC | 2036.28 |
| `FInStockEntry_FCostAmount_LC` | CostAmount_LC | 15663.72 |
| `FInStockEntry_FAllAmount_LC` | AllAmount_LC | 17700.0 |
| `FInStockEntry_FStockFlag` | StockFlag | true |
| `FInStockEntry_FBaseUnitPrice` | BaseUnitPrice | 0.0 |
| `FInStockEntry_FUnitID` | UnitID | 025 |
| `FInStockEntry_FBaseUnitID` | BaseUnitID | 025 |
| `FInStockEntry_FBaseUnitQty` | 基本单位数量 | 60.0 |
| `FInStockEntry_FAuxUnitID` | AuxUnitID | - |
| `FInStockEntry_FPriceUnitID` | PriceUnitID | 025 |
| `FInStockEntry_FBaseJoinQty` | BaseJoinQty | 0.0 |
| `FInStockEntry_FAuxPropId` | 辅助属性 | - |
| `FInStockEntry_FPOOrderNo` | POOrderNo | BJ241111185 |
| `FInStockEntry_FReceiveStockStatus` | ReceiveStockStatus | - |
| `FInStockEntry_FStockLocId` | 仓位 | - |
| `FInStockEntry_FSRCBILLTYPEID` | SRCBILLTYPEID | PUR_PurchaseOrder |
| `FInStockEntry_FSRCBillNo` | SRCBillNo | BJ241111185 |
| `FInStockEntry_FKeeperTypeID` | KeeperTypeID | BD_KeeperOrg |
| `FInStockEntry_FKeeperID` | KeeperID | 102 |
| `FInStockEntry_FInvoicedQty` | InvoicedQty | 0.0 |
| `FInStockEntry_FBaseAPJoinQty` | BaseAPJoinQty | 60.0 |
| `FInStockEntry_FReceiveStockFlag` | ReceiveStockFlag | false |
| `FInStockEntry_FProcessFee` | ProcessFee | 0.0 |
| `FInStockEntry_FMaterialCosts` | MaterialCosts | 0.0 |
| `FInStockEntry_FOWNERTYPEID` | OWNERTYPEID | BD_OwnerOrg |
| `FInStockEntry_FOWNERID` | OWNERID | 102 |
| `FInStockEntry_FJOINEDQTY` | JOINEDQTY | 0.0 |
| `FInStockEntry_FUNJOINQTY` | UNJOINQTY | 0.0 |
| `FInStockEntry_FJOINEDAMOUNT` | JOINEDAMOUNT | 0.0 |
| `FInStockEntry_FUNJOINAMOUNT` | UNJOINAMOUNT | 0.0 |
| `FInStockEntry_FULLYJOINED` | FULLYJOINED | false |
| `FInStockEntry_FJOINSTATUS` | JOINSTATUS | A |
| `FInStockEntry_FLot` | 批号 | BJ241111185 |
| `FInStockEntry_FLot_Text` | Lot_Text | BJ241111185 |
| `FInStockEntry_FReceiveOwnerTypeId` | ReceiveOwnerTypeId |   |
| `FInStockEntry_FReceiveOwnerId` | ReceiveOwnerId | - |
| `FInStockEntry_FTaxCombination` | TaxCombination | - |
| `FInStockEntry_FPrice` | 单价 | 261.061947 |
| `FInStockEntry_FSysPrice` | SysPrice | 0.0 |
| `FInStockEntry_FUpPrice` | UpPrice | 0.0 |
| `FInStockEntry_FDownPrice` | DownPrice | 0.0 |
| `FInStockEntry_FAmount` | 金额 | 15663.72 |
| `FInStockEntry_FAmount_LC` | Amount_LC | 15663.72 |
| `FInStockEntry_FDiscount` | Discount | 0.0 |
| `FInStockEntry_FBaseReturnJoinQty` | BaseReturnJoinQty | 0.0 |
| `FInStockEntry_FReturnJoinQty` | ReturnJoinQty | 0.0 |
| `FInStockEntry_FBFLowId` | BFLowId | - |
| `FInStockEntry_FReceiveLot` | ReceiveLot | - |
| `FInStockEntry_FReceiveLot_Text` | ReceiveLot_Text |   |
| `FInStockEntry_FReceiveStockId` | ReceiveStockId | - |
| `FInStockEntry_FReceiveStockLocId` | ReceiveStockLocId | - |
| `FInStockEntry_FReceiveAuxPropId` | ReceiveAuxPropId | - |
| `FInStockEntry_FMtoNo` | 计划跟踪号 | BJ241111185 |
| `FInStockEntry_FProjectNo` | ProjectNo |   |
| `FInStockEntry_FGiveAway` | GiveAway | false |
| `FInStockEntry_FSNUnitID` | SNUnitID | - |
| `FInStockEntry_FSNQty` | SNQty | 0.0 |
| `FInStockEntry_FSECRETURNJOINQTY` | SECRETURNJOINQTY | 0.0 |
| `FInStockEntry_FSampleDamageQty` | FSampleDamageQty | 0.0 |
| `FInStockEntry_FSampleDamageBaseQty` | FSampleDamageBaseQty | 0.0 |
| `FInStockEntry_FCheckInComing` | CheckInComing | false |
| `FInStockEntry_FIsReceiveUpdateStock` | IsReceiveUpdateStock | false |
| `FInStockEntry_FInvoicedStatus` | InvoicedStatus | A |
| `FInStockEntry_FInvoicedJoinQty` | InvoicedJoinQty | 0.0 |
| `FInStockEntry_FExtAuxUnitId` | ExtAuxUnitId | - |
| `FInStockEntry_FExtAuxUnitQty` | ExtAuxUnitQty | 0.0 |
| `FInStockEntry_FReceiveMtoNo` | ReceiveMtoNo |   |
| `FInStockEntry_FWWInType` | WWInType |   |
| `FInStockEntry_FPriceBaseQty` | PriceBaseQty | 60.0 |
| `FInStockEntry_FSetPriceUnitID` | SetPriceUnitID | - |
| `FInStockEntry_FRemainInStockUnitId` | RemainInStockUnitId | 025 |
| `FInStockEntry_FRemainInStockQty` | RemainInStockQty | 60.0 |
| `FInStockEntry_FRemainInStockBaseQty` | RemainInStockBaseQty | 60.0 |
| `FInStockEntry_FBILLINGCLOSE` | BILLINGCLOSE | true |
| `FInStockEntry_FPurBaseNum` | PurBaseNum | 60.0 |
| `FInStockEntry_FStockBaseDen` | FStockBaseDen | 60.0 |
| `FInStockEntry_FSrcBizUnitID` | SrcBizUnitID | 025 |
| `FInStockEntry_FRETURNSTOCKJNBASEQTY` | RETURNSTOCKJNBASEQTY | 0.0 |
| `FInStockEntry_FStockBaseAPJoinQty` | StockBaseAPJoinQty | 60.0 |
| `FInStockEntry_FCOSTPRICE_LC` | COSTPRICE_LC | 261.062 |
| `FInStockEntry_FPOORDERENTRYID` | POORDERENTRYID | 106494 |
| `FInStockEntry_FPriceListEntry` | PriceListEntry | - |
| `FInStockEntry_FAPNotJoinQty` | APNotJoinQty | 0.0 |
| `FInStockEntry_FAPJoinAmount` | APJoinAmount | 17700.0 |
| `FInStockEntry_FPayableCloseStatus` | PayableCloseStatus | B |
| `FInStockEntry_FPayableCloseDate` | PayableCloseDate | 2024-12-14T00:00:00 |
| `FInStockEntry_FDisPriceQty` | DisPriceQty | 0.0 |
| `FInStockEntry_FBeforeDisPriceQty` | BeforeDisPriceQty | 0.0 |
| `FInStockEntry_FRECSUBENTRYID` | RECSUBENTRYID | 0 |
| `FInStockEntry_FRowType` | RowType | Standard |
| `FInStockEntry_FParentMatId` | ParentMatId | - |
| `FInStockEntry_FRowId` | RowId |   |
| `FInStockEntry_FParentRowId` | ParentRowId |   |
| `FInStockEntry_FTHIRDENTRYID` | THIRDENTRYID |   |
| `FInStockEntry_FProcessFee_LC` | ProcessFee_LC | 0.0 |
| `FInStockEntry_FMaterialCosts_LC` | MaterialCosts_LC | 0.0 |
| `FInStockEntry_FPriceDiscount` | PriceDiscount | 0.0 |
| `FInStockEntry_FPriLstEntryId` | PriLstEntryId | 0 |
| `FInStockEntry_FCMKBarCode` | FCMKBarCode |   |
| `FInStockEntry_FAllotBaseQty` | FAllotBaseQty | 0.0 |
| `FInStockEntry_FIsScanEntry` | FIsScanEntry | false |
| `FInStockEntry_FConsumeSumQty` | ConsumeSumQty | 0.0 |
| `FInStockEntry_FBaseConsumeSumQty` | BaseConsumeSumQty | 0.0 |
| `FInStockEntry_FRejectsDiscountAmount` | RejectsDiscountAmount | 0.0 |
| `FInStockEntry_FTailDiffFlag` | TailDiffFlag | false |
| `FInStockEntry_FAllAmountExceptDisCount` | AllAmountExceptDisCount | 17700.0 |
| `FInStockEntry_FSalOutStockBillNo` | SalOutStockBillNo |   |
| `FInStockEntry_FSalOutStockEntryId` | SalOutStockEntryId | 0 |
| `FInStockEntry_FIsReconciliationing` | IsReconciliationing | false |
| `FInStockEntry_FReconciliationBillNo` | ReconciliationBillNo |   |
| `FInStockEntry_FAllReconciliationBillNo` | AllReconciliationBillNo |   |
| `FInStockEntry_FPayableEntryID` | PayableEntryID | 0 |
| `FInStockEntry_FWWPickMtlQty` | WWPickMtlQty | 0.0 |
| `FInStockEntry_FSUBREQBILLNO` | SUBREQBILLNO |   |
| `FInStockEntry_FSUBREQBILLSEQ` | SUBREQBILLSEQ | 0 |
| `FInStockEntry_FSUBREQENTRYID` | SUBREQENTRYID | 0 |
| `FInStockEntry_FProductType` | ProductType | 1 |
| `FInStockEntry_FSubReqMEID` | SubReqMEID | 0 |
| `FInStockEntry_FCOSTRATE` | COSTRATE | 0.0 |
| `FInStockEntry_F_QWJI_JSKC` | F_QWJI_JSKC | 0.0 |
| `FInStockEntry_F_QWJI_ZP` | F_QWJI_ZP | 0.0 |
| `FInStockEntry_F_QWJI_JHRQ` | F_QWJI_JHRQ | 2024-12-09T15:36:11.693 |

## 三、常用查询示例

```python
# 根据计划跟踪号查询采购入库单
query_para = {
    "FormId": "STK_InStock",
    "FieldKeys": "FBillNo,FId,FInStockEntry_FMaterialId.FNumber,FInStockEntry_FMaterialId.FName,FInStockEntry_FQty",
    "FilterString": "FInStockEntry_FMTONo='AS251008'",
    "Limit": 100
}
result = api_sdk.ExecuteBillQuery(query_para)
```

## 四、状态值说明

### 单据状态 (FDocumentStatus)

| 值 | 说明 |
|----|------|
| A | 创建 |
| B | 审核中 |
| C | 已审核 |
| Z | 暂存 |

## 五、API 使用说明

### 单据查询 (ExecuteBillQuery)
- 用于批量查询，返回二维数组
- 支持过滤、排序、分页
- 最大返回 10000 条

### 查看 (View)
- 用于查看单条记录完整详情
- 通过 `Number` 或 `Id` 定位
- 返回完整 JSON 数据包
