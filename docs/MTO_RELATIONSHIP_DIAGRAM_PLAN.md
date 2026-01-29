# MTO 订单关联图 (Order Relationship Diagram) Implementation Plan

## Status: Completed (2026-01-29)

> **Implemented** - Visual relationship diagram for MTO orders

---

## Goal
Add a visual relationship diagram showing all orders related to a given MTO number, displaying only bill numbers (单据编号) with Chinese labels.

## Implementation Overview

```
                    ┌─────────────┐
                    │   MTO号     │
                    │ AK2510034   │
                    └──────┬──────┘
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌────────────┐  ┌────────────┐  ┌────────────┐
    │  销售订单   │  │  生产订单   │  │  采购订单   │
    │ XSDD001234 │  │ SCDD005678 │  │ CGDD009012 │
    └──────┬─────┘  └──────┬─────┘  └──────┬─────┘
           ▼               ▼               ▼
    ┌────────────┐  ┌────────────┐  ┌────────────┐
    │  销售出库   │  │ 生产入库/领料│  │  采购入库   │
    │ XSCK001234 │  │ SCRK/LLD.. │  │ CGRK001234 │
    └────────────┘  └────────────┘  └────────────┘
```

---

## Step 1: Add `bill_no` to Reader Models

**File:** `src/readers/models.py`

Add `bill_no: str = ""` to 4 models:
- `ProductionReceiptModel` (line ~40)
- `PurchaseReceiptModel` (line ~66)
- `MaterialPickingModel` (line ~87)
- `SalesDeliveryModel` (line ~97)

---

## Step 2: Add Field Mappings in Factory

**File:** `src/readers/factory.py`

Add `FBillNo` field mapping to these configs:
- `PRODUCTION_RECEIPT_CONFIG`
- `PURCHASE_RECEIPT_CONFIG`
- `MATERIAL_PICKING_CONFIG`
- `SALES_DELIVERY_CONFIG`

Example:
```python
"bill_no": FieldMapping("FBillNo"),
```

---

## Step 3: Add Response Models

**File:** `src/models/mto_status.py`

Add new Pydantic models:
```python
class OrderNode(BaseModel):
    """Order node in relationship tree."""
    bill_no: str
    label: str  # Chinese: "销售订单", "生产订单", etc.

class DocumentNode(BaseModel):
    """Document linked to an order."""
    bill_no: str
    label: str
    linked_order: Optional[str] = None

class MTORelatedOrdersResponse(BaseModel):
    """Response for /api/mto/{mto_number}/related-orders"""
    mto_number: str
    orders: dict[str, list[OrderNode]]      # sales_orders, production_orders, purchase_orders
    documents: dict[str, list[DocumentNode]] # receipts, pickings, deliveries
    query_time: datetime
    data_source: str = "live"
```

---

## Step 4: Add Handler Method

**File:** `src/query/mto_handler.py`

Add `get_related_orders(mto_number: str)` method:
1. Parallel fetch all 7 forms via `asyncio.gather()`
2. Extract unique bill_no from each result set
3. Return `MTORelatedOrdersResponse`

Key logic:
```python
async def get_related_orders(self, mto_number: str) -> MTORelatedOrdersResponse:
    (sales, prods, purch, prod_receipts, picks, deliveries, purch_receipts) = await asyncio.gather(
        self._readers["sales_order"].fetch_by_mto(mto_number),
        self._readers["production_order"].fetch_by_mto(mto_number),
        self._readers["purchase_order"].fetch_by_mto(mto_number),
        self._readers["production_receipt"].fetch_by_mto(mto_number),
        self._readers["material_picking"].fetch_by_mto(mto_number),
        self._readers["sales_delivery"].fetch_by_mto(mto_number),
        self._readers["purchase_receipt"].fetch_by_mto(mto_number),
    )
    # Deduplicate by bill_no, build response...
```

---

## Step 5: Add API Endpoint

**File:** `src/api/routers/mto.py`

Add new endpoint:
```python
@router.get("/mto/{mto_number}/related-orders", response_model=MTORelatedOrdersResponse)
async def get_mto_related_orders(
    request: Request,
    mto_number: str,
    current_user: str = Depends(get_current_user),
):
    handler = request.app.state.mto_handler
    return await handler.get_related_orders(mto_number)
```

---

## Step 6: Frontend - CSS Tree Styles

**File:** `src/frontend/static/css/main.css`

Add tree visualization styles:
```css
.tree-container { /* Container with connecting lines */ }
.tree-node { /* Node box: border, padding, rounded */ }
.tree-label { /* Chinese label: 销售订单 */ }
.tree-value { /* Bill number: XSDD001234 */ }
.tree-root { /* MTO node: emerald accent */ }
.tree-sales { /* Violet accent */ }
.tree-production { /* Sky accent */ }
.tree-purchase { /* Amber accent */ }
.tree-children { /* Indented children with left border line */ }
.tree-branch::before { /* Horizontal connector line */ }
```

---

## Step 7: Frontend - Alpine.js Component

**File:** `src/frontend/dashboard.html`

Add collapsible section after BOM table:
```html
<!-- 订单关联图 Section -->
<div x-show="childItems.length > 0" class="mt-6 ...">
  <div class="bg-slate-800 px-6 py-4 cursor-pointer" @click="relatedOrdersExpanded = !relatedOrdersExpanded">
    <h2>订单关联图</h2>
    <i :data-lucide="relatedOrdersExpanded ? 'chevron-up' : 'chevron-down'"></i>
  </div>
  <div x-show="relatedOrdersExpanded" class="p-6">
    <div class="tree-container">
      <!-- MTO Root -->
      <div class="tree-node tree-root">
        <span class="tree-label">MTO号</span>
        <span class="tree-value" x-text="mtoNumber"></span>
      </div>
      <!-- Orders branches with x-for loops -->
    </div>
  </div>
</div>
```

**File:** `src/frontend/static/js/dashboard.js`

Add state and method:
```javascript
relatedOrders: null,
relatedOrdersExpanded: true,
relatedOrdersLoading: false,

async fetchRelatedOrders() {
  this.relatedOrdersLoading = true;
  this.relatedOrders = await api.get(`/mto/${this.mtoNumber}/related-orders`);
  this.relatedOrdersLoading = false;
}
```

Call `fetchRelatedOrders()` after successful `search()`.

---

## Files to Modify (Summary)

| File | Change |
|------|--------|
| `src/readers/models.py` | Add `bill_no` to 4 models |
| `src/readers/factory.py` | Add `FBillNo` field mapping to 4 configs |
| `src/models/mto_status.py` | Add 3 new response models |
| `src/query/mto_handler.py` | Add `get_related_orders()` method |
| `src/api/routers/mto.py` | Add `/related-orders` endpoint |
| `src/frontend/static/css/main.css` | Add tree CSS styles |
| `src/frontend/dashboard.html` | Add relationship diagram section |
| `src/frontend/static/js/dashboard.js` | Add fetch/display logic |

---

## Verification

1. **API Test:**
   ```bash
   curl http://localhost:8000/api/mto/AK2510034/related-orders
   ```
   Expect JSON with orders and documents arrays containing bill_no values.

2. **UI Test:**
   - Search for an MTO number
   - Verify "订单关联图" section appears below table
   - Click to expand/collapse
   - Verify bill numbers display correctly with Chinese labels
   - Verify color coding (green=MTO, violet=sales, sky=production, amber=purchase)

3. **Edge Cases:**
   - MTO with only production orders (no sales/purchase)
   - MTO with no related documents
   - Duplicate bill numbers (should be deduplicated)
