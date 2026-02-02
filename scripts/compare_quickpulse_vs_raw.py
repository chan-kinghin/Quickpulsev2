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
        # 根据物料前缀确定字段类型
        prefix = target_material[:2] if target_material else ""

        print(f"\n【物料 {target_material} 明细 (每行一个 ChildItem)】")
        for i, child in enumerate(target_children):
            if i < 10:  # Only show first 10
                if prefix == "07":
                    print(f"  [{i+1}] 销售订单.数量={child.sales_order_qty}, "
                          f"生产入库单.实收数量={child.prod_instock_real_qty}")
                elif prefix == "05":
                    print(f"  [{i+1}] 生产入库单.应收数量={child.prod_instock_must_qty}, "
                          f"生产入库单.实收数量={child.prod_instock_real_qty}, "
                          f"生产领料单.实发数量={child.pick_actual_qty}")
                elif prefix == "03":
                    print(f"  [{i+1}] 采购订单.数量={child.purchase_order_qty}, "
                          f"采购订单.累计入库数量={child.purchase_stock_in_qty}, "
                          f"生产领料单.实发数量={child.pick_actual_qty}")
                print(f"       aux_attributes: {child.aux_attributes or '-'}")

        if len(target_children) > 10:
            print(f"  ... 还有 {len(target_children) - 10} 条未显示")

        # Summary totals based on material type
        print(f"\n【QuickPulse 总计 (所有 ChildItem 相加)】")
        if prefix == "07":
            total_qty = sum(c.sales_order_qty for c in target_children)
            total_receipt = sum(c.prod_instock_real_qty for c in target_children)
            print(f"  销售订单.数量 总计: {total_qty}")
            print(f"  生产入库单.实收数量 总计: {total_receipt}")
        elif prefix == "05":
            total_must = sum(c.prod_instock_must_qty for c in target_children)
            total_real = sum(c.prod_instock_real_qty for c in target_children)
            total_pick = sum(c.pick_actual_qty for c in target_children)
            print(f"  生产入库单.应收数量 总计: {total_must}")
            print(f"  生产入库单.实收数量 总计: {total_real}")
            print(f"  生产领料单.实发数量 总计: {total_pick}")
        elif prefix == "03":
            total_order = sum(c.purchase_order_qty for c in target_children)
            total_stock_in = sum(c.purchase_stock_in_qty for c in target_children)
            total_pick = sum(c.pick_actual_qty for c in target_children)
            print(f"  采购订单.数量 总计: {total_order}")
            print(f"  采购订单.累计入库数量 总计: {total_stock_in}")
            print(f"  生产领料单.实发数量 总计: {total_pick}")

        # =====================================================================
        # 2. Query raw Kingdee data for comparison
        # =====================================================================
        print(f"\n{'='*70}")
        print(f"【2. 金蝶原始数据 (动态查询)】")
        print(f"{'='*70}")

        # Fetch raw data based on material type
        if prefix == "07":
            # 成品: 查 SAL_SaleOrder 和 PRD_INSTOCK
            sales_orders = await SalesOrderReader(client).fetch_by_mto(mto)
            prod_receipts = await ProductionReceiptReader(client).fetch_by_mto(mto)
            raw_sales = [so for so in sales_orders if so.material_code == target_material]
            raw_receipts = [pr for pr in prod_receipts if pr.material_code == target_material]

            raw_qty = sum(getattr(so, "qty", Decimal(0)) for so in raw_sales)
            raw_receipt = sum(getattr(pr, "real_qty", Decimal(0)) for pr in raw_receipts)

            print(f"\n金蝶原始数据 (物料 {target_material} - 成品):")
            print(f"  SAL_SaleOrder 记录数: {len(raw_sales)}, FQty 合计: {raw_qty}")
            print(f"  PRD_INSTOCK 记录数: {len(raw_receipts)}, FRealQty 合计: {raw_receipt}")

            print(f"\n【3. 差异分析】")
            diff_qty = total_qty - raw_qty
            diff_receipt = total_receipt - raw_receipt
            print(f"  销售订单.数量: QuickPulse={total_qty}, 金蝶={raw_qty}, 差异={diff_qty} {'✅' if diff_qty == 0 else '⚠️'}")
            print(f"  生产入库单.实收数量: QuickPulse={total_receipt}, 金蝶={raw_receipt}, 差异={diff_receipt} {'✅' if diff_receipt == 0 else '⚠️'}")

        elif prefix == "05":
            # 自制件: 查 PRD_INSTOCK 和 PRD_PickMtrl
            prod_receipts = await ProductionReceiptReader(client).fetch_by_mto(mto)
            material_picks = await MaterialPickingReader(client).fetch_by_mto(mto)
            raw_receipts = [pr for pr in prod_receipts if pr.material_code == target_material]
            raw_picks = [mp for mp in material_picks if mp.material_code == target_material]

            raw_must = sum(getattr(pr, "must_qty", Decimal(0)) for pr in raw_receipts)
            raw_real = sum(getattr(pr, "real_qty", Decimal(0)) for pr in raw_receipts)
            raw_pick = sum(getattr(mp, "actual_qty", Decimal(0)) for mp in raw_picks)

            print(f"\n金蝶原始数据 (物料 {target_material} - 自制件):")
            print(f"  PRD_INSTOCK 记录数: {len(raw_receipts)}, FMustQty 合计: {raw_must}, FRealQty 合计: {raw_real}")
            print(f"  PRD_PickMtrl 记录数: {len(raw_picks)}, FActualQty 合计: {raw_pick}")

            print(f"\n【3. 差异分析】")
            diff_must = total_must - raw_must
            diff_real = total_real - raw_real
            diff_pick = total_pick - raw_pick
            print(f"  生产入库单.应收数量: QuickPulse={total_must}, 金蝶={raw_must}, 差异={diff_must} {'✅' if diff_must == 0 else '⚠️'}")
            print(f"  生产入库单.实收数量: QuickPulse={total_real}, 金蝶={raw_real}, 差异={diff_real} {'✅' if diff_real == 0 else '⚠️'}")
            print(f"  生产领料单.实发数量: QuickPulse={total_pick}, 金蝶={raw_pick}, 差异={diff_pick} {'✅' if diff_pick == 0 else '⚠️'}")

        elif prefix == "03":
            # 外购件: 查 PUR_PurchaseOrder 和 PRD_PickMtrl
            purchase_orders = await PurchaseOrderReader(client).fetch_by_mto(mto)
            material_picks = await MaterialPickingReader(client).fetch_by_mto(mto)
            raw_purchases = [po for po in purchase_orders if po.material_code == target_material]
            raw_picks = [mp for mp in material_picks if mp.material_code == target_material]

            raw_order = sum(getattr(po, "order_qty", Decimal(0)) for po in raw_purchases)
            raw_stock_in = sum(getattr(po, "stock_in_qty", Decimal(0)) for po in raw_purchases)
            raw_pick = sum(getattr(mp, "actual_qty", Decimal(0)) for mp in raw_picks)

            print(f"\n金蝶原始数据 (物料 {target_material} - 外购件):")
            print(f"  PUR_PurchaseOrder 记录数: {len(raw_purchases)}, FQty 合计: {raw_order}, FStockInQty 合计: {raw_stock_in}")
            print(f"  PRD_PickMtrl 记录数: {len(raw_picks)}, FActualQty 合计: {raw_pick}")

            print(f"\n【3. 差异分析】")
            diff_order = total_order - raw_order
            diff_stock_in = total_stock_in - raw_stock_in
            diff_pick = total_pick - raw_pick
            print(f"  采购订单.数量: QuickPulse={total_order}, 金蝶={raw_order}, 差异={diff_order} {'✅' if diff_order == 0 else '⚠️'}")
            print(f"  采购订单.累计入库数量: QuickPulse={total_stock_in}, 金蝶={raw_stock_in}, 差异={diff_stock_in} {'✅' if diff_stock_in == 0 else '⚠️'}")
            print(f"  生产领料单.实发数量: QuickPulse={total_pick}, 金蝶={raw_pick}, 差异={diff_pick} {'✅' if diff_pick == 0 else '⚠️'}")

    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
