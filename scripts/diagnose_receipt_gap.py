#!/usr/bin/env python3
"""
诊断成品 (07.xx) PRD_INSTOCK 入库单 缺漏问题

用法: python scripts/diagnose_receipt_gap.py [MTO号]
示例: python scripts/diagnose_receipt_gap.py AS2512074-3

调查假设:
  H1: PRD_INSTOCK 记录的 FMtoNo 为空，但通过 FMoBillNo 能关联到
  H2: aux_prop_id 不匹配 (销售订单 vs 入库单)
  H3: 入库单的 07.xx 物料编码不在销售订单中

对比:
  方式A: 按 FMtoNo 查询 PRD_INSTOCK (应用现有逻辑)
  方式B: 按 FMoBillNo 查询 PRD_INSTOCK (经由 PRD_MO 关联)
"""

import json
import sys
from collections import defaultdict
from decimal import Decimal

sys.path.insert(0, "/Users/kinghinchan/Documents/Cursor Projects/Quickpulsev2/Quickpulsev2")

from k3cloud_webapi_sdk.main import K3CloudApiSdk


ZERO = Decimal(0)


def query(api_sdk, params):
    """Execute query and parse JSON result."""
    result = api_sdk.ExecuteBillQuery(params)
    if isinstance(result, str):
        return json.loads(result)
    return result


def query_all(api_sdk, params, page_size=2000):
    """Query with pagination to get all records."""
    all_results = []
    start = 0
    while True:
        p = dict(params)
        p["StartRow"] = start
        p["Limit"] = page_size
        batch = query(api_sdk, p)
        if not batch:
            break
        all_results.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    return all_results


def print_section(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def print_subsection(title: str):
    print(f"\n--- {title} ---")


def main():
    mto = sys.argv[1] if len(sys.argv) > 1 else "AS2512074-3"

    print_section(f"成品入库缺漏诊断: {mto}")

    # Initialize Kingdee API
    api_sdk = K3CloudApiSdk("http://flt.hotker.com:8200/k3cloud/")
    api_sdk.Init(config_path='conf.ini', config_node='config')

    # =========================================================================
    # Step 1: Query PRD_INSTOCK by FMtoNo (how the app does it)
    # =========================================================================
    print_section("Step 1: PRD_INSTOCK by FMtoNo (应用现有方式)")

    instock_by_mto = query_all(api_sdk, {
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
            "FDocumentStatus",
        ]),
        "FilterString": f"FMtoNo LIKE '{mto}%' AND FDocumentStatus IN ('B','C','D')",
    })

    print(f"查询条件: FMtoNo LIKE '{mto}%' AND FDocumentStatus IN ('B','C','D')")
    print(f"总记录数: {len(instock_by_mto)}")

    # Filter for 07.xx (finished goods) only
    instock_07_by_mto = [r for r in instock_by_mto if len(r) > 2 and r[2].startswith("07.")]
    print(f"其中 07.xx 记录数: {len(instock_07_by_mto)}")

    mto_total = ZERO
    mto_bills = set()
    mto_by_key = defaultdict(lambda: ZERO)
    print_subsection("07.xx 明细 (by FMtoNo)")
    for row in instock_07_by_mto:
        bill_no, mto_no, mat_code, mat_name, aux_prop_id, real_qty, must_qty, mo_bill_no, doc_status = row[:9]
        real_qty = Decimal(str(real_qty or 0))
        aux_prop_id = int(aux_prop_id or 0)
        mto_total += real_qty
        mto_bills.add(bill_no)
        mto_by_key[(mat_code, aux_prop_id)] += real_qty
        print(f"  {bill_no} | {mat_code} | aux={aux_prop_id} | 实收={real_qty} | 源单={mo_bill_no} | 状态={doc_status}")

    print(f"\n>>> 方式A汇总: {len(instock_07_by_mto)} 条, FRealQty={mto_total}")
    print(f">>> 按 (material_code, aux_prop_id) 分组:")
    for key, total in sorted(mto_by_key.items()):
        print(f"    {key}: {total}")

    # Also show ALL material types summary
    all_total = sum(Decimal(str(r[5] or 0)) for r in instock_by_mto)
    non_07 = [r for r in instock_by_mto if len(r) > 2 and not r[2].startswith("07.")]
    print(f"\n>>> 全部物料汇总: {len(instock_by_mto)} 条, FRealQty={all_total}")
    print(f">>> 非07.xx 记录数: {len(non_07)}, 合计: {sum(Decimal(str(r[5] or 0)) for r in non_07)}")

    # =========================================================================
    # Step 2: Query PRD_MO by FMTONo (get production order bill numbers)
    # =========================================================================
    print_section("Step 2: PRD_MO by FMTONo (获取生产订单号)")

    mo_result = query_all(api_sdk, {
        "FormId": "PRD_MO",
        "FieldKeys": ",".join([
            "FBillNo",
            "FMTONo",
            "FMaterialId.FNumber",
            "FMaterialId.FName",
            "FQty",
            "FDocumentStatus",
        ]),
        "FilterString": f"FMTONo LIKE '{mto}%'",
    })

    print(f"查询条件: FMTONo LIKE '{mto}%'")
    print(f"总记录数: {len(mo_result)}")

    mo_07 = [r for r in mo_result if len(r) > 2 and r[2].startswith("07.")]
    mo_non_07 = [r for r in mo_result if len(r) > 2 and not r[2].startswith("07.")]

    print(f"其中 07.xx 记录数: {len(mo_07)}")
    print(f"其中 非07.xx 记录数: {len(mo_non_07)}")

    mo_bill_nos_07 = set()
    mo_bill_nos_all = set()

    print_subsection("07.xx 生产订单")
    for row in mo_07:
        bill_no, mto_no, mat_code, mat_name, qty, doc_status = row[:6]
        qty = Decimal(str(qty or 0))
        mo_bill_nos_07.add(bill_no)
        mo_bill_nos_all.add(bill_no)
        print(f"  {bill_no} | {mat_code} | 数量={qty} | 状态={doc_status}")

    # Also collect all MO bill numbers (for completeness)
    for row in mo_non_07:
        mo_bill_nos_all.add(row[0])

    print(f"\n>>> 07.xx 生产订单号: {sorted(mo_bill_nos_07)}")
    print(f">>> 全部生产订单号数量: {len(mo_bill_nos_all)}")

    # =========================================================================
    # Step 3: Query PRD_INSTOCK by FMoBillNo (using MO bill numbers)
    # =========================================================================
    print_section("Step 3: PRD_INSTOCK by FMoBillNo (经由生产订单关联)")

    if not mo_bill_nos_07:
        print("无 07.xx 生产订单，跳过此步骤")
        instock_by_mo = []
    else:
        # Build IN clause for MO bill numbers
        # Query in batches if too many MO numbers
        mo_list = sorted(mo_bill_nos_07)
        instock_by_mo = []

        batch_size = 20  # IN clause batch size
        for i in range(0, len(mo_list), batch_size):
            batch = mo_list[i:i + batch_size]
            in_clause = ",".join(f"'{b}'" for b in batch)
            batch_result = query_all(api_sdk, {
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
                    "FDocumentStatus",
                ]),
                "FilterString": f"FMoBillNo IN ({in_clause}) AND FDocumentStatus IN ('B','C','D')",
            })
            instock_by_mo.extend(batch_result)

        print(f"查询条件: FMoBillNo IN ({len(mo_bill_nos_07)} 个生产订单号) AND FDocumentStatus IN ('B','C','D')")
        print(f"总记录数: {len(instock_by_mo)}")

        # Filter for 07.xx
        instock_07_by_mo = [r for r in instock_by_mo if len(r) > 2 and r[2].startswith("07.")]
        print(f"其中 07.xx 记录数: {len(instock_07_by_mo)}")

        mo_route_total = ZERO
        mo_route_bills = set()
        mo_route_by_key = defaultdict(lambda: ZERO)

        print_subsection("07.xx 明细 (by FMoBillNo)")
        for row in instock_07_by_mo:
            bill_no, mto_no, mat_code, mat_name, aux_prop_id, real_qty, must_qty, mo_bill_no, doc_status = row[:9]
            real_qty = Decimal(str(real_qty or 0))
            aux_prop_id = int(aux_prop_id or 0)
            mto_no_str = mto_no or "(空)"
            mo_route_total += real_qty
            mo_route_bills.add(bill_no)
            mo_route_by_key[(mat_code, aux_prop_id)] += real_qty

            # Flag if this receipt was NOT found by FMtoNo
            flag = " ← MISSING from FMtoNo query!" if bill_no not in mto_bills else ""
            print(f"  {bill_no} | {mat_code} | aux={aux_prop_id} | 实收={real_qty} | 源单={mo_bill_no} | FMtoNo={mto_no_str}{flag}")

        print(f"\n>>> 方式B汇总: {len(instock_07_by_mo)} 条, FRealQty={mo_route_total}")
        print(f">>> 按 (material_code, aux_prop_id) 分组:")
        for key, total in sorted(mo_route_by_key.items()):
            print(f"    {key}: {total}")

        # =========================================================================
        # Step 4: Compare A vs B — find invisible receipts
        # =========================================================================
        print_section("Step 4: 对比 — 缺漏分析")

        only_in_mo = mo_route_bills - mto_bills
        only_in_mto = mto_bills - mo_route_bills

        print(f"方式A (FMtoNo):   {len(mto_bills)} 入库单号, 合计 {mto_total}")
        print(f"方式B (FMoBillNo): {len(mo_route_bills)} 入库单号, 合计 {mo_route_total}")
        print(f"差额: {mo_route_total - mto_total}")
        print()
        print(f"仅在方式B中出现 (FMtoNo 缺失): {len(only_in_mo)} 单")
        if only_in_mo:
            invisible_total = ZERO
            for row in instock_07_by_mo:
                if row[0] in only_in_mo:
                    real_qty = Decimal(str(row[5] or 0))
                    invisible_total += real_qty
                    mto_no_str = row[1] or "(空)"
                    print(f"  {row[0]} | {row[2]} | aux={int(row[4] or 0)} | 实收={real_qty} | FMtoNo={mto_no_str} | 源单={row[7]}")
            print(f"  >>> 不可见入库合计: {invisible_total}")
            print()
            print("  ✅ H1 确认: 这些入库单的 FMtoNo 为空或不匹配，导致应用查询不到")
        else:
            print("  ❌ H1 排除: 所有 FMoBillNo 关联的入库单都能通过 FMtoNo 查到")

        print()
        print(f"仅在方式A中出现 (无对应生产订单): {len(only_in_mto)} 单")
        if only_in_mto:
            for row in instock_07_by_mto:
                if row[0] in only_in_mto:
                    print(f"  {row[0]} | {row[2]} | aux={int(row[4] or 0)} | 实收={Decimal(str(row[5] or 0))}")

    # =========================================================================
    # Step 5: SAL_SaleOrder — get (material_code, aux_prop_id) keys
    # =========================================================================
    print_section("Step 5: SAL_SaleOrder 销售订单 (07.xx keys)")

    so_result = query_all(api_sdk, {
        "FormId": "SAL_SaleOrder",
        "FieldKeys": ",".join([
            "FBillNo",
            "FMtoNo",
            "FMaterialId.FNumber",
            "FMaterialId.FName",
            "FAuxPropId",
            "FQty",
        ]),
        "FilterString": f"FMtoNo LIKE '{mto}%'",
    })

    print(f"查询条件: FMtoNo LIKE '{mto}%'")
    print(f"总记录数: {len(so_result)}")

    so_07 = [r for r in so_result if len(r) > 2 and r[2].startswith("07.")]
    print(f"其中 07.xx 记录数: {len(so_07)}")

    so_by_key = defaultdict(lambda: ZERO)
    so_aux_props = set()

    print_subsection("07.xx 销售订单明细")
    for row in so_07:
        bill_no, mto_no, mat_code, mat_name, aux_prop_id, qty = row[:6]
        qty = Decimal(str(qty or 0))
        aux_prop_id = int(aux_prop_id or 0)
        so_by_key[(mat_code, aux_prop_id)] += qty
        so_aux_props.add(aux_prop_id)
        print(f"  {bill_no} | {mat_code} | {mat_name} | aux={aux_prop_id} | 数量={qty}")

    print(f"\n>>> 按 (material_code, aux_prop_id) 分组:")
    for key, total in sorted(so_by_key.items()):
        print(f"    {key}: {total}")

    # =========================================================================
    # Step 6: Cross-check aux_prop_ids
    # =========================================================================
    print_section("Step 6: aux_prop_id 交叉检查")

    # Use the best available receipt data (by FMoBillNo if available, else by FMtoNo)
    if mo_bill_nos_07:
        receipt_keys = mo_route_by_key
        receipt_label = "方式B (FMoBillNo)"
    else:
        receipt_keys = mto_by_key
        receipt_label = "方式A (FMtoNo)"

    print(f"销售订单 keys: {sorted(so_by_key.keys())}")
    print(f"入库单 keys ({receipt_label}): {sorted(receipt_keys.keys())}")

    # Check each sales order key against receipt keys
    print_subsection("匹配分析")
    matched_receipt_total = ZERO
    unmatched_so_keys = []

    for so_key, so_qty in sorted(so_by_key.items()):
        receipt_qty = receipt_keys.get(so_key, ZERO)
        matched_receipt_total += receipt_qty
        status = "✅" if receipt_qty > 0 else "❌ 无匹配入库"
        print(f"  销售订单 {so_key}: 需求={so_qty}, 入库={receipt_qty}  {status}")
        if receipt_qty == 0:
            unmatched_so_keys.append(so_key)

    # Check for receipt keys not in sales orders
    orphan_receipt_keys = set(receipt_keys.keys()) - set(so_by_key.keys())
    if orphan_receipt_keys:
        print_subsection("H3: 入库单中有但销售订单中没有的 keys")
        for key in sorted(orphan_receipt_keys):
            print(f"  {key}: 入库={receipt_keys[key]}  ← 孤立入库记录")

    # Check if material_code matches but aux_prop_id differs
    so_materials = {k[0] for k in so_by_key.keys()}
    receipt_materials = {k[0] for k in receipt_keys.keys()}

    print_subsection("H2: 物料编码相同但 aux_prop_id 不同的情况")
    aux_mismatch_found = False
    for mat_code in sorted(so_materials & receipt_materials):
        so_auxes = {k[1] for k in so_by_key if k[0] == mat_code}
        rc_auxes = {k[1] for k in receipt_keys if k[0] == mat_code}
        if so_auxes != rc_auxes:
            aux_mismatch_found = True
            print(f"  {mat_code}:")
            print(f"    销售订单 aux_prop_ids: {so_auxes}")
            print(f"    入库单 aux_prop_ids:   {rc_auxes}")
            print(f"    仅销售订单: {so_auxes - rc_auxes}")
            print(f"    仅入库单:   {rc_auxes - so_auxes}")

            # Show qty impact
            for aux in so_auxes - rc_auxes:
                so_q = so_by_key.get((mat_code, aux), ZERO)
                print(f"    → 销售订单 ({mat_code}, {aux}) 需求={so_q} 但无匹配入库!")
            for aux in rc_auxes - so_auxes:
                rc_q = receipt_keys.get((mat_code, aux), ZERO)
                print(f"    → 入库单 ({mat_code}, {aux}) 入库={rc_q} 但无匹配销售订单!")

    if not aux_mismatch_found:
        print("  无 aux_prop_id 不匹配情况")

    # =========================================================================
    # 诊断总结
    # =========================================================================
    print_section("诊断总结")

    print(f"MTO: {mto}")
    print()

    # H1 summary
    if mo_bill_nos_07 and instock_by_mo:
        only_in_mo_count = len(only_in_mo)
        invisible_qty = mo_route_total - mto_total
        if only_in_mo_count > 0:
            print(f"H1 (FMtoNo 缺失): ✅ 确认 — {only_in_mo_count} 条入库单缺少 FMtoNo, 丢失数量 = {invisible_qty}")
        else:
            print(f"H1 (FMtoNo 缺失): ❌ 排除 — 所有入库单 FMtoNo 正常")
    else:
        print("H1 (FMtoNo 缺失): ⚠️ 无法验证 (无 07.xx 生产订单)")

    # H2 summary
    if aux_mismatch_found:
        print(f"H2 (aux_prop_id 不匹配): ✅ 确认 — 存在物料编码相同但 aux_prop_id 不同的情况")
    else:
        print(f"H2 (aux_prop_id 不匹配): ❌ 排除")

    # H3 summary
    if orphan_receipt_keys:
        orphan_total = sum(receipt_keys[k] for k in orphan_receipt_keys)
        print(f"H3 (孤立入库记录): ✅ 确认 — {len(orphan_receipt_keys)} 个 key 无对应销售订单, 合计 = {orphan_total}")
    else:
        print(f"H3 (孤立入库记录): ❌ 排除")

    # Overall gap
    print()
    so_total = sum(so_by_key.values())
    print(f"销售订单需求总量:    {so_total}")
    print(f"应用匹配入库量:      {matched_receipt_total} (按 (code, aux) 精确匹配)")
    if mo_bill_nos_07 and instock_by_mo:
        print(f"MO关联实际入库量:    {mo_route_total} (经生产订单链接)")
    print(f"直接FMtoNo入库量:    {mto_total}")
    print()
    print(f"缺口 (需求 - 匹配入库): {so_total - matched_receipt_total}")

    # Recommendation
    print()
    print("【建议修复方案】")
    if mo_bill_nos_07 and only_in_mo:
        print("  方案1 (H1): 增加 FMoBillNo 二次查询路径")
        print("    — 查 PRD_INSTOCK 时，除了 FMtoNo LIKE，还按 MO 的 FBillNo 查")
        print("    — 按 bill_no 去重后合并结果")
    if aux_mismatch_found:
        print("  方案2 (H2): 增加 material_code-only 回退匹配")
        print("    — 若 (code, aux) 精确匹配无结果，退化到仅按 code 匹配")
    if orphan_receipt_keys:
        print("  方案3 (H3): 为孤立入库记录创建 ChildItem")


if __name__ == "__main__":
    main()
