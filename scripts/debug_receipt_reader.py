#!/usr/bin/env python3
"""
Debug script to compare ProductionReceiptReader output with raw API queries.

Identifies why reader returns different aux_prop_id aggregations than direct SQL.
"""

import asyncio
import json
import sys
from collections import defaultdict
from decimal import Decimal

sys.path.insert(0, "/Users/kinghinchan/Documents/Cursor Projects/Quickpulsev2/Quickpulsev2")

from k3cloud_webapi_sdk.main import K3CloudApiSdk

from src.config import get_config
from src.kingdee.client import KingdeeClient
from src.readers import ProductionReceiptReader


def query_raw(api_sdk, params):
    """Execute raw API query and parse JSON result."""
    result = api_sdk.ExecuteBillQuery(params)
    if isinstance(result, str):
        return json.loads(result)
    return result


async def main():
    mto = sys.argv[1] if len(sys.argv) > 1 else "DK25B294S"
    target_material = sys.argv[2] if len(sys.argv) > 2 else "07.32.002"

    print(f"{'='*70}")
    print(f"  Debug: ProductionReceiptReader vs Raw API")
    print(f"  MTO: {mto}, Material: {target_material}")
    print(f"{'='*70}")

    # Initialize
    config = get_config()
    client = KingdeeClient(config.kingdee)
    reader = ProductionReceiptReader(client)

    # Initialize raw SDK
    api_sdk = K3CloudApiSdk(config.kingdee.server_url)
    api_sdk.InitConfig(
        acct_id=config.kingdee.acct_id,
        user_name=config.kingdee.user_name,
        app_id=config.kingdee.app_id,
        app_secret=config.kingdee.app_sec,
        server_url=config.kingdee.server_url,
        lcid=config.kingdee.lcid,
    )

    # =========================================================================
    # 1. Query via ProductionReceiptReader
    # =========================================================================
    print("\n【1. ProductionReceiptReader 返回数据】")
    print("-" * 70)

    receipts = await reader.fetch_by_mto(mto)
    target_receipts = [r for r in receipts if r.material_code == target_material]

    print(f"总记录数: {len(receipts)}")
    print(f"物料 {target_material} 记录数: {len(target_receipts)}")

    reader_by_aux = defaultdict(list)
    for r in target_receipts:
        reader_by_aux[r.aux_prop_id].append(r)

    print(f"\n按 aux_prop_id 分组:")
    reader_totals = {}
    for aux_id, recs in sorted(reader_by_aux.items()):
        total = sum(r.real_qty for r in recs)
        reader_totals[aux_id] = total
        print(f"  aux_prop_id={aux_id}: {len(recs)} records, real_qty合计={total}")
        # Show individual records
        for i, r in enumerate(recs[:5]):
            print(f"    [{i+1}] bill_no={r.bill_no}, real_qty={r.real_qty}, mo_bill_no={r.mo_bill_no}")
        if len(recs) > 5:
            print(f"    ... 还有 {len(recs) - 5} 条")

    reader_grand_total = sum(reader_totals.values())
    print(f"\nReader 总计: {reader_grand_total}")

    # =========================================================================
    # 2. Query via Raw API (same as diagnose script)
    # =========================================================================
    print("\n【2. Raw API 返回数据】")
    print("-" * 70)

    raw_params = {
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
        "Limit": 2000
    }
    raw_result = query_raw(api_sdk, raw_params)

    print(f"查询条件: FMtoNo='{mto}'")
    print(f"总记录数: {len(raw_result)}")

    raw_target = [r for r in raw_result if len(r) > 2 and r[2] == target_material]
    print(f"物料 {target_material} 记录数: {len(raw_target)}")

    raw_by_aux = defaultdict(list)
    for r in raw_target:
        aux_prop_id = r[4] or 0  # FAuxPropId
        raw_by_aux[aux_prop_id].append(r)

    print(f"\n按 aux_prop_id 分组:")
    raw_totals = {}
    for aux_id, recs in sorted(raw_by_aux.items()):
        total = sum(Decimal(str(r[5] or 0)) for r in recs)  # FRealQty
        raw_totals[aux_id] = total
        print(f"  aux_prop_id={aux_id}: {len(recs)} records, real_qty合计={total}")
        # Show individual records
        for i, r in enumerate(recs[:5]):
            print(f"    [{i+1}] bill_no={r[0]}, real_qty={r[5]}, mo_bill_no={r[7]}")
        if len(recs) > 5:
            print(f"    ... 还有 {len(recs) - 5} 条")

    raw_grand_total = sum(raw_totals.values())
    print(f"\nRaw API 总计: {raw_grand_total}")

    # =========================================================================
    # 3. Compare
    # =========================================================================
    print("\n【3. 对比分析】")
    print("-" * 70)

    all_aux_ids = set(reader_totals.keys()) | set(raw_totals.keys())

    print(f"{'aux_prop_id':<15} {'Reader':<15} {'Raw API':<15} {'差异':<15}")
    print("-" * 60)

    for aux_id in sorted(all_aux_ids):
        r_val = reader_totals.get(aux_id, Decimal(0))
        raw_val = raw_totals.get(aux_id, Decimal(0))
        diff = r_val - raw_val
        diff_mark = "⚠️" if diff != 0 else "✅"
        print(f"{aux_id:<15} {r_val:<15} {raw_val:<15} {diff:<15} {diff_mark}")

    print("-" * 60)
    print(f"{'总计':<15} {reader_grand_total:<15} {raw_grand_total:<15} {reader_grand_total - raw_grand_total:<15}")

    if reader_grand_total != raw_grand_total:
        print(f"\n⚠️ 发现差异: Reader比Raw API多 {reader_grand_total - raw_grand_total}")

    # =========================================================================
    # 4. Check field mapping
    # =========================================================================
    print("\n【4. Field Mapping 检查】")
    print("-" * 70)

    print(f"Reader 请求的 field_keys: {reader.field_keys}")
    print(f"Raw API 请求的 FieldKeys: {raw_params['FieldKeys'].split(',')}")

    # Check if there are duplicate bill_no entries
    print("\n【5. 检查是否有重复单号】")
    print("-" * 70)

    reader_bills = [r.bill_no for r in target_receipts]
    raw_bills = [r[0] for r in raw_target]

    print(f"Reader 唯一单号数: {len(set(reader_bills))}")
    print(f"Raw API 唯一单号数: {len(set(raw_bills))}")

    # Count duplicates
    from collections import Counter
    reader_bill_counts = Counter(reader_bills)
    raw_bill_counts = Counter(raw_bills)

    reader_dups = {k: v for k, v in reader_bill_counts.items() if v > 1}
    raw_dups = {k: v for k, v in raw_bill_counts.items() if v > 1}

    if reader_dups:
        print(f"\nReader 有重复的单号:")
        for bill, count in sorted(reader_dups.items())[:10]:
            print(f"  {bill}: {count} 次")

    if raw_dups:
        print(f"\nRaw API 有重复的单号:")
        for bill, count in sorted(raw_dups.items())[:10]:
            print(f"  {bill}: {count} 次")


if __name__ == "__main__":
    asyncio.run(main())
