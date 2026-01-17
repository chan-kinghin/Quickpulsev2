# 委外订单 (Outsourcing Order) API Documentation

## Overview
- **Form ID**: `SUB_POORDER`
- **Module**: 生产制造 > 委外管理 > 委外订单
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
| ExecToPlanConfirm | 执行至计划确认 | - | Execute to plan confirm |
| ExecToRelease | 执行至下达 | - | Execute to release |
| ExecToComplete | 执行至完工 | - | Execute to complete |
| ExecToClose | 执行至结案 | - | Execute to close |
| UnExecToPlan | 反执行至计划 | - | Reverse execute to plan |
| UnExecToPlanConfirm | 反执行至计划确认 | - | Reverse execute to plan confirm |
| UnExecToRelease | 反执行至下达 | - | Reverse execute to release |
| UnExecToComplete | 反执行至完工 | - | Reverse execute to complete |
| ForceClose | 强制结案 | - | Force close |

---

## Query API (单据查询)

### Description
本接口用于实现委外订单 (SUB_POORDER) 的单据查询(ExecuteBillQuery)功能

### Request Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| FormId | String | 必录 | SUB_POORDER | 业务对象表单Id |
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
  "FormId": "SUB_POORDER",
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
    "FormId": "SUB_POORDER",
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
本接口用于实现委外订单 (SUB_POORDER) 的查看(View)功能

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

formId = "SUB_POORDER"
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

formId = "SUB_POORDER"
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

formId = "SUB_POORDER"
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

formId = "SUB_POORDER"
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

formId = "SUB_POORDER"
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

formId = "SUB_POORDER"
data = {
    "Ids": "id1,id2"
}

response = api_sdk.UnAudit(formId, data)
res = json.loads(response)
if res["Result"]["ResponseStatus"]["IsSuccess"]:
    print("反审核成功")
```

---

## Notes

- 委外订单 is used for managing outsourced manufacturing orders
- Similar to 生产订单 (Production Order), it supports state machine operations for order execution workflow
- Operations like 执行至计划确认, 执行至下达, 执行至完工, 执行至结案 control the outsourcing order lifecycle
