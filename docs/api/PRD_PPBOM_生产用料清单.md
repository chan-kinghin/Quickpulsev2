# 生产用料清单 (Production BOM) API Documentation

## Overview
- **Form ID**: `PRD_PPBOM`
- **Module**: 生产制造 > 生产管理 > 生产用料清单
- **Last Updated**: 2023-03-09

## Available Operations

| Operation | Chinese | Method | Description |
|-----------|---------|--------|-------------|
| Query | 单据查询 | ExecuteBillQuery | Query/List documents |
| View | 查看 | View | View single document details |
| Submit | 提交 | Submit | Submit for approval |
| Audit | 审核 | Audit | Approve document |
| Unaudit | 反审核 | UnAudit | Reverse approval |
| Push | 下推 | Push | Push to downstream document |

---

## Query API (单据查询)

### Description
本接口用于实现生产用料清单 (PRD_PPBOM) 的单据查询(ExecuteBillQuery)功能

### Request Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| FormId | String | 必录 | PRD_PPBOM | 业务对象表单Id |
| FieldKeys | String | 必录 | | 需查询的字段key集合，格式："key1,key2,..." |
| FilterString | Array | 非必录 | [] | 过滤条件数组 |
| OrderString | String | 非必录 | | 排序字段 |
| TopRowCount | Integer | 非必录 | 0 | 返回总行数 |
| StartRow | Integer | 非必录 | 0 | 开始行索引 |
| Limit | Integer | 非必录 | 2000 | 最大行数，不能超过10000 |
| SubSystemId | String | 非必录 | | 表单所在的子系统内码 |

### Response Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| Result | Array | [] | 查询的FieldKeys结果集合 |

### Request Example
```json
{
  "FormId": "PRD_PPBOM",
  "FieldKeys": "",
  "FilterString": [],
  "OrderString": "",
  "TopRowCount": 0,
  "StartRow": 0,
  "Limit": 2000,
  "SubSystemId": ""
}
```

### Response Example
```json
[["FValue1","FValue2",...],["FValue1","FValue2",...],...]
```

### Python Code Example
```python
from k3cloud_webapi_sdk import K3CloudApiSdk
import json

# 读取配置，初始化SDK
api_sdk = K3CloudApiSdk()
api_sdk.Init(config_path='../conf.ini', config_node='config')

# 请求参数
para = {
    "FormId": "PRD_PPBOM",
    "FieldKeys": "",
    "FilterString": [],
    "OrderString": "",
    "TopRowCount": 0,
    "StartRow": 0,
    "Limit": 2000,
    "SubSystemId": ""
}

# 调用接口
response = api_sdk.ExecuteBillQuery(para)
print("接口返回结果：" + response)

res = json.loads(response)
if len(res) > 0:
    return True
return False
```

---

## View API (查看)

### Description
本接口用于实现生产用料清单 (PRD_PPBOM) 的查看(View)功能

### Request Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| formid | String | 必录 | PRD_PPBOM | 业务对象表单Id |
| CreateOrgId | Integer | 非必录 | 0 | 创建者组织内码 |
| Number | String | 非必录 | | 单据编码（使用编码时必录） |
| Id | String | 非必录 | | 表单内码（使用内码时必录） |
| IsSortBySeq | bool | 非必录 | false | 单据体是否按序号排序 |

### Python Code Example
```python
from k3cloud_webapi_sdk import K3CloudApiSdk
import json

api_sdk = K3CloudApiSdk()
api_sdk.Init(config_path='../conf.ini', config_node='config')

para = {
    "CreateOrgId": 0,
    "Number": "",
    "Id": "",
    "IsSortBySeq": "false"
}

formId = "PRD_PPBOM"
response = api_sdk.View(formId, para)
print("接口返回结果：" + response)

res = json.loads(response)
if res["Result"]["ResponseStatus"]["IsSuccess"]:
    return True
else:
    return False
```

---

## Submit API (提交)

### Description
本接口用于实现生产用料清单 (PRD_PPBOM) 的提交(Submit)功能

### Python Code Example
```python
from k3cloud_webapi_sdk import K3CloudApiSdk
import json

api_sdk = K3CloudApiSdk()
api_sdk.Init(config_path='../conf.ini', config_node='config')

formId = "PRD_PPBOM"
data = {
    "Ids": "id1,id2"
}

response = api_sdk.Submit(formId, data)
res = json.loads(response)
if res["Result"]["ResponseStatus"]["IsSuccess"]:
    print("提交成功")
```

---

## Audit API (审核)

### Description
本接口用于实现生产用料清单 (PRD_PPBOM) 的审核(Audit)功能

### Python Code Example
```python
from k3cloud_webapi_sdk import K3CloudApiSdk
import json

api_sdk = K3CloudApiSdk()
api_sdk.Init(config_path='../conf.ini', config_node='config')

formId = "PRD_PPBOM"
data = {
    "Ids": "id1,id2"
}

response = api_sdk.Audit(formId, data)
res = json.loads(response)
if res["Result"]["ResponseStatus"]["IsSuccess"]:
    print("审核成功")
```

---

## UnAudit API (反审核)

### Description
本接口用于实现生产用料清单 (PRD_PPBOM) 的反审核(UnAudit)功能

### Python Code Example
```python
from k3cloud_webapi_sdk import K3CloudApiSdk
import json

api_sdk = K3CloudApiSdk()
api_sdk.Init(config_path='../conf.ini', config_node='config')

formId = "PRD_PPBOM"
data = {
    "Ids": "id1,id2"
}

response = api_sdk.UnAudit(formId, data)
res = json.loads(response)
if res["Result"]["ResponseStatus"]["IsSuccess"]:
    print("反审核成功")
```

---

## Field Reference

### Header Fields (单据头)

| Field Name | Field Key | Required | Default | Description |
|------------|-----------|----------|---------|-------------|
| 生产组织 | FPrdOrgId | true | | Production Organization |
| 产品编码 | FMaterialID | true | | Product Material Code |
| 生产订单编号 | FMOBillNO | true | | Production Order Number |
| 单位 | FUnitID | true | | Unit |
| 单据编号 | FBillNo | false | | Bill Number |
| 单据状态 | FDocumentStatus | false | Z | Document Status |
| BOM版本 | FBOMID | false | | BOM Version |
| 产品名称 | FMaterialName | false | | Product Name |
| 规格型号 | FMaterialModel | false | | Specification |
| 数量 | FQty | false | | Quantity |
| 基本单位数量 | FBaseQty | false | | Base Unit Quantity |
| 基本单位 | FBaseUnitID | false | | Base Unit |
| 生产车间 | FWorkshopID | false | | Workshop |
| 生产订单内码 | FMoId | false | | MO Internal ID |
| 生产订单分录内码 | FMOEntryID | false | | MO Entry Internal ID |
| 生产订单行号 | FMOEntrySeq | false | | MO Entry Seq |
| 生产订单状态 | FMOStatus | false | | MO Status |
| 销售订单 | FSALEORDERNO | false | | Sales Order Number |
| 备注 | FDescription | false | | Description |

### Detail Fields (子项明细)

| Field Name | Field Key | Required | Default | Description |
|------------|-----------|----------|---------|-------------|
| 子项类型 | FMaterialType | true | 1 | Material Type |
| 用量类型 | FDosageType | true | 2 | Dosage Type |
| 子项物料编码 | FMaterialID2 | true | | Child Material Code |
| 子项单位 | FUnitID2 | true | | Child Unit |
| 超发控制方式 | FOverControlMode | true | 1 | Over Control Mode |
| 偏置提前期单位 | FTimeUnit2 | true | 1 | Time Unit |
| 发料组织 | FSupplyOrg | true | GetFieldValue(FPrdOrgId) | Supply Organization |
| 预留类型 | FReserveType | true | 2 | Reserve Type |
| 发料方式 | FIssueType | true | 1 | Issue Type |
| 应发数量 | FMustQty | false | | Must Quantity |
| 已领数量 | FPickedQty | false | | Picked Quantity |
| 实领数量 | FACTUALPICKQty | false | | Actual Pick Quantity |
| 未领数量 | FNoPickedQty | false | | Not Picked Quantity |
| 需求数量 | FNeedQty2 | false | | Need Quantity |
| 标准用量 | FStdQty | false | | Standard Quantity |
| 分子 | FNumerator | false | 1 | Numerator |
| 分母 | FDenominator | false | 1 | Denominator |
| 固定损耗 | FFixScrapQty | false | 0 | Fixed Scrap Quantity |
| 变动损耗率% | FScrapRate | false | 0 | Scrap Rate |
| 仓库 | FStockID | false | | Warehouse |
| 仓位 | FStockLOCID | false | | Stock Location |
| 批号 | FLot | false | | Lot Number |
| 货主 | FOwnerID | false | | Owner |
| 货主类型 | FOwnerTypeId | false | BD_OwnerOrg | Owner Type |
| 库存状态 | FStockStatusId | false | KCZT01_SYS | Stock Status |
| 计划跟踪号 | FMTONO | false | | MTO Number |
| 项目编号 | FProjectNO | false | | Project Number |
| 位置号 | FPositionNO | false | | Position Number |
| BOM版本 | FBomId2 | false | | BOM Version |
| 工序 | FOperID | false | | Operation |
| 作业 | FProcessID | false | | Process |
| 备注 | FMEMO1 | false | | Memo |

---

## Reference Links

- [WebAPI保存新增行json模板](https://openapi.open.kingdee.com/ApiDoc)
- [如何修改单据头和单据体字段JSON实例](https://openapi.open.kingdee.com/ApiDoc)
