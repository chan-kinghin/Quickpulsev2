# 生产入库单 (PRD_INSTOCK) 字段清单

## 一、单据头字段

| 查询字段名 | 说明 | 示例值 |
|-----------|------|--------|
| `FId` | 单据内码 | 113260 |
| `FBillNo` | 单据编号 | CP25020001 |
| `FDocumentStatus` | 单据状态 | C |
| `FApproverId` | 审核人 | (object) |
| `FApproveDate` | 审核日期 | 2025-02-07T18:54:10.677 |
| `FModifierId` | 修改人 | (object) |
| `FCreateDate` | 创建日期 | 2025-02-04T10:56:25.457 |
| `FCreatorId` | 创建人 | (object) |
| `FModifyDate` | 修改日期 | 2025-02-07T10:00:29.373 |
| `FCancelDate` | 作废日期 | - |
| `FCANCELER` | CANCELER | - |
| `FCancelStatus` | CancelStatus | A |
| `FDate` | 日期 | 2025-02-04T00:00:00 |
| `FPrdOrgId` | 生产组织 | 101 |
| `FBillType` | BillType | SCRKD02_SYS |
| `FStockOrgId` | 库存组织 | 101 |
| `FWorkShopId` | 车间 | - |
| `FStockId` | 仓库 | - |
| `FOwnerTypeId` | OwnerTypeId | BD_OwnerOrg |
| `FOwnerId` | 货主 | 101 |
| `FCurrId` | CurrId | PRE001 |
| `FSTOCKERID_Id` | FSTOCKERID_Id | 0 |
| `FSTOCKERID` | FSTOCKERID | - |
| `FIOSBizTypeId_Id` | FIOSBizTypeId_Id | 10 |
| `FIOSBizTypeId` | FIOSBizTypeId | OverOrgPrdIn |
| `FIsEntrust` | IsEntrust | false |
| `FEntrustInStockId` | EntrustInStockId | 0 |
| `FIsIOSForFin` | IsIOSForFin | false |
| `FScanBox` | ScanBox | - |
| `FISGENFORIOS` | ISGENFORIOS | false |
| `FBOS_ConvertTakeDataInfo` | BOS_ConvertTakeDataInfo | - |

## 二、明细行字段 (Entity)

| 查询字段名 | 说明 | 示例值 |
|-----------|------|--------|
| `FEntity_FId` | 单据内码 | 115473 |
| `FEntity_FSeq` | 行号 | 1 |
| `FEntity_FMaterialId` | 物料 | 05.02.27.022 |
| `FEntity_FProductType` | ProductType | 1 |
| `FEntity_FInStockType` | InStockType | 1 |
| `FEntity_FUnitID_Id` | FUnitID_Id | 296939 |
| `FEntity_FUnitID` | FUnitID | 005 |
| `FEntity_FBaseUnitId` | 基本单位 | 005 |
| `FEntity_FMustQty` | 应收/应发数量 | 9072.0 |
| `FEntity_FBaseMustQty` | BaseMustQty | 9072.0 |
| `FEntity_FRealQty` | 实收/实发数量 | 1365.0 |
| `FEntity_FBaseRealQty` | BaseRealQty | 1365.0 |
| `FEntity_FOwnerTypeId` | OwnerTypeId | BD_OwnerOrg |
| `FEntity_FOwnerId` | 货主 | 101 |
| `FEntity_FStockId` | 仓库 | 05.01 |
| `FEntity_FStockLocId` | 仓位 | - |
| `FEntity_FBomId` | BOM版本 | - |
| `FEntity_FLot` | 批号 | AK2412053 |
| `FEntity_FLot_Text` | Lot_Text | AK2412053 |
| `FEntity_FAuxpropId` | AuxpropId | (object) |
| `FEntity_FMtoNo` | 计划跟踪号 | AK2412053 |
| `FEntity_FProjectNo` | ProjectNo |   |
| `FEntity_FWorkShopId` | 车间 | 03 |
| `FEntity_FMoBillNo` | 生产订单编号 | MO250110899 |
| `FEntity_FMoId` | MoId | 151263 |
| `FEntity_FMoEntryId` | 生产订单分录内码 | 151266 |
| `FEntity_FMoEntrySeq` | MoEntrySeq | 1 |
| `FEntity_FStockUnitId` | StockUnitId | 005 |
| `FEntity_FStockRealQty` | StockRealQty | 1365.0 |
| `FEntity_FSecUnitId` | SecUnitId | - |
| `FEntity_FSecRealQty` | SecRealQty | 0.0 |
| `FEntity_FPrice` | 单价 | 0.24241172 |
| `FEntity_FAmount` | 金额 | 330.89 |
| `FEntity_FSrcInterId` | SrcInterId | 151263 |
| `FEntity_FSrcEntryId` | SrcEntryId | 151266 |
| `FEntity_FSrcEntrySeq` | SrcEntrySeq | 1 |
| `FEntity_FStockStatusId` | 库存状态 | KCZT01_SYS |
| `FEntity_FKeeperTypeId` | KeeperTypeId | BD_KeeperOrg |
| `FEntity_FKeeperId` | 保管者 | 101 |
| `FEntity_FProduceDate` | 生产日期 | - |
| `FEntity_FExpiryDate` | 有效期至 | - |
| `FEntity_FStockFlag` | StockFlag | true |
| `FEntity_FSrcBillType` | 源单类型 | PRD_MO |
| `FEntity_FSrcBillNo` | 源单编号 | MO250110899 |
| `FEntity_FBFLowId` | BFLowId | 生产直接入库流程 |
| `FEntity_FShiftGroupId` | ShiftGroupId | - |
| `FEntity_FSNUnitId` | SNUnitId | - |
| `FEntity_FSNQty` | SNQty | 0.0 |
| `FEntity_FCheckProduct` | CheckProduct | false |
| `FEntity_FQAIP` | QAIP | A |
| `FEntity_FCOSTRATE` | COSTRATE | 100.0 |
| `FEntity_FIsNew` | IsNew | false |
| `FEntity_FIsFinished` | IsFinished | false |
| `FEntity_FISBACKFLUSH` | ISBACKFLUSH | true |
| `FEntity_FMoMainEntryId` | MoMainEntryId | 151266 |
| `FEntity_FBasePrdRealQty` | BasePrdRealQty | 1365.0 |
| `FEntity_FReqSrc` | ReqSrc |   |
| `FEntity_FReqBillNo` | ReqBillNo |   |
| `FEntity_FReqBillId` | ReqBillId | 0 |
| `FEntity_FReqEntrySeq` | ReqEntrySeq | 0 |
| `FEntity_FReqEntryId` | ReqEntryId | 0 |
| `FEntity_FSelReStkQty` | SelReStkQty | 0.0 |
| `FEntity_FBaseSelReStkQty` | BaseSelReStkQty | 0.0 |
| `FEntity_FSrcBusinessType` | SrcBusinessType |   |
| `FEntity_FSendRowId` | SendRowId |   |
| `FEntity_FIsOverLegalOrg` | IsOverLegalOrg | false |
| `FEntity_FLINEID` | LINEID | - |
| `FEntity_FSeqNumber` | SeqNumber |   |
| `FEntity_FSeqType` | SeqType |   |
| `FEntity_FOperNumber` | OperNumber | 0 |
| `FEntity_FWorkCenterId` | WorkCenterId | - |
| `FEntity_FProcessId` | ProcessId | - |
| `FEntity_FReportPrdOrgId` | ReportPrdOrgId | - |
| `FEntity_F_QWJI_SCCL` | F_QWJI_SCCL | 0.0 |
| `FEntity_F_QWJI_JSKC` | F_QWJI_JSKC | 0.0 |
| `FEntity_F_QWJI_KHMC_Id` | F_QWJI_KHMC_Id | 0 |
| `FEntity_F_QWJI_KHMC` | F_QWJI_KHMC | - |

## 三、常用查询示例

```python
# 根据计划跟踪号查询生产入库单
query_para = {
    "FormId": "PRD_INSTOCK",
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
