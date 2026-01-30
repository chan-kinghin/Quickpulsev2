#!/usr/bin/env python3
"""
Batch comparison of QuickPulse vs Kingdee raw data.

Automatically selects random MTOs and compares all quantity fields.

Usage:
    python scripts/batch_compare.py --count 10
    python scripts/batch_compare.py --mto DK25B294S  # Test specific MTO
"""

import argparse
import asyncio
import random
import sys
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

sys.path.insert(0, "/Users/kinghinchan/Documents/Cursor Projects/Quickpulsev2/Quickpulsev2")

from src.config import get_config
from src.kingdee.client import KingdeeClient
from src.query.mto_handler import MTOQueryHandler
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


@dataclass
class ComparisonResult:
    """Result of comparing one MTO."""
    mto: str
    material_code: str
    qp_required: Decimal
    qp_receipt: Decimal
    qp_picked: Decimal
    raw_required: Decimal
    raw_receipt: Decimal
    raw_picked: Decimal

    @property
    def required_match(self) -> bool:
        return self.qp_required == self.raw_required

    @property
    def receipt_match(self) -> bool:
        return self.qp_receipt == self.raw_receipt

    @property
    def picked_match(self) -> bool:
        return self.qp_picked == self.raw_picked

    @property
    def all_match(self) -> bool:
        return self.required_match and self.receipt_match and self.picked_match


async def get_recent_mtos(client: KingdeeClient, limit: int = 50) -> list[str]:
    """Fetch recent MTOs from SAL_SaleOrder."""
    result = await client.query(
        form_id="SAL_SaleOrder",
        field_keys=["FMtoNo"],
        filter_string="FMtoNo<>'' AND FDocumentStatus='C'",
        limit=limit * 3,  # Fetch extra to account for duplicates
    )
    # Deduplicate and filter empty (result is list[dict] with field keys)
    mtos = list(set(row.get("FMtoNo", "") for row in result if row.get("FMtoNo")))
    return mtos[:limit]


async def compare_mto(
    handler: MTOQueryHandler,
    client: KingdeeClient,
    mto: str,
) -> list[ComparisonResult]:
    """Compare QuickPulse result with raw Kingdee data for one MTO."""
    results = []

    try:
        # Get QuickPulse result
        qp_result = await handler.get_status(mto, use_cache=False)

        if not qp_result.children:
            return results

        # Aggregate QuickPulse by material_code
        qp_by_material = defaultdict(lambda: {
            "required": Decimal(0),
            "receipt": Decimal(0),
            "picked": Decimal(0),
        })
        for child in qp_result.children:
            # Only compare 07.xx materials (成品) for sales order routing
            if child.material_code.startswith("07."):
                qp_by_material[child.material_code]["required"] += child.required_qty
                qp_by_material[child.material_code]["receipt"] += child.receipt_qty
                qp_by_material[child.material_code]["picked"] += child.picked_qty

        if not qp_by_material:
            return results

        # Fetch raw data
        sales_orders = await SalesOrderReader(client).fetch_by_mto(mto)
        prod_receipts = await ProductionReceiptReader(client).fetch_by_mto(mto)
        sales_deliveries = await SalesDeliveryReader(client).fetch_by_mto(mto)

        # Aggregate raw by material_code
        raw_by_material = defaultdict(lambda: {
            "required": Decimal(0),
            "receipt": Decimal(0),
            "picked": Decimal(0),
        })
        for so in sales_orders:
            if so.material_code.startswith("07."):
                raw_by_material[so.material_code]["required"] += getattr(so, "qty", Decimal(0))
        for pr in prod_receipts:
            if pr.material_code.startswith("07."):
                raw_by_material[pr.material_code]["receipt"] += getattr(pr, "real_qty", Decimal(0))
        for sd in sales_deliveries:
            if sd.material_code.startswith("07."):
                raw_by_material[sd.material_code]["picked"] += getattr(sd, "real_qty", Decimal(0))

        # Compare each material
        all_materials = set(qp_by_material.keys()) | set(raw_by_material.keys())
        for mat in all_materials:
            qp = qp_by_material.get(mat, {"required": Decimal(0), "receipt": Decimal(0), "picked": Decimal(0)})
            raw = raw_by_material.get(mat, {"required": Decimal(0), "receipt": Decimal(0), "picked": Decimal(0)})

            results.append(ComparisonResult(
                mto=mto,
                material_code=mat,
                qp_required=qp["required"],
                qp_receipt=qp["receipt"],
                qp_picked=qp["picked"],
                raw_required=raw["required"],
                raw_receipt=raw["receipt"],
                raw_picked=raw["picked"],
            ))

    except Exception as e:
        print(f"  Error comparing {mto}: {e}")

    return results


def print_result(r: ComparisonResult, verbose: bool = False):
    """Print comparison result for one material."""
    req_status = "✅" if r.required_match else "❌"
    rec_status = "✅" if r.receipt_match else "❌"
    pick_status = "✅" if r.picked_match else "❌"

    if r.all_match:
        if verbose:
            print(f"  {r.material_code}: required={req_status} receipt={rec_status} picked={pick_status}")
    else:
        print(f"  {r.material_code}: required={req_status} receipt={rec_status} picked={pick_status}")
        if not r.required_match:
            print(f"    required: QP={r.qp_required} vs Raw={r.raw_required} (diff={r.qp_required - r.raw_required})")
        if not r.receipt_match:
            print(f"    receipt: QP={r.qp_receipt} vs Raw={r.raw_receipt} (diff={r.qp_receipt - r.raw_receipt})")
        if not r.picked_match:
            print(f"    picked: QP={r.qp_picked} vs Raw={r.raw_picked} (diff={r.qp_picked - r.raw_picked})")


async def main():
    parser = argparse.ArgumentParser(description="Batch compare QuickPulse vs Kingdee data")
    parser.add_argument("--count", type=int, default=5, help="Number of MTOs to test")
    parser.add_argument("--mto", type=str, help="Test specific MTO(s), comma-separated")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show all results including passes")
    args = parser.parse_args()

    print("=" * 70)
    print("  QuickPulse vs Kingdee Batch Comparison")
    print("=" * 70)

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
        memory_cache_enabled=False,
    )

    # Get MTOs to test
    if args.mto:
        mtos = [m.strip() for m in args.mto.split(",")]
    else:
        print(f"\nFetching {args.count} recent MTOs from SAL_SaleOrder...")
        all_mtos = await get_recent_mtos(client, limit=args.count * 3)
        mtos = random.sample(all_mtos, min(args.count, len(all_mtos)))

    print(f"Testing {len(mtos)} MTOs: {', '.join(mtos[:5])}{'...' if len(mtos) > 5 else ''}\n")

    # Run comparisons
    all_results: list[ComparisonResult] = []
    passed_mtos = 0
    failed_mtos = 0

    for i, mto in enumerate(mtos, 1):
        print(f"[{i}/{len(mtos)}] MTO: {mto}")
        results = await compare_mto(handler, client, mto)

        if not results:
            print("  (no 07.xx materials found)")
            continue

        all_results.extend(results)
        mto_passed = all(r.all_match for r in results)

        if mto_passed:
            passed_mtos += 1
            print(f"  ✅ All {len(results)} materials match")
        else:
            failed_mtos += 1
            for r in results:
                print_result(r, verbose=args.verbose)

    # Summary
    print("\n" + "=" * 70)
    print("  Summary")
    print("=" * 70)

    total_materials = len(all_results)
    passed_materials = sum(1 for r in all_results if r.all_match)
    failed_materials = total_materials - passed_materials

    print(f"\nMTOs tested: {len(mtos)}")
    print(f"  Passed: {passed_mtos} ✅")
    print(f"  Failed: {failed_mtos} {'❌' if failed_mtos > 0 else ''}")

    print(f"\nMaterials compared: {total_materials}")
    print(f"  Passed: {passed_materials} ✅")
    print(f"  Failed: {failed_materials} {'❌' if failed_materials > 0 else ''}")

    # Field-level summary
    req_pass = sum(1 for r in all_results if r.required_match)
    rec_pass = sum(1 for r in all_results if r.receipt_match)
    pick_pass = sum(1 for r in all_results if r.picked_match)

    print(f"\nField accuracy:")
    print(f"  required_qty: {req_pass}/{total_materials} ({100*req_pass/total_materials:.1f}%)" if total_materials else "  required_qty: N/A")
    print(f"  receipt_qty:  {rec_pass}/{total_materials} ({100*rec_pass/total_materials:.1f}%)" if total_materials else "  receipt_qty: N/A")
    print(f"  picked_qty:   {pick_pass}/{total_materials} ({100*pick_pass/total_materials:.1f}%)" if total_materials else "  picked_qty: N/A")

    if failed_materials == 0:
        print("\n🎉 All comparisons passed!")
        return 0
    else:
        print(f"\n⚠️ {failed_materials} material(s) have discrepancies")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
