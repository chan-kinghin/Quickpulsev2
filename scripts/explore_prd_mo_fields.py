#!/usr/bin/env python3
"""
探测生产订单 (PRD_MO) 的字段结构
用于找出"计划跟踪号"等字段的实际字段名
"""

import json
from k3cloud_webapi_sdk.main import K3CloudApiSdk


def print_fields(data, prefix="", keywords=None):
    """递归打印所有字段，高亮包含关键词的字段"""
    if keywords is None:
        keywords = ["track", "mto", "plan", "跟踪", "计划", "order"]

    if isinstance(data, dict):
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key

            # 检查是否包含关键词
            key_lower = key.lower()
            is_highlight = any(kw.lower() in key_lower for kw in keywords)

            if isinstance(value, (dict, list)):
                if is_highlight:
                    print(f">>> {full_key}: (nested)")
                print_fields(value, full_key, keywords)
            else:
                if is_highlight:
                    print(f">>> {full_key}: {value}")
                else:
                    print(f"    {full_key}: {value}")

    elif isinstance(data, list):
        if len(data) > 0:
            print(f"    {prefix}: [列表，共 {len(data)} 项]")
            # 只打印第一项作为示例
            if isinstance(data[0], dict):
                print(f"    {prefix}[0]: (第一项示例)")
                print_fields(data[0], f"{prefix}[0]", keywords)
            else:
                print(f"    {prefix}[0]: {data[0]}")


def main():
    # 初始化 SDK (需要先传入 server_url)
    api_sdk = K3CloudApiSdk("http://flt.hotker.com:8200/k3cloud/")
    api_sdk.Init(config_path='conf.ini', config_node='config')

    # 第一步：先用 ExecuteBillQuery 查询一些生产订单编号
    print("第一步：查询生产订单列表...")
    print("=" * 60)

    query_para = {
        "FormId": "PRD_MO",
        "FieldKeys": "FBillNo,FId",
        "FilterString": [],
        "OrderString": "",
        "TopRowCount": 0,
        "StartRow": 0,
        "Limit": 10,
        "SubSystemId": ""
    }

    query_response = api_sdk.ExecuteBillQuery(query_para)
    query_result = json.loads(query_response)

    print(f"查询到 {len(query_result)} 条生产订单:")
    for item in query_result[:10]:
        print(f"  - 编号: {item[0]}, ID: {item[1]}")

    if not query_result:
        print("没有找到任何生产订单")
        return

    # 使用第一条订单的编号
    bill_number = query_result[0][0]
    print(f"\n第二步：查看订单 {bill_number} 的完整字段...")
    print("=" * 60)

    para = {
        "CreateOrgId": 0,
        "Number": bill_number,
        "Id": "",
        "IsSortBySeq": "false"
    }

    # 调用 View 接口
    response = api_sdk.View("PRD_MO", para)
    res = json.loads(response)

    # 检查返回状态
    if "Result" not in res:
        print(f"错误: 返回数据格式异常")
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return

    result = res["Result"]

    if "ResponseStatus" in result:
        status = result["ResponseStatus"]
        if not status.get("IsSuccess", False):
            print(f"查询失败:")
            print(json.dumps(status, indent=2, ensure_ascii=False))
            return

    # 获取单据数据
    bill_data = result.get("Result", {})

    if not bill_data:
        print("警告: 单据数据为空")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    print("\n所有字段 (>>> 开头为可能的跟踪号相关字段):")
    print("-" * 60)
    print_fields(bill_data)

    # 保存完整数据到文件
    output_file = "prd_mo_fields_output.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(bill_data, f, indent=2, ensure_ascii=False)
    print(f"\n完整数据已保存到: {output_file}")


if __name__ == "__main__":
    main()
