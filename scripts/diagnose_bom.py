#!/usr/bin/env python3
"""Diagnose BOM data for a given MTO number."""

import json
import sys
sys.path.insert(0, "/Users/kinghinchan/Documents/Cursor Projects/Quickpulsev2/Quickpulsev2")

from k3cloud_webapi_sdk.main import K3CloudApiSdk


def query(api_sdk, params):
    """Execute query and parse JSON result."""
    result = api_sdk.ExecuteBillQuery(params)
    if isinstance(result, str):
        return json.loads(result)
    return result


def main():
    api_sdk = K3CloudApiSdk("http://flt.hotker.com:8200/k3cloud/")
    api_sdk.Init(config_path='conf.ini', config_node='config')

    # Use AS MTO number
    mto = "AS2510034"  # AS开头的MTO号

    print(f"{'='*60}")
    print(f"诊断 MTO: {mto}")
    print(f"{'='*60}")

    # 1. 查生产订单
    mo_params = {
        "FormId": "PRD_MO",
        "FieldKeys": "FBillNo,FMTONo,FMaterialId.FNumber,FMaterialId.FName,FQty,FStatus",
        "FilterString": f"FMTONo='{mto}'",
        "Limit": 100
    }
    mo_result = query(api_sdk, mo_params)

    print(f"\n【1. 生产订单 PRD_MO】共 {len(mo_result)} 条")
    print("-" * 60)

    for row in mo_result[:5]:  # Only show first 5
        if isinstance(row, list) and len(row) >= 6:
            print(f"  订单号: {row[0]}")
            print(f"  MTO: {row[1]}")
            print(f"  物料: {row[2]} - {row[3]}")
            print(f"  数量: {row[4]}, 状态: {row[5]}")
            print()

    if not mo_result:
        print("  ❌ 没有找到生产订单!")
        return

    # 2. 用第一个订单号查BOM (不带辅助属性字段，因为FAuxPropId不存在)
    bill_no = mo_result[0][0]
    bom_params = {
        "FormId": "PRD_PPBOM",
        "FieldKeys": ",".join([
            "FMOBillNO",
            "FMaterialId.FNumber",
            "FMaterialId.FName",
            "FMaterialId.FSpecification",
            "FMaterialType",  # 1=自制, 2=外购, 3=委外
            "FMustQty",
            "FPickedQty",
            "FNoPickedQty",
            "FMTONO",
        ]),
        "FilterString": f"FMOBillNO='{bill_no}'",
        "Limit": 500
    }

    print(f"\n【2. BOM子项 PRD_PPBOM】查询订单: {bill_no}")
    print("-" * 60)

    bom_result = query(api_sdk, bom_params)

    type_names = {1: "自制", 2: "外购", 3: "委外"}
    type_counts = {1: 0, 2: 0, 3: 0, 0: 0}

    print(f"  共 {len(bom_result)} 条子项")
    print()

    for i, row in enumerate(bom_result[:30]):  # 只显示前30条
        # Debug: show row length
        if i == 0:
            print(f"  [DEBUG] 字段数: {len(row)}, 内容: {row}")
            print()

        # Handle variable field count
        mat_type = row[4] if len(row) > 4 and row[4] else 0
        type_counts[mat_type] = type_counts.get(mat_type, 0) + 1
        type_name = type_names.get(mat_type, f"未知({mat_type})")
        aux = row[9] if len(row) > 9 else ""

        mat_code = row[1] if len(row) > 1 else "-"
        mat_name = row[2][:25] if len(row) > 2 and row[2] else "-"
        spec = row[3][:30] if len(row) > 3 and row[3] else "-"
        need_qty = row[5] if len(row) > 5 else "-"
        pick_qty = row[6] if len(row) > 6 else "-"
        unpick_qty = row[7] if len(row) > 7 else "-"

        print(f"  [{i+1}] {mat_code} | {type_name} | {mat_name}")
        print(f"       规格: {spec}")
        print(f"       辅助属性: {aux if aux else '-'}")
        print(f"       需求: {need_qty}, 已领: {pick_qty}, 未领: {unpick_qty}")
        print()

    if len(bom_result) > 30:
        print(f"  ... 还有 {len(bom_result) - 30} 条未显示")

    # Count all types (overwrite the partial counts from display loop)
    type_counts = {1: 0, 2: 0, 3: 0, 0: 0}
    for row in bom_result:
        mat_type = row[4] if len(row) > 4 and row[4] else 0
        type_counts[mat_type] = type_counts.get(mat_type, 0) + 1

    print(f"\n【3. 物料类型统计】")
    print("-" * 60)
    for t in [1, 2, 3]:
        name = type_names.get(t, "未知")
        count = type_counts.get(t, 0)
        status = "✅" if count > 0 else "❌"
        print(f"  {status} {name} (FMaterialType={t}): {count} 条")

    if type_counts.get(0, 0) > 0:
        print(f"  ⚠️ 未知类型: {type_counts[0]} 条")

    # 3. 检查采购订单
    print(f"\n【4. 采购订单 PUR_PurchaseOrder】")
    print("-" * 60)
    po_params = {
        "FormId": "PUR_PurchaseOrder",
        "FieldKeys": "FBillNo,FMtoNo,FMaterialId.FNumber,FMaterialId.FName,FQty,FStockInQty,FRemainStockInQty",
        "FilterString": f"FMtoNo='{mto}'",
        "Limit": 50
    }
    po_result = query(api_sdk, po_params)
    print(f"  共 {len(po_result)} 条")
    for row in po_result[:10]:
        print(f"  {row[0]} | {row[2]} | {row[3][:20] if row[3] else '-'} | 订单:{row[4]} 入库:{row[5]} 未入:{row[6]}")

    # 4. 检查委外订单
    print(f"\n【5. 委外订单 SUB_POORDER】")
    print("-" * 60)
    sub_params = {
        "FormId": "SUB_POORDER",
        "FieldKeys": "FBillNo,FMtoNo,FMaterialId.FNumber,FMaterialId.FName,FQty,FStockInQty,FNoStockInQty",
        "FilterString": f"FMtoNo='{mto}'",
        "Limit": 50
    }
    sub_result = query(api_sdk, sub_params)
    print(f"  共 {len(sub_result)} 条")
    for row in sub_result[:10]:
        if len(row) >= 7:
            print(f"  {row[0]} | {row[2]} | {row[3][:20] if row[3] else '-'} | 订单:{row[4]} 入库:{row[5]} 未入:{row[6]}")
        else:
            print(f"  [DEBUG] 数据格式异常: {row}")


if __name__ == "__main__":
    main()
