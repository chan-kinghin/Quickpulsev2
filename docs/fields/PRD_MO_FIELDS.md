# 生产订单 (PRD_MO) 字段清单

## 一、单据头字段

| 查询字段名 | 说明 | 示例值 |
|-----------|------|--------|
| `FId` | 单据内码 | 100054 |
| `FBillNo` | 单据编号 | MO25010001 |
| `FDocumentStatus` | 单据状态 | C (已审核) |
| `FDate` | 单据日期 | 2025-01-03 |
| `FBillType` | 单据类型 | 直接入库-普通生产 |
| `FPrdOrgId` | 生产组织 | 洛阳富隆特体育用品有限公司 |
| `FOwnerId` | 货主 | 洛阳富隆特体育用品有限公司 |
| `FPlannerID` | 计划员 | - |
| `FWorkShopID` | 生产车间(表头) | - |
| `FBusinessType` | 业务类型 | 1 |
| `FIsRework` | 是否返工 | false |
| `FIsEntrust` | 是否委外 | false |
| `FCreateDate` | 创建日期 | 2025-01-03 |
| `FCreatorId` | 创建人 | 樊继平 |
| `FApproveDate` | 审核日期 | 2025-01-03 |
| `FApproverId` | 审核人 | 樊继平 |
| `F_QWJI_KHMC1` | 客户名称(自定义) | 法国ITS |

## 二、明细行字段 (TreeEntity)

| 查询字段名 | 说明 | 示例值 |
|-----------|------|--------|
| `FTreeEntity_FEntryId` | 分录内码 | 100053 |
| `FTreeEntity_FSeq` | 行号 | 1 |
| `FMaterialId` | 物料编码 | 06.04.087 |
| `FMaterialId.FName` | 物料名称 | 未包装呼吸管 |
| `FMaterialId.FSpecification` | 规格型号 | SN9871-成人咬嘴 |
| `FQty` | 数量 | 1300 |
| `FBaseUnitQty` | 基本单位数量 | 1300 |
| `FUnitId` | 单位 | Pcs |
| **`FMTONo`** | **计划跟踪号** | **AK2412023** |
| `FLot` | 批号 | - |
| `FProjectNo` | 项目号 | - |
| `FPlanStartDate` | 计划开工日期 | 2025-04-10 |
| `FPlanFinishDate` | 计划完工日期 | 2025-04-10 |
| `FStatus` | 生产状态 | 3 (已下达) |
| `FBomId` | BOM版本 | 法国ITS-07.04.231-001 |
| `FWorkShopID` | 生产车间 | 包装工段（泳帽） |
| `FStockId` | 入库仓库 | 外销成品仓 |
| `FStockInOrgId` | 入库组织 | 洛阳富隆特体育用品有限公司 |
| `FYieldRate` | 合格率 | 100 |
| `FStockInQuaQty` | 良品入库数量 | 0 |
| `FNoStockInQty` | 未入库数量 | 1300 |
| `FSaleOrderNo` | 销售订单号 | AS2501002 |
| `FSaleOrderId` | 销售订单内码 | 100031 |
| `FRequestOrgId` | 需求组织 | 深圳市富隆特体育科技有限公司 |
| `FSrcBillType` | 源单类型 | PLN_PLANORDER |
| `FSrcBillNo` | 源单编号 | MRP0801 |
| `FAuxPropId` | 辅助属性 | 客户型号:6001292 |
| `FPlanConfirmDate` | 计划确认日期 | 2025-01-03 |
| `FConveyDate` | 下达日期 | 2025-01-03 |

## 三、常用查询示例

```python
# 根据计划跟踪号查询生产订单
query_para = {
    "FormId": "PRD_MO",
    "FieldKeys": "FBillNo,FId,FMTONo,FMaterialId.FNumber,FMaterialId.FName,FQty,FPlanStartDate,FPlanFinishDate,FStatus,FSaleOrderNo",
    "FilterString": "FMTONo='AK2412023'",
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

### 生产状态 (FStatus)

| 值 | 说明 |
|----|------|
| 1 | 计划 |
| 2 | 计划确认 |
| 3 | 下达 |
| 4 | 开工 |
| 5 | 完工 |
| 6 | 结案 |

## 五、API 使用说明

### 单据查询 (ExecuteBillQuery)
- 用于批量查询，返回二维数组
- 支持过滤、排序、分页
- 最大返回 10000 条

### 查看 (View)
- 用于查看单条记录完整详情
- 通过 `Number` 或 `Id` 定位
- 返回完整 JSON 数据包
