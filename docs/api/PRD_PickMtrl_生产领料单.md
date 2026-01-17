# 生产领料单 (Production Material Requisition) API Documentation

## Overview
- **Form ID**: `PRD_PickMtrl`
- **Module**: 生产制造 > 生产管理 > 生产领料单
- **Last Updated**: 2023-03-09

## Available Operations

| Operation | Chinese | Method | Description |
|-----------|---------|--------|-------------|
| Query | 单据查询 | ExecuteBillQuery | Query/List documents |
| View | 查看 | View | View single document details |
| Save | 保存 | Save | Save document |
| Delete | 删除 | Delete | Delete document |
| Submit | 提交 | Submit | Submit for approval |
| Audit | 审核 | Audit | Approve document |
| Unaudit | 反审核 | UnAudit | Reverse approval |
| Draft | 暂存 | Draft | Save as draft |
| Push | 下推 | Push | Push to downstream document |
| Void | 作废 | Allocate | Void document |
| Unvoid | 反作废 | - | Reverse void |
| BatchSave | 批量保存 | BatchSave | Batch save documents |

---

## Query API (单据查询)

### Description
本接口用于实现生产领料单 (PRD_PickMtrl) 的单据查询(ExecuteBillQuery)功能

### Request Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| FormId | String | 必录 | PRD_PickMtrl | 业务对象表单Id |
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
  "FormId": "PRD_PickMtrl",
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
    "FormId": "PRD_PickMtrl",
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
本接口用于实现生产领料单 (PRD_PickMtrl) 的查看(View)功能

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

formId = "PRD_PickMtrl"
response = api_sdk.View(formId, para)
print("接口返回结果：" + response)

res = json.loads(response)
if res["Result"]["ResponseStatus"]["IsSuccess"]:
    return True
else:
    return False
```

---

## Save API (保存)

### Python Code Example
```python
from k3cloud_webapi_sdk import K3CloudApiSdk
import json

api_sdk = K3CloudApiSdk()
api_sdk.Init(config_path='../conf.ini', config_node='config')

formId = "PRD_PickMtrl"
data = {
    "Model": {
        # 单据数据
    }
}

response = api_sdk.Save(formId, data)
res = json.loads(response)
if res["Result"]["ResponseStatus"]["IsSuccess"]:
    print("保存成功")
```

---

## Delete API (删除)

### Python Code Example
```python
from k3cloud_webapi_sdk import K3CloudApiSdk
import json

api_sdk = K3CloudApiSdk()
api_sdk.Init(config_path='../conf.ini', config_node='config')

formId = "PRD_PickMtrl"
data = {
    "Ids": "id1,id2"
}

response = api_sdk.Delete(formId, data)
res = json.loads(response)
if res["Result"]["ResponseStatus"]["IsSuccess"]:
    print("删除成功")
```

---

## Submit API (提交)

### Python Code Example
```python
from k3cloud_webapi_sdk import K3CloudApiSdk
import json

api_sdk = K3CloudApiSdk()
api_sdk.Init(config_path='../conf.ini', config_node='config')

formId = "PRD_PickMtrl"
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

### Python Code Example
```python
from k3cloud_webapi_sdk import K3CloudApiSdk
import json

api_sdk = K3CloudApiSdk()
api_sdk.Init(config_path='../conf.ini', config_node='config')

formId = "PRD_PickMtrl"
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

### Python Code Example
```python
from k3cloud_webapi_sdk import K3CloudApiSdk
import json

api_sdk = K3CloudApiSdk()
api_sdk.Init(config_path='../conf.ini', config_node='config')

formId = "PRD_PickMtrl"
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
| 单据类型 | FBillType | true | f4f46eb78a7149b1b7e4de98586acb67 | Bill Type |
| 发料组织 | FStockOrgId | true | | Stock Organization |
| 日期 | FDate | true | GetDate(yyyy-MM-dd,@CurrentDate) | Date |
| 生产组织 | FPrdOrgId | true | GetOrgUnit(@CurrentOrgUnit) | Production Organization |
| 单据编号 | FBillNo | false | | Bill Number |
| 单据状态 | FDocumentStatus | false | Z | Document Status |
| 作废状态 | FCancelStatus | false | A | Cancel Status |
| 领料人 | FPickerId | false | | Picker |
| 仓管员 | FSTOCKERID | false | | Warehouse Keeper |
| 仓库 | FStockId0 | false | | Warehouse |
| 本位币 | FCurrId | false | | Currency |
| 货主 | FOwnerId0 | false | | Owner |
| 货主类型 | FOwnerTypeId0 | false | BD_OwnerOrg | Owner Type |
| 生产车间 | FWorkShopId | false | | Workshop |
| 备注 | FDescription | false | | Description |
| 跨组织业务类型 | FTransferBizType | false | OverOrgPick | Transfer Business Type |

### Detail Fields (明细)

| Field Name | Field Key | Required | Default | Description |
|------------|-----------|----------|---------|-------------|
| 产品货主类型 | FParentOwnerTypeId | true | | Parent Owner Type |
| 主库存单位 | FStockUnitId | true | | Stock Unit |
| 货主 | FOwnerId | true | | Owner |
| 单位 | FUnitID | true | | Unit |
| 生产订单编号 | FMoBillNo | true | | MO Bill Number |
| 货主类型 | FOwnerTypeId | true | BD_OwnerOrg | Owner Type |
| 产品货主 | FParentOwnerId | true | | Parent Owner |
| 保管者 | FKeeperId | true | | Keeper |
| 仓库 | FStockId | true | | Warehouse |
| 物料编码 | FMaterialId | true | | Material Code |
| 基本单位 | FBaseUnitId | true | | Base Unit |
| 库存状态 | FStockStatusId | true | | Stock Status |
| 保管者类型 | FKeeperTypeId | true | BD_KeeperOrg | Keeper Type |
| 预留类型 | FReserveType | false | 2 | Reserve Type |
| 申请数量 | FAppQty | false | | Apply Quantity |
| 实发数量 | FActualQty | false | | Actual Quantity |
| 基本单位实发数量 | FBaseActualQty | false | | Base Actual Quantity |
| 基本单位申请数量 | FBaseAppQty | false | | Base Apply Quantity |
| 批号 | FLot | false | | Lot Number |
| 仓位 | FStockLocId | false | | Stock Location |
| 计划跟踪号 | FMtoNo | false | | MTO Number |
| 生产订单内码 | FMoId | false | 1 | MO Internal ID |
| 生产订单分录内码 | FMoEntryId | false | 1 | MO Entry Internal ID |
| 生产订单行号 | FMoEntrySeq | false | 1 | MO Entry Seq |
| 用料清单编号 | FPPBomBillNo | false | | PPBOM Bill Number |
| 用料清单分录内码 | FPPBomEntryId | false | 1 | PPBOM Entry Internal ID |
| BOM版本 | FBomId | false | | BOM Version |
| 产品编码 | FParentMaterialId | false | | Parent Material Code |
| 项目编号 | FProjectNo | false | | Project Number |
| 有效期至 | FExpiryDate | false | | Expiry Date |
| 生产日期 | FProduceDate | false | | Production Date |
| 备注 | FEntrtyMemo | false | | Entry Memo |

### Serial Number Sub-Table (序列号子单据体)

| Field Name | Field Key | Required | Default | Description |
|------------|-----------|----------|---------|-------------|
| 请检关联标志 | FIsAppInspect | true | 0 | Inspection Link Flag |
| 序列号 | FSerialNo | false | | Serial Number |
| 序列号 | FSerialId | false | | Serial ID |
| 备注 | FSerialNote | false | | Serial Note |

---

## Reference Links

- [如何通过WebAPI构建生产领料单](https://openapi.open.kingdee.com/ApiDoc)
