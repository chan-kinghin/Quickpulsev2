#!/usr/bin/env python3
"""Test MTO query handler with real data."""

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
    )

    # Test with AS MTO number
    mto = "AS2510034"
    print(f"{'='*60}")
    print(f"Testing MTOQueryHandler for MTO: {mto}")
    print(f"{'='*60}")

    try:
        result = await handler.get_status(mto)

        print(f"\n【Order Info】")
        print(f"  MTO Number: {result.parent.mto_number}")
        print(f"  Customer: {result.parent.customer_name or '-'}")
        print(f"  Delivery Date: {result.parent.delivery_date or '-'}")

        # Count by material type
        type_counts = {1: 0, 2: 0, 3: 0}
        for child in result.children:
            type_counts[child.material_type] = type_counts.get(child.material_type, 0) + 1

        print(f"\n【Child Items Summary】")
        print(f"  Total: {len(result.children)} items")
        print(f"  - 自制 (Self-made): {type_counts.get(1, 0)}")
        print(f"  - 外购 (Purchased): {type_counts.get(2, 0)}")
        print(f"  - 委外 (Subcontracted): {type_counts.get(3, 0)}")

        # Show some purchased items
        purchased = [c for c in result.children if c.material_type == MaterialType.PURCHASED]
        if purchased:
            print(f"\n【Sample Purchased Items (first 5)】")
            for item in purchased[:5]:
                print(f"  {item.material_code} | {item.material_name[:30]}")
                print(f"    Order: {item.order_qty}, Receipt: {item.receipt_qty}, Remain: {item.unreceived_qty}")
                print()
        else:
            print("\n⚠️ No purchased items found!")

        # Show some self-made items
        self_made = [c for c in result.children if c.material_type == MaterialType.SELF_MADE]
        if self_made:
            print(f"\n【Sample Self-made Items (first 5)】")
            for item in self_made[:5]:
                print(f"  {item.material_code} | {item.material_name[:30]}")
                print(f"    Required: {item.required_qty}, Picked: {item.picked_qty}, Unpicked: {item.unpicked_qty}")
                print()
        else:
            print("\n⚠️ No self-made items found!")

        print(f"\n✅ Query completed successfully at {result.query_time}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
