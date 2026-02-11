# QuickPulse V2 - Features Overview

> **产品状态明细表** (Product Status Detail Sheet) dashboard integrated with Kingdee K3Cloud ERP

## Application Overview

QuickPulse V2 is a web dashboard for querying **计划跟踪号** (MTO/Production Tracking Numbers) to display complete BOM status with real-time inventory data. It uses a two-tier caching architecture (SQLite + in-memory) for sub-100ms query responses.

**Tech Stack:**
- Backend: Python 3.11+, FastAPI, SQLite (WAL mode), aiosqlite
- Frontend: Alpine.js, Tailwind CSS (CDN), Lucide icons
- External: Kingdee K3Cloud WebAPI SDK
- Deployment: Docker Compose, Uvicorn, Aliyun CVM (`121.41.81.36`)

---

## Core Feature: MTO Query

Query a **计划跟踪号** (MTO Number) to get the complete BOM status:

| Data Point | Description |
|------------|-------------|
| **Parent Item** | Customer name, delivery date |
| **Child Items** | All BOM components with material types |
| **Quantities** | Sales order, instock must/real, purchase order, pick actual, purchase stock-in |

**API Endpoint**: `GET /api/mto/{mto_number}`

### Response Structure

```json
{
  "mto_number": "AK2510034",
  "parent_item": {
    "mto_number": "AK2510034",
    "customer_name": "Customer Name",
    "delivery_date": "2025-03-15T00:00:00"
  },
  "child_items": [
    {
      "material_code": "07.01.001",
      "material_name": "Product Name",
      "specification": "Spec",
      "bom_short_name": "BOM-Name",
      "aux_attributes": "Blue",
      "material_type": "成品",
      "material_type_code": 1,
      "sales_order_qty": "100",
      "prod_instock_must_qty": "0",
      "purchase_order_qty": "0",
      "pick_actual_qty": "0",
      "prod_instock_real_qty": "80",
      "purchase_stock_in_qty": "0"
    }
  ],
  "query_time": "2025-02-02T10:30:45.123Z",
  "data_source": "cache"
}
```

---

## Dashboard Features (`/dashboard.html`)

### Search Section
- **MTO Number Input**: Single text field for entering tracking number
- **URL State**: MTO number automatically appended to URL (`?mto=AK2510034`)
- **Keyboard Shortcuts**:
  - `/` - Quick focus on search field
  - `F11` - Toggle fullscreen mode
  - `Esc` - Exit fullscreen

### MTO Summary Card
- MTO Number (bold, monospace font)
- Customer Name
- Delivery Date (formatted as YYYY-MM-DD)

### BOM Components Table

| Column | Field | Description |
|--------|-------|-------------|
| 物料编码 | `material_code` | Material code |
| 物料名称 | `material_name` | Material name |
| 规格型号 | `specification` | Specification |
| BOM简称 | `bom_short_name` | BOM short name (07.xx only) |
| 辅助属性 | `aux_attributes` | Color/size variants |
| 物料类型 | `material_type` | 成品/自制/包材 |
| 销售订单.数量 | `sales_order_qty` | Sales order quantity (07.xx only) |
| 生产入库单.应收数量 | `prod_instock_must_qty` | PRD_INSTOCK must qty (05.xx only) |
| 采购订单.数量 | `purchase_order_qty` | Purchase order qty (03.xx only) |
| 生产领料单.实发数量 | `pick_actual_qty` | Picked qty (05.xx/03.xx) |
| 生产入库单.实收数量 | `prod_instock_real_qty` | PRD_INSTOCK real qty (07.xx/05.xx) |
| 采购订单.累计入库数量 | `purchase_stock_in_qty` | Purchase stock-in qty (03.xx only) |

### Related Orders Section
Shows all linked orders by type:
- Sales Orders (销售订单)
- Purchase Orders (采购订单)
- Production Orders (生产订单)
- Production Receipts (生产入库)
- Purchase Receipts (采购入库)
- Sales Deliveries (销售出库)
- Material Picking (生产领料)

### Action Buttons
- **Export to CSV**: Downloads MTO data as UTF-8 CSV
- **Fullscreen**: Maximizes table view
- **Collapse/Expand**: Toggle header visibility

---

## Data Synchronization (`/sync.html`)

### Auto-Sync Schedule
| Time | Days Back |
|------|-----------|
| 07:00 | 30 days |
| 12:00 | 30 days |
| 16:00 | 30 days |
| 18:00 | 30 days |

### Manual Sync
- Configurable days-back (1-365)
- Force refresh option (ignore cache)
- Real-time progress tracking
- Sync history view (last 10 operations)

### Data Sources Synced
9 Kingdee forms are synchronized:

| Form ID | Chinese Name | Purpose |
|---------|-------------|---------|
| PRD_MO | 生产订单 | Production orders |
| PRD_PPBOM | 生产用料清单 | BOM components |
| PUR_PurchaseOrder | 采购订单 | Purchase orders |
| PRD_INSTOCK | 生产入库单 | Production receipts |
| STK_InStock | 采购入库单 | Purchase receipts |
| SAL_OUTSTOCK | 销售出库单 | Sales deliveries |
| PRD_PickMtrl | 生产领料单 | Material picking |
| SAL_SaleOrder | 销售订单 | Sales orders |
| SUB_POORDER | 委外订单 | Subcontracting orders |

---

## Three-Tier Caching Architecture

| Tier | Storage | Response Time | TTL | Purpose |
|------|---------|---------------|-----|---------|
| **L1** | Memory | <10ms | 5 min | Hot queries |
| **L2** | SQLite | ~100ms | 1 hour | Persistent cache |
| **L3** | Kingdee API | 1-5s | Live | Fallback |

### Cache Management Endpoints
- `GET /api/cache/stats` - Cache statistics
- `POST /api/cache/clear` - Clear memory cache
- `POST /api/cache/warm` - Pre-load MTOs
- `GET /api/cache/hot-mtos` - Frequently queried MTOs

---

## API Endpoints Summary

### Authentication (`/api/auth`)
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/auth/token` | POST | Login with username/password |

### MTO Query (`/api/mto`)
| Endpoint | Method | Purpose | Rate Limit |
|----------|--------|---------|------------|
| `/api/mto/{mto_number}` | GET | Get MTO status with BOM | 30/min |
| `/api/mto/{mto_number}/related-orders` | GET | Get related orders | 30/min |
| `/api/search` | GET | Search MTOs | 60/min |
| `/api/export/mto/{mto_number}` | GET | Export to CSV | 20/min |

### Sync Management (`/api/sync`)
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/sync/trigger` | POST | Start manual sync |
| `/api/sync/status` | GET | Get sync progress |
| `/api/sync/config` | GET/PUT | Sync configuration |
| `/api/sync/history` | GET | Sync history |

### Cache Management (`/api/cache`)
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/cache/stats` | GET | Cache statistics |
| `/api/cache/clear` | POST | Clear memory cache |
| `/api/cache/warm` | POST | Pre-load MTOs |
| `/api/cache/hot-mtos` | GET | Hot MTO list |

### Health & Static
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Login page |
| `/dashboard.html` | GET | MTO query dashboard |
| `/sync.html` | GET | Sync management |
| `/health` | GET | Health check |

---

## Material Type Routing

| Code Prefix | Type | Source Form | MTO Field | Receipts From |
|-------------|------|-------------|-----------|---------------|
| `07.xx.xxx` | 成品 (Finished) | SAL_SaleOrder | FMtoNo | PRD_INSTOCK |
| `05.xx.xxx` | 自制 (Self-Made) | PRD_MO | FMTONo | PRD_INSTOCK |
| `03.xx.xxx` | 外购 (Purchased) | PUR_PurchaseOrder | FMtoNo | STK_InStock |

---

## Authentication & Security

- **Token Type**: Bearer (JWT-based)
- **Expiration**: 24 hours
- **Password**: Fixed "quickpulse" for all users
- **Rate Limiting**: Applied per endpoint
- **CORS**: Same origin only
- **Auto-logout**: Redirects on 401 response

---

## Data Flow for MTO Lookup

```
User Input: MTO "AK2510034"
    │
    ▼
[Kingdee Client] → Parallel Queries:
    ├─ PRD_MO.FMTONo = 'AK2510034'
    │  → Get parent item (material, customer, delivery date)
    │
    ├─ PRD_PPBOM.FMTONO = 'AK2510034'
    │  → Get child items with material types
    │
    ├─ By Material Type:
    │  ├─ Type 1 (自制): PRD_INSTOCK.FMtoNo
    │  ├─ Type 2 (外购): STK_InStock (RKD01_SYS)
    │  └─ Type 3 (委外): STK_InStock (RKD02_SYS)
    │
    └─ Additional queries:
       ├─ PRD_PickMtrl (material picking)
       ├─ SAL_OUTSTOCK (sales delivery)
       └─ PUR_PurchaseOrder (order quantities)
    │
    ▼
[Aggregation] → Combine results by material code
    │
    ▼
Response: MTOStatusResponse
```

---

## Performance Characteristics

| Operation | Response Time | Notes |
|-----------|---------------|-------|
| Hot memory cache hit | <10ms | L1 cache |
| SQLite cache hit | ~100ms | L2 cache |
| Kingdee API call | 1-5s | Live query |
| Full sync (90 days) | 5-15 min | Parallel processing |
| CSV export | <1s | Live data |

---

## Configuration Files

| File | Purpose |
|------|---------|
| `config/mto_config.json` | Material class routing rules |
| `sync_config.json` | Sync schedule, parallel chunks |
| `.env` | Kingdee API credentials (gitignored) |
| `src/database/schema.sql` | Database schema |

---

## Database Tables

| Table | Purpose |
|-------|---------|
| `cached_production_orders` | PRD_MO data |
| `cached_production_bom` | PRD_PPBOM data |
| `cached_purchase_orders` | PUR_PurchaseOrder data |
| `cached_subcontracting_orders` | SUB_POORDER data |
| `cached_production_receipts` | PRD_INSTOCK data |
| `cached_purchase_receipts` | STK_InStock data |
| `cached_material_picking` | PRD_PickMtrl data |
| `cached_sales_delivery` | SAL_OUTSTOCK data |
| `cached_sales_orders` | SAL_SaleOrder data |
| `sync_history` | Sync operation history |
| `_migrations` | Schema migration tracking |

---

## Deployment

### CVM (Shared Aliyun ECS)

> Full infrastructure docs: `docs/CVM_INFRASTRUCTURE.md`

| Environment | URL | Port | Branch |
|---|---|---|---|
| **Prod** | `http://121.41.81.36:8003` | `:8003` | `main` |
| **Dev** | `http://121.41.81.36:8004` | `:8004` | `develop` |

- **Server**: `root@121.41.81.36` (Ubuntu 22.04.5 LTS, 4 cores, 7.1 GB RAM)
- **Deploy**: `/opt/ops/scripts/deploy.sh quickpulse <prod|dev>`
- **CI/CD**: Push to `develop` auto-deploys dev; manual dispatch for prod
- **Secrets**: `/opt/ops/secrets/quickpulse/{prod,dev}.env` (KINGDEE_* credentials)
- **Volumes**: `qp-{prod,dev}-data` (SQLite), `qp-{prod,dev}-reports` (reports)
- **Co-hosted with**: Fluent Skills (`:8001/:8002`), jiejiawater (`:8010-8021`), Grafana (`:3100`)

### Local Development

```bash
cp .env.example .env   # Fill in Kingdee credentials
uvicorn src.main:app --reload --port 8000
# or
docker-compose -f docker-compose.dev.yml up --build
```
