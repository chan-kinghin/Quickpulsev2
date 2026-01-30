#!/usr/bin/env python3
"""
对比 QuickPulse 取数结果与金蝶原始数据

用法: python scripts/compare_quickpulse_vs_raw.py [MTO号] [物料编码]
"""

import asyncio
import sys
from collections import defaultdict
from decimal import Decimal

sys.path.insert(0, "/Users/kinghinchan/Documents/Cursor Projects/Quickpulsev2/Quickpulsev2")

from src.config import get_config
from src.kingdee.client import KingdeeClient
from src.query.mto_handler import MTOQueryHandler, MaterialType
from src.readers import (
    MaterialPickingReader,
    ProductionBOMReader,
    ProductionOrderReader,
    ProductionReceiptReader,
    PurchaseOrderReader,
    PurchaseReceiptReader,
    SalesDeliveryReader,
    SalesOrderReader,
    SubcontractingOrderReader,
)


async def main():
    mto = sys.argv[1] if len(sys.argv) > 1 else "DK25B294S"
    target_material = sys.argv[2] if len(sys.argv) > 2 else "07.32.002"

    print(f"{'='*70}")
    print(f"  对比 QuickPulse vs 金蝶原始数据")
    print(f"  MTO: {mto}, 物料: {target_material}")
    print(f"{'='*70}")

    # Initialize
    config = get_config()
    client = KingdeeClient(config.kingdee)

    handler = MTOQueryHandler(
        production_order_reader=ProductionOrderReader(client),
        production_bom_reader=ProductionBOMReader(client),
        production_receipt_reader=ProductionReceiptReader(client),
        purchase_order_reader=PurchaseOrderReader(client),
        purchase_receipt_reader=PurchaseReceiptReader(client),
        subcontracting_order_reader=SubcontractingOrderReader(client),
        material_picking_reader=MaterialPickingReader(client),
        sales_delivery_reader=SalesDeliveryReader(client),
        sales_order_reader=SalesOrderReader(client),
        memory_cache_enabled=False,  # Disable cache for testing
    )

    # Get QuickPulse result
    print("\n【1. QuickPulse 返回数据】")
    print("-" * 70)

    try:
        result = await handler.get_status(mto, use_cache=False)

        # Filter for target material
        target_children = [c for c in result.children if c.material_code == target_material]

        print(f"总 ChildItem 数: {len(result.children)}")
        print(f"物料 {target_material} 的 ChildItem 数: {len(target_children)}")

        if not target_children:
            print(f"\n⚠️ 没有找到物料 {target_material} 的数据!")
            return

        # Aggregate by aux_attributes (since that's what user sees)
        by_aux = defaultdict(lambda: {
            "count": 0,
            "required_qty": Decimal(0),
            "receipt_qty": Decimal(0),
            "picked_qty": Decimal(0),
            "unreceived_qty": Decimal(0),
        })

        print(f"\n【物料 {target_material} 明细 (每行一个 ChildItem)】")
        for i, child in enumerate(target_children):
            aux = child.aux_attributes or "(无)"
            by_aux[aux]["count"] += 1
            by_aux[aux]["required_qty"] += child.required_qty
            by_aux[aux]["receipt_qty"] += child.receipt_qty
            by_aux[aux]["picked_qty"] += child.picked_qty
            by_aux[aux]["unreceived_qty"] += child.unreceived_qty

            if i < 10:  # Only show first 10
                print(f"  [{i+1}] required={child.required_qty}, receipt={child.receipt_qty}, "
                      f"picked={child.picked_qty}, unreceived={child.unreceived_qty}")
                print(f"       aux_attributes: {child.aux_attributes or '-'}")

        if len(target_children) > 10:
            print(f"  ... 还有 {len(target_children) - 10} 条未显示")

        # Summary by aux
        print(f"\n【按辅助属性汇总 (QuickPulse ChildItems 相加)】")
        total_required = Decimal(0)
        total_receipt = Decimal(0)
        total_picked = Decimal(0)

        for aux, data in by_aux.items():
            print(f"  辅助属性: {aux}")
            print(f"    ChildItem数: {data['count']}")
            print(f"    required_qty 合计: {data['required_qty']}")
            print(f"    receipt_qty 合计: {data['receipt_qty']}")
            print(f"    picked_qty 合计: {data['picked_qty']}")
            print()

            total_required += data['required_qty']
            total_receipt += data['receipt_qty']
            total_picked += data['picked_qty']

        print(f"\n【QuickPulse 总计 (所有 ChildItem 相加)】")
        print(f"  required_qty 总计: {total_required}")
        print(f"  receipt_qty 总计: {total_receipt}")
        print(f"  picked_qty 总计: {total_picked}")

        # =====================================================================
        # 2. Query raw Kingdee data for comparison
        # =====================================================================
        print(f"\n{'='*70}")
        print(f"【2. 金蝶原始数据 (动态查询)】")
        print(f"{'='*70}")

        # Fetch raw data using readers
        sales_orders = await SalesOrderReader(client).fetch_by_mto(mto)
        prod_receipts = await ProductionReceiptReader(client).fetch_by_mto(mto)
        sales_deliveries = await SalesDeliveryReader(client).fetch_by_mto(mto)

        # Filter for target material
        raw_sales = [so for so in sales_orders if so.material_code == target_material]
        raw_receipts = [pr for pr in prod_receipts if pr.material_code == target_material]
        raw_deliveries = [sd for sd in sales_deliveries if sd.material_code == target_material]

        # Calculate raw totals
        raw_required = sum(getattr(so, "qty", Decimal(0)) for so in raw_sales)
        raw_receipt = sum(getattr(pr, "real_qty", Decimal(0)) for pr in raw_receipts)
        raw_picked = sum(getattr(sd, "real_qty", Decimal(0)) for sd in raw_deliveries)

        print(f"\n金蝶原始数据 (物料 {target_material}):")
        print(f"  SAL_SaleOrder 记录数: {len(raw_sales)}, FQty 合计: {raw_required}")
        print(f"  PRD_INSTOCK 记录数: {len(raw_receipts)}, FRealQty 合计: {raw_receipt}")
        print(f"  SAL_OUTSTOCK 记录数: {len(raw_deliveries)}, FRealQty 合计: {raw_picked}")

        # =====================================================================
        # 3. Comparison
        # =====================================================================
        print(f"\n{'='*70}")
        print(f"【3. 差异分析】")
        print(f"{'='*70}")

        print(f"\n{'字段':<20} {'QuickPulse':<15} {'金蝶原始':<15} {'差异':<15} {'状态'}")
        print("-" * 75)

        diff_required = total_required - raw_required
        diff_receipt = total_receipt - raw_receipt
        diff_picked = total_picked - raw_picked

        status_required = "✅" if diff_required == 0 else "⚠️"
        status_receipt = "✅" if diff_receipt == 0 else "⚠️"
        status_picked = "✅" if diff_picked == 0 else "⚠️"

        print(f"{'required_qty':<20} {total_required:<15} {raw_required:<15} {diff_required:<15} {status_required}")
        print(f"{'receipt_qty':<20} {total_receipt:<15} {raw_receipt:<15} {diff_receipt:<15} {status_receipt}")
        print(f"{'picked_qty':<20} {total_picked:<15} {raw_picked:<15} {diff_picked:<15} {status_picked}")

        if diff_required == 0 and diff_receipt == 0 and diff_picked == 0:
            print(f"\n🎉 所有字段数据一致!")
        else:
            print(f"\n⚠️ 发现差异，请检查以下可能原因:")
            if diff_required != 0:
                print(f"  - required_qty 差异 {diff_required}: 检查销售订单聚合逻辑")
            if diff_receipt != 0:
                print(f"  - receipt_qty 差异 {diff_receipt}: 检查生产入库聚合逻辑")
            if diff_picked != 0:
                print(f"  - picked_qty 差异 {diff_picked}: 检查销售出库聚合逻辑")

    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
