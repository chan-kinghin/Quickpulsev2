# Plan: Refactor MTO Query to Use Direct Source Forms

> **Status: COMPLETE** - Archived 2026-01-29. Config-driven material routing implemented.

---

## Key Feature: Configurable Logic via JSON

All column mappings and data flow rules will be defined in a **JSON config file** (`mto_config.json`), making it easy to adjust without code changes.

---

## Problem Summary
For MTO AS2509076, item 07.02.037 shows incorrect quantities because:
1. Current code uses PRD_PPBOM (BOM explosion) as the source of child items
2. Quantities are aggregated incorrectly across production orders
3. Wrong source forms are used for different material classes

## New Architecture

### Remove PRD_PPBOM - Use Direct Source Forms Instead

| Material Class | Source Form | Key Quantity Fields |
|----------------|-------------|---------------------|
| **07.xx.xxx** (Finished goods) | SAL_SaleOrder | 销售数量, from SAL_OUTSTOCK: 实发数量, from PRD_INSTOCK: 实收数量 |
| **05.xx.xxx** (Self-made) | PRD_MO | Production order quantities, from PRD_INSTOCK: 实收数量 |
| **03.xx.xxx** (Purchased) | PUR_PurchaseOrder | 采购数量, 累计入库数量, 剩余入库数量, from STK_InStock: 实收数量 |

### Data Flow (NEW)

```
MTO Number (e.g., AS2509076)
    │
    ├─► SAL_SaleOrder (FMtoNo) ──► 07.xx.xxx items
    │       • 销售数量 (FQty)
    │       • 辅助属性
    │       • 单据编号 (unique key)
    │
    ├─► PRD_MO (FMTONo) ──► 05.xx.xxx items (if any)
    │       • 生产数量 (FQty)
    │       • FBillNo (unique key)
    │
    ├─► PUR_PurchaseOrder (FMtoNo) ──► 03.xx.xxx items
    │       • 采购数量 (FQty)
    │       • 累计入库数量 (FStockInQty)
    │       • 剩余入库数量 (FRemainStockInQty)
    │       • FBillNo (unique key)
    │
    ├─► PRD_INSTOCK (FMtoNo) ──► Receipt quantities for 07/05 items
    │       • 实收数量 (FRealQty)
    │       • Link by FMoBillNo or material_code
    │
    └─► STK_InStock (FMtoNo) ──► Receipt quantities for 03 items
            • 实收数量 (FRealQty)
            • Link by FPOOrderNo or material_code
```

---

## Implementation Summary

### Created Files
- `config/mto_config.json` - Configuration file for material classes and column mappings
- `src/mto_config/mto_config.py` - Config loader class

### Modified Files
- `src/readers/models.py` - Updated SalesOrderModel with qty fields
- `src/readers/factory.py` - Updated SALES_ORDER_CONFIG
- `src/query/mto_handler.py` - Major refactor with config-driven routing

### Key Design Decisions Implemented
1. **No aggregation** - Each record from source form is a separate row
2. **Include all classes** - 07, 05, and 03 items all appear
3. **Keep picking columns** - Show actual picking data for 03/05, delivery data for 07
4. **Receipt matching** - By material_code + aux_attributes (no document linking)

---

## Verification (PASSED)

1. ✅ Query MTO AS2509076: `GET /api/mto/AS2509076`
2. ✅ 07.02.037 appears as separate rows per sales order line
3. ✅ 03.xx.xxx items show purchase order quantities
4. ✅ 05.xx.xxx items show production order quantities
5. ✅ Tests pass: `pytest tests/`
