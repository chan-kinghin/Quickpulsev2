#!/usr/bin/env python3
"""Check auxiliary data for purchased/subcontracted items."""

import asyncio
import sys
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
    )

    mto = "AS2510034"
    print(f"{'='*70}")
    print(f"检查辅助数据 - MTO: {mto}")
    print(f"{'='*70}")

    result = await handler.get_status(mto)

    # Show detailed info for purchased items
    purchased = [c for c in result.children if c.material_type == MaterialType.PURCHASED]
    print(f"\n【外购件详细数据 (共 {len(purchased)} 项)】")
    print("-" * 70)

    for i, item in enumerate(purchased[:5], 1):
        print(f"\n[{i}] {item.material_code}")
        print(f"    物料名称:     {item.material_name}")
        print(f"    规格型号:     {item.specification or '(空)'}")
        print(f"    辅助属性:     {item.aux_attributes or '(空)'}")
        print(f"    物料类型:     {item.material_type_name}")
        print(f"    ---订单数据---")
        print(f"    需求数量:     {item.required_qty}")
        print(f"    订单数量:     {item.order_qty}")
        print(f"    入库数量:     {item.receipt_qty}")
        print(f"    未入库数量:   {item.unreceived_qty}")
        print(f"    ---领料数据---")
        print(f"    申请领料:     {item.pick_request_qty}")
        print(f"    实际领料:     {item.pick_actual_qty}")
        print(f"    ---出库数据---")
        print(f"    已发货数量:   {item.delivered_qty}")
        print(f"    库存数量:     {item.inventory_qty}")
        print(f"    数据来源:     {item.receipt_source}")

    # Show detailed info for self-made items for comparison
    self_made = [c for c in result.children if c.material_type == MaterialType.SELF_MADE]
    print(f"\n\n【自制件详细数据 (共 {len(self_made)} 项, 显示前3项对比)】")
    print("-" * 70)

    for i, item in enumerate(self_made[:3], 1):
        print(f"\n[{i}] {item.material_code}")
        print(f"    物料名称:     {item.material_name}")
        print(f"    规格型号:     {item.specification or '(空)'}")
        print(f"    辅助属性:     {item.aux_attributes or '(空)'}")
        print(f"    物料类型:     {item.material_type_name}")
        print(f"    ---BOM数据---")
        print(f"    需求数量:     {item.required_qty}")
        print(f"    已领数量:     {item.picked_qty}")
        print(f"    未领数量:     {item.unpicked_qty}")
        print(f"    ---订单数据---")
        print(f"    订单数量:     {item.order_qty}")
        print(f"    入库数量:     {item.receipt_qty}")
        print(f"    未入库数量:   {item.unreceived_qty}")
        print(f"    ---领料数据---")
        print(f"    申请领料:     {item.pick_request_qty}")
        print(f"    实际领料:     {item.pick_actual_qty}")
        print(f"    ---出库数据---")
        print(f"    已发货数量:   {item.delivered_qty}")
        print(f"    数据来源:     {item.receipt_source}")

    # Check subcontracted items
    subcontracted = [c for c in result.children if c.material_type == MaterialType.SUBCONTRACTED]
    print(f"\n\n【委外件详细数据 (共 {len(subcontracted)} 项)】")
    if subcontracted:
        for i, item in enumerate(subcontracted[:3], 1):
            print(f"\n[{i}] {item.material_code}")
            print(f"    物料名称:     {item.material_name}")
            print(f"    规格型号:     {item.specification or '(空)'}")
    else:
        print("  ⚠️ 无委外件数据 (SUB_POORDER 表单不存在)")


if __name__ == "__main__":
    asyncio.run(main())
