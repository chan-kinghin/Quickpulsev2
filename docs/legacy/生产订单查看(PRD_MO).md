
最新更新时间：2023-03-09

查看

接口描述

本接口用于实现生产订单 (PRD_MO) 的查看(View)功能

请求参数

|   |   |   |   |   |
|---|---|---|---|---|
|formid|String|必录|PRD_MO|业务对象表单Id，字符串类型（必录）|
|data|Object|必录||JSON格式数据（详情参考JSON格式数据）（必录）|
|CreateOrgId|Integer|非必录|0|创建者组织内码（非必录）|
|Number|String|非必录||单据编码，字符串类型（使用编码时必录）|
|Id|String|非必录||表单内码（使用内码时必录）|
|IsSortBySeq|bool|非必录|false|单据体是否按序号排序，默认false|

响应参数

|   |   |   |   |
|---|---|---|---|
|Result|Object|{}|JSON响应参数描述|
|ResponseStatus|Object|{}|返回结果信息|
|Result|Object|{}|单据数据包,单据完整数据内容|

请求示例

标准请求示例

copy

{

CreateOrgId:0

Id:""

IsSortBySeq:"false"

Number:""

}

响应示例

copy

{

Result:{

ResponseStatus:{

IsSuccess:"false"

}

Result:"{}"

}

}

代码示例

JAVA

C#

PHP

Python

```python

# 注意 1：此处不再使用参数形式传入用户名及密码等敏感信息，改为在登录配置文件中设置。
# 注意 2：必须先配置第三方系统登录授权信息后，再进行业务操作，详情参考各语言版本SDK介绍中的登录配置文件说明。
# 读取配置，初始化SDK
api_sdk = K3CloudApiSdk()
api_sdk.Init(config_path='../conf.ini', config_node='config')
# 请求参数
para =  {"CreateOrgId":0,"Number":"","Id":"","IsSortBySeq":"false"}
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

API工具

帮助文档

[如何通过WebAPI操作生产订单状态机](https://vip.kingdee.com/article/456866098298657280?productLineId=1&isKnowledge=2&lang=zh-CN)