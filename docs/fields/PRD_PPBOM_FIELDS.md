# 生产用料清单 (PRD_PPBOM) 字段清单

## 一、单据头字段

| 查询字段名 | 说明 | 示例值 |
|-----------|------|--------|
| `FId` | 单据内码 | 100047 |
| `FBillNo` | 单据编号 | PPBOM25010001 |
| `FDocumentStatus` | 单据状态 | C |
| `FApproverId` | 审核人 | (object) |
| `FApproveDate` | 审核日期 | 2025-01-03T10:42:48.013 |
| `FModifierId` | 修改人 | - |
| `FCreateDate` | 创建日期 | 2025-01-03T10:30:21.597 |
| `FCreatorId` | 创建人 | (object) |
| `FModifyDate` | 修改日期 | - |
| `FMaterialID` | MaterialID | 06.04.087 |
| `FWorkshopID` | WorkshopID | 06 |
| `FBOMID_Id` | FBOMID_Id | 814575 |
| `FBOMID` | FBOMID | 法国ITS-07.04.231-001 |
| `FQty` | 数量 | 1300.0 |
| `FMOBillNO` | MOBillNO | MO25010001 |
| `FMOEntrySeq` | MOEntrySeq | 1 |
| `FMOStatus` | MOStatus | - |
| `FMOEntryID` | MOEntryID | 100053 |
| `FBaseQty` | BaseQty | 1300.0 |
| `FMoId` | MoId | 100054 |
| `FBaseUnitID` | BaseUnitID | Pcs |
| `FMOType` | MOType | SCDD03_SYS |
| `FUnitID` | UnitID | Pcs |
| `FPrdOrgId` | 生产组织 | 101 |
| `FAuxPropIDHead` | AuxPropIDHead | (object) |
| `FParentOwnerTypeId` | ParentOwnerTypeId | BD_OwnerOrg |
| `FParentOwnerId` | ParentOwnerId | 101 |
| `FEntrustOrgId` | EntrustOrgId | - |
| `FMoEntryMirror` | MoEntryMirror | MO25010001 |
| `FSaleOrderId` | SaleOrderId | 100031 |
| `FSaleOrderEntryId` | SaleOrderEntryId | 0 |
| `FSALEORDERNO` | SALEORDERNO | AS2501002 |
| `FSaleOrderEntrySeq` | SaleOrderEntrySeq | 0 |
| `FReqSrc` | ReqSrc | 1 |
| `FInventoryDate` | InventoryDate | 2025-04-11T17:22:05 |
| `FGeneRateDate` | GeneRateDate | 2025-01-03T10:05:37.097 |
| `FIsQCMo` | IsQCMo | false |
| `F_QWJI_KHMC_Id` | F_QWJI_KHMC_Id | 0 |
| `F_QWJI_KHMC` | F_QWJI_KHMC | - |
| `FBOS_ConvertTakeDataInfo` | BOS_ConvertTakeDataInfo | - |

## 二、明细行字段 (PPBomEntry)

| 查询字段名 | 说明 | 示例值 |
|-----------|------|--------|
| `FPPBomEntry_FId` | 单据内码 | 100099 |
| `FPPBomEntry_FSeq` | 行号 | 1 |
| `FPPBomEntry_FParentRowId` | ParentRowId |   |
| `FPPBomEntry_FRowExpandType` | RowExpandType | 16 |
| `FPPBomEntry_FRowId` | RowId | d4f5ef8e-7b8f-8da2-11ef-c97aa8acb5fe |
| `FPPBomEntry_FBOMEntryID` | BOMEntryID | 465001 |
| `FPPBomEntry_FReplaceGroup` | ReplaceGroup | 1 |
| `FPPBomEntry_FMaterialID` | MaterialID | 05.20.03.01.018 |
| `FPPBomEntry_FMaterialType` | MaterialType | 1 |
| `FPPBomEntry_FTimeUnit` | TimeUnit | 1 |
| `FPPBomEntry_FDosageType` | DosageType | 2 |
| `FPPBomEntry_FUseRate` | UseRate | 100.0 |
| `FPPBomEntry_FScrapRate` | ScrapRate | 0.0 |
| `FPPBomEntry_FOperID` | OperID | 10 |
| `FPPBomEntry_FProcessID` | ProcessID | - |
| `FPPBomEntry_FNeedDate` | NeedDate | 2025-04-10T00:00:00 |
| `FPPBomEntry_FStdQty` | StdQty | 1300.0 |
| `FPPBomEntry_FNeedQty` | NeedQty | 1300.0 |
| `FPPBomEntry_FMustQty` | 应收/应发数量 | 1300.0 |
| `FPPBomEntry_FPickedQty` | PickedQty | 0.0 |
| `FPPBomEntry_FRePickedQty` | RePickedQty | 0.0 |
| `FPPBomEntry_FScrapQty` | ScrapQty | 0.0 |
| `FPPBomEntry_FGoodReturnQty` | GoodReturnQty | 0.0 |
| `FPPBomEntry_FINCDefectReturnQty` | INCDefectReturnQty | 0.0 |
| `FPPBomEntry_FProcessDefectReturnQty` | ProcessDefectReturnQty | 0.0 |
| `FPPBomEntry_FConsumeQty` | ConsumeQty | 0.0 |
| `FPPBomEntry_FWipQty` | WipQty | 0.0 |
| `FPPBomEntry_FIssueType` | IssueType | 1 |
| `FPPBomEntry_FBackFlushType` | BackFlushType |   |
| `FPPBomEntry_FOverRate` | OverRate | 0.0 |
| `FPPBomEntry_FStockLocID` | StockLocID | - |
| `FPPBomEntry_FStockID` | StockID | 05.01 |
| `FPPBomEntry_FMTONO` | MTONO | AK2412023 |
| `FPPBomEntry_FProjectNO` | ProjectNO |   |
| `FPPBomEntry_FPositionNO` | PositionNO |   |
| `FPPBomEntry_FSelPickedQty` | SelPickedQty | 0.0 |
| `FPPBomEntry_FSelRePickedQty` | SelRePickedQty | 0.0 |
| `FPPBomEntry_FSelPrcdReturnQty` | SelPrcdReturnQty | 0.0 |
| `FPPBomEntry_FSrcTransOrgId` | SrcTransOrgId | - |
| `FPPBomEntry_FSrcTransStockId` | SrcTransStockId | - |
| `FPPBomEntry_FSrcTransStockLocId` | SrcTransStockLocId | - |
| `FPPBomEntry_FSelTranslateQty` | SelTranslateQty | 0.0 |
| `FPPBomEntry_FTranslateQty` | TranslateQty | 0.0 |
| `FPPBomEntry_FIsGetScrapd` | IsGetScrapd | true |
| `FPPBomEntry_FAllowOver` | AllowOver | false |
| `FPPBomEntry_FBOMID` | BOMID | - |
| `FPPBomEntry_FSupplyOrg` | SupplyOrg | 101 |
| `FPPBomEntry_FBaseStdQty` | BaseStdQty | 1300.0 |
| `FPPBomEntry_FBaseNeedQty` | BaseNeedQty | 1300.0 |
| `FPPBomEntry_FBaseUnitID` | BaseUnitID | 007 |
| `FPPBomEntry_FBaseMustQty` | BaseMustQty | 1300.0 |
| `FPPBomEntry_FBasePickedQty` | BasePickedQty | 0.0 |
| `FPPBomEntry_FBaseRepickedQty` | BaseRepickedQty | 0.0 |
| `FPPBomEntry_FBaseScrapQty` | BaseScrapQty | 0.0 |
| `FPPBomEntry_FBaseGoodReturnQty` | BaseGoodReturnQty | 0.0 |
| `FPPBomEntry_FBaseIncDefectReturnQty` | BaseIncDefectReturnQty | 0.0 |
| `FPPBomEntry_FBasePrcDefectReturnQty` | BasePrcDefectReturnQty | 0.0 |
| `FPPBomEntry_FBaseConsumeQty` | BaseConsumeQty | 0.0 |
| `FPPBomEntry_FBaseWipQty` | BaseWipQty | 0.0 |
| `FPPBomEntry_FBaseSelGoodReturnQty` | BaseSelGoodReturnQty | 0.0 |
| `FPPBomEntry_FBaseSelIncDefectReturnQty` | BaseSelIncDefectReturnQty | 0.0 |
| `FPPBomEntry_FBaseSelPrcDefectReturnQty` | BaseSelPrcDefectReturnQty | 0.0 |
| `FPPBomEntry_FBaseSelPickedQty` | BaseSelPickedQty | 0.0 |
| `FPPBomEntry_FBaseSelRePickedQty` | BaseSelRePickedQty | 0.0 |
| `FPPBomEntry_FBaseSelPrcdReturnQty` | BaseSelPrcdReturnQty | 0.0 |
| `FPPBomEntry_FBaseSelTranslateQty` | BaseSelTranslateQty | 0.0 |
| `FPPBomEntry_FBaseTranslateQty` | BaseTranslateQty | 0.0 |
| `FPPBomEntry_FBaseReturnNoOkQty` | BaseReturnNoOkQty | 0.0 |
| `FPPBomEntry_FReturnNoOkQty` | ReturnNoOkQty | 0.0 |
| `FPPBomEntry_FMOType` | MOType | SCDD03_SYS |
| `FPPBomEntry_FMoBillNo` | 生产订单编号 | MO25010001 |
| `FPPBomEntry_FMoId` | MoId | 100054 |
| `FPPBomEntry_FMoEntryId` | 生产订单分录内码 | 100053 |
| `FPPBomEntry_FMoEntrySeq` | MoEntrySeq | 1 |
| `FPPBomEntry_FUnitID` | UnitID | 007 |
| `FPPBomEntry_FBOMNumerator` | BOMNumerator | 1.0 |
| `FPPBomEntry_FBOMDenominator` | BOMDenominator | 1.0 |
| `FPPBomEntry_FNumerator` | Numerator | 1.0 |
| `FPPBomEntry_FDenominator` | Denominator | 1.0 |
| `FPPBomEntry_FBaseBOMNumerator` | BaseBOMNumerator | 1.0 |
| `FPPBomEntry_FBaseNumerator` | BaseNumerator | 1.0 |
| `FPPBomEntry_FAuxPropID` | AuxPropID | (object) |
| `FPPBomEntry_FOwnerID` | OwnerID | 101 |
| `FPPBomEntry_FOwnerTypeId` | OwnerTypeId | BD_OwnerOrg |
| `FPPBomEntry_FIsKeyItem` | IsKeyItem | false |
| `FPPBomEntry_FixScrapQty` | FixScrapQty | 0.0 |
| `FPPBomEntry_FLot` | 批号 | - |
| `FPPBomEntry_FLot_Text` | Lot_Text |   |
| `FPPBomEntry_FOffsetTime` | OffsetTime | 0 |
| `FPPBomEntry_FBaseFixScrapQTY` | BaseFixScrapQTY | 0.0 |
| `FPPBomEntry_FBaseDenominator` | BaseDenominator | 1.0 |
| `FPPBomEntry_FBaseBomDenominator` | BaseBomDenominator | 1.0 |
| `FPPBomEntry_FIsKeyComponent` | IsKeyComponent | true |
| `FPPBomEntry_FBFLowId` | BFLowId | 生产领退补料流程 |
| `FPPBomEntry_FWorkCalId` | WorkCalId | CA000001 |
| `FPPBomEntry_FPriority` | Priority | 0 |
| `FPPBomEntry_FReserveType` | ReserveType | 3 |
| `FPPBomEntry_FReplacePolicy` | ReplacePolicy |   |
| `FPPBomEntry_FReplaceType` | ReplaceType |   |
| `FPPBomEntry_FReplacePriority` | ReplacePriority | 0 |
| `FPPBomEntry_FOverControlMode` | OverControlMode | 1 |
| `FPPBomEntry_FSMId` | SMId | - |
| `FPPBomEntry_FSMEntryId` | SMEntryId | 0 |
| `FPPBomEntry_FBaseStockReadyQty` | BaseStockReadyQty | 0.0 |
| `FPPBomEntry_FStockReadyQty` | StockReadyQty | 0.0 |
| `FPPBomEntry_FChildSupplyOrgId` | ChildSupplyOrgId | - |
| `FPPBomEntry_FOptQueue` | OptQueue | 0 |
| `FPPBomEntry_FStockStatusId` | 库存状态 | KCZT01_SYS |
| `FPPBomEntry_FEntrustPickOrgId` | EntrustPickOrgId | 101 |
| `FPPBomEntry_FIsSkip` | IsSkip | false |
| `FPPBomEntry_FISMinIssueQty` | ISMinIssueQty | false |
| `FPPBomEntry_FPPBomEntryType` | PPBomEntryType | 0 |
| `FPPBomEntry_FUPDATERID` | UPDATERID | - |
| `FPPBomEntry_FUPDateDate` | UPDateDate | - |
| `FPPBomEntry_FGroupByOwnerId` | GroupByOwnerId | 101 |
| `FPPBomEntry_FSupplyMode` | SupplyMode |   |
| `FPPBomEntry_FBaseNoPickedQty` | BaseNoPickedQty | 1300.0 |
| `FPPBomEntry_FNoPickedQty` | NoPickedQty | 1300.0 |
| `FPPBomEntry_FSelIssueQty` | SelIssueQty | 0.0 |
| `FPPBomEntry_FBaseSelIssueQty` | BaseSelIssueQty | 0.0 |
| `FPPBomEntry_FIssueQty` | IssueQty | 0.0 |
| `FPPBomEntry_FBaseIssueQty` | BaseIssueQty | 0.0 |
| `FPPBomEntry_FIsMrpRun` | IsMrpRun | true |
| `FPPBomEntry_FSrcPPBOMID` | SrcPPBOMID | 0 |
| `FPPBomEntry_FSrcPPBOMEntryId` | SrcPPBOMEntryId | 0 |
| `FPPBomEntry_FPathEntryID` | PathEntryID | 465001 |
| `FPPBomEntry_FBaseInventoryQty` | BaseInventoryQty | 0.0 |
| `FPPBomEntry_FInventoryQty` | InventoryQty | 0.0 |
| `FPPBomEntry_FSupplyType` | SupplyType |   |
| `FPPBomEntry_FSrcPathEntryID` | SrcPathEntryID |   |
| `FPPBomEntry_FReturnQty` | ReturnQty | 0.0 |
| `FPPBomEntry_FBaseReturnQty` | BaseReturnQty | 0.0 |
| `FPPBomEntry_FIsExpand` | IsExpand | false |
| `FPPBomEntry_FCheckReturnMtrl` | CheckReturnMtrl | false |
| `FPPBomEntry_FBaseReturnAppSelQty` | BaseReturnAppSelQty | 0.0 |
| `FPPBomEntry_FReturnAppSelQty` | ReturnAppSelQty | 0.0 |
| `FPPBomEntry_FBillAccuYieldRate` | BillAccuYieldRate | 0.0 |
| `FPPBomEntry_FMinIssueQty` | MinIssueQty | 0.0 |
| `FPPBomEntry_FBaseMinIssueQty` | BaseMinIssueQty | 0.0 |
| `FPPBomEntry_FALLOCATEQTY` | ALLOCATEQTY | 0.0 |
| `FPPBomEntry_FBASEALLOCATEQTY` | BASEALLOCATEQTY | 0.0 |
| `FPPBomEntry_FISMODIFYMQ` | ISMODIFYMQ | false |
| `FPPBomEntry_FTOPMATERIALID` | TOPMATERIALID | - |
| `FPPBomEntry_FPARENTMATERIALID` | PARENTMATERIALID | - |
| `FPPBomEntry_FACTUALPICKQTY` | ACTUALPICKQTY | 0.0 |
| `FPPBomEntry_FBASEACTUALPICKQTY` | BASEACTUALPICKQTY | 0.0 |
| `FPPBomEntry_FPPBOMChangeFlag` | PPBOMChangeFlag | false |
| `FPPBomEntry_FNoReCalSubRate` | NoReCalSubRate | false |
| `FPPBomEntry_FSrcSpMoPpbomEntryId` | SrcSpMoPpbomEntryId | 0 |
| `FPPBomEntry_FSrcSpMoPpbomId` | SrcSpMoPpbomId | 0 |
| `FPPBomEntry_FSrcSpRoPpbomEntryId` | SrcSpRoPpbomEntryId | 0 |
| `FPPBomEntry_FSrcSpRoPpbomId` | SrcSpRoPpbomId | 0 |
| `FPPBomEntry_FCloseScrapQty` | CloseScrapQty | 0.0 |
| `FPPBomEntry_FBaseCloseScrapQty` | BaseCloseScrapQty | 0.0 |
| `FPPBomEntry_FBasePickingQty` | BasePickingQty | 0.0 |
| `FPPBomEntry_FPickingQty` | PickingQty | 0.0 |
| `FPPBomEntry_F_QWJI_MS` | F_QWJI_MS |   |
| `FPPBomEntry_F_QWJI_MS2` | F_QWJI_MS2 |   |
| `FPPBomEntry_F_QWJI_YSTP` | F_QWJI_YSTP |   |
| `FPPBomEntry_F_QWJI_YSTP2` | F_QWJI_YSTP2 |   |
| `FPPBomEntry_F_QWJI_FJ` | F_QWJI_FJ |   |
| `FPPBomEntry_F_QWJI_YSTP3` | F_QWJI_YSTP3 |   |
| `FPPBomEntry_F_QWJI_XSWLBM_Id` | F_QWJI_XSWLBM_Id | 809248 |
| `FPPBomEntry_F_QWJI_XSWLBM` | F_QWJI_XSWLBM | 06.04.087 |

## 三、常用查询示例

```python
# 根据计划跟踪号查询生产用料清单
query_para = {
    "FormId": "PRD_PPBOM",
    "FieldKeys": "FBillNo,FId,FPPBomEntry_FMaterialId.FNumber,FPPBomEntry_FMaterialId.FName,FPPBomEntry_FQty",
    "FilterString": "FPPBomEntry_FMTONo='AS251008'",
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
