# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

QuickPulse V2 is a web dashboard that displays **产品状态明细表** (Product Status Detail Sheet) by querying **计划跟踪号** (MTO Number). It integrates with Kingdee K3Cloud ERP via their Python SDK.

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, SQLite (WAL mode), aiosqlite
- **Frontend**: Alpine.js, Tailwind CSS (CDN)
- **External**: Kingdee K3Cloud WebAPI SDK (`kingdee.cdp.webapi.sdk`)
- **Deployment**: Docker Compose, Uvicorn

## Architecture

### Two-Layer Data Architecture
```
Layer 1 (Cache)     → SQLite snapshot cache    → <100ms queries
Layer 2 (Real-time) → Direct Kingdee API calls → 1-5s queries
```

### MTO Query Data Flow
```
User Input: MTO Number (e.g., AK2510034)
    │
    ▼
PRD_MO (生产订单) → Get parent item info + FBillNo
    │
    ▼ Link via FMOBillNO
PRD_PPBOM (生产用料清单) → Get child items + FMaterialType
    │
    ▼ Parallel queries by material type:
    ├─ FMaterialType=1 (自制) → PRD_INSTOCK receipts
    ├─ FMaterialType=2 (外购) → STK_InStock (RKD01_SYS)
    └─ FMaterialType=3 (委外) → STK_InStock (RKD02_SYS)
    │
    ▼
Aggregate and return MTOStatusResponse
```

### Key Material Type Logic
- `FMaterialType=1` (自制件): Query `PRD_INSTOCK` for receipts
- `FMaterialType=2` (外购件): Query `STK_InStock` with `FBillTypeID.FNumber='RKD01_SYS'`
- `FMaterialType=3` (委外件): Query `STK_InStock` with `FBillTypeID.FNumber='RKD02_SYS'`

## Commands

### Development
```bash
# Install dependencies
pip install -e .

# Run development server
uvicorn src.main:app --reload --port 8000

# Run with Docker (development)
docker-compose -f docker-compose.dev.yml up --build
```

### Production
```bash
# Docker production build
docker-compose up -d --build

# Check health
curl http://localhost:8000/health
```

### Testing
```bash
# Run all tests
pytest

# Run single test file
pytest tests/test_kingdee_client.py -v

# Run with coverage
pytest --cov=src
```

### Kingdee SDK Exploration
```bash
# Explore API fields (uses conf.ini credentials)
python scripts/explore_all_api_fields.py
```

## Kingdee K3Cloud SDK Usage

The SDK is initialized from `conf.ini`:
```python
from k3cloud_webapi_sdk.main import K3CloudApiSdk

api_sdk = K3CloudApiSdk("http://server:port/k3cloud/")
api_sdk.Init(config_path='conf.ini', config_node='config')

# Execute query
params = {
    "FormId": "PRD_MO",
    "FieldKeys": "FBillNo,FMTONo,FMaterialId.FNumber",
    "FilterString": "FMTONo='AK2510034'",
    "Limit": 100
}
result = api_sdk.ExecuteBillQuery(params)
```

## Key Kingdee Form IDs

| Form ID | Chinese Name | Purpose |
|---------|-------------|---------|
| PRD_MO | 生产订单 | Parent item (production order) |
| PRD_PPBOM | 生产用料清单 | BOM components with material type |
| PRD_INSTOCK | 生产入库单 | Self-made item receipts |
| PUR_PurchaseOrder | 采购订单 | Purchase order quantities |
| STK_InStock | 采购入库单 | Purchase/subcontracting receipts |
| SUB_POORDER | 委外订单 | Subcontracting order quantities |
| PRD_PickMtrl | 生产领料单 | Material picking |
| SAL_OUTSTOCK | 销售出库单 | Sales deliveries |

## Project Structure (Target)

```
src/
├── config.py           # Single config class (from conf.ini + sync_config.json)
├── exceptions.py       # Custom exception hierarchy
├── main.py             # FastAPI app entry
├── kingdee/
│   └── client.py       # Async wrapper around K3Cloud SDK
├── readers/            # One reader per Kingdee form
│   ├── base.py         # Abstract BaseReader
│   ├── production_order.py    # PRD_MO
│   ├── production_bom.py      # PRD_PPBOM
│   └── ...
├── database/
│   ├── connection.py   # aiosqlite connection
│   └── schema.sql      # Cache tables with indexes
├── sync/
│   ├── sync_service.py # Orchestrates data sync
│   └── scheduler.py    # Auto-sync at 07:00, 12:00, 16:00, 18:00
├── query/
│   └── mto_handler.py  # MTO lookup logic with parallel fetches
├── api/routers/
│   ├── mto.py          # GET /api/mto/{mto_number}
│   └── sync.py         # POST /api/sync/trigger, GET /api/sync/status
└── frontend/           # Static HTML/JS served by FastAPI
```

## Configuration Files

- `conf.ini`: Kingdee K3Cloud API credentials (not committed, see template)
- `sync_config.json`: Sync schedule and performance settings
- `.gitignore`: Excludes `data/*.json`, `*.log`, `__pycache__/`

## API Field Documentation

Detailed field mappings are in `docs/fields/` and `docs/api/`:
- `PRD_MO_FIELDS.md` - Production order fields
- `PRD_PPBOM_FIELDS.md` - BOM component fields
- `STK_InStock_FIELDS.md` - Instock receipt fields

## Important Implementation Notes

1. **超领 Detection**: Negative `FNoPickedQty` means over-picking - highlight in red
2. **Async SDK Calls**: Use `asyncio.Lock()` and `run_in_executor()` since SDK is synchronous
3. **Parallel Fetching**: Use `asyncio.gather()` for independent receipt queries by material type
4. **SQLite WAL Mode**: Enable for better concurrent read/write performance
5. **Chunk Sync**: Process date ranges in 7-day chunks to avoid memory issues
