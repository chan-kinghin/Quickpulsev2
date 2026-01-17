# 委外申请订单 (SUB_SUBREQORDER) 字段清单

## 一、单据头字段

| 查询字段名 | 说明 | 示例值 |
|-----------|------|--------|
| `FId` | 单据内码 | 100001 |
| `FBillNo` | 单据编号 | SUB00000001 |
| `FDocumentStatus` | 单据状态 | C |
| `FApproverId` | 审核人 | (object) |
| `FApproveDate` | 审核日期 | 2024-12-16T10:03:18.807 |
| `FModifierId` | 修改人 | (object) |
| `FCreateDate` | 创建日期 | 2024-12-16T10:03:13.28 |
| `FCreatorId` | 创建人 | (object) |
| `FModifyDate` | 修改日期 | 2024-12-16T10:03:18.91 |
| `FCancelDate` | 作废日期 | - |
| `FCANCELER` | CANCELER | - |
| `FCancelStatus` | CancelStatus | A |
| `FSubOrgId` | SubOrgId | 102 |
| `FOwnerTypeId` | OwnerTypeId | BD_OwnerOrg |
| `FOwnerId` | 货主 | - |
| `FPlannerID` | PlannerID | - |
| `FDate` | 日期 | 2024-12-13T00:00:00 |
| `FBillType` | BillType | WWDD01_SYS |
| `FWorkGroupId` | WorkGroupId | - |
| `FIsRework` | IsRework | false |
| `FIsQCSub` | IsQCSub | false |
| `FPPBOMType` | PPBOMType | 1 |
| `FBOS_ConvertTakeDataInfo` | BOS_ConvertTakeDataInfo | - |

## 二、明细行字段 (TreeEntity)

| 查询字段名 | 说明 | 示例值 |
|-----------|------|--------|
| `FTreeEntity_FId` | 单据内码 | 100001 |
| `FTreeEntity_FSeq` | 行号 | 1 |
| `FTreeEntity_FParentRowId` | ParentRowId |   |
| `FTreeEntity_FRowExpandType` | RowExpandType | 0 |
| `FTreeEntity_FRowId` | RowId | d4f5ef8e-7b8f-8da0-11ef-bb51886a0d55 |
| `FTreeEntity_FMaterialId` | 物料 | 28.03.01.01.002.001.24 |
| `FTreeEntity_FProductType` | ProductType | 1 |
| `FTreeEntity_FUnitId` | 单位 | 003 |
| `FTreeEntity_FQty` | 数量 | 470.0 |
| `FTreeEntity_FPlanStartDate` | PlanStartDate | 2024-12-16T00:00:00 |
| `FTreeEntity_FPlanFinishDate` | PlanFinishDate | 2024-12-16T00:00:00 |
| `FTreeEntity_FBomId` | BOM版本 | - |
| `FTreeEntity_FSupplierId` | 供应商 | - |
| `FTreeEntity_FStatus` | 状态 | 3 |
| `FTreeEntity_FRequestOrgId` | RequestOrgId | 102 |
| `FTreeEntity_FRoutingId` | RoutingId | - |
| `FTreeEntity_FYieldRate` | YieldRate | 100.0 |
| `FTreeEntity_FStockInLimitH` | StockInLimitH | 470.0 |
| `FTreeEntity_FStockInLimitL` | StockInLimitL | 470.0 |
| `FTreeEntity_FStockID` | StockID | 05.05 |
| `FTreeEntity_FStockLOCID` | StockLOCID | - |
| `FTreeEntity_FAuxPropID` | AuxPropID | - |
| `FTreeEntity_Fmtono` | mtono |   |
| `FTreeEntity_FProjectNo` | ProjectNo |   |
| `FTreeEntity_FOperId` | OperId | 0 |
| `FTreeEntity_FProcessId` | ProcessId | - |
| `FTreeEntity_FCostRate` | CostRate | 100.0 |
| `FTreeEntity_FPlanConfirmDate` | PlanConfirmDate | 2024-12-16T10:03:18 |
| `FTreeEntity_FConveyDate` | ConveyDate | 2024-12-16T10:08:59 |
| `FTreeEntity_FinishDate` | FinishDate | - |
| `FTreeEntity_FCloseDate` | CloseDate | - |
| `FTreeEntity_FCostDate` | CostDate | - |
| `FTreeEntity_FStockInQty` | StockInQty | 0.0 |
| `FTreeEntity_FPurSelQty` | PurSelQty | 0.0 |
| `FTreeEntity_FPurQty` | PurQty | 0.0 |
| `FTreeEntity_FCreateType` | CreateType | 1 |
| `FTreeEntity_FGroup` | Group | 1 |
| `FTreeEntity_FSrcBillId` | SrcBillId | 0 |
| `FTreeEntity_FSrcBillEntrySeq` | SrcBillEntrySeq | 0 |
| `FTreeEntity_FSrcBillEntryId` | SrcBillEntryId | 0 |
| `FTreeEntity_FSaleOrderId` | SaleOrderId | 0 |
| `FTreeEntity_FSALEORDERNO` | SALEORDERNO |   |
| `FTreeEntity_FSaleOrderEntrySeq` | SaleOrderEntrySeq | 0 |
| `FTreeEntity_FSaleOrderEntryId` | SaleOrderEntryId | 0 |
| `FTreeEntity_FPurOrderId` | PurOrderId | 0 |
| `FTreeEntity_FPurOrderNo` | PurOrderNo | - |
| `FTreeEntity_FPurOrderEntrySeq` | PurOrderEntrySeq | 0 |
| `FTreeEntity_FBaseUnitId` | 基本单位 | 003 |
| `FTreeEntity_FStockInOrgId` | StockInOrgId | 102 |
| `FTreeEntity_FPurOrderEntryId` | PurOrderEntryId | 0 |
| `FTreeEntity_FBaseUnitQty` | 基本单位数量 | 470.0 |
| `FTreeEntity_FBaseStockInLimitH` | BaseStockInLimitH | 470.0 |
| `FTreeEntity_FBaseStockInLimitL` | BaseStockInLimitL | 470.0 |
| `FTreeEntity_FBaseStockInQty` | BaseStockInQty | 0.0 |
| `FTreeEntity_FBasePurSelQty` | BasePurSelQty | 0.0 |
| `FTreeEntity_FSrcBillType` | 源单类型 |   |
| `FTreeEntity_FSrcBillNo` | 源单编号 |   |
| `FTreeEntity_FLot` | 批号 | - |
| `FTreeEntity_FLot_Text` | Lot_Text |   |
| `FTreeEntity_FPurorgId` | PurorgId | 102 |
| `FTreeEntity_FCopyEntryId` | CopyEntryId | 0 |
| `FTreeEntity_FBasePurQty` | BasePurQty | 0.0 |
| `FTreeEntity_FBFLowId` | BFLowId | 委外申请采购流程 |
| `FTreeEntity_FPriority` | Priority | 0 |
| `FTreeEntity_FSettleOrgId` | SettleOrgId | 102 |
| `FTreeEntity_FInStockOwnerTypeId` | InStockOwnerTypeId | BD_OwnerOrg |
| `FTreeEntity_FInStockOwnerId` | InStockOwnerId | 102 |
| `FTreeEntity_FBaseYieldQty` | BaseYieldQty | 470.0 |
| `FTreeEntity_FYieldQty` | YieldQty | 470.0 |
| `FTreeEntity_FSampleDamageQty` | SampleDamageQty | 0.0 |
| `FTreeEntity_FBaseSampleDamageQty` | BaseSampleDamageQty | 0.0 |
| `FTreeEntity_FStockReadyqty` | StockReadyqty | 0.0 |
| `FTreeEntity_FBaseStockReadyqty` | BaseStockReadyqty | 0.0 |
| `FTreeEntity_FReqSrc` | ReqSrc |   |
| `FTreeEntity_FBaseNoStockInQty` | BaseNoStockInQty | 470.0 |
| `FTreeEntity_FNoStockInQty` | NoStockInQty | 470.0 |
| `FTreeEntity_FIsSuspend` | IsSuspend | 0 |
| `FTreeEntity_FBasePickMtlQty` | BasePickMtlQty | 0.0 |
| `FTreeEntity_FPickMtlQty` | PickMtlQty | 0.0 |
| `FTreeEntity_FISNEWLC` | ISNEWLC | 0 |
| `FTreeEntity_FPickMtrlStatus` | PickMtrlStatus | 1 |
| `FTreeEntity_FSrcSplitBillNo` | SrcSplitBillNo |   |
| `FTreeEntity_FSrcSplitSeq` | SrcSplitSeq | 0 |
| `FTreeEntity_FSrcSplitEntryId` | SrcSplitEntryId | 0 |
| `FTreeEntity_FSrcSplitId` | SrcSplitId | 0 |
| `FTreeEntity_ForceCloserId_Id` | ForceCloserId_Id | 0 |
| `FTreeEntity_ForceCloserId` | ForceCloserId | - |
| `FTreeEntity_FCloseType` | CloseType |   |
| `FTreeEntity_FSrcBomEntryId` | SrcBomEntryId | 0 |
| `FTreeEntity_FConfirmId` | ConfirmId | (object) |
| `FTreeEntity_FReleaseId` | ReleaseId | (object) |
| `FTreeEntity_FinishId_Id` | FinishId_Id | 0 |
| `FTreeEntity_FinishId` | FinishId | - |
| `FTreeEntity_FIsMRP` | IsMRP | false |
| `FTreeEntity_FPathEntryId` | PathEntryId |   |
| `FTreeEntity_FPPBOMENTRYID` | PPBOMENTRYID | 0 |
| `FTreeEntity_FBOMENTRYID` | BOMENTRYID | 0 |
| `FTreeEntity_FSrcFormID` | SrcFormID |   |
| `FTreeEntity_FBaseScheduledQtySum` | BaseScheduledQtySum | 0.0 |
| `FTreeEntity_FScheduledQtySum` | ScheduledQtySum | 0.0 |
| `FTreeEntity_FISENABLESCHEDULE` | ISENABLESCHEDULE | false |
| `FTreeEntity_FScheduleStatus` | ScheduleStatus | 1 |
| `FTreeEntity_FMatchQty` | MatchQty | 0.0 |
| `FTreeEntity_FInvMatchQty` | InvMatchQty | 0.0 |
| `FTreeEntity_FMatchDate` | MatchDate | - |
| `FTreeEntity_FCompleteCon` | FCompleteCon |   |
| `FTreeEntity_FRemarks` | 备注 |   |
| `FTreeEntity_FISMRPCAL` | ISMRPCAL | false |
| `FTreeEntity_FIsGenerateOrder` | IsGenerateOrder | false |
| `FTreeEntity_FANALYSEPRIORITY` | ANALYSEPRIORITY | 0 |

## 三、常用查询示例

```python
# 根据计划跟踪号查询委外申请订单
query_para = {
    "FormId": "SUB_SUBREQORDER",
    "FieldKeys": "FBillNo,FId,FTreeEntity_FMaterialId.FNumber,FTreeEntity_FMaterialId.FName,FTreeEntity_FQty",
    "FilterString": "FTreeEntity_FMTONo='AS251008'",
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
