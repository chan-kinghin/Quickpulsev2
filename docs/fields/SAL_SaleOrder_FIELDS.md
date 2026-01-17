# 销售订单 (SAL_SaleOrder) 字段清单

## 一、单据头字段

| 查询字段名 | 说明 | 示例值 |
|-----------|------|--------|
| `FId` | 单据内码 | 100030 |
| `FBillNo` | 单据编号 | AS2501001 |
| `FDocumentStatus` | 单据状态 | C |
| `FSaleOrgId` | 销售组织 | 105 |
| `FDate` | 日期 | 2025-01-02T00:00:00 |
| `FCustId` | 客户 | 178-1 |
| `FSaleDeptId` | 销售部门 | BM03 |
| `FSaleGroupId` | SaleGroupId | - |
| `FSalerId` | 销售员 | 01900_GW000012_100278 |
| `FReceiveId` | ReceiveId | 178-1 |
| `FSettleId` | SettleId | 178-1 |
| `FChargeId` | ChargeId | 178-1 |
| `FCreatorId` | 创建人 | (object) |
| `FCreateDate` | 创建日期 | 2025-01-02T14:49:44.537 |
| `FModifierId` | 修改人 | (object) |
| `FMOdifyDate` | MOdifyDate | 2025-01-09T12:00:45.053 |
| `FApproverId` | 审核人 | (object) |
| `FApproveDate` | 审核日期 | 2025-01-09T13:43:06.013 |
| `FCloseStatus` | CloseStatus | A |
| `FCloserId` | CloserId | - |
| `FCloseDate` | CloseDate | - |
| `FCancelStatus` | CancelStatus | A |
| `FCancellerId` | CancellerId | - |
| `FCancelDate` | 作废日期 | - |
| `FVersionNo` | VersionNo | 000 |
| `FChangerId` | ChangerId | - |
| `FChangeDate` | ChangeDate | - |
| `FChangeReason` | ChangeReason |   |
| `FBillTypeId` | BillTypeId | XSDD011_SYS |
| `FBusinessType` | BusinessType | NORMAL |
| `FHeadDeliveryWay` | HeadDeliveryWay | - |
| `FReceiveAddress` | ReceiveAddress |   |
| `FHeadLocId` | HeadLocId | - |
| `FCreditCheckResult` | CreditCheckResult | 0 |
| `FCorrespondOrgId` | CorrespondOrgId | - |
| `FReceiveContact` | ReceiveContact | - |
| `FNetOrderBillNo` | NetOrderBillNo |   |
| `FNetOrderBillId` | NetOrderBillId | 0 |
| `FOppID` | OppID | 0 |
| `FSalePhaseID` | SalePhaseID | - |
| `FISINIT` | ISINIT | false |
| `FNote` | 备注 |   |
| `FIsMobile` | IsMobile | false |
| `FSignStatus` | SignStatus | A |
| `FIsDirectChange` | IsDirectChange | false |
| `FManualClose` | ManualClose | false |
| `FLinkMan` | FLinkMan |   |
| `FLinkPhone` | FLinkPhone |   |
| `FSOFrom` | SOFrom |   |
| `FContractType` | ContractType |   |
| `FContractId` | ContractId | 0 |
| `FIsUseOEMBomPush` | IsUseOEMBomPush | false |
| `FXPKID` | XPKID | 0 |
| `FCloseReason` | CloseReason |   |
| `FIsUseDrpSalePOPush` | IsUseDrpSalePOPush | false |
| `FIsCreateStraightOutIN` | IsCreateStraightOutIN | false |
| `FPRESETBASE1` | PRESETBASE1 | - |
| `FPRESETASSISTANT1` | PRESETASSISTANT1 | - |
| `FPRESETASSISTANT2` | PRESETASSISTANT2 | - |
| `FPRESETBASE2` | PRESETBASE2 | - |
| `FDispatchDate` | FDispatchDate | - |
| `F_QWJI_JHGZH` | F_QWJI_JHGZH | - |
| `FBOS_ConvertTakeDataInfo` | BOS_ConvertTakeDataInfo | - |

## 二、明细行字段 (SaleOrderEntry)

| 查询字段名 | 说明 | 示例值 |
|-----------|------|--------|
| `FSaleOrderEntry_FId` | 单据内码 | 100034 |
| `FSaleOrderEntry_FSeq` | 行号 | 1 |
| `FSaleOrderEntry_FMaterialId` | 物料 | 07.18.020 |
| `FSaleOrderEntry_FUnitId` | 单位 | Pcs |
| `FSaleOrderEntry_FPrice` | 单价 | 25.62 |
| `FSaleOrderEntry_FTaxPrice` | 含税单价 | 25.62 |
| `FSaleOrderEntry_FBomId` | BOM版本 | MS11P+SN01P |
| `FSaleOrderEntry_FPriceUnitId` | PriceUnitId | Pcs |
| `FSaleOrderEntry_FPriceUnitQty` | PriceUnitQty | 2400.0 |
| `FSaleOrderEntry_FPriceCoefficient` | PriceCoefficient | 0.0 |
| `FSaleOrderEntry_FDiscountRate` | DiscountRate | 0.0 |
| `FSaleOrderEntry_FDiscount` | Discount | 0.0 |
| `FSaleOrderEntry_FTaxRate` | 税率 | 0.0 |
| `FSaleOrderEntry_FTaxAmount` | TaxAmount | 0.0 |
| `FSaleOrderEntry_FAllAmount` | AllAmount | 61488.0 |
| `FSaleOrderEntry_FTaxNetPrice` | TaxNetPrice | 25.62 |
| `FSaleOrderEntry_FBaseUnitQty` | 基本单位数量 | 2400.0 |
| `FSaleOrderEntry_FDeliveryControl` | DeliveryControl | true |
| `FSaleOrderEntry_FDeliveryMaxQty` | DeliveryMaxQty | 2400.0 |
| `FSaleOrderEntry_FDeliveryMinQty` | DeliveryMinQty | 2400.0 |
| `FSaleOrderEntry_FTransportLeadTime1` | TransportLeadTime1 | 0 |
| `FSaleOrderEntry_FBefDisAllAmt` | BefDisAllAmt | 0.0 |
| `FSaleOrderEntry_FBefDisAmt` | BefDisAmt | 0.0 |
| `FSaleOrderEntry_FTaxAmount_LC` | TaxAmount_LC | 0.0 |
| `FSaleOrderEntry_FAmount_LC` | Amount_LC | 61488.0 |
| `FSaleOrderEntry_FAllAmount_LC` | AllAmount_LC | 61488.0 |
| `FSaleOrderEntry_FMrpCloseStatus` | MrpCloseStatus | A |
| `FSaleOrderEntry_FMrpFreezeStatus` | MrpFreezeStatus | A |
| `FSaleOrderEntry_FreezerId_Id` | FreezerId_Id | 0 |
| `FSaleOrderEntry_FreezerId` | FreezerId | - |
| `FSaleOrderEntry_FreezeDate` | FreezeDate | - |
| `FSaleOrderEntry_FMrpTerminateStatus` | MrpTerminateStatus | A |
| `FSaleOrderEntry_FTerminaterId` | TerminaterId | - |
| `FSaleOrderEntry_FTerminateDate` | TerminateDate | - |
| `FSaleOrderEntry_FBaseDeliJoinQty` | BaseDeliJoinQty | 0.0 |
| `FSaleOrderEntry_FDeliQty` | DeliQty | 0.0 |
| `FSaleOrderEntry_FStockOutQty` | StockOutQty | 0.0 |
| `FSaleOrderEntry_FRetNoticeQty` | RetNoticeQty | 0.0 |
| `FSaleOrderEntry_FReturnQty` | ReturnQty | 0.0 |
| `FSaleOrderEntry_FRemainOutQty` | RemainOutQty | 2400.0 |
| `FSaleOrderEntry_FBaseInvoiceJoinQty` | BaseInvoiceJoinQty | 0.0 |
| `FSaleOrderEntry_FInvoiceJoinQty` | InvoiceJoinQty | 0.0 |
| `FSaleOrderEntry_FInvoiceQty` | InvoiceQty | 0.0 |
| `FSaleOrderEntry_FInvoiceAmount` | InvoiceAmount | 0.0 |
| `FSaleOrderEntry_FReceiveAmount` | ReceiveAmount | 0.0 |
| `FSaleOrderEntry_FBasePurJoinQty` | BasePurJoinQty | 0.0 |
| `FSaleOrderEntry_FPurJoinQty` | PurJoinQty | 0.0 |
| `FSaleOrderEntry_FPurReqQty` | PurReqQty | 0.0 |
| `FSaleOrderEntry_FPurOrderQty` | PurOrderQty | 0.0 |
| `FSaleOrderEntry_FReceiptOrgId` | ReceiptOrgId | 105 |
| `FSaleOrderEntry_FSettleOrgId` | SettleOrgId | 105 |
| `FSaleOrderEntry_FAmount` | 金额 | 61488.0 |
| `FSaleOrderEntry_FNote` | 备注 |   |
| `FSaleOrderEntry_FQty` | 数量 | 2400.0 |
| `FSaleOrderEntry_FLimitDownPrice` | LimitDownPrice | 0.0 |
| `FSaleOrderEntry_FSysPrice` | SysPrice | 0.0 |
| `FSaleOrderEntry_FStockOrgId` | 库存组织 | 101 |
| `FSaleOrderEntry_FBaseStockOutQty` | BaseStockOutQty | 0.0 |
| `FSaleOrderEntry_FBaseDeliQty` | BaseDeliQty | 0.0 |
| `FSaleOrderEntry_FBaseRetNoticeQty` | BaseRetNoticeQty | 0.0 |
| `FSaleOrderEntry_FBaseReturnQty` | BaseReturnQty | 0.0 |
| `FSaleOrderEntry_FBasePurReqQty` | BasePurReqQty | 0.0 |
| `FSaleOrderEntry_FBasePurOrderQty` | BasePurOrderQty | 0.0 |
| `FSaleOrderEntry_FBaseUnitId` | 基本单位 | Pcs |
| `FSaleOrderEntry_FChangeFlag` | ChangeFlag |   |
| `FSaleOrderEntry_FMapId` | MapId | - |
| `FSaleOrderEntry_FOwnerTypeId` | OwnerTypeId | BD_OwnerOrg |
| `FSaleOrderEntry_FOwnerId` | 货主 | 101 |
| `FSaleOrderEntry_FIsFree` | IsFree | false |
| `FSaleOrderEntry_FLOCKQTY` | LOCKQTY | 0.0 |
| `FSaleOrderEntry_FLOCKFLAG` | FLOCKFLAG | false |
| `FSaleOrderEntry_FProduceDate` | 生产日期 | - |
| `FSaleOrderEntry_FExpiryDate` | 有效期至 | - |
| `FSaleOrderEntry_FExpUnit` | ExpUnit |   |
| `FSaleOrderEntry_FExpPeriod` | ExpPeriod | 0 |
| `FSaleOrderEntry_FTaxCombination` | TaxCombination | - |
| `FSaleOrderEntry_FLot` | 批号 | - |
| `FSaleOrderEntry_FLot_Text` | Lot_Text |   |
| `FSaleOrderEntry_FAuxPropId` | 辅助属性 | (object) |
| `FSaleOrderEntry_FReturnType` | ReturnType |   |
| `FSaleOrderEntry_FDeliveryDate` | 交货日期 | 2025-04-01T00:00:00 |
| `FSaleOrderEntry_FTransJoinQty` | TransJoinQty | 0.0 |
| `FSaleOrderEntry_FBaseTransJoinQty` | BaseTransJoinQty | 0.0 |
| `FSaleOrderEntry_FSrcType` | SrcType |   |
| `FSaleOrderEntry_FSrcBillNo` | 源单编号 |   |
| `FSaleOrderEntry_FBaseDeliveryMaxQty` | BaseDeliveryMaxQty | 2400.0 |
| `FSaleOrderEntry_FBaseDeliveryMinQty` | BaseDeliveryMinQty | 2400.0 |
| `FSaleOrderEntry_FOEMInStockJoinQty` | OEMInStockJoinQty | 0.0 |
| `FSaleOrderEntry_FBaseOEMInStockJoinQty` | BaseOEMInStockJoinQty | 0.0 |
| `FSaleOrderEntry_FBaseARJoinQty` | BaseARJoinQty | 0.0 |
| `FSaleOrderEntry_FInventoryQty` | InventoryQty | 0.0 |
| `FSaleOrderEntry_FBFLowId_Id` | FBFLowId_Id |   |
| `FSaleOrderEntry_FBFLowId` | FBFLowId | - |
| `FSaleOrderEntry_FBASEARQTY` | BASEARQTY | 0.0 |
| `FSaleOrderEntry_FARJOINAMOUNT` | ARJOINAMOUNT | 0.0 |
| `FSaleOrderEntry_FARAMOUNT` | ARAMOUNT | 0.0 |
| `FSaleOrderEntry_FBaseRemainOutQty` | BaseRemainOutQty | 2400.0 |
| `FSaleOrderEntry_FReBackQty` | ReBackQty | 0.0 |
| `FSaleOrderEntry_FBaseReBackQty` | BaseReBackQty | 0.0 |
| `FSaleOrderEntry_FARQTY` | ARQTY | 0.0 |
| `FSaleOrderEntry_FCanOutQty` | CanOutQty | 2400.0 |
| `FSaleOrderEntry_FBaseCanOutQty` | BaseCanOutQty | 2400.0 |
| `FSaleOrderEntry_FCanReturnQty` | CanReturnQty | 0.0 |
| `FSaleOrderEntry_FBaseCanReturnQty` | BaseCanReturnQty | 0.0 |
| `FSaleOrderEntry_FBASEAPQTY` | BASEAPQTY | 0.0 |
| `FSaleOrderEntry_FAPAMOUNT` | FAPAMOUNT | 0.0 |
| `FSaleOrderEntry_FMtoNo` | 计划跟踪号 | AK2412042-2 |
| `FSaleOrderEntry_FPriority` | Priority | 0 |
| `FSaleOrderEntry_FReserveType` | ReserveType | 3 |
| `FSaleOrderEntry_FMinPlanDeliveryDate` | MinPlanDeliveryDate | 2025-04-01T00:00:00 |
| `FSaleOrderEntry_FDeliveryStatus` | DeliveryStatus | A |
| `FSaleOrderEntry_FOldQty` | OldQty | 2400.0 |
| `FSaleOrderEntry_FPromotionMatchType` | PromotionMatchType |   |
| `FSaleOrderEntry_FPriceListEntry` | PriceListEntry | - |
| `FSaleOrderEntry_FAwaitQty` | AwaitQty | 0.0 |
| `FSaleOrderEntry_FAvailableQty` | AvailableQty | 0.0 |
| `FSaleOrderEntry_FSupplyOrgId` | SupplyOrgId | 101 |
| `FSaleOrderEntry_FNetOrderEntryId` | NetOrderEntryId | 0 |
| `FSaleOrderEntry_FPriceBaseQty` | PriceBaseQty | 2400.0 |
| `FSaleOrderEntry_FSetPriceUnitID` | SetPriceUnitID | - |
| `FSaleOrderEntry_FStockUnitID` | StockUnitID | Pcs |
| `FSaleOrderEntry_FStockQty` | StockQty | 2400.0 |
| `FSaleOrderEntry_FStockBaseQty` | StockBaseQty | 2400.0 |
| `FSaleOrderEntry_FStockBaseCanOutQty` | StockBaseCanOutQty | 2400.0 |
| `FSaleOrderEntry_FStockBaseCanReturnQty` | StockBaseCanReturnQty | 0.0 |
| `FSaleOrderEntry_FStockBaseARJoinQty` | StockBaseARJoinQty | 0.0 |
| `FSaleOrderEntry_FStockBaseTransJoinQty` | StockBaseTransJoinQty | 0.0 |
| `FSaleOrderEntry_FServiceContext` | ServiceContext | - |
| `FSaleOrderEntry_FStockBasePurJoinQty` | StockBasePurJoinQty | 0.0 |
| `FSaleOrderEntry_FSalBaseNum` | SalBaseNum | 0.0 |
| `FSaleOrderEntry_FStockBaseDen` | StockBaseDen | 0.0 |
| `FSaleOrderEntry_FSRCBIZUNITID` | SRCBIZUNITID | - |
| `FSaleOrderEntry_FPurBaseQty` | PurBaseQty | 0.0 |
| `FSaleOrderEntry_FPurUnitID` | PurUnitID | - |
| `FSaleOrderEntry_FPurQty` | PurQty | 0.0 |
| `FSaleOrderEntry_FSalBaseARJoinQty` | SalBaseARJoinQty | 0.0 |
| `FSaleOrderEntry_FSTOCKBASESTOCKOUTQTY` | STOCKBASESTOCKOUTQTY | 0.0 |
| `FSaleOrderEntry_FSTOCKBASEREBACKQTY` | STOCKBASEREBACKQTY | 0.0 |
| `FSaleOrderEntry_FOUTLMTUNIT` | OUTLMTUNIT | SAL |
| `FSaleOrderEntry_FOutLmtUnitID` | OutLmtUnitID | Pcs |
| `FSaleOrderEntry_FTRANSRETURNQTY` | TRANSRETURNQTY | 0.0 |
| `FSaleOrderEntry_FTRANSRETURNBASEQTY` | TRANSRETURNBASEQTY | 0.0 |
| `FSaleOrderEntry_FCONSIGNSETTQTY` | CONSIGNSETTQTY | 0.0 |
| `FSaleOrderEntry_FCONSIGNSETTBASEQTY` | CONSIGNSETTBASEQTY | 0.0 |
| `FSaleOrderEntry_FLeftQty` | LeftQty | 0.0 |
| `FSaleOrderEntry_FCurrentInventory` | CurrentInventory | 0.0 |
| `FSaleOrderEntry_FRowType` | RowType | Standard |
| `FSaleOrderEntry_FParentMatId` | ParentMatId | - |
| `FSaleOrderEntry_FRowId` | RowId | d4f5ef8e-7b8f-8da2-11ef-c8cd640176bb |
| `FSaleOrderEntry_FParentRowId` | ParentRowId |   |
| `FSaleOrderEntry_FInStockPrice` | InStockPrice | 0.0 |
| `FSaleOrderEntry_FSOStockId` | SOStockId | - |
| `FSaleOrderEntry_FSOStockLocalId` | SOStockLocalId | - |
| `FSaleOrderEntry_FPurPriceUnitId` | PurPriceUnitId | - |
| `FSaleOrderEntry_FISMRP` | FISMRP | true |
| `FSaleOrderEntry_FBarcode` | FBarcode |   |
| `FSaleOrderEntry_FBranchId_Id` | FBranchId_Id | 0 |
| `FSaleOrderEntry_FBranchId` | FBranchId | - |
| `FSaleOrderEntry_FRetailSaleProm` | FRetailSaleProm | false |
| `FSaleOrderEntry_FBASEFINARQTY` | BASEFINARQTY | 0.0 |
| `FSaleOrderEntry_FSALBASEFINARQTY` | SALBASEFINARQTY | 0.0 |
| `FSaleOrderEntry_FEntryDiscountList` | EntryDiscountList | - |
| `FSaleOrderEntry_FPriceDiscount` | PriceDiscount | 0.0 |
| `FSaleOrderEntry_FZHJStockQty` | ZHJStockQty | 0.0 |
| `FSaleOrderEntry_FSPMENTRYID` | SPMENTRYID |   |
| `FSaleOrderEntry_FSPMANDRPMCONTENT` | SPMANDRPMCONTENT |   |
| `FSaleOrderEntry_FTransReturnStockBaseQty` | TransReturnStockBaseQty | 0.0 |
| `FSaleOrderEntry_FTailDiffFlag` | TailDiffFlag | false |
| `FSaleOrderEntry_FOldTaxPrice` | OldTaxPrice | 0.0 |
| `FSaleOrderEntry_FOldAmount` | OldAmount | 0.0 |
| `FSaleOrderEntry_FOldAllAmount` | OldAllAmount | 0.0 |
| `FSaleOrderEntry_FOldDiscountRate` | OldDiscountRate | 0.0 |
| `FSaleOrderEntry_FOldDiscount` | OldDiscount | 0.0 |
| `FSaleOrderEntry_FRPAmount` | RPAmount | 0.0 |
| `FSaleOrderEntry_FAccountBalanceId` | AccountBalanceId | 0 |
| `FSaleOrderEntry_FBOMEntryId` | BOMEntryId | 0 |
| `FSaleOrderEntry_FRPDiscountRate` | FRPDiscountRate | 0.0 |
| `FSaleOrderEntry_FStockBaseOutJoinQty` | StockBaseOutJoinQty | 0.0 |
| `FSaleOrderEntry_FAllAmountExceptDisCount` | AllAmountExceptDisCount | 61488.0 |
| `FSaleOrderEntry_FIsSumQtyTag` | IsSumQtyTag | false |
| `FSaleOrderEntry_FMaterialGroup` | MaterialGroup | - |
| `FSaleOrderEntry_FXPKID` | XPKID | 0 |
| `FSaleOrderEntry_FMANUALROWCLOSE` | MANUALROWCLOSE | false |
| `FSaleOrderEntry_FMaterialGroupByMat` | MaterialGroupByMat | - |
| `FSaleOrderEntry_FISMRPCAL` | ISMRPCAL | true |
| `FSaleOrderEntry_FThirdPartyNo` | ThirdPartyNo |   |
| `FSaleOrderEntry_FThirdPartyId` | ThirdPartyId |   |
| `FSaleOrderEntry_FThirdPartyEntrySeq` | ThirdPartyEntrySeq | 0 |
| `FSaleOrderEntry_F_QWJI_WK` | F_QWJI_WK |   |
| `FSaleOrderEntry_F_QWJI_WLTP` | F_QWJI_WLTP |   |
| `FSaleOrderEntry_F_QWJI_DDH_Id` | F_QWJI_DDH_Id | 0 |
| `FSaleOrderEntry_F_QWJI_DDH` | F_QWJI_DDH | - |
| `FSaleOrderEntry_F_QWJI_PACKAGE` | F_QWJI_PACKAGE |   |
| `FSaleOrderEntry_F_QWJI_CARTON` | F_QWJI_CARTON |   |
| `FSaleOrderEntry_F_QWJI_BARCODE` | F_QWJI_BARCODE |   |
| `FSaleOrderEntry_F_QWJI_CTNQTY` | F_QWJI_CTNQTY | 0.0 |
| `FSaleOrderEntry_F_QWJI_CTNS` | F_QWJI_CTNS | 0.0 |
| `FSaleOrderEntry_F_QWJI_CBM` | F_QWJI_CBM | 0.0 |
| `FSaleOrderEntry_F_QWJI_Qty_qtr` | F_QWJI_Qty_qtr | 0.0 |
| `FSaleOrderEntry_F_QWJI_KJDJ` | F_QWJI_KJDJ | 0.0 |
| `FSaleOrderEntry_F_QWJI_JJDJ` | F_QWJI_JJDJ | 0.0 |
| `FSaleOrderEntry_F_QWJI_WXDJ` | F_QWJI_WXDJ | 0.0 |
| `FSaleOrderEntry_FCurrInventoryQty` | FCurrInventoryQty | 0.0 |

## 三、常用查询示例

```python
# 根据计划跟踪号查询销售订单
query_para = {
    "FormId": "SAL_SaleOrder",
    "FieldKeys": "FBillNo,FId,FSaleOrderEntry_FMaterialId.FNumber,FSaleOrderEntry_FMaterialId.FName,FSaleOrderEntry_FQty",
    "FilterString": "FSaleOrderEntry_FMTONo='AS251008'",
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
