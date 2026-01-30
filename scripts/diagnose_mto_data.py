#!/usr/bin/env python3
"""
诊断 MTO 取数问题的脚本

用法: python scripts/diagnose_mto_data.py [MTO号] [物料编码]
示例: python scripts/diagnose_mto_data.py DK25B294S 07.32.002

功能:
1. 查询金蝶各表单的原始数据
2. 对比 aux_prop_id 是否一致
3. 计算汇总值，与 QuickPulse 预期对比
"""

import json
import sys
from collections import defaultdict
from decimal import Decimal

sys.path.insert(0, "/Users/kinghinchan/Documents/Cursor Projects/Quickpulsev2/Quickpulsev2")

from k3cloud_webapi_sdk.main import K3CloudApiSdk


def query(api_sdk, params):
    """Execute query and parse JSON result."""
    result = api_sdk.ExecuteBillQuery(params)
    if isinstance(result, str):
        return json.loads(result)
    return result


def print_section(title: str):
    """Print a section header."""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def print_subsection(title: str):
    """Print a subsection header."""
    print(f"\n--- {title} ---")


def main():
    # Default values
    mto = sys.argv[1] if len(sys.argv) > 1 else "DK25B294S"
    target_material = sys.argv[2] if len(sys.argv) > 2 else "07.32.002"

    print_section(f"MTO 取数诊断: {mto}")
    print(f"目标物料: {target_material}")

    # Initialize Kingdee API
    api_sdk = K3CloudApiSdk("http://flt.hotker.com:8200/k3cloud/")
    api_sdk.Init(config_path='conf.ini', config_node='config')

    # =========================================================================
    # 1. 销售订单 SAL_SaleOrder
    # =========================================================================
    print_section("1. 销售订单 SAL_SaleOrder")

    so_params = {
        "FormId": "SAL_SaleOrder",
        "FieldKeys": ",".join([
            "FBillNo",
            "FMtoNo",
            "FMaterialId.FNumber",
            "FMaterialId.FName",
            "FAuxPropId",
            "FQty",
            "FCustId.FName",
            "FDeliveryDate",
        ]),
        "FilterString": f"FMtoNo='{mto}'",
        "Limit": 500
    }
    so_result = query(api_sdk, so_params)

    print(f"查询条件: FMtoNo='{mto}'")
    print(f"总记录数: {len(so_result)}")

    # Filter for target material
    so_target = [r for r in so_result if len(r) > 2 and r[2] == target_material]
    print(f"目标物料 {target_material} 记录数: {len(so_target)}")

    so_total_qty = Decimal(0)
    so_aux_props = set()

    print_subsection(f"物料 {target_material} 明细")
    for row in so_target:
        bill_no = row[0]
        mat_code = row[2]
        mat_name = row[3][:30] if row[3] else ""
        aux_prop_id = row[4]
        qty = Decimal(str(row[5] or 0))
        customer = row[6][:20] if row[6] else ""

        so_total_qty += qty
        so_aux_props.add(aux_prop_id)

        print(f"  单号: {bill_no}")
        print(f"  物料: {mat_code} | {mat_name}")
        print(f"  辅助属性ID: {aux_prop_id}")
        print(f"  数量: {qty}")
        print(f"  客户: {customer}")
        print()

    print(f">>> SAL_SaleOrder 汇总: qty={so_total_qty}, aux_prop_ids={so_aux_props}")

    # =========================================================================
    # 2. 销售出库 SAL_OUTSTOCK
    # =========================================================================
    print_section("2. 销售出库 SAL_OUTSTOCK")

    outstock_params = {
        "FormId": "SAL_OUTSTOCK",
        "FieldKeys": ",".join([
            "FBillNo",
            "FMTONO",
            "FMaterialId.FNumber",
            "FMaterialId.FName",
            "FAuxPropId",
            "FRealQty",
            "FMustQty",
        ]),
        "FilterString": f"FMTONO='{mto}'",
        "Limit": 500
    }
    outstock_result = query(api_sdk, outstock_params)

    print(f"查询条件: FMTONO='{mto}'")
    print(f"总记录数: {len(outstock_result)}")

    outstock_target = [r for r in outstock_result if len(r) > 2 and r[2] == target_material]
    print(f"目标物料 {target_material} 记录数: {len(outstock_target)}")

    outstock_total_qty = Decimal(0)
    outstock_aux_props = set()
    outstock_by_aux = defaultdict(Decimal)

    print_subsection(f"物料 {target_material} 明细")
    for row in outstock_target:
        bill_no = row[0]
        mat_code = row[2]
        aux_prop_id = row[4]
        real_qty = Decimal(str(row[5] or 0))

        outstock_total_qty += real_qty
        outstock_aux_props.add(aux_prop_id)
        outstock_by_aux[aux_prop_id] += real_qty

        print(f"  单号: {bill_no} | 辅助属性ID: {aux_prop_id} | 实发: {real_qty}")

    print()
    print(f">>> SAL_OUTSTOCK 汇总: real_qty={outstock_total_qty}")
    print(f">>> 按辅助属性分组: {dict(outstock_by_aux)}")
    print(f">>> aux_prop_ids: {outstock_aux_props}")

    # =========================================================================
    # 3. 生产入库 PRD_INSTOCK
    # =========================================================================
    print_section("3. 生产入库 PRD_INSTOCK")

    instock_params = {
        "FormId": "PRD_INSTOCK",
        "FieldKeys": ",".join([
            "FBillNo",
            "FMtoNo",
            "FMaterialId.FNumber",
            "FMaterialId.FName",
            "FAuxPropId",
            "FRealQty",
            "FMustQty",
            "FMoBillNo",
        ]),
        "FilterString": f"FMtoNo='{mto}'",
        "Limit": 2000  # Increased from 500 to avoid truncation
    }
    instock_result = query(api_sdk, instock_params)

    print(f"查询条件: FMtoNo='{mto}'")
    print(f"总记录数: {len(instock_result)}")

    instock_target = [r for r in instock_result if len(r) > 2 and r[2] == target_material]
    print(f"目标物料 {target_material} 记录数: {len(instock_target)}")

    instock_total_qty = Decimal(0)
    instock_aux_props = set()
    instock_by_aux = defaultdict(Decimal)

    print_subsection(f"物料 {target_material} 明细")
    for row in instock_target:
        bill_no = row[0]
        mat_code = row[2]
        aux_prop_id = row[4]
        real_qty = Decimal(str(row[5] or 0))
        mo_bill_no = row[7] if len(row) > 7 else ""

        instock_total_qty += real_qty
        instock_aux_props.add(aux_prop_id)
        instock_by_aux[aux_prop_id] += real_qty

        print(f"  单号: {bill_no} | 辅助属性ID: {aux_prop_id} | 实收: {real_qty} | 源单: {mo_bill_no}")

    print()
    print(f">>> PRD_INSTOCK 汇总: real_qty={instock_total_qty}")
    print(f">>> 按辅助属性分组: {dict(instock_by_aux)}")
    print(f">>> aux_prop_ids: {instock_aux_props}")

    # =========================================================================
    # 4. 生产订单 PRD_MO
    # =========================================================================
    print_section("4. 生产订单 PRD_MO")

    mo_params = {
        "FormId": "PRD_MO",
        "FieldKeys": ",".join([
            "FBillNo",
            "FMTONo",
            "FMaterialId.FNumber",
            "FMaterialId.FName",
            "FQty",
            "FStatus",
        ]),
        "FilterString": f"FMTONo='{mto}'",
        "Limit": 500
    }
    mo_result = query(api_sdk, mo_params)

    print(f"查询条件: FMTONo='{mto}'")
    print(f"总记录数: {len(mo_result)}")

    mo_target = [r for r in mo_result if len(r) > 2 and r[2] == target_material]
    print(f"目标物料 {target_material} 记录数: {len(mo_target)}")

    mo_total_qty = Decimal(0)

    print_subsection(f"物料 {target_material} 明细")
    for row in mo_target:
        bill_no = row[0]
        mat_code = row[2]
        mat_name = row[3][:30] if row[3] else ""
        qty = Decimal(str(row[4] or 0))
        status = row[5]

        mo_total_qty += qty

        print(f"  单号: {bill_no} | {mat_code} | 数量: {qty} | 状态: {status}")

    print()
    print(f">>> PRD_MO 汇总: qty={mo_total_qty}")

    # =========================================================================
    # 5. 领料单 PRD_PickMtrl
    # =========================================================================
    print_section("5. 领料单 PRD_PickMtrl")

    pick_params = {
        "FormId": "PRD_PickMtrl",
        "FieldKeys": ",".join([
            "FBillNo",
            "FMTONO",
            "FMaterialId.FNumber",
            "FMaterialId.FName",
            "FAppQty",
            "FActualQty",
        ]),
        "FilterString": f"FMTONO='{mto}'",
        "Limit": 500
    }
    pick_result = query(api_sdk, pick_params)

    print(f"查询条件: FMTONO='{mto}'")
    print(f"总记录数: {len(pick_result)}")

    pick_target = [r for r in pick_result if len(r) > 2 and r[2] == target_material]
    print(f"目标物料 {target_material} 记录数: {len(pick_target)}")

    pick_app_total = Decimal(0)
    pick_actual_total = Decimal(0)

    print_subsection(f"物料 {target_material} 明细")
    for row in pick_target:
        bill_no = row[0]
        mat_code = row[2]
        app_qty = Decimal(str(row[4] or 0))
        actual_qty = Decimal(str(row[5] or 0))

        pick_app_total += app_qty
        pick_actual_total += actual_qty

        print(f"  单号: {bill_no} | 申请: {app_qty} | 实发: {actual_qty}")

    print()
    print(f">>> PRD_PickMtrl 汇总: app_qty={pick_app_total}, actual_qty={pick_actual_total}")

    # =========================================================================
    # 诊断总结
    # =========================================================================
    print_section("诊断总结")

    print(f"MTO: {mto}")
    print(f"物料: {target_material}")
    print()

    print("【各表单汇总值】")
    print(f"  SAL_SaleOrder.FQty (需求量):     {so_total_qty}")
    print(f"  PRD_MO.FQty (生产订单数量):      {mo_total_qty}")
    print(f"  PRD_INSTOCK.FRealQty (入库数):   {instock_total_qty}")
    print(f"  SAL_OUTSTOCK.FRealQty (出库数):  {outstock_total_qty}")
    print(f"  PRD_PickMtrl.FActualQty (领料):  {pick_actual_total}")
    print()

    print("【辅助属性ID对比】")
    print(f"  SAL_SaleOrder 的 aux_prop_ids:   {so_aux_props}")
    print(f"  PRD_INSTOCK 的 aux_prop_ids:     {instock_aux_props}")
    print(f"  SAL_OUTSTOCK 的 aux_prop_ids:    {outstock_aux_props}")

    # Check for mismatches
    if so_aux_props and instock_aux_props:
        common = so_aux_props & instock_aux_props
        if not common:
            print()
            print("  ⚠️  警告: SAL_SaleOrder 和 PRD_INSTOCK 的 aux_prop_id 完全不一致!")
            print("     这会导致入库数匹配失败，显示为0")
        elif common != so_aux_props:
            print()
            print(f"  ⚠️  警告: 部分 aux_prop_id 不一致")
            print(f"     公共: {common}")
            print(f"     仅销售订单: {so_aux_props - instock_aux_props}")
            print(f"     仅入库单: {instock_aux_props - so_aux_props}")

    print()
    print("【QuickPulse 预期计算值 (基于当前逻辑)】")

    # Current logic uses (material_code, aux_prop_id) matching
    # For finished goods (07.xx), it gets required_qty from SAL_SaleOrder
    # and receipt_qty from PRD_INSTOCK with aux matching

    matched_receipt = Decimal(0)
    for aux in so_aux_props:
        matched_receipt += instock_by_aux.get(aux, Decimal(0))

    matched_delivery = Decimal(0)
    for aux in so_aux_props:
        matched_delivery += outstock_by_aux.get(aux, Decimal(0))

    print(f"  required_qty (需求量): {so_total_qty} (来自 SAL_SaleOrder)")
    print(f"  receipt_qty (入库数):  {matched_receipt} (PRD_INSTOCK 按 aux_prop_id 匹配)")
    print(f"  picked_qty (已领数):   {matched_delivery} (SAL_OUTSTOCK 按 aux_prop_id 匹配)")
    print(f"  unreceived_qty:        {so_total_qty - matched_receipt} (需求量 - 入库数)")

    if matched_receipt != instock_total_qty:
        print()
        print(f"  ⚠️  差异: PRD_INSTOCK 实际汇总 {instock_total_qty}，但匹配后只有 {matched_receipt}")
        print(f"     丢失数量: {instock_total_qty - matched_receipt}")

    if matched_delivery != outstock_total_qty:
        print()
        print(f"  ⚠️  差异: SAL_OUTSTOCK 实际汇总 {outstock_total_qty}，但匹配后只有 {matched_delivery}")
        print(f"     丢失数量: {outstock_total_qty - matched_delivery}")

    print()
    print("【建议修复方案】")
    if so_aux_props != instock_aux_props:
        print("  方案A (推荐): 改用纯 material_code 聚合，不考虑 aux_prop_id")
        print("  方案B: 添加回退机制，先按 (code, aux_id) 匹配，失败则按 code 匹配")
    else:
        print("  aux_prop_id 一致，问题可能在其他地方，需进一步排查")


if __name__ == "__main__":
    main()
