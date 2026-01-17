# 生产订单 (Production Order) API Documentation

## Overview
- **Form ID**: `PRD_MO`
- **Module**: 生产制造 > 生产管理 > 生产订单（生产管理）
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

---

## Query API (单据查询)

### Description
本接口用于实现生产订单 (PRD_MO) 的单据查询(ExecuteBillQuery)功能

### Request Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| FormId | String | 必录 | PRD_MO | 业务对象表单Id |
| FieldKeys | String | 必录 | | 需查询的字段key集合，格式："key1,key2,..." 注：查询单据体内码需加单据体Key和下划线，如：FEntryKey_FEntryId |
| FilterString | Array | 非必录 | [] | 过滤条件数组 |
| OrderString | String | 非必录 | | 排序字段 |
| TopRowCount | Integer | 非必录 | 0 | 返回总行数 |
| StartRow | Integer | 非必录 | 0 | 开始行索引 |
| Limit | Integer | 非必录 | 2000 | 最大行数，不能超过10000 |
| SubSystemId | String | 非必录 | | 表单所在的子系统内码 |

### FilterString Format
```json
[
  {
    "Left": "(",
    "FieldName": "Field1",
    "Compare": "67",
    "Value": "111",
    "Right": ")",
    "Logic": "0"
  }
]
```

### Response Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| Result | Array | [] | 查询的FieldKeys结果集合 |

### Request Example
```json
{
  "FormId": "PRD_MO",
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
    "FormId": "PRD_MO",
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
本接口用于实现生产订单 (PRD_MO) 的查看(View)功能

### Request Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| formid | String | 必录 | PRD_MO | 业务对象表单Id |
| CreateOrgId | Integer | 非必录 | 0 | 创建者组织内码 |
| Number | String | 非必录 | | 单据编码（使用编码时必录） |
| Id | String | 非必录 | | 表单内码（使用内码时必录） |
| IsSortBySeq | bool | 非必录 | false | 单据体是否按序号排序 |

### Response Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| Result | Object | {} | JSON响应参数 |
| ResponseStatus | Object | {} | 返回结果信息 |
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
formId = "PRD_MO"

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
本接口用于实现生产订单 (PRD_MO) 的保存(Save)功能

### Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| formid | String | 必录 | 业务对象表单Id: PRD_MO |
| data | Object | 必录 | JSON格式单据数据 |

### Python Code Example
```python
from k3cloud_webapi_sdk import K3CloudApiSdk
import json

api_sdk = K3CloudApiSdk()
api_sdk.Init(config_path='../conf.ini', config_node='config')

formId = "PRD_MO"
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
本接口用于实现生产订单 (PRD_MO) 的删除(Delete)功能

### Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| formid | String | 必录 | 业务对象表单Id: PRD_MO |
| data | Object | 必录 | 包含要删除的单据标识 |

### Python Code Example
```python
from k3cloud_webapi_sdk import K3CloudApiSdk
import json

api_sdk = K3CloudApiSdk()
api_sdk.Init(config_path='../conf.ini', config_node='config')

formId = "PRD_MO"
data = {
    "Ids": "id1,id2"  # 或使用 Numbers
}

response = api_sdk.Delete(formId, data)
res = json.loads(response)
if res["Result"]["ResponseStatus"]["IsSuccess"]:
    print("删除成功")
```

---

## Submit API (提交)

### Description
本接口用于实现生产订单 (PRD_MO) 的提交(Submit)功能

### Python Code Example
```python
from k3cloud_webapi_sdk import K3CloudApiSdk
import json

api_sdk = K3CloudApiSdk()
api_sdk.Init(config_path='../conf.ini', config_node='config')

formId = "PRD_MO"
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
本接口用于实现生产订单 (PRD_MO) 的审核(Audit)功能

### Python Code Example
```python
from k3cloud_webapi_sdk import K3CloudApiSdk
import json

api_sdk = K3CloudApiSdk()
api_sdk.Init(config_path='../conf.ini', config_node='config')

formId = "PRD_MO"
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
本接口用于实现生产订单 (PRD_MO) 的反审核(UnAudit)功能

### Python Code Example
```python
from k3cloud_webapi_sdk import K3CloudApiSdk
import json

api_sdk = K3CloudApiSdk()
api_sdk.Init(config_path='../conf.ini', config_node='config')

formId = "PRD_MO"
data = {
    "Ids": "id1,id2"
}

response = api_sdk.UnAudit(formId, data)
res = json.loads(response)
if res["Result"]["ResponseStatus"]["IsSuccess"]:
    print("反审核成功")
```

---

## Reference Links

- [如何通过WebAPI操作生产订单状态机](https://vip.kingdee.com/article/456866098298657280?productLineId=1&isKnowledge=2&lang=zh-CN)
