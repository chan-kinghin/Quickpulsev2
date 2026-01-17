# 生产入库单 (Production Receipt) API Documentation

## Overview
- **Form ID**: `PRD_INSTOCK`
- **Module**: 生产制造 > 生产管理 > 生产入库单
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
本接口用于实现生产入库单 (PRD_INSTOCK) 的单据查询(ExecuteBillQuery)功能

### Request Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| FormId | String | 必录 | PRD_INSTOCK | 业务对象表单Id |
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
  "FormId": "PRD_INSTOCK",
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
    "FormId": "PRD_INSTOCK",
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
本接口用于实现生产入库单 (PRD_INSTOCK) 的查看(View)功能

### Request Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| formid | String | 必录 | PRD_INSTOCK | 业务对象表单Id |
| CreateOrgId | Integer | 非必录 | 0 | 创建者组织内码 |
| Number | String | 非必录 | | 单据编码（使用编码时必录） |
| Id | String | 非必录 | | 表单内码（使用内码时必录） |
| IsSortBySeq | bool | 非必录 | false | 单据体是否按序号排序 |

### Response Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| Result | Object | {} | JSON响应参数 |
| ResponseStatus | Object | {} | 返回结果信息 |
| IsSuccess | bool | false | 操作状态 |
| Result | Object | {} | 单据数据包，单据完整数据内容 |

### Request Example
```json
{
  "CreateOrgId": 0,
  "Number": "",
  "Id": "",
  "IsSortBySeq": "false"
}
```

### Response Example
```json
{
  "Result": {
    "ResponseStatus": {
      "IsSuccess": "true"
    },
    "Result": "{...}"
  }
}
```

### Python Code Example
```python
from k3cloud_webapi_sdk import K3CloudApiSdk
import json
import logging

# 读取配置，初始化SDK
api_sdk = K3CloudApiSdk()
api_sdk.Init(config_path='../conf.ini', config_node='config')

# 请求参数
para = {
    "CreateOrgId": 0,
    "Number": "",
    "Id": "",
    "IsSortBySeq": "false"
}

# 业务对象标识
formId = "PRD_INSTOCK"

# 调用接口
response = api_sdk.View(formId, para)
print("接口返回结果：" + response)

# 对返回结果进行解析和校验
res = json.loads(response)
if res["Result"]["ResponseStatus"]["IsSuccess"]:
    return True
else:
    logging.error(res)
    return False
```

---

## Save API (保存)

### Description
本接口用于实现生产入库单 (PRD_INSTOCK) 的保存(Save)功能

### Python Code Example
```python
from k3cloud_webapi_sdk import K3CloudApiSdk
import json

api_sdk = K3CloudApiSdk()
api_sdk.Init(config_path='../conf.ini', config_node='config')

formId = "PRD_INSTOCK"
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

### Description
本接口用于实现生产入库单 (PRD_INSTOCK) 的删除(Delete)功能

### Python Code Example
```python
from k3cloud_webapi_sdk import K3CloudApiSdk
import json

api_sdk = K3CloudApiSdk()
api_sdk.Init(config_path='../conf.ini', config_node='config')

formId = "PRD_INSTOCK"
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

### Description
本接口用于实现生产入库单 (PRD_INSTOCK) 的提交(Submit)功能

### Python Code Example
```python
from k3cloud_webapi_sdk import K3CloudApiSdk
import json

api_sdk = K3CloudApiSdk()
api_sdk.Init(config_path='../conf.ini', config_node='config')

formId = "PRD_INSTOCK"
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
本接口用于实现生产入库单 (PRD_INSTOCK) 的审核(Audit)功能

### Python Code Example
```python
from k3cloud_webapi_sdk import K3CloudApiSdk
import json

api_sdk = K3CloudApiSdk()
api_sdk.Init(config_path='../conf.ini', config_node='config')

formId = "PRD_INSTOCK"
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
本接口用于实现生产入库单 (PRD_INSTOCK) 的反审核(UnAudit)功能

### Python Code Example
```python
from k3cloud_webapi_sdk import K3CloudApiSdk
import json

api_sdk = K3CloudApiSdk()
api_sdk.Init(config_path='../conf.ini', config_node='config')

formId = "PRD_INSTOCK"
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
| 仓库 | FStockId0 | false | | Stock/Warehouse |
| 货主 | FOwnerId0 | true | | Owner |
| 入库组织 | FStockOrgId | true | | Stock Organization |
| 单据类型 | FBillType | true | de29f16214744c21b374044d629595f2 | Bill Type |
| 生产组织 | FPrdOrgId | true | GetOrgUnit(@CurrentOrgUnit) | Production Organization |
| 日期 | FDate | true | GetDate(yyyy-MM-dd,@CurrentDate) | Date |
| 单据编号 | FBillNo | false | | Bill Number |
| 单据状态 | FDocumentStatus | false | Z | Document Status |
| 作废状态 | FCancelStatus | false | A | Cancel Status |
| 货主类型 | FOwnerTypeId0 | false | BD_OwnerOrg | Owner Type |
| 本位币 | FCurrId | false | | Currency |
| 车间 | FWorkShopId | false | | Workshop |
| 备注 | FDescription | false | | Description |

### Detail Fields (明细)

| Field Name | Field Key | Required | Default | Description |
|------------|-----------|----------|---------|-------------|
| 物料编码 | FMaterialId | true | | Material Code |
| 货主 | FOwnerId | true | | Owner |
| 保管者 | FKeeperId | true | | Keeper |
| 单位 | FUnitID | true | | Unit |
| 货主类型 | FOwnerTypeId | true | BD_OwnerOrg | Owner Type |
| 保管者类型 | FKeeperTypeId | true | | Keeper Type |
| 基本单位 | FBaseUnitId | true | | Base Unit |
| 入库类型 | FInStockType | true | 1 | Instock Type |
| 生产订单编号 | FMoBillNo | true | | Production Order Number |
| 库存状态 | FStockStatusId | true | | Stock Status |
| 仓库 | FStockId | true | | Warehouse |
| 实收数量 | FRealQty | false | | Actual Quantity |
| 应收数量 | FMustQty | false | 0 | Expected Quantity |
| 批号 | FLot | false | | Lot Number |
| 生产日期 | FProduceDate | false | | Production Date |
| 有效期至 | FExpiryDate | false | | Expiry Date |
| 计划跟踪号 | FMtoNo | false | | MTO Number |
| BOM版本 | FBomId | false | | BOM Version |
| 仓位 | FStockLocId | false | | Stock Location |
| 备注 | FMemo | false | | Memo |

---

## Reference Links

- [构建生产入库单的Json数据需注意的点](https://openapi.open.kingdee.com/ApiDoc)
- [如何在填写WebAPI测试数据时调出选单](https://openapi.open.kingdee.com/ApiDoc)
