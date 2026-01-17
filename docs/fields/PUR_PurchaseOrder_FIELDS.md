# 采购订单 (PUR_PurchaseOrder) 字段清单

## 一、单据头字段

| 查询字段名 | 说明 | 示例值 |
|-----------|------|--------|
| `FId` | 单据内码 | 101391 |
| `FBillNo` | 单据编号 | F2412390 |
| `FDocumentStatus` | 单据状态 | C |
| `FDate` | 日期 | 2024-12-09T00:00:00 |
| `FPurchaseOrgId` | 采购组织 | 102 |
| `FSupplierId` | 供应商 | 03.0827 |
| `FPurchaserGroupId` | PurchaserGroupId | - |
| `FPurchaseDeptId` | PurchaseDeptId | BM11 |
| `FCreatorId` | 创建人 | (object) |
| `FCreateDate` | 创建日期 | 2024-12-09T10:22:02.103 |
| `FModifierId` | 修改人 | (object) |
| `FModifyDate` | 修改日期 | 2024-12-23T16:50:01.487 |
| `FApproverId` | 审核人 | (object) |
| `FApproveDate` | 审核日期 | 2024-12-23T17:28:14.817 |
| `FCancellerId` | CancellerId | - |
| `FCancelDate` | 作废日期 | - |
| `FCancelStatus` | CancelStatus | A |
| `FCloseStatus` | CloseStatus | B |
| `FPurchaserId` | 采购员 | 00973 |
| `FCloserId` | CloserId | (object) |
| `FCloseDate` | CloseDate | 2024-12-24T09:04:26.53 |
| `FBillTypeId` | BillTypeId | CGDD01_SYS |
| `FSettleId` | SettleId | 03.0827 |
| `FChargeId` | ChargeId | 03.0827 |
| `FProviderId` | ProviderId | 03.0827 |
| `FChangerId` | ChangerId | - |
| `FVersionNo` | VersionNo | 000 |
| `FChangeDate` | ChangeDate | - |
| `FChangeReason` | ChangeReason |   |
| `FBusinessType` | BusinessType | CG |
| `FProviderAddress` | ProviderAddress |   |
| `FAssignSupplierId` | AssignSupplierId | - |
| `FCorrespondOrgId` | CorrespondOrgId | - |
| `FProviderContact` | ProviderContact |   |
| `FIsModificationOperator` | IsModificationOperator | false |
| `FNETORDERBILLNO` | NETORDERBILLNO |   |
| `FNetOrderBillId` | NetOrderBillId | 0 |
| `FConfirmStatus` | ConfirmStatus | A |
| `FConfirmerId` | ConfirmerId | - |
| `FConfirmDate` | ConfirmDate | - |
| `FProviderContactId` | ProviderContactId | - |
| `FSourceBillNo` | FSourceBillNo |   |
| `FChangeStatus` | ChangeStatus | A |
| `FACCTYPE` | FACCTYPE | Q |
| `FRelReqStatus` | FRelReqStatus | A |
| `FMANUALCLOSE` | MANUALCLOSE | false |
| `FProviderEMail` | ProviderEMail |   |
| `FCloseReason` | CloseReason |   |
| `FIsMobBill` | IsMobBill | false |
| `FIsUseDrpSalePOPush` | IsUseDrpSalePOPush | false |
| `FIsCreateStraightOutIN` | IsCreateStraightOutIN | false |
| `FContractType` | FContractType |   |
| `F_QWJI_SCCS_Id` | F_QWJI_SCCS_Id | 0 |
| `F_QWJI_SCCS` | F_QWJI_SCCS | - |
| `F_QWJI_FKTJ2_Id` | F_QWJI_FKTJ2_Id | 0 |
| `F_QWJI_FKTJ2` | F_QWJI_FKTJ2 | - |
| `F_QWJI_HTH` | F_QWJI_HTH | BJ2406192-A3 |
| `FBOS_ConvertTakeDataInfo` | BOS_ConvertTakeDataInfo | - |

## 二、明细行字段 (POOrderEntry)

| 查询字段名 | 说明 | 示例值 |
|-----------|------|--------|
| `FPOOrderEntry_FId` | 单据内码 | 109666 |
| `FPOOrderEntry_FSeq` | 行号 | 1 |
| `FPOOrderEntry_FMaterialId` | 物料 | 21.11.020.04 |
| `FPOOrderEntry_FQty` | 数量 | 150.0 |
| `FPOOrderEntry_FPrice` | 单价 | 180.79646 |
| `FPOOrderEntry_FDiscountRate` | DiscountRate | 0.0 |
| `FPOOrderEntry_FTaxRate` | 税率 | 13.0 |
| `FPOOrderEntry_FTaxNetPrice` | TaxNetPrice | 204.3 |
| `FPOOrderEntry_FAmount` | 金额 | 27119.47 |
| `FPOOrderEntry_FAllAmount` | AllAmount | 30645.0 |
| `FPOOrderEntry_FDiscount` | Discount | 0.0 |
| `FPOOrderEntry_FNote` | 备注 |   |
| `FPOOrderEntry_FReceiveQty` | ReceiveQty | 150.0 |
| `FPOOrderEntry_FStockInQty` | StockInQty | 150.0 |
| `FPOOrderEntry_FInvoiceQty` | InvoiceQty | 150.0 |
| `FPOOrderEntry_FInvoiceAmount` | InvoiceAmount | 0.0 |
| `FPOOrderEntry_FPayAmount` | PayAmount | 0.0 |
| `FPOOrderEntry_FPriceCoefficient` | PriceCoefficient | 1.0 |
| `FPOOrderEntry_FPriceUnitQty` | PriceUnitQty | 150.0 |
| `FPOOrderEntry_FRequireDeptId` | RequireDeptId | - |
| `FPOOrderEntry_FRequireStaffId` | RequireStaffId | - |
| `FPOOrderEntry_FLocationId_Id` | FLocationId_Id | 0 |
| `FPOOrderEntry_FLocationId` | FLocationId | - |
| `FPOOrderEntry_FLocationAddress` | LocationAddress |   |
| `FPOOrderEntry_FDeliveryControl` | DeliveryControl | false |
| `FPOOrderEntry_FDeliveryBeforeDays` | DeliveryBeforeDays | 0 |
| `FPOOrderEntry_FDeliveryDelayDays` | DeliveryDelayDays | 0 |
| `FPOOrderEntry_FTimeControl` | TimeControl | false |
| `FPOOrderEntry_FMRPFreezeStatus` | MRPFreezeStatus | A |
| `FPOOrderEntry_FMRPTerminateStatus` | MRPTerminateStatus | A |
| `FPOOrderEntry_FMRPCloseStatus` | MRPCloseStatus | B |
| `FPOOrderEntry_FSupplierLot` | SupplierLot |   |
| `FPOOrderEntry_FRemainReceiveQty` | RemainReceiveQty | 0.0 |
| `FPOOrderEntry_FRemainStockInQty` | RemainStockInQty | 0.0 |
| `FPOOrderEntry_FTaxPrice` | 含税单价 | 204.3 |
| `FPOOrderEntry_FTaxAmount` | TaxAmount | 3525.53 |
| `FPOOrderEntry_FreezerId_Id` | FreezerId_Id | 0 |
| `FPOOrderEntry_FreezerId` | FreezerId | - |
| `FPOOrderEntry_FreezeDate` | FreezeDate | - |
| `FPOOrderEntry_FTerminaterId` | TerminaterId | - |
| `FPOOrderEntry_FTerminateDate` | TerminateDate | - |
| `FPOOrderEntry_FReceiveOrgId` | ReceiveOrgId | 102 |
| `FPOOrderEntry_FRequireOrgId` | RequireOrgId | 102 |
| `FPOOrderEntry_FRowCost` | RowCost | 0.0 |
| `FPOOrderEntry_FPayOrgId` | PayOrgId | - |
| `FPOOrderEntry_FSettleOrgId` | SettleOrgId | 102 |
| `FPOOrderEntry_FProcesser` | Processer | - |
| `FPOOrderEntry_FSysPrice` | SysPrice | 0.0 |
| `FPOOrderEntry_FUpPrice` | UpPrice | 0.0 |
| `FPOOrderEntry_FDownPrice` | DownPrice | 0.0 |
| `FPOOrderEntry_FBillDisApportion` | BillDisApportion | 0.0 |
| `FPOOrderEntry_FPlanConfirm` | PlanConfirm | true |
| `FPOOrderEntry_FBomId` | BOM版本 | - |
| `FPOOrderEntry_FMrbQty` | MrbQty | 0.0 |
| `FPOOrderEntry_FChangeFlag` | ChangeFlag | N |
| `FPOOrderEntry_FAmount_LC` | Amount_LC | 27119.47 |
| `FPOOrderEntry_FAllAmount_LC` | AllAmount_LC | 30645.0 |
| `FPOOrderEntry_FTaxAmount_LC` | TaxAmount_LC | 3525.53 |
| `FPOOrderEntry_FBaseAPJoinQty` | BaseAPJoinQty | 150.0 |
| `FPOOrderEntry_FDeliveryStockStatus` | DeliveryStockStatus | KCZT02_SYS |
| `FPOOrderEntry_FUnitId` | 单位 | 021 |
| `FPOOrderEntry_FPriceUnitId` | PriceUnitId | 021 |
| `FPOOrderEntry_FBaseUnitId` | 基本单位 | 021 |
| `FPOOrderEntry_FBASEMRBQTY` | BASEMRBQTY | 0.0 |
| `FPOOrderEntry_FBASERECEIVEQTY` | BASERECEIVEQTY | 150.0 |
| `FPOOrderEntry_FBASESTOCKINQTY` | BASESTOCKINQTY | 150.0 |
| `FPOOrderEntry_FJOINQTY` | JOINQTY | 150.0 |
| `FPOOrderEntry_FBaseJoinQty` | BaseJoinQty | 150.0 |
| `FPOOrderEntry_FAuxPropId` | 辅助属性 | - |
| `FPOOrderEntry_FContractNo` | ContractNo |   |
| `FPOOrderEntry_FReqTraceNo` | ReqTraceNo |   |
| `FPOOrderEntry_FSrcBillTypeId` | SrcBillTypeId |   |
| `FPOOrderEntry_FSrcBillNo` | 源单编号 |   |
| `FPOOrderEntry_FTaxCombination_Id` | FTaxCombination_Id | 0 |
| `FPOOrderEntry_FTaxCombination` | FTaxCombination | - |
| `FPOOrderEntry_FLot_Id` | 批号 | 0 |
| `FPOOrderEntry_FLot` | 批号 | - |
| `FPOOrderEntry_FLot_Text` | FLot_Text |   |
| `FPOOrderEntry_FDeliveryMaxQty` | DeliveryMaxQty | 150.0 |
| `FPOOrderEntry_FDeliveryMinQty` | DeliveryMinQty | 150.0 |
| `FPOOrderEntry_FLocation` | Location |   |
| `FPOOrderEntry_FDeliveryLastDate` | DeliveryLastDate | 2024-12-23T23:59:59 |
| `FPOOrderEntry_FDeliveryEarlyDate` | DeliveryEarlyDate | 2024-12-23T16:48:17.27 |
| `FPOOrderEntry_FBaseDeliveryMaxQty` | BaseDeliveryMaxQty | 150.0 |
| `FPOOrderEntry_FBaseDeliveryMinQty` | BaseDeliveryMinQty | 150.0 |
| `FPOOrderEntry_FBaseUnitQty` | 基本单位数量 | 150.0 |
| `FPOOrderEntry_FInventoryQty` | InventoryQty | 0.0 |
| `FPOOrderEntry_FProductType` | ProductType | 1 |
| `FPOOrderEntry_FCopyEntryId` | CopyEntryId | 0 |
| `FPOOrderEntry_FRowId` | RowId |   |
| `FPOOrderEntry_FParentRowId` | ParentRowId |   |
| `FPOOrderEntry_FGroup` | Group | 0 |
| `FPOOrderEntry_FBASECHECKRETQTY` | BASECHECKRETQTY | 0.0 |
| `FPOOrderEntry_FBASESTOCKRETQTY` | BASESTOCKRETQTY | 150.0 |
| `FPOOrderEntry_FCHECKRETQTY` | CHECKRETQTY | 0.0 |
| `FPOOrderEntry_FSTOCKRETQTY` | STOCKRETQTY | 150.0 |
| `FPOOrderEntry_FBFLowId_Id` | FBFLowId_Id |   |
| `FPOOrderEntry_FBFLowId` | FBFLowId | - |
| `FPOOrderEntry_FSupMatId` | SupMatId |   |
| `FPOOrderEntry_FSupMatName` | SupMatName |   |
| `FPOOrderEntry_FEntrySettleModeId` | EntrySettleModeId | - |
| `FPOOrderEntry_FDeliveryDate` | 交货日期 | 2024-12-23T16:48:17.27 |
| `FPOOrderEntry_FMtoNo` | 计划跟踪号 | 2406192-A2 |
| `FPOOrderEntry_FGiveAway` | GiveAway | false |
| `FPOOrderEntry_FCentSettleOrgId` | CentSettleOrgId | - |
| `FPOOrderEntry_FDispSettleOrgId` | DispSettleOrgId | - |
| `FPOOrderEntry_FAPJoinAmount` | APJoinAmount | 30645.0 |
| `FPOOrderEntry_FChargeProjectID` | ChargeProjectID | - |
| `FPOOrderEntry_FReceiveDeptId` | ReceiveDeptId | - |
| `FPOOrderEntry_FMaxPrice` | MaxPrice | 0.0 |
| `FPOOrderEntry_FMinPrice` | MinPrice | 0.0 |
| `FPOOrderEntry_FIsStock` | IsStock | true |
| `FPOOrderEntry_FConsumeSumQty` | ConsumeSumQty | 0.0 |
| `FPOOrderEntry_FBaseConsumeSumQty` | FBaseConsumeSumQty | 0.0 |
| `FPOOrderEntry_FBaseSalJoinQty` | BaseSalJoinQty | 0.0 |
| `FPOOrderEntry_FSalJoinQty` | SalJoinQty | 0.0 |
| `FPOOrderEntry_FNetOrderEntryId` | NetOrderEntryId | 0 |
| `FPOOrderEntry_FPriceBaseQty` | PriceBaseQty | 150.0 |
| `FPOOrderEntry_FSetPriceUnitID` | SetPriceUnitID | - |
| `FPOOrderEntry_FSalUnitID` | SalUnitID | 021 |
| `FPOOrderEntry_FSalQty` | SalQty | 150.0 |
| `FPOOrderEntry_FSalBaseQty` | SalBaseQty | 150.0 |
| `FPOOrderEntry_FStockUnitID` | StockUnitID | 021 |
| `FPOOrderEntry_FStockQty` | StockQty | 150.0 |
| `FPOOrderEntry_FStockBaseQty` | StockBaseQty | 150.0 |
| `FPOOrderEntry_FSRCBIZUNITID` | SRCBIZUNITID | - |
| `FPOOrderEntry_FPurBaseNum` | PurBaseNum | 0.0 |
| `FPOOrderEntry_FStockBaseDen` | StockBaseDen | 0.0 |
| `FPOOrderEntry_FSTOCKJOINBASEQTY` | STOCKJOINBASEQTY | 150.0 |
| `FPOOrderEntry_FStockBaseSalJoinQty` | StockBaseSalJoinQty | 0.0 |
| `FPOOrderEntry_FStockBaseAPJoinQty` | StockBaseAPJoinQty | 150.0 |
| `FPOOrderEntry_FSTOCKBASESTOCKINQTY` | STOCKBASESTOCKINQTY | 150.0 |
| `FPOOrderEntry_FPriceListEntry` | PriceListEntry | - |
| `FPOOrderEntry_FSubOrgId` | SubOrgId | - |
| `FPOOrderEntry_FIsQuota` | IsQuota | false |
| `FPOOrderEntry_FDEMANDTYPE` | DEMANDTYPE |   |
| `FPOOrderEntry_FDEMANDBILLNO` | DEMANDBILLNO |   |
| `FPOOrderEntry_FDEMANDBILLENTRYSEQ` | DEMANDBILLENTRYSEQ | 0 |
| `FPOOrderEntry_FDEMANDBILLENTRYID` | DEMANDBILLENTRYID | 0 |
| `FPOOrderEntry_FRowType` | RowType | Standard |
| `FPOOrderEntry_FPARENTMATID` | PARENTMATID | - |
| `FPOOrderEntry_FPARENTBOMID` | PARENTBOMID | - |
| `FPOOrderEntry_FPriceDiscount` | PriceDiscount | 0.0 |
| `FPOOrderEntry_FPRILSTENTRYID` | PRILSTENTRYID | 0 |
| `FPOOrderEntry_FBarcode` | FBarcode |   |
| `FPOOrderEntry_FBranchId_Id` | FBranchId_Id | 0 |
| `FPOOrderEntry_FBranchId` | FBranchId | - |
| `FPOOrderEntry_FBASEFINAPQTY` | BASEFINAPQTY | 0.0 |
| `FPOOrderEntry_FBASECHECKCUTPAYQTY` | BASECHECKCUTPAYQTY | 0.0 |
| `FPOOrderEntry_FSAMPLEDAMAGEBASEQTY` | SAMPLEDAMAGEBASEQTY | 0.0 |
| `FPOOrderEntry_FSUMACCALLAMOUNT` | SUMACCALLAMOUNT | 0.0 |
| `FPOOrderEntry_FSUMACCRATE` | SUMACCRATE | 0.0 |
| `FPOOrderEntry_FSTOCKBASEFINAPQTY` | STOCKBASEFINAPQTY | 0.0 |
| `FPOOrderEntry_FTailDiffFlag` | TailDiffFlag | false |
| `FPOOrderEntry_FAllAmountExceptDisCount` | AllAmountExceptDisCount | 30645.0 |
| `FPOOrderEntry_FInqueryGetId` | InqueryGetId | 0 |
| `FPOOrderEntry_FWBADUBASEPURQTY` | WBADUBASEPURQTY | 0.0 |
| `FPOOrderEntry_FWBADUBASESTOCKQTY` | WBADUBASESTOCKQTY | 0.0 |
| `FPOOrderEntry_FWWPickMtlQty` | WWPickMtlQty | 0.0 |
| `FPOOrderEntry_FMYDAMAGESAMPLEBASEQTY` | MYDAMAGESAMPLEBASEQTY | 0.0 |
| `FPOOrderEntry_FSUBREQBILLNO` | SUBREQBILLNO |   |
| `FPOOrderEntry_FSUBREQBILLSEQ` | SUBREQBILLSEQ | 0 |
| `FPOOrderEntry_FSUBREQENTRYID` | SUBREQENTRYID | 0 |
| `FPOOrderEntry_FRepOldMaterialNumber` | RepOldMaterialNumber |   |
| `FPOOrderEntry_FIsRepMaterial` | IsRepMaterial | false |
| `FPOOrderEntry_FINSTOCKENTRYID` | INSTOCKENTRYID | 0 |
| `FPOOrderEntry_FOrderExecAllamount` | OrderExecAllamount | 0.0 |
| `FPOOrderEntry_FOrderExecAmount` | OrderExecAmount | 0.0 |
| `FPOOrderEntry_FWbAduExecAllamount` | WbAduExecAllamount | 0.0 |
| `FPOOrderEntry_FWbAduExecAmount` | WbAduExecAmount | 0.0 |
| `FPOOrderEntry_FOrderJoinAllamount` | OrderJoinAllamount | 0.0 |
| `FPOOrderEntry_FOrderJoinAmount` | OrderJoinAmount | 0.0 |
| `FPOOrderEntry_FStockId` | 仓库 | - |
| `FPOOrderEntry_FStockLocId` | 仓位 | - |
| `FPOOrderEntry_F_QWJI_JHZT` | F_QWJI_JHZT |   |
| `FPOOrderEntry_F_QWJI_Remarks_qtr` | F_QWJI_Remarks_qtr | - |
| `FPOOrderEntry_F_QWJI_Remarks_83g` | F_QWJI_Remarks_83g | - |
| `FPOOrderEntry_F_QWJI_Picture_re5` | F_QWJI_Picture_re5 | - |
| `FPOOrderEntry_F_QWJI_Picture_apv` | F_QWJI_Picture_apv | - |
| `FPOOrderEntry_F_QWJI_Picture_tzk` | F_QWJI_Picture_tzk | - |
| `FPOOrderEntry_F_QWJI_Attachments_ca9` | F_QWJI_Attachments_ca9 | - |
| `FPOOrderEntry_F_QWJI_JSKC` | F_QWJI_JSKC | 0.0 |
| `FPOOrderEntry_F_QWJI_GGBC` | F_QWJI_GGBC | - |

## 三、常用查询示例

```python
# 根据计划跟踪号查询采购订单
query_para = {
    "FormId": "PUR_PurchaseOrder",
    "FieldKeys": "FBillNo,FId,FPOOrderEntry_FMaterialId.FNumber,FPOOrderEntry_FMaterialId.FName,FPOOrderEntry_FQty",
    "FilterString": "FPOOrderEntry_FMTONo='AS251008'",
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
