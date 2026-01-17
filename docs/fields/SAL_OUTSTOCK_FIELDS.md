# 销售出库单 (SAL_OUTSTOCK) 字段清单

## 一、单据头字段

| 查询字段名 | 说明 | 示例值 |
|-----------|------|--------|
| `FId` | 单据内码 | 100006 |
| `FSrcEntityDisa` | SrcEntityDisa |   |
| `FBillNo` | 单据编号 | XSCKD000001 |
| `FDocumentStatus` | 单据状态 | C |
| `FSaleOrgId` | 销售组织 | 102 |
| `FDate` | 日期 | 2024-12-04T00:00:00 |
| `FStockOrgId` | 库存组织 | 102 |
| `FCustomerID` | 客户 | 09.048 |
| `FDeliveryDeptID` | DeliveryDeptID | - |
| `FSaleDeptID` | SaleDeptID | - |
| `FStockerGroupID` | StockerGroupID | - |
| `FStockerID` | StockerID | - |
| `FSalesGroupID` | SalesGroupID | - |
| `FSalesManID` | SalesManID | - |
| `FCarrierID` | CarrierID | - |
| `FCarriageNO` | CarriageNO |   |
| `FReceiverID` | ReceiverID | 09.048 |
| `FSettleID` | SettleID | 09.048 |
| `FPayerID` | PayerID | 09.048 |
| `FCreateDate` | 创建日期 | 2024-12-12T17:55:51.52 |
| `FModifierId_Id` | 修改人 | 183832 |
| `FModifierId` | 修改人 | (object) |
| `FModifyDate` | 修改日期 | 2024-12-18T16:21:55.723 |
| `FCreatorId_Id` | 创建人 | 183832 |
| `FCreatorId` | 创建人 | (object) |
| `FApproverID` | ApproverID | (object) |
| `FApproveDate` | 审核日期 | 2024-12-19T08:27:48.863 |
| `FCancelStatus` | CancelStatus | A |
| `FCancellerID` | CancellerID | - |
| `FCancelDate` | 作废日期 | - |
| `FBillTypeID` | BillTypeID | XSCKD01_SYS |
| `FOwnerTypeIdHead` | OwnerTypeIdHead | BD_OwnerOrg |
| `FOwnerIdHead` | 货主(表头) | - |
| `FBussinessType` | BussinessType | NORMAL |
| `FReceiveAddress` | ReceiveAddress |   |
| `FHeadLocationId` | HeadLocationId | - |
| `FCreditCheckResult` | CreditCheckResult | 0 |
| `FTransferBizType` | TransferBizType | OverOrgSal |
| `FCorrespondOrgId` | CorrespondOrgId | - |
| `FReceiverContactID` | ReceiverContactID | - |
| `FIsInterLegalPerson` | IsInterLegalPerson | false |
| `FGenFromPOS_CMK` | FGenFromPOS_CMK | false |
| `FLinkPhone` | FLinkPhone |   |
| `FLinkMan` | FLinkMan |   |
| `FBranchId_Id` | FBranchId_Id | 0 |
| `FBranchId` | FBranchId | - |
| `FScanBox` | ScanBox | - |
| `FCDateOffsetUnit` | CDateOffsetUnit | - |
| `FCDateOffsetValue` | CDateOffsetValue | 0 |
| `FPlanRecAddress` | PlanRecAddress |   |
| `FIsTotalServiceOrCost` | IsTotalServiceOrCost | false |
| `FNote` | 备注 |   |
| `FDisassemblyFlag` | DisassemblyFlag | false |
| `FSHOPNUMBER` | FSHOPNUMBER |   |
| `FGYDATE` | FGYDATE | - |
| `FSALECHANNEL` | FSALECHANNEL |   |
| `FLogisticsNos` | LogisticsNos |   |
| `FPRESETBASE2` | PRESETBASE2 | - |
| `FPRESETBASE1` | PRESETBASE1 | - |
| `FPRESETASSISTANT1` | PRESETASSISTANT1 | - |
| `FPRESETASSISTANT2` | PRESETASSISTANT2 | - |
| `FARStatus` | ARStatus | C |
| `FBOS_ConvertTakeDataInfo` | BOS_ConvertTakeDataInfo | - |

## 二、明细行字段 (SAL_OUTSTOCKENTRY)

| 查询字段名 | 说明 | 示例值 |
|-----------|------|--------|
| `FSAL_OUTSTOCKENTRY_FId` | 单据内码 | 100005 |
| `FSAL_OUTSTOCKENTRY_FSeq` | 行号 | 1 |
| `FSAL_OUTSTOCKENTRY_FSrcEntityDisa` | SrcEntityDisa |   |
| `FSAL_OUTSTOCKENTRY_FCustMatID` | CustMatID | - |
| `FSAL_OUTSTOCKENTRY_FMaterialID` | MaterialID | 27.09.02.03.01 |
| `FSAL_OUTSTOCKENTRY_FUnitID` | UnitID | 003 |
| `FSAL_OUTSTOCKENTRY_FMustQty` | 应收/应发数量 | 0.0 |
| `FSAL_OUTSTOCKENTRY_FRealQty` | 实收/实发数量 | 133.0 |
| `FSAL_OUTSTOCKENTRY_FStockID` | StockID | 07.01 |
| `FSAL_OUTSTOCKENTRY_FStockStatusID` | StockStatusID | KCZT01_SYS |
| `FSAL_OUTSTOCKENTRY_FOwnerTypeID` | OwnerTypeID | BD_OwnerOrg |
| `FSAL_OUTSTOCKENTRY_FOwnerID` | OwnerID | 102 |
| `FSAL_OUTSTOCKENTRY_FKeeperTypeID` | KeeperTypeID | BD_KeeperOrg |
| `FSAL_OUTSTOCKENTRY_FKeeperID` | KeeperID | 102 |
| `FSAL_OUTSTOCKENTRY_FNote` | 备注 |   |
| `FSAL_OUTSTOCKENTRY_FBomID` | BomID | - |
| `FSAL_OUTSTOCKENTRY_FBaseUnitQty` | 基本单位数量 | 133.0 |
| `FSAL_OUTSTOCKENTRY_FAuxUnitID` | AuxUnitID | - |
| `FSAL_OUTSTOCKENTRY_FAuxUnitQty` | AuxUnitQty | 0.0 |
| `FSAL_OUTSTOCKENTRY_FCostPrice` | CostPrice | 47.143775 |
| `FSAL_OUTSTOCKENTRY_FCostAmount` | CostAmount | 6270.12 |
| `FSAL_OUTSTOCKENTRY_FCostAmount_LC` | CostAmount_LC | 6270.12 |
| `FSAL_OUTSTOCKENTRY_FReturnQty` | ReturnQty | 0.0 |
| `FSAL_OUTSTOCKENTRY_FSumRetNoticeQty` | SumRetNoticeQty | 0.0 |
| `FSAL_OUTSTOCKENTRY_FSumRetStockQty` | SumRetStockQty | 0.0 |
| `FSAL_OUTSTOCKENTRY_FInvoicedQty` | InvoicedQty | 0.0 |
| `FSAL_OUTSTOCKENTRY_FSumInvoicedQty` | SumInvoicedQty | 133.0 |
| `FSAL_OUTSTOCKENTRY_FSumInvoicedAMT` | SumInvoicedAMT | 0.0 |
| `FSAL_OUTSTOCKENTRY_FSumReceivedAMT` | SumReceivedAMT | 0.0 |
| `FSAL_OUTSTOCKENTRY_FBaseReturnQty` | BaseReturnQty | 0.0 |
| `FSAL_OUTSTOCKENTRY_FBaseInvoicedQty` | BaseInvoicedQty | 0.0 |
| `FSAL_OUTSTOCKENTRY_FStockFlag` | StockFlag | true |
| `FSAL_OUTSTOCKENTRY_FSoorDerno` | SoorDerno |   |
| `FSAL_OUTSTOCKENTRY_FAuxPropId` | 辅助属性 | - |
| `FSAL_OUTSTOCKENTRY_FBaseSumRetNoticeQty` | BaseSumRetNoticeQty | 0.0 |
| `FSAL_OUTSTOCKENTRY_FSrcType` | SrcType |   |
| `FSAL_OUTSTOCKENTRY_FBaseSumRetstockQty` | BaseSumRetstockQty | 0.0 |
| `FSAL_OUTSTOCKENTRY_FStockLocID` | StockLocID | - |
| `FSAL_OUTSTOCKENTRY_FProduceDate` | 生产日期 | - |
| `FSAL_OUTSTOCKENTRY_FExpiryDate` | 有效期至 | - |
| `FSAL_OUTSTOCKENTRY_FJoinedQty` | JoinedQty | 0 |
| `FSAL_OUTSTOCKENTRY_FUnJoinQty` | UnJoinQty | 0 |
| `FSAL_OUTSTOCKENTRY_FJoinedAmount` | JoinedAmount | 0.0 |
| `FSAL_OUTSTOCKENTRY_FUnJoinAmount` | UnJoinAmount | 0.0 |
| `FSAL_OUTSTOCKENTRY_FullyJoined` | FullyJoined | false |
| `FSAL_OUTSTOCKENTRY_FJoinStatus` | JoinStatus |   |
| `FSAL_OUTSTOCKENTRY_FLot` | 批号 | 2411294 |
| `FSAL_OUTSTOCKENTRY_FLot_Text` | Lot_Text | 2411294 |
| `FSAL_OUTSTOCKENTRY_FIsFree` | IsFree | false |
| `FSAL_OUTSTOCKENTRY_FBaseSumInvoicedQty` | BaseSumInvoicedQty | 0.0 |
| `FSAL_OUTSTOCKENTRY_FBaseMustQty` | BaseMustQty | 0.0 |
| `FSAL_OUTSTOCKENTRY_FBaseUnitID` | BaseUnitID | 003 |
| `FSAL_OUTSTOCKENTRY_FArrivalStatus` | ArrivalStatus |   |
| `FSAL_OUTSTOCKENTRY_FArrivalConfirmor` | ArrivalConfirmor | - |
| `FSAL_OUTSTOCKENTRY_FValidateDate` | ValidateDate | - |
| `FSAL_OUTSTOCKENTRY_FValidateStatus` | ValidateStatus |   |
| `FSAL_OUTSTOCKENTRY_FValidateConfirmor` | ValidateConfirmor | - |
| `FSAL_OUTSTOCKENTRY_FPriceUnitId` | PriceUnitId | 003 |
| `FSAL_OUTSTOCKENTRY_FPriceUnitQty` | PriceUnitQty | 133.0 |
| `FSAL_OUTSTOCKENTRY_FPrice` | 单价 | 0.0 |
| `FSAL_OUTSTOCKENTRY_FTaxPrice` | 含税单价 | 0.0 |
| `FSAL_OUTSTOCKENTRY_FTaxCombination` | TaxCombination | - |
| `FSAL_OUTSTOCKENTRY_FTaxRate` | 税率 | 13.0 |
| `FSAL_OUTSTOCKENTRY_FPriceCoefficient` | PriceCoefficient | 1.0 |
| `FSAL_OUTSTOCKENTRY_FSysPrice` | SysPrice | 0.0 |
| `FSAL_OUTSTOCKENTRY_FLimitDownPrice` | LimitDownPrice | 0.0 |
| `FSAL_OUTSTOCKENTRY_FBefDisAmt` | BefDisAmt | 0.0 |
| `FSAL_OUTSTOCKENTRY_FBefDisAllAmt` | BefDisAllAmt | 0.0 |
| `FSAL_OUTSTOCKENTRY_FDiscountRate` | DiscountRate | 0.0 |
| `FSAL_OUTSTOCKENTRY_FDiscount` | Discount | 0.0 |
| `FSAL_OUTSTOCKENTRY_FAmount` | 金额 | 0.0 |
| `FSAL_OUTSTOCKENTRY_FAmount_LC` | Amount_LC | 0.0 |
| `FSAL_OUTSTOCKENTRY_FTaxAmount` | TaxAmount | 0.0 |
| `FSAL_OUTSTOCKENTRY_FTaxAmount_LC` | TaxAmount_LC | 0.0 |
| `FSAL_OUTSTOCKENTRY_FAllAmount` | AllAmount | 0.0 |
| `FSAL_OUTSTOCKENTRY_FAllAmount_LC` | AllAmount_LC | 0.0 |
| `FSAL_OUTSTOCKENTRY_FTaxNetPrice` | TaxNetPrice | 0.0 |
| `FSAL_OUTSTOCKENTRY_FBaseARJoinQty` | FBaseARJoinQty | 133.0 |
| `FSAL_OUTSTOCKENTRY_FArrivalDate` | ArrivalDate | - |
| `FSAL_OUTSTOCKENTRY_FBFLowId_Id` | FBFLowId_Id |   |
| `FSAL_OUTSTOCKENTRY_FBFLowId` | FBFLowId | - |
| `FSAL_OUTSTOCKENTRY_FBASEARQTY` | BASEARQTY | 133.0 |
| `FSAL_OUTSTOCKENTRY_FARJOINAMOUNT` | ARJOINAMOUNT | 14630.0 |
| `FSAL_OUTSTOCKENTRY_FARAMOUNT` | ARAMOUNT | 12946.9 |
| `FSAL_OUTSTOCKENTRY_FServiceContext` | ServiceContext | - |
| `FSAL_OUTSTOCKENTRY_FSalCostPrice` | SalCostPrice | 47.143759 |
| `FSAL_OUTSTOCKENTRY_FSrcBillNo` | 源单编号 |   |
| `FSAL_OUTSTOCKENTRY_FActQty` | ActQty | 0.0 |
| `FSAL_OUTSTOCKENTRY_FBaseJoinInStockQty` | BaseJoinInStockQty | 0.0 |
| `FSAL_OUTSTOCKENTRY_FJoinInStockQty` | JoinInStockQty | 0.0 |
| `FSAL_OUTSTOCKENTRY_FSNUnitID` | SNUnitID | - |
| `FSAL_OUTSTOCKENTRY_FSNQty` | SNQty | 0.0 |
| `FSAL_OUTSTOCKENTRY_FMTONO` | MTONO | 2411294 |
| `FSAL_OUTSTOCKENTRY_FProjectNo` | ProjectNo |   |
| `FSAL_OUTSTOCKENTRY_FRefuseQty` | RefuseQty | 0.0 |
| `FSAL_OUTSTOCKENTRY_FRepairQty` | RepairQty | 0.0 |
| `FSAL_OUTSTOCKENTRY_FIsRepair` | IsRepair | false |
| `FSAL_OUTSTOCKENTRY_FPickDeptId` | PickDeptId | - |
| `FSAL_OUTSTOCKENTRY_FSECJOININSTOCKQTY` | SECJOININSTOCKQTY | 0.0 |
| `FSAL_OUTSTOCKENTRY_FSECRETURNQTY` | SECRETURNQTY | 0.0 |
| `FSAL_OUTSTOCKENTRY_FIsConsumeSum` | IsConsumeSum | 0 |
| `FSAL_OUTSTOCKENTRY_FARJoinQty` | ARJoinQty | 133.0 |
| `FSAL_OUTSTOCKENTRY_FOUTCONTROL` | OUTCONTROL | false |
| `FSAL_OUTSTOCKENTRY_FExtAuxUnitId` | ExtAuxUnitId | - |
| `FSAL_OUTSTOCKENTRY_FExtAuxUnitQty` | ExtAuxUnitQty | 0.0 |
| `FSAL_OUTSTOCKENTRY_FBarcode` | FBarcode |   |
| `FSAL_OUTSTOCKENTRY_FProPrice` | FProPrice | 0.0 |
| `FSAL_OUTSTOCKENTRY_FProAmount` | FProAmount | 0.0 |
| `FSAL_OUTSTOCKENTRY_FRetailSaleProm` | FRetailSaleProm | false |
| `FSAL_OUTSTOCKENTRY_FInventoryQty` | InventoryQty | 0.0 |
| `FSAL_OUTSTOCKENTRY_FSalUnitId` | SalUnitId | 003 |
| `FSAL_OUTSTOCKENTRY_FSALUNITQTY` | SALUNITQTY | 133.0 |
| `FSAL_OUTSTOCKENTRY_FSALBASEQTY` | SALBASEQTY | 133.0 |
| `FSAL_OUTSTOCKENTRY_FPRICEBASEQTY` | PRICEBASEQTY | 133.0 |
| `FSAL_OUTSTOCKENTRY_FQualifyType` | QualifyType |   |
| `FSAL_OUTSTOCKENTRY_FSalBaseNum` | SalBaseNum | 0.0 |
| `FSAL_OUTSTOCKENTRY_FStockBaseDen` | StockBaseDen | 0.0 |
| `FSAL_OUTSTOCKENTRY_FStockBaseReturnQty` | StockBaseReturnQty | 0.0 |
| `FSAL_OUTSTOCKENTRY_FStockBaseSumRetStockQty` | StockBaseSumRetStockQty | 0.0 |
| `FSAL_OUTSTOCKENTRY_FStockBaseARJoinQty` | StockBaseARJoinQty | 133.0 |
| `FSAL_OUTSTOCKENTRY_FSRCBIZUNITID` | SRCBIZUNITID | - |
| `FSAL_OUTSTOCKENTRY_FIsCreateProDoc` | IsCreateProDoc |   |
| `FSAL_OUTSTOCKENTRY_FEOwnerSupplierId` | EOwnerSupplierId | 07.0002 |
| `FSAL_OUTSTOCKENTRY_FIsOverLegalOrg` | IsOverLegalOrg | false |
| `FSAL_OUTSTOCKENTRY_FESettleCustomerId` | ESettleCustomerId | - |
| `FSAL_OUTSTOCKENTRY_FSalBaseARJoinQty` | SalBaseARJoinQty | 133.0 |
| `FSAL_OUTSTOCKENTRY_FPURBASEJOININSTOCKQTY` | PURBASEJOININSTOCKQTY | 0.0 |
| `FSAL_OUTSTOCKENTRY_FPriceListEntry` | PriceListEntry | - |
| `FSAL_OUTSTOCKENTRY_FARNOTJOINQTY` | ARNOTJOINQTY | 0.0 |
| `FSAL_OUTSTOCKENTRY_FQmEntryID` | QmEntryID | 0 |
| `FSAL_OUTSTOCKENTRY_FConvertEntryID` | ConvertEntryID | 0 |
| `FSAL_OUTSTOCKENTRY_FB2CORDERDETAILID` | B2CORDERDETAILID | 0 |
| `FSAL_OUTSTOCKENTRY_FSOEntryId` | SOEntryId | 0 |
| `FSAL_OUTSTOCKENTRY_FReserveEntryId` | ReserveEntryId | 0 |
| `FSAL_OUTSTOCKENTRY_FDisPriceQty` | DisPriceQty | 0.0 |
| `FSAL_OUTSTOCKENTRY_FBeforeDisPriceQty` | BeforeDisPriceQty | 0.0 |
| `FSAL_OUTSTOCKENTRY_FRowType` | RowType | Standard |
| `FSAL_OUTSTOCKENTRY_FParentMatId` | ParentMatId | - |
| `FSAL_OUTSTOCKENTRY_FRowId` | RowId | d4f5ef8e-7b8f-8da0-11ef-b86efae7371e |
| `FSAL_OUTSTOCKENTRY_FParentRowId` | ParentRowId |   |
| `FSAL_OUTSTOCKENTRY_FSignQty` | SignQty | 0.0 |
| `FSAL_OUTSTOCKENTRY_FThirdEntryId` | ThirdEntryId |   |
| `FSAL_OUTSTOCKENTRY_FCheckDelivery` | CheckDelivery | false |
| `FSAL_OUTSTOCKENTRY_FETHIRDBILLID` | FETHIRDBILLID |   |
| `FSAL_OUTSTOCKENTRY_FETHIRDBILLNO` | FETHIRDBILLNO |   |
| `FSAL_OUTSTOCKENTRY_FGYFINSTATUS` | FGYFINSTATUS | false |
| `FSAL_OUTSTOCKENTRY_FGYFINDate` | FGYFINDate | - |
| `FSAL_OUTSTOCKENTRY_FPriceDiscount` | PriceDiscount | 0.0 |
| `FSAL_OUTSTOCKENTRY_FTailDiffFlag` | TailDiffFlag | false |
| `FSAL_OUTSTOCKENTRY_FWRITEOFFPRICEBASEQTY` | WRITEOFFPRICEBASEQTY | 0.0 |
| `FSAL_OUTSTOCKENTRY_FWRITEOFFSALEBASEQTY` | WRITEOFFSALEBASEQTY | 0.0 |
| `FSAL_OUTSTOCKENTRY_FWRITEOFFSTOCKBASEQTY` | WRITEOFFSTOCKBASEQTY | 0.0 |
| `FSAL_OUTSTOCKENTRY_FWRITEOFFAMOUNT` | WRITEOFFAMOUNT | 0.0 |
| `FSAL_OUTSTOCKENTRY_FSettleBySon` | SettleBySon | false |
| `FSAL_OUTSTOCKENTRY_FBOMEntryId` | BOMEntryId | 0 |
| `FSAL_OUTSTOCKENTRY_FAllAmountExceptDisCount` | AllAmountExceptDisCount | 0.0 |
| `FSAL_OUTSTOCKENTRY_FLotPickFlag` | FLotPickFlag | 0 |
| `FSAL_OUTSTOCKENTRY_FGYENTERTIME` | FGYENTERTIME | - |
| `FSAL_OUTSTOCKENTRY_FMaterialxID_Sal` | MaterialxID_Sal | 27.09.02.03.01 |
| `FSAL_OUTSTOCKENTRY_FInStockBillno` | InStockBillno |   |
| `FSAL_OUTSTOCKENTRY_FInStockEntryId` | InStockEntryId | 0 |
| `FSAL_OUTSTOCKENTRY_FVmiBusinessStatus` | VmiBusinessStatus | false |
| `FSAL_OUTSTOCKENTRY_FReceiveBillno` | ReceiveBillno |   |
| `FSAL_OUTSTOCKENTRY_FReceiveEntryId` | ReceiveEntryId | 0 |
| `FSAL_OUTSTOCKENTRY_FIsReplaceOut` | IsReplaceOut | false |
| `FSAL_OUTSTOCKENTRY_FReplaceMaterialID` | ReplaceMaterialID | - |
| `FSAL_OUTSTOCKENTRY_FRowARStatus` | RowARStatus | C |
| `FSAL_OUTSTOCKENTRY_FApAmount` | ApAmount | 0.0 |
| `FSAL_OUTSTOCKENTRY_FApAmountLC` | ApAmountLC | 0.0 |
| `FSAL_OUTSTOCKENTRY_F_QWJI_ddh_Id` | F_QWJI_ddh_Id | 0 |
| `FSAL_OUTSTOCKENTRY_F_QWJI_ddh` | F_QWJI_ddh | - |
| `FSAL_OUTSTOCKENTRY_F_QWJI_DJ` | F_QWJI_DJ | 0.0 |
| `FSAL_OUTSTOCKENTRY_F_QWJI_JSKC` | F_QWJI_JSKC | 0.0 |

## 三、常用查询示例

```python
# 根据计划跟踪号查询销售出库单
query_para = {
    "FormId": "SAL_OUTSTOCK",
    "FieldKeys": "FBillNo,FId,FSAL_OUTSTOCKENTRY_FMaterialId.FNumber,FSAL_OUTSTOCKENTRY_FMaterialId.FName,FSAL_OUTSTOCKENTRY_FQty",
    "FilterString": "FSAL_OUTSTOCKENTRY_FMTONo='AS251008'",
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
