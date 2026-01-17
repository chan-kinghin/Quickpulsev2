# 生产订单(PRD_MO)

最新更新时间：2023-03-09

单据查询

接口描述

本接口用于实现生产订单 (PRD_MO) 的单据查询(ExecuteBillQuery)功能

请求参数

|   |   |   |   |   |
|---|---|---|---|---|
|data|Object|必录||JSON格式数据（详情参考JSON格式数据）（必录）|
|FormId|String|必录|PRD_MO|业务对象表单Id（必录）|
|FieldKeys|String|必录||需查询的字段key集合，字符串类型，格式："key1,key2,..."（必录） 注（查询单据体内码,需加单据体Key和下划线,如：FEntryKey_FEntryId）|
|FilterString|Array|非必录|[]|过滤条件，数组类型，如：[{"Left":"(","FieldName":"Field1","Compare":"67","Value":"111","Right":")","Logic":"0"},{"Left":"(","FieldName":"Field2","Compare":"67","Value":"222","Right":")","Logic":"0"}]|
|OrderString|String|非必录||排序字段，字符串类型（非必录）|
|TopRowCount|Integer|非必录|0|返回总行数，整型（非必录）|
|StartRow|Integer|非必录|0|开始行索引，整型（非必录）|
|Limit|Integer|非必录|2000|最大行数，整型，不能超过10000（非必录）|
|SubSystemId|String|非必录||表单所在的子系统内码，字符串类型（非必录）|

响应参数

|   |   |   |   |
|---|---|---|---|
|Result|Array|[]|查询的FieldKeys结果集合|

请求示例

标准请求示例

copy

{

FieldKeys:""

FilterString:[]

FormId:""

Limit:2000

OrderString:""

StartRow:0

SubSystemId:""

TopRowCount:0

}

响应示例

copy

"[["FValue1","FValue2",...],["FValue1","FValue2",...],...]"

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
para =  {"FormId":"","FieldKeys":"","FilterString":[],"OrderString":"","TopRowCount":0,"StartRow":0,"Limit":2000,"SubSystemId":""}
# 调用接口
response = api_sdk.ExecuteBillQuery(para)
print("接口返回结果：" + response)
res = json.loads(response)
if len(res) > 0:
	return True
return False
```

API工具

帮助文档

[如何通过WebAPI操作生产订单状态机](https://vip.kingdee.com/article/456866098298657280?productLineId=1&isKnowledge=2&lang=zh-CN)