# QuickPulse V2 Implementation Plan

## Objective
Build a web dashboard that displays **产品状态明细表** (Product Status Detail Sheet) when searching by **计划跟踪号** (MTO Number), following the architecture established in `QUICKPULSE_V2_PLAN.md`.

---

## Target Display Structure

When user searches by MTO Number (e.g., `AK2510034`), display a hierarchical view:

### Parent Item (父项) - From Production Order (PRD_MO)
| Column | API Field | Description |
|--------|-----------|-------------|
| 生产订单编号 | FBillNo | Production Order Number |
| 生产车间 | FWorkShopID | Workshop |
| 计划跟踪号 | FMTONo | MTO Number (search key) |
| 父项物料编码 | FMaterialId.FNumber | Parent Material Code |
| 父项物料名称 | FMaterialId.FName | Parent Material Name |
| 父项规格型号 | FMaterialId.FSpecification | Parent Spec |
| 父项辅助属性 | FAuxPropId | Color/Spec (物料规格+产品颜色) |
| 订单数量 | FQty | Order Quantity |

### Child Items (子项) - From Production BOM (PRD_PPBOM)
| Column | API Field | Source | Notes |
|--------|-----------|--------|-------|
| 子项物料编码 | FMaterialID.FNumber | PRD_PPBOM | |
| 子项物料名称 | FMaterialID.FName | PRD_PPBOM | |
| 子项规格型号 | FMaterialID.FSpecification | PRD_PPBOM | |
| 子项辅助属性 | FAuxPropId | PRD_PPBOM | 产品颜色 |
| **物料类型** | FMaterialType | PRD_PPBOM | 1=自制, 2=外购, 3=委外 |
| 需求数量 | FNeedQty | PRD_PPBOM | BOM requirement |
| 已领数量 | FPickedQty | PRD_PPBOM | |
| 未领数量 | FNoPickedQty | PRD_PPBOM | negative = 超领 |
| **订单数量** | FQty | PUR_PurchaseOrder / SUB_POORDER | 外购/委外 only |
| **入库数量** | FRealQty | *See below* | Source by type |
| **未入库数量** | FRemainStockInQty / FNoStockInQty | PUR/SUB Order | Or calculated |
| 销售出库 | FRealQty | SAL_OUTSTOCK | |
| 即时库存 | F_QWJI_JSKC | Custom field | Real-time |

#### 入库数量 Source by Material Type
| Material Type | Chinese | 入库数量 Source |
|--------------|---------|----------------|
| 1 (自制) | 生产入库 | PRD_INSTOCK `FEntity_FRealQty` |
| 2 (外购) | 采购入库 | STK_InStock `FInStockEntry_FRealQty` (FBillTypeID=RKD01_SYS) |
| 3 (委外) | 委外入库 | STK_InStock `FInStockEntry_FRealQty` (FBillTypeID=RKD02_SYS) |

---

## Data Flow (MTO Tracing)

```
User Input: 计划跟踪号 (MTO Number)
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 1: Query PRD_MO (生产订单) - Parent Item Info          │
│   FilterString: FMTONo='AK2510034'                         │
│   Get: FBillNo, FMaterialId, FQty (订单数量), FWorkShopID  │
└─────────────────────────────────────────────────────────────┘
         │
         ▼ FMOBillNO (from PRD_MO.FBillNo)
┌─────────────────────────────────────────────────────────────┐
│ Step 2: Query PRD_PPBOM (生产用料清单) - Child Items        │
│   FilterString: FMOBillNO='MO251203242'                    │
│   Get: Child materials, FMaterialType, FNeedQty,           │
│        FPickedQty, FNoPickedQty                            │
│   NOTE: FMaterialType determines receipt source!           │
└─────────────────────────────────────────────────────────────┘
         │
         ▼ Parallel queries based on material type
┌─────────────────────────────────────────────────────────────┐
│ Step 3a: PRD_INSTOCK (生产入库) - 自制品 (FMaterialType=1)  │
│   Filter: FEntity_FMtoNo='AK2510034'                       │
│   Get: FRealQty for self-made items                        │
├─────────────────────────────────────────────────────────────┤
│ Step 3b: PUR_PurchaseOrder - 外购物料 Order Info            │
│   Filter: FPOOrderEntry_FMtoNo='AK2510034'                 │
│   Get: 采购数量(FQty), 累计入库(FStockInQty),              │
│        剩余入库(FRemainStockInQty)                         │
├─────────────────────────────────────────────────────────────┤
│ Step 3c: STK_InStock (采购入库) - 外购物料 Receipts         │
│   Filter: FInStockEntry_FMtoNo='AK2510034'                 │
│          AND FBillTypeID.FNumber='RKD01_SYS'               │
│   Get: FRealQty for purchased items                        │
├─────────────────────────────────────────────────────────────┤
│ Step 3d: SUB_POORDER - 委外加工 Order Info                  │
│   Filter: FTreeEntity_FMtoNo='AK2510034'                   │
│   Get: 委外数量(FQty), 入库数量(FStockInQty),              │
│        未入库(FNoStockInQty)                               │
├─────────────────────────────────────────────────────────────┤
│ Step 3e: STK_InStock (委外入库) - 委外加工 Receipts         │
│   Filter: FInStockEntry_FMtoNo='AK2510034'                 │
│          AND FBillTypeID.FNumber='RKD02_SYS'               │
│   Get: FRealQty for subcontracted items                    │
├─────────────────────────────────────────────────────────────┤
│ Step 3f: PRD_PickMtrl (生产领料) - 领料跟踪                 │
│   Filter: FEntity_FMTONO='AK2510034'                       │
│   Get: 申请数量(FAppQty), 实发数量(FActualQty)             │
├─────────────────────────────────────────────────────────────┤
│ Step 3g: SAL_OUTSTOCK (销售出库) - 出库跟踪                 │
│   Filter: FSAL_OUTSTOCKENTRY_FMTONO='AK2510034'            │
│   Get: FRealQty for delivered items                        │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 4: Aggregate by Material Type                          │
│   - Match child materials by code across all sources       │
│   - Use correct receipt source based on FMaterialType:     │
│     * 自制(1) → PRD_INSTOCK                                │
│     * 外购(2) → STK_InStock (标准采购)                     │
│     * 委外(3) → STK_InStock (委外入库)                     │
│   - Calculate 未入库数量 = 需求数量 - 入库数量             │
│   - Highlight negative 未领数量 (超领)                      │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 5: Return MTOStatusResponse                            │
│   - Parent item info                                       │
│   - List of child items with all quantities by type        │
└─────────────────────────────────────────────────────────────┘
```

---

## Quantity Source Logic by Material Type

**IMPORTANT**: Quantities come from different sources depending on the material type. PRD_PPBOM provides the BOM structure and picking quantities, but **receipt quantities** come from different forms.

### Material Type Determination

The `FMaterialType` field in PRD_PPBOM indicates:
- `1` = 自制件 (Self-made) → Receipt from PRD_INSTOCK
- `2` = 外购件 (Purchased) → Receipt from STK_InStock (标准采购入库)
- `3` = 委外件 (Subcontracted) → Receipt from STK_InStock (委外入库)

### Quantity Source Matrix

| Material Type | Chinese | Order Qty Source | Receipt Qty Source | Form ID |
|--------------|---------|------------------|-------------------|---------|
| **Parent Item** | 生产订单 | PRD_MO `FQty` | PRD_INSTOCK `FRealQty` | PRD_MO, PRD_INSTOCK |
| **Self-made** (自制件) | 生产入库 | PRD_PPBOM `FNeedQty` | PRD_INSTOCK `FRealQty` | PRD_PPBOM, PRD_INSTOCK |
| **Purchased** (外购物料) | 采购入库 | PUR_PurchaseOrder `FQty` | STK_InStock `FRealQty` | PUR_PurchaseOrder, STK_InStock |
| **Subcontracted** (委外加工) | 委外入库 | SUB_POORDER `FQty` | STK_InStock `FRealQty` | SUB_POORDER, STK_InStock |
| **Picking** (领料) | 生产领料 | PRD_PPBOM `FMustQty` | PRD_PickMtrl `FRealQty` | PRD_PPBOM, PRD_PickMtrl |
| **Sales** (销售出库) | 销售出库 | SAL_SaleOrder `FQty` | SAL_OUTSTOCK `FRealQty` | SAL_SaleOrder, SAL_OUTSTOCK |

### Key Fields by Source

#### For 外购物料 (Purchased Materials)
```python
# From PUR_PurchaseOrder
采购数量 = FPOOrderEntry_FQty
累计入库数量 = FPOOrderEntry_FStockInQty
剩余入库数量 = FPOOrderEntry_FRemainStockInQty

# From STK_InStock
实收数量 = FInStockEntry_FRealQty
```

#### For 委外加工 (Subcontracted Items)
```python
# From SUB_POORDER
委外数量 = FTreeEntity_FQty
已入库数量 = FTreeEntity_FStockInQty
未入库数量 = FTreeEntity_FNoStockInQty

# From STK_InStock (单据类型=委外入库单)
实收数量 = FInStockEntry_FRealQty
```

#### For 自制件 (Self-made Items)
```python
# From PRD_PPBOM
需求数量 = FPPBomEntry_FNeedQty

# From PRD_INSTOCK
实收数量 = FEntity_FRealQty
```

#### For 领料跟踪 (Material Picking)
```python
# From PRD_PickMtrl
申请数量 = FEntity_FAppQty
实发数量 = FEntity_FActualQty  # or FRealQty
```

### STK_InStock Document Type Differentiation

The STK_InStock form handles both purchase receipts and subcontracting receipts:
- **标准采购入库**: `FBillTypeID` = standard purchase
- **委外入库**: `FBillTypeID` = subcontracting receipt

Filter example:
```python
# For purchased materials only
FilterString: "FInStockEntry_FMtoNo='AK2510034' AND FBillTypeID.FNumber='RKD01_SYS'"

# For subcontracting receipts only
FilterString: "FInStockEntry_FMtoNo='AK2510034' AND FBillTypeID.FNumber='RKD02_SYS'"
```

---

## Phase 1: Foundation

### 1.1 Project Setup
**Create `pyproject.toml`:**
```toml
[project]
name = "quickpulse-v2"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "httpx>=0.26.0",
    "sqlalchemy>=2.0.25",
    "aiosqlite>=0.19.0",
]

[project.optional-dependencies]
dev = ["pytest>=7.4.0", "pytest-asyncio>=0.23.0"]
```

### 1.2 Config Class
**File:** `src/config.py`
- Read from `conf.ini`
- Validate required settings
- Single source of truth for all config

### 1.3 Kingdee Client Wrapper
**File:** `src/kingdee/client.py`
```python
class KingdeeClient:
    """Clean wrapper around K3Cloud SDK."""

    async def query(
        self,
        form_id: str,
        field_keys: list[str],
        filter_string: str,
        limit: int = 2000
    ) -> list[dict]:
        """Execute Query API call."""

    async def view(
        self,
        form_id: str,
        key_value: str
    ) -> dict:
        """Execute View API call for single record."""
```

### 1.4 Pydantic Models
**File:** `src/models/mto_status.py`
```python
class ParentItem(BaseModel):
    """Production order (father item) info."""
    production_order_no: str      # 生产订单编号
    workshop: str                 # 生产车间
    mto_number: str               # 计划跟踪号
    material_code: str            # 父项物料编码
    material_name: str            # 父项物料名称
    specification: str            # 父项规格型号
    aux_attributes: str           # 父项辅助属性
    order_qty: Decimal            # 订单数量

class ChildItem(BaseModel):
    """BOM component (child item) with status."""
    # Basic Info
    material_code: str            # 子项物料编码
    material_name: str            # 子项物料名称
    specification: str            # 子项规格型号
    aux_attributes: str           # 子项辅助属性
    material_type: int            # 物料类型: 1=自制, 2=外购, 3=委外
    material_type_name: str       # 物料类型名称

    # BOM Quantities (from PRD_PPBOM)
    required_qty: Decimal         # 需求数量 (FNeedQty)
    picked_qty: Decimal           # 已领数量 (FPickedQty)
    unpicked_qty: Decimal         # 未领数量 (FNoPickedQty, negative = 超领)

    # Order Quantities (source depends on material_type)
    order_qty: Decimal            # 订单数量 (采购/委外订单)

    # Receipt Quantities (source depends on material_type)
    receipt_qty: Decimal          # 入库数量 (实收)
    unreceived_qty: Decimal       # 未入库数量 (calculated or from order)

    # Picking Quantities (from PRD_PickMtrl)
    pick_request_qty: Decimal     # 申请数量 (FAppQty)
    pick_actual_qty: Decimal      # 实发数量 (FActualQty)

    # Sales & Inventory
    delivered_qty: Decimal        # 销售出库
    inventory_qty: Decimal        # 即时库存

    # Source tracking
    receipt_source: str           # 入库来源: PRD_INSTOCK/STK_InStock/STK_InStock(委外)

class MTOStatusResponse(BaseModel):
    """Complete MTO status response."""
    mto_number: str
    parent: ParentItem
    children: list[ChildItem]
    query_time: datetime
```

### 1.5 Database Schema
**File:** `src/database/schema.sql`
```sql
-- Cache for production orders
CREATE TABLE IF NOT EXISTS production_orders (
    id INTEGER PRIMARY KEY,
    mto_number TEXT NOT NULL,
    bill_no TEXT NOT NULL,
    workshop TEXT,
    material_code TEXT,
    material_name TEXT,
    specification TEXT,
    aux_attributes TEXT,
    qty REAL,
    raw_data TEXT,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_po_mto ON production_orders(mto_number);

-- Cache for production BOM entries
CREATE TABLE IF NOT EXISTS production_bom_entries (
    id INTEGER PRIMARY KEY,
    ppbom_bill_no TEXT NOT NULL,
    mo_bill_no TEXT NOT NULL,
    material_code TEXT NOT NULL,
    material_name TEXT,
    specification TEXT,
    aux_attributes TEXT,
    need_qty REAL,
    picked_qty REAL,
    no_picked_qty REAL,
    raw_data TEXT,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_bom_mo ON production_bom_entries(mo_bill_no);
```

---

## Phase 2: Data Ingestion

### 2.1 Base Reader
**File:** `src/readers/base.py`
```python
class BaseReader(ABC):
    """Abstract base reader for Kingdee data."""

    @property
    @abstractmethod
    def form_id(self) -> str: ...

    @property
    @abstractmethod
    def field_keys(self) -> list[str]: ...

    async def fetch_by_mto(self, mto_number: str) -> list[dict]: ...
    async def fetch_by_bill_no(self, bill_no: str) -> list[dict]: ...
```

### 2.2 Readers to Implement
| Reader | Form ID | Key Fields | Purpose |
|--------|---------|------------|---------|
| ProductionOrderReader | PRD_MO | FBillNo, FMTONo, FMaterialId.*, FQty | Parent item info |
| ProductionBOMReader | PRD_PPBOM | FMOBillNO, FMaterialID.*, FMaterialType, FNeedQty, FPickedQty | Child items & type |
| ProductionReceiptReader | PRD_INSTOCK | FEntity_FMtoNo, FEntity_FRealQty | 自制品 receipts |
| PurchaseOrderReader | PUR_PurchaseOrder | FPOOrderEntry_FMtoNo, FQty, FStockInQty, FRemainStockInQty | 外购 order info |
| PurchaseReceiptReader | STK_InStock | FInStockEntry_FMtoNo, FInStockEntry_FRealQty, FBillTypeID | 外购/委外 receipts |
| SubcontractingOrderReader | SUB_POORDER | FTreeEntity_FMtoNo, FQty, FStockInQty, FNoStockInQty | 委外 order info |
| MaterialPickingReader | PRD_PickMtrl | FEntity_FMTONO, FAppQty, FActualQty | Actual picking |
| SalesDeliveryReader | SAL_OUTSTOCK | FSAL_OUTSTOCKENTRY_FMTONO, FRealQty | Sales delivery |

### 2.3 Sync Service
**File:** `src/sync/sync_service.py`
- Manual sync trigger endpoint
- Fetch by MTO number
- Cache results in SQLite
- Track sync timestamps

---

## Phase 3: Query & API

### 3.1 MTO Query Handler
**File:** `src/query/mto_handler.py`
```python
class MTOQueryHandler:
    """Handler for MTO number lookups."""

    async def get_status(self, mto_number: str) -> MTOStatusResponse:
        # 1. Get production order
        prod_orders = await self.prod_reader.fetch_by_mto(mto_number)

        # 2. Get BOM entries for each production order
        bom_entries = []
        for po in prod_orders:
            entries = await self.bom_reader.fetch_by_bill_no(po['FBillNo'])
            bom_entries.extend(entries)

        # 3. Get receipts (parallel)
        prod_receipts, purch_receipts, deliveries = await asyncio.gather(
            self.prod_receipt_reader.fetch_by_mto(mto_number),
            self.purch_receipt_reader.fetch_by_mto(mto_number),
            self.delivery_reader.fetch_by_mto(mto_number),
        )

        # 4. Aggregate and build response
        return self._build_response(
            prod_orders, bom_entries,
            prod_receipts, purch_receipts, deliveries
        )
```

### 3.2 FastAPI Routes
**File:** `src/api/routes.py`
```python
@router.get("/api/mto/{mto_number}", response_model=MTOStatusResponse)
async def get_mto_status(mto_number: str) -> MTOStatusResponse:
    """Get complete MTO status by tracking number."""
    handler = MTOQueryHandler(...)
    return await handler.get_status(mto_number)

@router.get("/api/search")
async def search_mto(q: str = Query(..., min_length=2)) -> list[MTOSummary]:
    """Search for MTO numbers (autocomplete)."""
    # Search cached production orders
```

---

## Phase 4: Frontend

### 4.1 Web Dashboard Layout
**File:** `src/frontend/index.html`
```
┌─────────────────────────────────────────────────────────────────┐
│ QuickPulse V2 - 产品状态明细表                                   │
├─────────────────────────────────────────────────────────────────┤
│ 计划跟踪号: [________________] [搜索]                            │
├─────────────────────────────────────────────────────────────────┤
│ 父项信息 (Production Order)                                      │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ 生产订单: MO251203242      车间: 潜水镜工段                  │ │
│ │ 物料编码: 07.18.422        物料名称: 潜水镜+呼吸管           │ │
│ │ 规格型号: M9610+SN9810     客户型号: 30318                   │ │
│ │ 辅助属性: 西班牙TNC        订单数量: 1,440                   │ │
│ └─────────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│ 子项明细 (BOM Components)                            [导出Excel] │
│ ┌────────┬────────┬──────┬──────┬──────┬──────┬──────┬──────┐  │
│ │物料编码│物料名称│需求量│已领量│未领量│入库量│出库量│库存  │  │
│ ├────────┼────────┼──────┼──────┼──────┼──────┼──────┼──────┤  │
│ │03.02.11│潜水镜+S│1,440 │1,440 │  0   │1,440 │1,440 │ 500  │  │
│ │03.20.00│潜水镜纸│1,440 │1,440 │  0   │1,440 │1,440 │ 200  │  │
│ │03.23.01│SN9810上│1,440 │1,500 │ -60  │1,440 │ 720  │ 100  │  │  ← Red highlight
│ │...     │...     │...   │...   │...   │...   │...   │...   │  │
│ └────────┴────────┴──────┴──────┴──────┴──────┴──────┴──────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Alpine.js Component
**File:** `src/frontend/static/js/app.js`
```javascript
document.addEventListener('alpine:init', () => {
    Alpine.data('mtoSearch', () => ({
        mtoNumber: '',
        loading: false,
        result: null,
        error: null,

        async search() {
            this.loading = true;
            this.error = null;
            try {
                const res = await fetch(`/api/mto/${this.mtoNumber}`);
                if (!res.ok) throw new Error('Not found');
                this.result = await res.json();
            } catch (e) {
                this.error = e.message;
            } finally {
                this.loading = false;
            }
        },

        isOverPicked(qty) {
            return qty < 0;  // Negative means over-picked
        }
    }));
});
```

### 4.3 Styling with Tailwind
- Red highlight for negative quantities (超领)
- Green for completed items
- Yellow for partial completion
- Progress bars for visual status

---

## Project Structure

```
Quickpulsev2/
├── pyproject.toml
├── conf.ini                      # Existing - Kingdee credentials
├── src/
│   ├── __init__.py
│   ├── config.py                 # Config class
│   ├── exceptions.py             # Custom exceptions
│   ├── main.py                   # FastAPI app entry
│   │
│   ├── kingdee/
│   │   ├── __init__.py
│   │   └── client.py             # K3Cloud SDK wrapper
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── production_order.py
│   │   ├── production_bom.py
│   │   └── mto_status.py         # Combined response model
│   │
│   ├── readers/
│   │   ├── __init__.py
│   │   ├── base.py               # Abstract base
│   │   ├── production_order.py   # PRD_MO
│   │   ├── production_bom.py     # PRD_PPBOM
│   │   ├── production_receipt.py # PRD_INSTOCK
│   │   ├── purchase_receipt.py   # STK_InStock
│   │   └── sales_delivery.py     # SAL_OUTSTOCK
│   │
│   ├── database/
│   │   ├── __init__.py
│   │   ├── connection.py
│   │   └── schema.sql
│   │
│   ├── query/
│   │   ├── __init__.py
│   │   └── mto_handler.py        # MTO lookup logic
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py             # FastAPI routes
│   │
│   └── frontend/
│       ├── index.html
│       └── static/
│           ├── css/styles.css
│           └── js/app.js
│
├── tests/
│   ├── __init__.py
│   ├── test_kingdee_client.py
│   └── test_mto_handler.py
│
├── docs/                         # Existing documentation
│   ├── API_FIELD_ANALYSIS.md
│   ├── api/
│   └── fields/
│
└── scripts/                      # Existing exploration scripts
    └── explore_*.py
```

---

## Verification Plan

### Phase 1 Complete When:
- [ ] `python -c "from src.config import Config; c = Config(); print(c.kingdee_server_url)"` works
- [ ] `python -c "from src.kingdee.client import KingdeeClient"` imports without error
- [ ] Kingdee client can execute test query against PRD_MO
- [ ] SQLite database created with correct schema

### Phase 2 Complete When:
- [ ] `ProductionOrderReader.fetch_by_mto("AK2510034")` returns data
- [ ] `ProductionBOMReader.fetch_by_bill_no("MO251203242")` returns BOM entries
- [ ] Data cached in SQLite after fetch

### Phase 3 Complete When:
- [ ] `GET /api/mto/AK2510034` returns complete `MTOStatusResponse`
- [ ] Response includes parent item with correct fields
- [ ] Response includes all child items with quantities
- [ ] Calculated fields (未入库数量, 未领数量) are correct

### Phase 4 Complete When:
- [ ] Web UI loads at `http://localhost:8000`
- [ ] Search by MTO number displays parent info
- [ ] BOM table shows all child items
- [ ] Negative quantities highlighted in red
- [ ] Export to Excel works

---

## API Query Patterns Reference

### Core Queries

```python
# Find Production Order by MTO (Parent Item)
{
    "FormId": "PRD_MO",
    "FieldKeys": "FBillNo,FMTONo,FMaterialId.FNumber,FMaterialId.FName,FQty,FWorkShopID.FName",
    "FilterString": "FMTONo='AK2510034'"
}

# Find BOM entries by Production Order (Child Items)
{
    "FormId": "PRD_PPBOM",
    "FieldKeys": "FPPBomEntry_FMaterialID.FNumber,FPPBomEntry_FMaterialID.FName,FPPBomEntry_FMaterialType,FPPBomEntry_FNeedQty,FPPBomEntry_FPickedQty,FPPBomEntry_FNoPickedQty",
    "FilterString": "FMOBillNO='MO251203242'"
}
```

### Receipt Queries by Material Type

```python
# 自制品: Production Receipts (PRD_INSTOCK)
{
    "FormId": "PRD_INSTOCK",
    "FieldKeys": "FEntity_FMaterialId.FNumber,FEntity_FRealQty,FEntity_FMustQty",
    "FilterString": "FEntity_FMtoNo='AK2510034'"
}

# 外购物料: Purchase Order Info (Order Qty, Received Qty)
{
    "FormId": "PUR_PurchaseOrder",
    "FieldKeys": "FBillNo,FPOOrderEntry_FMaterialId.FNumber,FPOOrderEntry_FQty,FPOOrderEntry_FStockInQty,FPOOrderEntry_FRemainStockInQty",
    "FilterString": "FPOOrderEntry_FMtoNo='AK2510034'"
}

# 外购物料: Purchase Receipts (STK_InStock - Standard Type)
{
    "FormId": "STK_InStock",
    "FieldKeys": "FInStockEntry_FMaterialId.FNumber,FInStockEntry_FRealQty,FInStockEntry_FMustQty",
    "FilterString": "FInStockEntry_FMtoNo='AK2510034' AND FBillTypeID.FNumber='RKD01_SYS'"
}

# 委外加工: Subcontracting Order Info
{
    "FormId": "SUB_POORDER",
    "FieldKeys": "FBillNo,FTreeEntity_FMaterialId.FNumber,FTreeEntity_FQty,FTreeEntity_FStockInQty,FTreeEntity_FNoStockInQty",
    "FilterString": "FTreeEntity_FMtoNo='AK2510034'"
}

# 委外加工: Subcontracting Receipts (STK_InStock - Subcontract Type)
{
    "FormId": "STK_InStock",
    "FieldKeys": "FInStockEntry_FMaterialId.FNumber,FInStockEntry_FRealQty,FInStockEntry_FMustQty",
    "FilterString": "FInStockEntry_FMtoNo='AK2510034' AND FBillTypeID.FNumber='RKD02_SYS'"
}
```

### Material Picking & Sales Queries

```python
# Material Picking (Actual Consumption)
{
    "FormId": "PRD_PickMtrl",
    "FieldKeys": "FEntity_FMaterialId.FNumber,FEntity_FAppQty,FEntity_FActualQty,FEntity_FPPBomBillNo",
    "FilterString": "FEntity_FMTONO='AK2510034'"
}

# Sales Deliveries
{
    "FormId": "SAL_OUTSTOCK",
    "FieldKeys": "FSAL_OUTSTOCKENTRY_FMaterialId.FNumber,FSAL_OUTSTOCKENTRY_FRealQty,FSAL_OUTSTOCKENTRY_FMustQty",
    "FilterString": "FSAL_OUTSTOCKENTRY_FMTONO='AK2510034'"
}
```

---

## Notes

1. **超领 Detection**: When `未领数量` (FNoPickedQty) is negative, it means materials were over-picked - highlight in red

2. **Material Type Determines Receipt Source**:
   - `FMaterialType = 1` (自制件) → Query PRD_INSTOCK
   - `FMaterialType = 2` (外购件) → Query STK_InStock with FBillTypeID='RKD01_SYS'
   - `FMaterialType = 3` (委外件) → Query STK_InStock with FBillTypeID='RKD02_SYS'

3. **入库数量 Sources**:
   - 自制品: PRD_INSTOCK `FEntity_FRealQty`
   - 外购物料: STK_InStock `FInStockEntry_FRealQty` (标准采购入库)
   - 委外加工: STK_InStock `FInStockEntry_FRealQty` (委外入库单)

4. **Order Quantity Sources**:
   - 外购物料: PUR_PurchaseOrder `FPOOrderEntry_FQty`
   - 委外加工: SUB_POORDER `FTreeEntity_FQty`
   - Shows: 累计入库数量, 剩余入库数量 for tracking

5. **Parallel Fetching**: Use `asyncio.gather()` for independent API calls by material type

6. **Caching Strategy**: Cache by MTO number with timestamp, refresh on demand

7. **Field Mapping Reference**: Use `docs/API_FIELD_ANALYSIS.md` for complete field documentation

8. **STK_InStock Document Types**:
   - `RKD01_SYS` = 标准采购入库单 (Standard Purchase Receipt)
   - `RKD02_SYS` = 委外入库单 (Subcontracting Receipt)
