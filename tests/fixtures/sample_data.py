"""Sample test data for QuickPulse V2 tests."""

from decimal import Decimal

# Sample MTO numbers for different scenarios
MTO_NUMBERS = {
    "normal": "AK2510034",
    "empty": "NONEXISTENT",
    "complex": "AK2510099",  # Multiple material types
}

# Sample production orders (raw dict format, as returned by Kingdee API)
SAMPLE_PRODUCTION_ORDER_RAW = {
    "FBillNo": "MO0001",
    "FMTONo": "AK2510034",
    "FWorkShopID.FName": "Workshop A",
    "FMaterialId.FNumber": "P001",
    "FMaterialId.FName": "Finished Product A",
    "FMaterialId.FSpecification": "Spec A",
    "FQty": 100,
    "FStatus": "Approved",
    "FCreateDate": "2025-01-15",
}

SAMPLE_PRODUCTION_ORDERS_RAW = [
    {
        "FBillNo": "MO0001",
        "FMTONo": "AK2510034",
        "FWorkShopID.FName": "Workshop A",
        "FMaterialId.FNumber": "P001",
        "FMaterialId.FName": "Finished Product A",
        "FMaterialId.FSpecification": "Spec A",
        "FQty": 100,
        "FStatus": "Approved",
        "FCreateDate": "2025-01-15",
    },
    {
        "FBillNo": "MO0002",
        "FMTONo": "AK2510034",
        "FWorkShopID.FName": "Workshop B",
        "FMaterialId.FNumber": "P002",
        "FMaterialId.FName": "Finished Product B",
        "FMaterialId.FSpecification": "Spec B",
        "FQty": 50,
        "FStatus": "Approved",
        "FCreateDate": "2025-01-16",
    },
]

# Sample BOM entries covering all material types (raw dict format)
SAMPLE_BOM_ENTRIES_RAW = [
    # Self-made (material_type=1)
    {
        "FMOBillNO": "MO0001",
        "FMTONO": "AK2510034",
        "FMaterialId.FNumber": "C001",
        "FMaterialId.FName": "Self-made Part 1",
        "FMaterialId.FSpecification": "Spec1",
        "FAuxPropId": 0,
        "FMaterialType": 1,
        "FMustQty": 50,
        "FPickedQty": 30,
        "FNoPickedQty": 20,
    },
    # Purchased (material_type=2)
    {
        "FMOBillNO": "MO0001",
        "FMTONO": "AK2510034",
        "FMaterialId.FNumber": "C002",
        "FMaterialId.FName": "Purchased Part 1",
        "FMaterialId.FSpecification": "Spec2",
        "FAuxPropId": 1001,
        "FMaterialType": 2,
        "FMustQty": 100,
        "FPickedQty": 0,
        "FNoPickedQty": 100,
    },
    # Subcontracted (material_type=3)
    {
        "FMOBillNO": "MO0001",
        "FMTONO": "AK2510034",
        "FMaterialId.FNumber": "C003",
        "FMaterialId.FName": "Subcontracted Part 1",
        "FMaterialId.FSpecification": "Spec3",
        "FAuxPropId": 0,
        "FMaterialType": 3,
        "FMustQty": 25,
        "FPickedQty": 25,
        "FNoPickedQty": 0,
    },
]

# Sample receipts for different types
SAMPLE_PRODUCTION_RECEIPTS_RAW = [
    {
        "FMtoNo": "AK2510034",
        "FMaterialId.FNumber": "C001",
        "FRealQty": 20,
        "FMustQty": 50,
    },
]

SAMPLE_PURCHASE_RECEIPTS_RAW = [
    # Purchase receipt (RKD01_SYS)
    {
        "FMtoNo": "AK2510034",
        "FMaterialId.FNumber": "C002",
        "FRealQty": 80,
        "FMustQty": 100,
        "FBillTypeID.FNumber": "RKD01_SYS",
    },
    # Subcontracting receipt (RKD02_SYS)
    {
        "FMtoNo": "AK2510034",
        "FMaterialId.FNumber": "C003",
        "FRealQty": 25,
        "FMustQty": 25,
        "FBillTypeID.FNumber": "RKD02_SYS",
    },
]

# Expected model data (for verification)
EXPECTED_PRODUCTION_ORDER = {
    "bill_no": "MO0001",
    "mto_number": "AK2510034",
    "workshop": "Workshop A",
    "material_code": "P001",
    "material_name": "Finished Product A",
    "specification": "Spec A",
    "qty": Decimal("100"),
    "status": "Approved",
    "create_date": "2025-01-15",
}

EXPECTED_BOM_ENTRY_SELF_MADE = {
    "mo_bill_no": "MO0001",
    "mto_number": "AK2510034",
    "material_code": "C001",
    "material_name": "Self-made Part 1",
    "specification": "Spec1",
    "material_type": 1,
    "need_qty": Decimal("50"),
    "picked_qty": Decimal("30"),
    "no_picked_qty": Decimal("20"),
}
