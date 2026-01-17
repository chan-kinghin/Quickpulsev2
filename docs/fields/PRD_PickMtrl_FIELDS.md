# 生产领料单 (PRD_PickMtrl) 字段清单

## 一、单据头字段

| 查询字段名 | 说明 | 示例值 |
|-----------|------|--------|
| `FId` | 单据内码 | 100029 |
| `FBillNo` | 单据编号 | LL25040001 |
| `FDocumentStatus` | 单据状态 | C |
| `FApproverId` | 审核人 | (object) |
| `FApproveDate` | 审核日期 | 2025-05-08T10:42:59.073 |
| `FModifierId` | 修改人 | (object) |
| `FCreateDate` | 创建日期 | 2025-04-02T09:28:49.487 |
| `FCreatorId` | 创建人 | (object) |
| `FModifyDate` | 修改日期 | 2025-05-08T10:42:55.04 |
| `FCancelDate` | 作废日期 | - |
| `FCANCELER` | CANCELER | - |
| `FCancelStatus` | CancelStatus | A |
| `FDate` | 日期 | 2025-04-02T00:00:00 |
| `FPrdOrgId` | 生产组织 | 101 |
| `FStockOrgId` | 库存组织 | 101 |
| `FWorkShopId` | 车间 | - |
| `FStockId` | 仓库 | - |
| `FBillType` | BillType | SCLLD01_SYS |
| `FOwnerTypeId` | OwnerTypeId | BD_OwnerOrg |
| `FOwnerId` | 货主 | - |
| `FCurrId` | CurrId | PRE001 |
| `FTransferBizType` | TransferBizType | OverOrgPick |
| `FPickerId` | PickerId | - |
| `FSTOCKERID_Id` | FSTOCKERID_Id | 0 |
| `FSTOCKERID` | FSTOCKERID | - |
| `FIsCrossTrade` | IsCrossTrade | false |
| `FVmiBusiness` | FVmiBusiness | false |
| `FScanBox` | ScanBox | - |
| `FSourceType` | SourceType |   |
| `FIsOwnerTInclOrg` | IsOwnerTInclOrg | true |
| `FInventoryDate` | InventoryDate | - |
| `F_QWJI_Base_qtr_Id` | F_QWJI_Base_qtr_Id | 361545 |
| `F_QWJI_Base_qtr` | F_QWJI_Base_qtr | 20 |
| `FBOS_ConvertTakeDataInfo` | BOS_ConvertTakeDataInfo | - |

## 二、明细行字段 (Entity)

| 查询字段名 | 说明 | 示例值 |
|-----------|------|--------|
| `FEntity_FId` | 单据内码 | 100062 |
| `FEntity_FSeq` | 行号 | 1 |
| `FEntity_FMaterialId` | 物料 | 05.20.01.01.027 |
| `FEntity_FBomId` | BOM版本 | - |
| `FEntity_FStockId` | 仓库 | 05.01 |
| `FEntity_FStockLocId` | 仓位 | - |
| `FEntity_FStockStatusId` | 库存状态 | KCZT01_SYS |
| `FEntity_FProduceDate` | 生产日期 | - |
| `FEntity_FMTONO` | MTONO | DS252019S |
| `FEntity_FProjectNo` | ProjectNo |   |
| `FEntity_FMoBillNo` | 生产订单编号 | MO250302174 |
| `FEntity_FMoEntryId` | 生产订单分录内码 | 174958 |
| `FEntity_FPPBomEntryId` | PPBomEntryId | 265411 |
| `FEntity_FOperId` | OperId | 10 |
| `FEntity_FProcessId` | ProcessId | - |
| `FEntity_FOwnerTypeId` | OwnerTypeId | BD_OwnerOrg |
| `FEntity_FAppQty` | AppQty | 2000.0 |
| `FEntity_FActualQty` | ActualQty | 1000.0 |
| `FEntity_FStockAppQty` | StockAppQty | 2000.0 |
| `FEntity_FStockActualQty` | StockActualQty | 1000.0 |
| `FEntity_FSecActualQty` | SecActualQty | 0.0 |
| `FEntity_FMoId` | MoId | 173137 |
| `FEntity_FMoEntrySeq` | MoEntrySeq | 1 |
| `FEntity_FBaseAppQty` | BaseAppQty | 2000.0 |
| `FEntity_FAllowOverQty` | AllowOverQty | 0.0 |
| `FEntity_FStockAllowOverQty` | StockAllowOverQty | 0.0 |
| `FEntity_FSecAllowOverQty` | SecAllowOverQty | 0.0 |
| `FEntity_FBaseAllowOverQty` | BaseAllowOverQty | 0.0 |
| `FEntity_FPPBomBillNo` | PPBomBillNo | PPBOM250301013 |
| `FEntity_FUnitId` | 单位 | 007 |
| `FEntity_FBaseUnitId` | 基本单位 | 007 |
| `FEntity_FStockUnitId` | StockUnitId | 007 |
| `FEntity_FSecUnitId` | SecUnitId | - |
| `FEntity_FWorkShopId` | 车间 | 20 |
| `FEntity_FSelPrcdReturnQty` | SelPrcdReturnQty | 0.0 |
| `FEntity_FBaseSelPrcdReturnQty` | BaseSelPrcdReturnQty | 0.0 |
| `FEntity_FStockSelPrcdReturnQty` | StockSelPrcdReturnQty | 0.0 |
| `FEntity_FSecSelPrcdReturnQty` | SecSelPrcdReturnQty | 0.0 |
| `FEntity_FBaseActualQty` | BaseActualQty | 1000.0 |
| `FEntity_FAuxPropId` | 辅助属性 | (object) |
| `FEntity_FKeeperTypeId` | KeeperTypeId | BD_KeeperOrg |
| `FEntity_FKeeperId` | 保管者 | 101 |
| `FEntity_FStockFlag` | StockFlag | true |
| `FEntity_FOwnerId` | 货主 | 101 |
| `FEntity_FExpiryDate` | 有效期至 | - |
| `FEntity_FSrcBillType` | 源单类型 | PRD_PPBOM |
| `FEntity_FSrcBillNo` | 源单编号 | PPBOM250301013 |
| `FEntity_FPrice` | 单价 | 0.72721263 |
| `FEntity_FAmount` | 金额 | 727.21 |
| `FEntity_FSrcInterId` | SrcInterId | 161962 |
| `FEntity_FSrcEnteryId` | SrcEnteryId | 265411 |
| `FEntity_FSrcEntrySeq` | SrcEntrySeq | 10 |
| `FEntity_FLot` | 批号 | DS252019S |
| `FEntity_FLot_Text` | Lot_Text | DS252019S |
| `FEntity_FParentOwnerTypeId` | ParentOwnerTypeId | BD_OwnerOrg |
| `FEntity_FParentOwnerId` | ParentOwnerId | 101 |
| `FEntity_FSRCBIZBILLTYPE` | SRCBIZBILLTYPE | - |
| `FEntity_FSRCBIZBILLNO` | SRCBIZBILLNO |   |
| `FEntity_FSRCBIZINTERID` | SRCBIZINTERID | 0 |
| `FEntity_FSRCBIZENTRYID` | SRCBIZENTRYID | 0 |
| `FEntity_FSRCBIZENTRYSEQ` | SRCBIZENTRYSEQ | 0 |
| `FEntity_FPickingStatus` | PickingStatus | 0 |
| `FEntity_FBFLowId` | BFLowId | 生产领退补料流程 |
| `FEntity_FParentMaterialId` | ParentMaterialId | 06.02.012 |
| `FEntity_FPMBillNo` | PMBillNo |   |
| `FEntity_FSNUnitID` | SNUnitID | - |
| `FEntity_FSNQty` | SNQty | 0.0 |
| `FEntity_FReserveType` | ReserveType | 3 |
| `FEntity_FBaseStockActualQty` | BaseStockActualQty | 1000.0 |
| `FEntity_FOptQueue` | OptQueue | 0 |
| `FEntity_FConsome` | Consome | 0 |
| `FEntity_FEntryVmiBusiness` | EntryVmiBusiness | false |
| `FEntity_FOptPlanBillNo` | OptPlanBillNo |   |
| `FEntity_FOptPlanBillId` | OptPlanBillId | 0 |
| `FEntity_FWorkCenterId` | WorkCenterId | - |
| `FEntity_FOptDetailId` | OptDetailId | 0 |
| `FEntity_FCobyBomEntryID` | CobyBomEntryID | 0 |
| `FEntity_FReqSrc` | ReqSrc | 1 |
| `FEntity_FReqBillNo` | ReqBillNo | XSDD2502055 |
| `FEntity_FReqBillId` | ReqBillId | 107244 |
| `FEntity_FReqEntrySeq` | ReqEntrySeq | 4 |
| `FEntity_FReqEntryId` | ReqEntryId | 218377 |
| `FEntity_FGroupRow` | GroupRow | d4f5ef8e-7b8e-8dad-11f0-0f61b31e68d4 |
| `FEntity_FQueryStockUpdate` | QueryStockUpdate | - |
| `FEntity_FSrcPickEntryId` | SrcPickEntryId | 0 |
| `FEntity_FSrcBusinessType` | SrcBusinessType |   |
| `FEntity_FSendRowId` | SendRowId |   |
| `FEntity_FInventoryQty` | InventoryQty | 0.0 |
| `FEntity_FBaseInventoryQty` | BaseInventoryQty | 0.0 |
| `FEntity_FTransRetFormId` | TransRetFormId |   |
| `FEntity_FTransRetBillNo` | TransRetBillNo |   |
| `FEntity_FTransRetId` | TransRetId | 0 |
| `FEntity_FTransRetEntryId` | TransRetEntryId | 0 |
| `FEntity_FTransRetEntrySeq` | TransRetEntrySeq | 0 |
| `FEntity_FCheckReturnMtrl` | CheckReturnMtrl | false |
| `FEntity_FBaseReturnAppSelQty` | BaseReturnAppSelQty | 0.0 |
| `FEntity_FReturnAppSelQty` | ReturnAppSelQty | 0.0 |
| `FEntity_FIsOverLegalOrg` | IsOverLegalOrg | false |
| `FEntity_FPlanEntryID` | PlanEntryID | 0 |
| `FEntity_FISSUEINFOENTRYID` | ISSUEINFOENTRYID | 0 |
| `FEntity_F_QWJI_JSKC` | F_QWJI_JSKC | 19000.0 |
| `FEntity_F_QWJI_KHMC_Id` | F_QWJI_KHMC_Id | 0 |
| `FEntity_F_QWJI_KHMC` | F_QWJI_KHMC | - |

## 三、常用查询示例

```python
# 根据计划跟踪号查询生产领料单
query_para = {
    "FormId": "PRD_PickMtrl",
    "FieldKeys": "FBillNo,FId,FEntity_FMaterialId.FNumber,FEntity_FMaterialId.FName,FEntity_FQty",
    "FilterString": "FEntity_FMTONo='AS251008'",
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
