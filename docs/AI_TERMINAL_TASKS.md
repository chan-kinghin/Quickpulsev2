# QuickPulse V2 - AI Terminal Task Allocation

> **Purpose**: This document assigns implementation tasks to 4 parallel AI terminals.
> **Reference**: See `IMPLEMENTATION_PLAN.md` for detailed code examples and architecture.

---

## ✅ IMPLEMENTATION STATUS: COMPLETE

**Last Updated**: 2026-01-18

All tasks across all 4 terminals have been implemented. Key implementation notes:

| Terminal | Tasks | Status | Notes |
|----------|-------|--------|-------|
| T1: Foundation | 11 tasks | ✅ Complete | Config, Database, Kingdee Client |
| T2: Data Readers | 11 tasks | ✅ Complete | Consolidated via factory pattern |
| T3: Sync & API | 10 tasks | ✅ Complete | Full sync service + REST API |
| T4: Frontend & Docker | 9 tasks | ✅ Complete | Dark theme UI + Docker deploy |

**Architecture Improvements**: Readers were consolidated from 9 separate files into a factory pattern (`src/readers/factory.py`) for reduced duplication.

---

## Quick Start Guide

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PARALLEL DEVELOPMENT TIMELINE (COMPLETE)                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Terminal 1: ████████████████████████████████████████████████████████████ ✅│
│              Foundation (config, db, client)                                │
│              COMPLETE                                                       │
│                                                                             │
│  Terminal 2: ████████████████████████████████████████████████████████████ ✅│
│              Data Readers (9 readers via factory)                           │
│              COMPLETE                                                       │
│                                                                             │
│  Terminal 3: ████████████████████████████████████████████████████████████ ✅│
│              Sync Service + API                                             │
│              COMPLETE                                                       │
│                                                                             │
│  Terminal 4: ████████████████████████████████████████████████████████████ ✅│
│              Frontend + Docker                                              │
│              COMPLETE                                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Terminal 1: Foundation Layer

> **Priority**: HIGH - Start First
> **Dependencies**: None
> **Total Tasks**: 9

### T1-1: Create pyproject.toml

**File**: `pyproject.toml`

**Content**:
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
    "schedule>=1.2.0",
]

[project.optional-dependencies]
dev = ["pytest>=7.4.0", "pytest-asyncio>=0.23.0"]
```

**Verification**:
```bash
pip install -e .
```

- [x] Done

---

### T1-2: Create src/__init__.py

**File**: `src/__init__.py`

**Content**:
```python
"""QuickPulse V2 - Product Status Dashboard"""
__version__ = "0.1.0"
```

**Verification**:
```bash
python -c "import src; print(src.__version__)"
```

- [x] Done

---

### T1-3: Create src/exceptions.py

**File**: `src/exceptions.py`

**Content**:
```python
"""Custom exceptions for QuickPulse V2."""


class QuickPulseError(Exception):
    """Base exception for all QuickPulse errors."""
    pass


class ConfigError(QuickPulseError):
    """Configuration-related errors."""
    pass


class KingdeeError(QuickPulseError):
    """Kingdee API errors."""
    pass


class KingdeeConnectionError(KingdeeError):
    """Connection to Kingdee failed."""
    pass


class KingdeeQueryError(KingdeeError):
    """Query execution failed."""
    pass


class DatabaseError(QuickPulseError):
    """Database operation errors."""
    pass


class SyncError(QuickPulseError):
    """Data synchronization errors."""
    pass
```

**Verification**:
```bash
python -c "from src.exceptions import KingdeeError; print('OK')"
```

- [x] Done

---

### T1-4: Create src/config.py

**File**: `src/config.py`

**Reference**: `IMPLEMENTATION_PLAN.md` Section 5.1.2

**Key Classes**:
- `KingdeeConfig` - Load from `conf.ini`
- `AutoSyncConfig` - Schedule settings
- `ManualSyncConfig` - Days range
- `PerformanceConfig` - Chunk/batch settings
- `SyncConfig` - Load/save from `sync_config.json`
- `Config` - Singleton main config

**Key Methods**:
```python
# KingdeeConfig.from_ini("conf.ini")
# SyncConfig.load("sync_config.json")
# SyncConfig.save()
# SyncConfig.reload()
```

**Verification**:
```bash
python -c "from src.config import Config; c = Config(); print(c.kingdee.server_url)"
```

- [x] Done

---

### T1-5: Create src/kingdee/__init__.py

**File**: `src/kingdee/__init__.py`

**Content**:
```python
"""Kingdee K3Cloud API integration."""
from src.kingdee.client import KingdeeClient

__all__ = ["KingdeeClient"]
```

- [x] Done

---

### T1-6: Create src/kingdee/client.py

**File**: `src/kingdee/client.py`

**Reference**: `IMPLEMENTATION_PLAN.md` Section 5.1.3

**Key Methods**:
```python
class KingdeeClient:
    async def query(form_id, field_keys, filter_string, limit, start_row) -> list[dict]
    async def query_all(form_id, field_keys, filter_string, page_size) -> list[dict]
    async def query_by_date_range(form_id, field_keys, date_field, start_date, end_date) -> list[dict]
    async def query_by_mto(form_id, field_keys, mto_field, mto_number) -> list[dict]
```

**Key Points**:
- Use `asyncio.Lock()` for thread safety
- Use `run_in_executor()` for sync SDK calls
- Convert 2D array response to list[dict]

**Verification**:
```bash
python -c "from src.kingdee.client import KingdeeClient; print('OK')"
```

- [x] Done

---

### T1-7: Create src/database/__init__.py and connection.py

**Files**:
- `src/database/__init__.py`
- `src/database/connection.py`

**connection.py Key Content**:
```python
import aiosqlite
from pathlib import Path

class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._connection = None

    async def connect(self):
        self._connection = await aiosqlite.connect(self.db_path)
        await self._init_schema()

    async def _init_schema(self):
        schema_path = Path(__file__).parent / "schema.sql"
        schema = schema_path.read_text()
        await self._connection.executescript(schema)
        await self._connection.commit()

    async def execute(self, query: str, params=None):
        async with self._connection.execute(query, params or []) as cursor:
            return await cursor.fetchall()

    async def close(self):
        if self._connection:
            await self._connection.close()
```

**Verification**:
```bash
python -c "from src.database.connection import Database; print('OK')"
```

- [x] Done

---

### T1-8: Create src/database/schema.sql

**File**: `src/database/schema.sql`

**Reference**: `IMPLEMENTATION_PLAN.md` Section 5.1.5

**Tables**:
- `cached_production_orders` (mto_number, bill_no, workshop, material_*, qty, synced_at)
- `cached_production_bom` (mo_bill_no, material_code, material_type, *_qty, synced_at)
- `sync_history` (started_at, finished_at, status, days_back, records_synced, error_message)

**Indexes**:
- `idx_po_mto` on `mto_number`
- `idx_po_synced` on `synced_at`
- `idx_bom_mo` on `mo_bill_no`

- [x] Done

---

### T1-9: Create sync_config.json

**File**: `sync_config.json` (project root)

**Content**:
```json
{
  "auto_sync": {
    "enabled": true,
    "schedule": ["07:00", "12:00", "16:00", "18:00"],
    "days_back": 90
  },
  "manual_sync": {
    "default_days": 90,
    "max_days": 365,
    "min_days": 1
  },
  "performance": {
    "chunk_days": 7,
    "batch_size": 1000,
    "parallel_chunks": 2,
    "retry_count": 3
  }
}
```

- [x] Done

---

### T1-10: Create src/models/__init__.py and Pydantic Models

**Files**:
- `src/models/__init__.py`
- `src/models/mto_status.py`
- `src/models/sync.py`

**src/models/__init__.py**:
```python
"""Pydantic models for QuickPulse V2."""
from src.models.mto_status import ParentItem, ChildItem, MTOStatusResponse, MTOSummary
from src.models.sync import (
    SyncTriggerRequest,
    SyncStatusResponse,
    SyncConfigResponse,
    SyncConfigUpdateRequest
)

__all__ = [
    "ParentItem",
    "ChildItem",
    "MTOStatusResponse",
    "MTOSummary",
    "SyncTriggerRequest",
    "SyncStatusResponse",
    "SyncConfigResponse",
    "SyncConfigUpdateRequest",
]
```

**Reference**: `IMPLEMENTATION_PLAN.md` Section 1.4 for model definitions

**Verification**:
```bash
python -c "from src.models import MTOStatusResponse, SyncTriggerRequest; print('OK')"
```

- [x] Done

---

### T1-11: Create Logging Configuration

**File**: `src/logging_config.py`

**Content**:
```python
"""Logging configuration for QuickPulse V2."""
import logging
import sys
from pathlib import Path

def setup_logging(log_level: str = "INFO", log_file: Path = None):
    """Configure application logging."""
    handlers = [logging.StreamHandler(sys.stdout)]

    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers
    )

    # Suppress noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    return logging.getLogger("quickpulse")
```

**Verification**:
```bash
python -c "from src.logging_config import setup_logging; logger = setup_logging(); logger.info('Test'); print('OK')"
```

- [x] Done

---

### T1 Completion Signal

When all T1 tasks complete, **notify Terminal 2** to start.

**Final Verification**:
```bash
python -c "
from src.config import Config
from src.kingdee.client import KingdeeClient
from src.database.connection import Database
from src.models import MTOStatusResponse
from src.logging_config import setup_logging
print('T1 Complete - All imports successful')
"
```

---

## Terminal 2: Data Readers

> **Priority**: HIGH
> **Dependencies**: Wait for Terminal 1 to complete T1-6 (KingdeeClient)
> **Total Tasks**: 11

### T2-1: Create src/readers/__init__.py

**File**: `src/readers/__init__.py`

**Content**:
```python
"""Data readers for Kingdee forms."""
from src.readers.base import BaseReader
from src.readers.production_order import ProductionOrderReader
from src.readers.production_bom import ProductionBOMReader
from src.readers.production_receipt import ProductionReceiptReader
from src.readers.purchase_order import PurchaseOrderReader
from src.readers.purchase_receipt import PurchaseReceiptReader
from src.readers.subcontracting_order import SubcontractingOrderReader
from src.readers.material_picking import MaterialPickingReader
from src.readers.sales_delivery import SalesDeliveryReader
from src.readers.sales_order import SalesOrderReader

__all__ = [
    "BaseReader",
    "ProductionOrderReader",
    "ProductionBOMReader",
    "ProductionReceiptReader",
    "PurchaseOrderReader",
    "PurchaseReceiptReader",
    "SubcontractingOrderReader",
    "MaterialPickingReader",
    "SalesDeliveryReader",
    "SalesOrderReader",
]
```

- [x] Done

---

### T2-2: Create src/readers/base.py

**File**: `src/readers/base.py`

**Reference**: `IMPLEMENTATION_PLAN.md` Section 5.2.1

**Abstract Base Class**:
```python
class BaseReader(ABC, Generic[T]):
    @property
    @abstractmethod
    def form_id(self) -> str: ...

    @property
    @abstractmethod
    def field_keys(self) -> list[str]: ...

    @property
    @abstractmethod
    def mto_field(self) -> str: ...

    @property
    def date_field(self) -> str:
        return "FDate"  # Override in subclass

    @abstractmethod
    def to_model(self, raw_data: dict) -> T: ...

    async def fetch_by_mto(self, mto_number: str) -> list[T]: ...
    async def fetch_by_date_range(self, start_date, end_date) -> list[T]: ...
    async def fetch_by_bill_no(self, bill_no: str) -> list[T]: ...
```

- [x] Done

---

### T2-3: Create src/readers/production_order.py (PRD_MO)

**File**: `src/readers/production_order.py`

**Reference**: `IMPLEMENTATION_PLAN.md` Section 5.2.3

**Form ID**: `PRD_MO`

**Field Keys**:
```python
[
    "FBillNo",
    "FMTONo",
    "FWorkShopID.FName",
    "FMaterialId.FNumber",
    "FMaterialId.FName",
    "FMaterialId.FSpecification",
    "FAuxPropId.FName",
    "FQty",
    "FStatus",
    "FCreateDate"
]
```

**MTO Field**: `FMTONo`

**Model Fields**: bill_no, mto_number, workshop, material_code, material_name, specification, aux_attributes, qty, status, create_date

- [x] Done

---

### T2-4: Create src/readers/production_bom.py (PRD_PPBOM)

**File**: `src/readers/production_bom.py`

**Form ID**: `PRD_PPBOM`

**Field Keys**:
```python
[
    "FBillNo",
    "FMOBillNO",
    "FPPBomEntry_FMaterialID.FNumber",
    "FPPBomEntry_FMaterialID.FName",
    "FPPBomEntry_FMaterialID.FSpecification",
    "FPPBomEntry_FAuxPropId.FName",
    "FPPBomEntry_FMaterialType",
    "FPPBomEntry_FNeedQty",
    "FPPBomEntry_FPickedQty",
    "FPPBomEntry_FNoPickedQty"
]
```

**MTO Field**: Use `FMOBillNO` to link from PRD_MO

**Key**: `FMaterialType` determines receipt source (1=自制, 2=外购, 3=委外)

- [x] Done

---

### T2-5: Create src/readers/production_receipt.py (PRD_INSTOCK)

**File**: `src/readers/production_receipt.py`

**Form ID**: `PRD_INSTOCK`

**Field Keys**:
```python
[
    "FBillNo",
    "FEntity_FMtoNo",
    "FEntity_FMaterialId.FNumber",
    "FEntity_FMaterialId.FName",
    "FEntity_FRealQty",
    "FEntity_FMustQty",
    "FDate"
]
```

**MTO Field**: `FEntity_FMtoNo`

**Purpose**: 自制品 (self-made) receipt quantities

- [x] Done

---

### T2-6: Create src/readers/purchase_order.py (PUR_PurchaseOrder)

**File**: `src/readers/purchase_order.py`

**Form ID**: `PUR_PurchaseOrder`

**Field Keys**:
```python
[
    "FBillNo",
    "FPOOrderEntry_FMtoNo",
    "FPOOrderEntry_FMaterialId.FNumber",
    "FPOOrderEntry_FMaterialId.FName",
    "FPOOrderEntry_FQty",
    "FPOOrderEntry_FStockInQty",
    "FPOOrderEntry_FRemainStockInQty",
    "FDate"
]
```

**MTO Field**: `FPOOrderEntry_FMtoNo`

**Purpose**: 外购 order quantities and cumulative receipt

- [x] Done

---

### T2-7: Create src/readers/purchase_receipt.py (STK_InStock)

**File**: `src/readers/purchase_receipt.py`

**Form ID**: `STK_InStock`

**Field Keys**:
```python
[
    "FBillNo",
    "FBillTypeID.FNumber",
    "FInStockEntry_FMtoNo",
    "FInStockEntry_FMaterialId.FNumber",
    "FInStockEntry_FMaterialId.FName",
    "FInStockEntry_FRealQty",
    "FInStockEntry_FMustQty",
    "FDate"
]
```

**MTO Field**: `FInStockEntry_FMtoNo`

**Key Filters**:
- 外购入库: `FBillTypeID.FNumber='RKD01_SYS'`
- 委外入库: `FBillTypeID.FNumber='RKD02_SYS'`

**Add Methods**:
```python
async def fetch_purchase_receipts(self, mto_number: str) -> list[T]:
    # Filter: FBillTypeID.FNumber='RKD01_SYS'

async def fetch_subcontracting_receipts(self, mto_number: str) -> list[T]:
    # Filter: FBillTypeID.FNumber='RKD02_SYS'
```

- [x] Done

---

### T2-8: Create src/readers/subcontracting_order.py (SUB_POORDER)

**File**: `src/readers/subcontracting_order.py`

**Form ID**: `SUB_POORDER`

**Field Keys**:
```python
[
    "FBillNo",
    "FTreeEntity_FMtoNo",
    "FTreeEntity_FMaterialId.FNumber",
    "FTreeEntity_FMaterialId.FName",
    "FTreeEntity_FQty",
    "FTreeEntity_FStockInQty",
    "FTreeEntity_FNoStockInQty",
    "FDate"
]
```

**MTO Field**: `FTreeEntity_FMtoNo`

**Purpose**: 委外 order quantities

- [x] Done

---

### T2-9: Create src/readers/material_picking.py (PRD_PickMtrl)

**File**: `src/readers/material_picking.py`

**Form ID**: `PRD_PickMtrl`

**Field Keys**:
```python
[
    "FBillNo",
    "FEntity_FMTONO",
    "FEntity_FMaterialId.FNumber",
    "FEntity_FMaterialId.FName",
    "FEntity_FAppQty",
    "FEntity_FActualQty",
    "FEntity_FPPBomBillNo",
    "FDate"
]
```

**MTO Field**: `FEntity_FMTONO`

**Purpose**: Material picking (actual consumption)

- [x] Done

---

### T2-10: Create src/readers/sales_delivery.py (SAL_OUTSTOCK)

**File**: `src/readers/sales_delivery.py`

**Form ID**: `SAL_OUTSTOCK`

**Field Keys**:
```python
[
    "FBillNo",
    "FSAL_OUTSTOCKENTRY_FMTONO",
    "FSAL_OUTSTOCKENTRY_FMaterialId.FNumber",
    "FSAL_OUTSTOCKENTRY_FMaterialId.FName",
    "FSAL_OUTSTOCKENTRY_FRealQty",
    "FSAL_OUTSTOCKENTRY_FMustQty",
    "FDate"
]
```

**MTO Field**: `FSAL_OUTSTOCKENTRY_FMTONO`

**Purpose**: Sales delivery quantities

- [x] Done

---

### T2-11: Create src/readers/sales_order.py (SAL_SaleOrder)

**File**: `src/readers/sales_order.py`

**Form ID**: `SAL_SaleOrder`

**Field Keys**:
```python
[
    "FBillNo",
    "FSaleOrderEntry_FMtoNo",
    "FCustomerID.FNumber",
    "FCustomerID.FName",
    "FSaleOrderEntry_FMaterialId.FNumber",
    "FSaleOrderEntry_FMaterialId.FName",
    "FSaleOrderEntry_FQty",
    "FSaleOrderEntry_FDeliveryDate",
    "FDate",
    "FDocumentStatus"
]
```

**MTO Field**: `FSaleOrderEntry_FMtoNo`

**Purpose**: Customer info (who ordered), delivery dates (when needed)

**Key Fields for Dashboard**:
- `FCustomerID.FName` - Customer name
- `FSaleOrderEntry_FDeliveryDate` - Required delivery date
- `FDocumentStatus` - Order status

- [x] Done

---

### T2 Completion Signal

When all T2 tasks complete, **notify Terminal 3** to start.

**Final Verification**:
```bash
python -c "
from src.readers import (
    ProductionOrderReader,
    ProductionBOMReader,
    ProductionReceiptReader,
    PurchaseOrderReader,
    PurchaseReceiptReader,
    SubcontractingOrderReader,
    MaterialPickingReader,
    SalesDeliveryReader,
    SalesOrderReader
)
print('T2 Complete - All 9 readers imported')
"
```

---

## Terminal 3: Sync Service + API

> **Priority**: MEDIUM
> **Dependencies**: Wait for Terminal 1 + Terminal 2
> **Total Tasks**: 10

### T3-1: Create src/sync/__init__.py

**File**: `src/sync/__init__.py`

**Content**:
```python
"""Data synchronization services."""
from src.sync.sync_service import SyncService
from src.sync.scheduler import SyncScheduler
from src.sync.progress import SyncProgress

__all__ = ["SyncService", "SyncScheduler", "SyncProgress"]
```

- [x] Done

---

### T3-2: Create src/sync/progress.py

**File**: `src/sync/progress.py`

**Content**:
```python
import json
from pathlib import Path
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class SyncProgressData(BaseModel):
    status: str = "idle"  # idle, running, success, error
    phase: str = ""
    message: str = ""
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    days_back: int = 0
    progress: dict = {}
    error: Optional[str] = None


class SyncProgress:
    def __init__(self, status_file: Path):
        self.status_file = status_file
        self._data = SyncProgressData()

    def start(self, days_back: int):
        self._data = SyncProgressData(
            status="running",
            phase="init",
            message="Starting sync...",
            started_at=datetime.now(),
            days_back=days_back
        )
        self._save()

    def update(self, phase: str, message: str, **progress):
        self._data.phase = phase
        self._data.message = message
        self._data.progress.update(progress)
        self._save()

    def finish_success(self):
        self._data.status = "success"
        self._data.finished_at = datetime.now()
        self._data.message = "Sync completed successfully"
        self._save()

    def finish_error(self, error: str):
        self._data.status = "error"
        self._data.finished_at = datetime.now()
        self._data.error = error
        self._save()

    def _save(self):
        self.status_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.status_file, 'w') as f:
            json.dump(self._data.model_dump(mode='json'), f, indent=2, default=str)

    def load(self) -> SyncProgressData:
        if self.status_file.exists():
            with open(self.status_file) as f:
                return SyncProgressData(**json.load(f))
        return SyncProgressData()
```

- [x] Done

---

### T3-3: Create src/sync/sync_service.py

**File**: `src/sync/sync_service.py`

**Reference**: `IMPLEMENTATION_PLAN.md` Section 5.2.4

**Key Methods**:
```python
class SyncService:
    def __init__(self, readers: dict, db: Database, progress: SyncProgress): ...

    def is_running(self) -> bool: ...

    async def run_sync(self, days_back: int = 90, chunk_days: int = 7) -> SyncResult:
        # 1. Acquire lock
        # 2. Calculate date range
        # 3. Generate chunks
        # 4. For each chunk: sync PRD_MO, PRD_PPBOM, etc.
        # 5. Update progress
        # 6. Return result

    def _generate_chunks(self, start_date, end_date, chunk_days):
        # Yield (chunk_start, chunk_end) tuples
```

- [x] Done

---

### T3-4: Create src/sync/scheduler.py

**File**: `src/sync/scheduler.py`

**Reference**: `IMPLEMENTATION_PLAN.md` Section 4 (Auto Sync Scheduler)

**Key Implementation**:
```python
import schedule
import threading

class SyncScheduler:
    def __init__(self, config: SyncConfig, sync_service: SyncService): ...

    def start(self):
        # Schedule jobs for each time in config.auto_sync.schedule
        # Start daemon thread

    def stop(self): ...

    def _sync_job(self):
        # Reload config
        # Run sync
```

- [x] Done

---

### T3-5: Create src/query/__init__.py

**File**: `src/query/__init__.py`

**Content**:
```python
"""Query handlers for MTO lookups."""
from src.query.mto_handler import MTOQueryHandler

__all__ = ["MTOQueryHandler"]
```

- [x] Done

---

### T3-6: Create src/query/mto_handler.py

**File**: `src/query/mto_handler.py`

**Reference**: `IMPLEMENTATION_PLAN.md` Section 5.3.1

**Key Logic**:
```python
class MTOQueryHandler:
    async def get_status(self, mto_number: str) -> MTOStatusResponse:
        # 1. Get production orders by MTO
        # 2. Get BOM entries by FMOBillNO
        # 3. Parallel fetch receipts by material type:
        #    - PRD_INSTOCK for 自制
        #    - STK_InStock (RKD01_SYS) for 外购
        #    - STK_InStock (RKD02_SYS) for 委外
        # 4. Aggregate and build response
```

**Use**: `asyncio.gather()` for parallel receipt queries

- [x] Done

---

### T3-7: Create src/api/__init__.py

**File**: `src/api/__init__.py`

**Content**:
```python
"""FastAPI routes and routers."""
```

- [x] Done

---

### T3-8: Create src/api/routers/sync.py

**File**: `src/api/routers/sync.py`

**Reference**: `IMPLEMENTATION_PLAN.md` Section 4 (Sync APIs)

**Endpoints**:
```python
router = APIRouter(prefix="/api/sync", tags=["sync"])

@router.post("/trigger")
async def trigger_sync(request: SyncTriggerRequest, background_tasks: BackgroundTasks):
    # Check if already running
    # Add background task
    # Return status

@router.get("/status")
async def get_sync_status() -> SyncProgressData:
    # Return current sync progress

@router.get("/config")
async def get_sync_config() -> SyncConfigResponse:
    # Return sync configuration

@router.put("/config")
async def update_sync_config(request: SyncConfigUpdateRequest):
    # Validate and update config
    # Save to JSON

@router.get("/history")
async def get_sync_history(limit: int = 10):
    # Return recent sync history from database
```

- [x] Done

---

### T3-9: Create src/api/routers/mto.py

**File**: `src/api/routers/mto.py`

**Reference**: `IMPLEMENTATION_PLAN.md` Section 5.3.3

**Endpoints**:
```python
router = APIRouter(prefix="/api", tags=["mto"])

@router.get("/mto/{mto_number}", response_model=MTOStatusResponse)
async def get_mto_status(mto_number: str):
    # Use MTOQueryHandler

@router.get("/search")
async def search_mto(q: str = Query(..., min_length=2)) -> list[MTOSummary]:
    # Search cached production orders

@router.get("/export/mto/{mto_number}")
async def export_mto_excel(mto_number: str):
    # Generate and return Excel file
```

- [x] Done

---

### T3-10: Create src/main.py

**File**: `src/main.py`

**Key Content**:
```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager

from src.config import Config
from src.database.connection import Database
from src.sync.scheduler import SyncScheduler
from src.api.routers import sync, mto


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    config = Config()
    db = Database(config.db_path)
    await db.connect()

    # Start scheduler
    scheduler = SyncScheduler(config.sync, sync_service)
    scheduler.start()

    yield

    # Shutdown
    scheduler.stop()
    await db.close()


app = FastAPI(title="QuickPulse V2", lifespan=lifespan)

# Mount static files
app.mount("/static", StaticFiles(directory="src/frontend/static"), name="static")

# Include routers
app.include_router(sync.router)
app.include_router(mto.router)

@app.get("/")
async def root():
    return FileResponse("src/frontend/index.html")

@app.get("/health")
async def health():
    return {"status": "healthy"}
```

**Verification**:
```bash
uvicorn src.main:app --reload
# Visit http://localhost:8000
```

- [x] Done

---

### T3-11: Create JWT Authentication Router

**File**: `src/api/routers/auth.py`

**Reference**: `IMPLEMENTATION_PLAN.md` Section 3.1

**Key Implementation**:
```python
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from datetime import datetime, timedelta
from pydantic import BaseModel

router = APIRouter(prefix="/api/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

# Config (move to config.py in production)
SECRET_KEY = "your-secret-key-change-in-production"  # Use env var!
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

class Token(BaseModel):
    access_token: str
    token_type: str

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=30))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        return username
    except JWTError:
        raise credentials_exception

@router.post("/token", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    # TODO: Replace with actual user validation
    # For now, accept any username with password "quickpulse"
    if form_data.password != "quickpulse":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    access_token = create_access_token(data={"sub": form_data.username})
    return {"access_token": access_token, "token_type": "bearer"}
```

**Verification**:
```bash
python -c "from src.api.routers.auth import router, get_current_user; print('OK')"
```

- [x] Done

---

### T3-12: Add Rate Limiting Middleware

**File**: `src/api/middleware/rate_limit.py`

**Content**:
```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)

def setup_rate_limiting(app):
    """Configure rate limiting for FastAPI app."""
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    return limiter
```

**Update `src/main.py`**:
```python
from src.api.middleware.rate_limit import setup_rate_limiting, limiter

app = FastAPI(title="QuickPulse V2", lifespan=lifespan)
setup_rate_limiting(app)

# Apply rate limits to routes
@router.get("/api/mto/{mto_number}")
@limiter.limit("30/minute")
async def get_mto_status(request: Request, mto_number: str, ...):
    ...
```

**Verification**:
```bash
python -c "from src.api.middleware.rate_limit import limiter; print('OK')"
```

- [x] Done

---

### T3-13: Protect API Routes with Authentication

**Update `src/api/routers/mto.py`**:
```python
from src.api.routers.auth import get_current_user

@router.get("/api/mto/{mto_number}", response_model=MTOStatusResponse)
async def get_mto_status(
    mto_number: str,
    current_user: str = Depends(get_current_user)  # Requires auth
):
    ...
```

**Update `src/api/routers/sync.py`**:
```python
from src.api.routers.auth import get_current_user

@router.post("/sync/trigger")
async def trigger_sync(
    request: SyncTriggerRequest,
    background_tasks: BackgroundTasks,
    current_user: str = Depends(get_current_user)  # Requires auth
):
    ...
```

**Note**: Keep `/health` and `/api/auth/token` public (no auth required).

**Verification**:
```bash
# Without token - should return 401
curl http://localhost:8000/api/mto/AK2510034

# Get token
TOKEN=$(curl -X POST http://localhost:8000/api/auth/token \
    -d "username=test&password=quickpulse" | jq -r '.access_token')

# With token - should work
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/mto/AK2510034
```

- [x] Done

---

### T3 Completion Signal

**Final Verification**:
```bash
uvicorn src.main:app --port 8000 &
sleep 3
curl http://localhost:8000/health

# Test auth flow
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/token \
    -d "username=test&password=quickpulse" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/sync/status
```

---

## Terminal 4: Frontend Rebuild (Industrial Precision Design)

> **Priority**: MEDIUM
> **Dependencies**: None - Can start immediately
> **Total Tasks**: 14
> **Design**: "Industrial Precision" - Dark theme, German industrial aesthetic

### Design System Reference

**Typography**:
- Display/Headers: `Geist` (Vercel's font)
- Body/Chinese: `Noto Sans SC`
- Monospace: `Geist Mono` for codes and numbers

**Color Palette**:
```css
--slate-950: #0a0a0b;      /* Primary dark - headers, nav */
--slate-900: #111113;      /* Card backgrounds */
--slate-800: #1e1e21;      /* Borders, dividers */
--slate-400: #9ca3af;      /* Secondary text */
--slate-50: #f8fafc;       /* Light text on dark */

--emerald-500: #10b981;    /* Success, 自制 badge */
--sky-500: #0ea5e9;        /* Info, 外购 badge */
--violet-500: #8b5cf6;     /* 委外 badge */
--amber-500: #f59e0b;      /* Warnings, pending */
--rose-500: #f43f5e;       /* Errors, 超领 highlighting */
```

**Visual Signature**:
- Dark mode default - easier on eyes for daily use
- Sharp corners (2-4px max radius) - industrial precision
- Hairline borders (1px slate-800) instead of shadows
- Accent glow effects on interactive elements
- Subtle grid/dot pattern backgrounds for texture

**File Structure**:
```
src/frontend/
├── index.html              # Login page
├── dashboard.html          # MTO query + results
├── sync.html               # Sync admin panel
├── static/
│   ├── css/
│   │   └── main.css        # Design tokens + custom styles
│   ├── js/
│   │   ├── api.js          # Auth-aware fetch wrapper
│   │   ├── auth.js         # Login/logout logic
│   │   ├── dashboard.js    # MTO search component
│   │   └── sync.js         # Sync panel component
```

---

### T4-1: Create src/frontend/static/css/main.css

**File**: `src/frontend/static/css/main.css`

**Content**:
```css
/* QuickPulse V2 - Industrial Precision Design System */

:root {
  /* Colors */
  --slate-950: #0a0a0b;
  --slate-900: #111113;
  --slate-800: #1e1e21;
  --slate-700: #2d2d31;
  --slate-600: #4a4a50;
  --slate-400: #9ca3af;
  --slate-300: #c9cdd4;
  --slate-50: #f8fafc;

  --emerald-500: #10b981;
  --emerald-400: #34d399;
  --sky-500: #0ea5e9;
  --sky-400: #38bdf8;
  --violet-500: #8b5cf6;
  --violet-400: #a78bfa;
  --amber-500: #f59e0b;
  --rose-500: #f43f5e;
  --rose-400: #fb7185;

  /* Typography */
  --font-sans: 'Geist', 'Noto Sans SC', system-ui, sans-serif;
  --font-mono: 'Geist Mono', monospace;

  /* Spacing */
  --radius-sm: 2px;
  --radius-md: 4px;
}

/* Base styles */
body {
  font-family: var(--font-sans);
  background: var(--slate-950);
  color: var(--slate-50);
}

/* Over-picking stripe pattern */
.row-overpick {
  background: repeating-linear-gradient(
    -45deg,
    rgb(254 205 211 / 0.1) 0px,
    rgb(254 205 211 / 0.1) 4px,
    transparent 4px,
    transparent 8px
  );
  border-left: 3px solid var(--rose-500);
}

/* Material type badges */
.badge-self-made {
  background: rgb(16 185 129 / 0.2);
  color: var(--emerald-400);
  border: 1px solid rgb(16 185 129 / 0.3);
}
.badge-purchased {
  background: rgb(14 165 233 / 0.2);
  color: var(--sky-400);
  border: 1px solid rgb(14 165 233 / 0.3);
}
.badge-subcontracted {
  background: rgb(139 92 246 / 0.2);
  color: var(--violet-400);
  border: 1px solid rgb(139 92 246 / 0.3);
}

/* Glow effect */
.glow-emerald:focus {
  box-shadow: 0 0 0 2px var(--slate-950), 0 0 0 4px var(--emerald-500);
}

/* Dot pattern background */
.bg-dots {
  background-image: radial-gradient(rgb(255 255 255 / 0.05) 1px, transparent 1px);
  background-size: 20px 20px;
}

/* Loading skeleton */
.skeleton {
  background: linear-gradient(90deg, var(--slate-800) 25%, var(--slate-700) 50%, var(--slate-800) 75%);
  background-size: 200% 100%;
  animation: skeleton-loading 1.5s ease-in-out infinite;
}
@keyframes skeleton-loading {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* Print styles */
@media print {
  body { background: white; color: black; }
  .no-print { display: none !important; }
}

/* Reduced motion */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

- [x] Done

---

### T4-2: Create src/frontend/static/js/api.js

**File**: `src/frontend/static/js/api.js`

**Content**:
```javascript
/**
 * Auth-aware API wrapper for QuickPulse V2
 */
const api = {
  baseUrl: '/api',

  getToken() {
    return localStorage.getItem('token');
  },

  setToken(token) {
    localStorage.setItem('token', token);
  },

  clearToken() {
    localStorage.removeItem('token');
  },

  isAuthenticated() {
    return !!this.getToken();
  },

  async request(endpoint, options = {}) {
    const token = this.getToken();
    const headers = {
      'Content-Type': 'application/json',
      ...(token && { 'Authorization': `Bearer ${token}` }),
      ...options.headers
    };

    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      ...options,
      headers
    });

    if (response.status === 401) {
      this.clearToken();
      window.location.href = '/';
      throw new Error('Unauthorized');
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    // Handle blob responses (Excel export)
    const contentType = response.headers.get('content-type');
    if (contentType && contentType.includes('application/vnd')) {
      return response.blob();
    }

    return response.json();
  },

  get: (endpoint) => api.request(endpoint),
  post: (endpoint, body) => api.request(endpoint, { method: 'POST', body: JSON.stringify(body) }),
  put: (endpoint, body) => api.request(endpoint, { method: 'PUT', body: JSON.stringify(body) }),

  // Auth endpoints
  async login(username, password) {
    const formData = new URLSearchParams();
    formData.append('username', username);
    formData.append('password', password);

    const response = await fetch(`${this.baseUrl}/auth/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: formData
    });

    if (!response.ok) {
      throw new Error('用户名或密码错误');
    }

    const data = await response.json();
    this.setToken(data.access_token);
    return data;
  },

  logout() {
    this.clearToken();
    window.location.href = '/';
  }
};

window.api = api;
```

- [x] Done

---

### T4-3: Create src/frontend/index.html (Login Page)

**File**: `src/frontend/index.html`

**Content**:
```html
<!DOCTYPE html>
<html lang="zh-CN" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QuickPulse V2 - 登录</title>

    <!-- Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;600&display=swap" rel="stylesheet">

    <!-- Tailwind CSS -->
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          colors: { slate: { 950: '#0a0a0b' } },
          fontFamily: { sans: ['Geist', 'Noto Sans SC', 'system-ui'] }
        }
      }
    }
    </script>

    <!-- Alpine.js -->
    <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>

    <!-- Custom styles -->
    <link rel="stylesheet" href="/static/css/main.css">
</head>
<body class="bg-slate-950 min-h-screen flex items-center justify-center bg-dots">
    <div x-data="loginForm()" class="w-full max-w-md px-6">

        <!-- Logo -->
        <div class="text-center mb-8">
            <h1 class="text-3xl font-semibold text-slate-50 tracking-wide">QuickPulse</h1>
            <p class="text-slate-400 text-sm mt-2">产品状态明细表</p>
        </div>

        <!-- Login Card -->
        <div class="bg-slate-900 border border-slate-800 rounded p-8">
            <form @submit.prevent="submit()">
                <!-- Username -->
                <div class="mb-6">
                    <label for="username" class="block text-sm text-slate-400 mb-2">用户名</label>
                    <input type="text" id="username" x-model="username" required
                           class="w-full bg-slate-800 border border-slate-700 text-slate-50 px-4 py-3 rounded focus:outline-none glow-emerald transition"
                           placeholder="请输入用户名">
                </div>

                <!-- Password -->
                <div class="mb-6">
                    <label for="password" class="block text-sm text-slate-400 mb-2">密码</label>
                    <input type="password" id="password" x-model="password" required
                           class="w-full bg-slate-800 border border-slate-700 text-slate-50 px-4 py-3 rounded focus:outline-none glow-emerald transition"
                           placeholder="请输入密码">
                </div>

                <!-- Error Message -->
                <div x-show="error" x-transition class="mb-4 p-3 bg-rose-500/10 border border-rose-500/30 rounded text-rose-400 text-sm">
                    <span x-text="error"></span>
                </div>

                <!-- Submit Button -->
                <button type="submit" :disabled="loading"
                        class="w-full bg-emerald-500 hover:bg-emerald-400 disabled:bg-slate-700 text-slate-950 font-medium py-3 rounded transition flex items-center justify-center gap-2">
                    <span x-show="loading" class="w-4 h-4 border-2 border-slate-950 border-t-transparent rounded-full animate-spin"></span>
                    <span x-text="loading ? '登录中...' : '登录'"></span>
                </button>
            </form>
        </div>

        <!-- Footer -->
        <p class="text-center text-slate-600 text-xs mt-8">
            QuickPulse V2 · ERP Integration Dashboard
        </p>
    </div>

    <script src="/static/js/api.js"></script>
    <script src="/static/js/auth.js"></script>
</body>
</html>
```

- [x] Done

---

### T4-4: Create src/frontend/static/js/auth.js

**File**: `src/frontend/static/js/auth.js`

**Content**:
```javascript
/**
 * Login form Alpine.js component
 */
function loginForm() {
    return {
        username: '',
        password: '',
        error: null,
        loading: false,

        async submit() {
            this.loading = true;
            this.error = null;

            try {
                await api.login(this.username, this.password);
                window.location.href = '/dashboard.html';
            } catch (e) {
                this.error = e.message;
                // Shake animation on error
                this.$el.classList.add('animate-shake');
                setTimeout(() => this.$el.classList.remove('animate-shake'), 500);
            } finally {
                this.loading = false;
            }
        }
    };
}

/**
 * Auth guard - redirect to login if not authenticated
 * Call this in dashboard.html and sync.html
 */
function authGuard() {
    return {
        init() {
            if (!api.isAuthenticated()) {
                window.location.href = '/';
            }
        }
    };
}

window.loginForm = loginForm;
window.authGuard = authGuard;
```

- [x] Done

---

### T4-5: Create src/frontend/dashboard.html

**File**: `src/frontend/dashboard.html`

**Content**:
```html
<!DOCTYPE html>
<html lang="zh-CN" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QuickPulse V2 - 产品状态明细表</title>

    <!-- Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;600&display=swap" rel="stylesheet">

    <!-- Tailwind CSS -->
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          colors: { slate: { 950: '#0a0a0b' } },
          fontFamily: {
            sans: ['Geist', 'Noto Sans SC', 'system-ui'],
            mono: ['Geist Mono', 'monospace']
          }
        }
      }
    }
    </script>

    <!-- Alpine.js -->
    <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>

    <!-- Lucide Icons -->
    <script src="https://unpkg.com/lucide@latest"></script>

    <!-- Custom styles -->
    <link rel="stylesheet" href="/static/css/main.css">
</head>
<body class="bg-slate-950 min-h-screen" x-data="authGuard()">

    <div x-data="mtoSearch()" x-init="init()" @keydown.escape.window="exitFullScreen()">

        <!-- Dark Nav Header -->
        <header class="bg-slate-900 border-b border-slate-800 px-6 py-4 no-print"
                :class="isFullScreen && isCollapsed ? 'hidden' : ''">
            <div class="flex items-center justify-between max-w-7xl mx-auto">
                <div class="flex items-center gap-4">
                    <h1 class="text-xl font-semibold text-slate-50 tracking-wide">QuickPulse</h1>
                    <span class="text-slate-600 text-sm">|</span>
                    <span class="text-slate-400 text-sm">产品状态明细表</span>
                </div>
                <div class="flex items-center gap-6">
                    <span class="text-slate-400 text-sm font-mono" x-text="new Date().toLocaleString('zh-CN')"></span>
                    <div class="relative" x-data="{ open: false }">
                        <button @click="open = !open" class="flex items-center gap-2 text-slate-400 hover:text-slate-50 transition">
                            <i data-lucide="user" class="w-4 h-4"></i>
                            <span class="text-sm">用户</span>
                            <i data-lucide="chevron-down" class="w-3 h-3"></i>
                        </button>
                        <div x-show="open" @click.away="open = false" x-transition
                             class="absolute right-0 mt-2 w-40 bg-slate-800 border border-slate-700 rounded shadow-lg py-1 z-50">
                            <a href="/sync.html" class="block px-4 py-2 text-sm text-slate-300 hover:bg-slate-700">同步管理</a>
                            <button @click="api.logout()" class="w-full text-left px-4 py-2 text-sm text-slate-300 hover:bg-slate-700">退出登录</button>
                        </div>
                    </div>
                </div>
            </div>
        </header>

        <!-- Main Content -->
        <main id="main-content" class="max-w-7xl mx-auto px-6 py-8" :class="isFullScreen ? 'max-w-full' : ''">

            <!-- Search Section -->
            <section :class="isFullScreen && isCollapsed ? 'hidden' : 'mb-8'" class="transition-all">
                <div class="flex gap-4 items-end">
                    <div class="flex-1 max-w-md">
                        <label for="mto-search" class="block text-sm text-slate-400 mb-2">MTO单号</label>
                        <input type="text" id="mto-search" x-model="mtoNumber" @keydown.enter="search()"
                               aria-label="计划跟踪号" aria-describedby="mto-help"
                               placeholder="输入计划跟踪号..."
                               class="w-full bg-slate-800 border border-slate-700 text-slate-50 px-4 py-3 rounded focus:outline-none glow-emerald transition font-mono"
                               :disabled="loading">
                        <p id="mto-help" class="sr-only">输入MTO跟踪号进行搜索，例如 AK2510034</p>
                    </div>
                    <button @click="search()" :disabled="loading || !mtoNumber"
                            aria-label="搜索MTO单号"
                            class="px-6 py-3 bg-emerald-500 hover:bg-emerald-400 disabled:bg-slate-700 disabled:cursor-not-allowed text-slate-950 font-medium rounded transition flex items-center gap-2">
                        <span x-show="loading" class="w-4 h-4 border-2 border-slate-950 border-t-transparent rounded-full animate-spin"></span>
                        <span x-text="loading ? '查询中...' : '查询'"></span>
                    </button>
                </div>
            </section>

            <!-- Error/Success Messages -->
            <div x-show="error" x-transition class="mb-6">
                <div class="p-4 bg-rose-500/10 border border-rose-500/30 rounded text-rose-400">
                    <span x-text="error"></span>
                </div>
            </div>
            <div x-show="successMessage" x-transition class="mb-6">
                <div class="p-4 bg-emerald-500/10 border border-emerald-500/30 rounded text-emerald-400">
                    <span x-text="successMessage"></span>
                </div>
            </div>

            <!-- Parent Item Card -->
            <div x-show="parentItem" x-transition :class="isFullScreen && isCollapsed ? 'hidden' : 'mb-8'">
                <!-- Content in T4-6 -->
            </div>

            <!-- Child Items Table -->
            <div x-show="childItems.length > 0" x-transition>
                <!-- Content in T4-7 -->
            </div>

            <!-- Empty State -->
            <div x-show="!loading && childItems.length === 0 && !error" class="text-center py-20">
                <i data-lucide="inbox" class="w-16 h-16 text-slate-700 mx-auto mb-4"></i>
                <h3 class="text-lg text-slate-400 mb-2">暂无数据</h3>
                <p class="text-slate-600 text-sm">请输入MTO单号进行查询</p>
            </div>

            <!-- Loading State -->
            <div x-show="loading" class="text-center py-20">
                <div class="w-8 h-8 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
                <p class="text-slate-400">正在查询数据...</p>
            </div>

        </main>

        <!-- Keyboard Shortcuts Hint -->
        <div class="fixed bottom-4 right-4 text-xs text-slate-600 no-print" x-show="childItems.length > 0">
            <span class="px-2 py-1 bg-slate-800 rounded mr-1">F11</span> 全屏
            <span class="px-2 py-1 bg-slate-800 rounded mr-1 ml-2">ESC</span> 退出
        </div>

        <!-- Live Region for Screen Readers -->
        <div aria-live="polite" aria-atomic="true" class="sr-only"
             x-text="loading ? '正在加载...' : (error ? '发生错误: ' + error : (parentItem ? '已加载MTO单号 ' + mtoNumber + ' 的数据' : ''))">
        </div>

    </div>

    <script src="/static/js/api.js"></script>
    <script src="/static/js/auth.js"></script>
    <script src="/static/js/dashboard.js"></script>
    <script>lucide.createIcons();</script>
</body>
</html>
```

- [x] Done

---

### T4-6: Create src/frontend/static/js/dashboard.js

**File**: `src/frontend/static/js/dashboard.js`

**Content**:
```javascript
/**
 * QuickPulse V2 - MTO Search Dashboard (Industrial Precision)
 * Alpine.js component for product status detail sheet
 */
function mtoSearch() {
    return {
        // State
        mtoNumber: '',
        parentItem: null,
        childItems: [],
        loading: false,
        error: '',
        successMessage: '',
        isFullScreen: false,
        isCollapsed: false,

        init() {
            console.log('QuickPulse V2 Dashboard initialized');

            // Check URL params
            const urlParams = new URLSearchParams(window.location.search);
            const mtoParam = urlParams.get('mto');
            if (mtoParam) {
                this.mtoNumber = mtoParam;
                this.search();
            }

            this.setupKeyboardListeners();
        },

        setupKeyboardListeners() {
            document.addEventListener('keydown', (e) => {
                if (e.key === 'F11' && this.childItems.length > 0) {
                    e.preventDefault();
                    this.toggleFullScreen();
                }
                if (e.key === '/' && !['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) {
                    e.preventDefault();
                    document.getElementById('mto-search')?.focus();
                }
            });
        },

        async search() {
            if (!this.mtoNumber?.trim()) {
                this.showError('请输入MTO单号');
                return;
            }

            this.clearMessages();
            this.parentItem = null;
            this.childItems = [];
            this.loading = true;

            try {
                const data = await api.get(`/mto/${encodeURIComponent(this.mtoNumber.trim())}`);

                this.parentItem = data.parent_item || null;
                this.childItems = data.child_items || [];

                this.successMessage = `成功查询到 ${this.childItems.length} 条BOM组件记录`;
                setTimeout(() => this.successMessage = '', 3000);

                // Update URL
                const newUrl = `${window.location.pathname}?mto=${encodeURIComponent(this.mtoNumber.trim())}`;
                window.history.pushState({}, '', newUrl);

            } catch (err) {
                console.error('Search error:', err);
                this.showError(err.message || '查询失败，请稍后重试');
            } finally {
                this.loading = false;
            }
        },

        toggleFullScreen() {
            this.isFullScreen = !this.isFullScreen;
            this.isCollapsed = this.isFullScreen;
            document.body.style.overflow = this.isFullScreen ? 'hidden' : '';
        },

        exitFullScreen() {
            if (this.isFullScreen) {
                this.isFullScreen = false;
                this.isCollapsed = false;
                document.body.style.overflow = '';
            }
        },

        async exportToExcel() {
            if (this.childItems.length === 0) {
                this.showError('没有可导出的数据');
                return;
            }

            try {
                this.showSuccess('正在导出Excel...');
                const blob = await api.get(`/export/mto/${encodeURIComponent(this.mtoNumber.trim())}`);

                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `MTO_${this.mtoNumber}_${this.getTimestamp()}.xlsx`;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);

                this.showSuccess('Excel导出成功');
            } catch (err) {
                console.error('Export error:', err);
                this.showError('导出失败: ' + err.message);
            }
        },

        isOverPicked: (qty) => parseFloat(qty) < 0,

        formatNumber(value) {
            if (value === null || value === undefined || value === '') return '0';
            const num = parseFloat(value);
            if (isNaN(num)) return '0';
            return num % 1 === 0
                ? num.toLocaleString('zh-CN')
                : num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        },

        getMaterialTypeBadge(type) {
            const badges = {
                '自制': 'badge-self-made',
                '外购': 'badge-purchased',
                '委外': 'badge-subcontracted'
            };
            return badges[type] || 'bg-slate-800 text-slate-400 border border-slate-700';
        },

        showError(msg) {
            this.error = msg;
            this.successMessage = '';
            setTimeout(() => this.error = '', 5000);
        },

        showSuccess(msg) {
            this.successMessage = msg;
            this.error = '';
            setTimeout(() => this.successMessage = '', 3000);
        },

        clearMessages() {
            this.error = '';
            this.successMessage = '';
        },

        getTimestamp() {
            const now = new Date();
            return `${now.getFullYear()}${String(now.getMonth()+1).padStart(2,'0')}${String(now.getDate()).padStart(2,'0')}_${String(now.getHours()).padStart(2,'0')}${String(now.getMinutes()).padStart(2,'0')}`;
        }
    };
}

window.mtoSearch = mtoSearch;
```

- [x] Done

---

### T4-7: Implement 13-Column Data Table with Column Group Tinting

**File**: `src/frontend/dashboard.html` (update Child Items Table section)

**Replace placeholder with**:
```html
<!-- Child Items Table -->
<div x-show="childItems.length > 0" x-transition
     class="bg-slate-900 border border-slate-800 rounded overflow-hidden">

    <!-- Table Header with Controls -->
    <div class="bg-slate-800 px-6 py-4 flex items-center justify-between">
        <h2 class="text-lg font-semibold text-slate-50 flex items-center gap-2">
            <i data-lucide="list" class="w-5 h-5"></i>
            BOM组件明细
            <span class="text-sm font-normal text-slate-400" x-text="`(${childItems.length} 条)`"></span>
        </h2>
        <div class="flex items-center gap-3">
            <!-- Collapse Toggle (fullscreen only) -->
            <button x-show="isFullScreen" @click="isCollapsed = !isCollapsed"
                    class="px-3 py-2 bg-slate-700 hover:bg-slate-600 rounded text-slate-300 text-sm transition">
                <span x-text="isCollapsed ? '展开' : '收起'"></span>
            </button>
            <!-- Export Button -->
            <button @click="exportToExcel()"
                    class="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 rounded text-slate-950 text-sm font-medium transition flex items-center gap-2">
                <i data-lucide="download" class="w-4 h-4"></i>
                导出
            </button>
            <!-- Fullscreen Toggle -->
            <button @click="toggleFullScreen()"
                    class="px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded text-slate-300 text-sm transition flex items-center gap-2">
                <i :data-lucide="isFullScreen ? 'minimize-2' : 'maximize-2'" class="w-4 h-4"></i>
                <span x-text="isFullScreen ? '退出全屏' : '全屏'"></span>
            </button>
        </div>
    </div>

    <!-- Table Container -->
    <div class="overflow-x-auto" :class="isFullScreen ? 'max-h-screen' : 'max-h-[600px]'">
        <table role="table" class="w-full text-sm">
            <thead class="sticky top-0 z-10">
                <tr role="row" class="border-b border-slate-700">
                    <!-- Info columns -->
                    <th scope="col" class="px-4 py-3 text-left font-medium text-slate-400 bg-slate-900 whitespace-nowrap">序号</th>
                    <th scope="col" class="px-4 py-3 text-left font-medium text-slate-400 bg-slate-900 whitespace-nowrap min-w-[120px]">物料编码</th>
                    <th scope="col" class="px-4 py-3 text-left font-medium text-slate-400 bg-slate-900 whitespace-nowrap min-w-[150px]">物料名称</th>
                    <th scope="col" class="px-4 py-3 text-left font-medium text-slate-400 bg-slate-900 whitespace-nowrap min-w-[120px]">规格型号</th>
                    <th scope="col" class="px-4 py-3 text-left font-medium text-slate-400 bg-slate-900 whitespace-nowrap">物料类型</th>
                    <!-- BOM columns (emerald tint) -->
                    <th scope="col" class="px-4 py-3 text-right font-medium text-slate-400 bg-emerald-950/30 whitespace-nowrap">需求量</th>
                    <th scope="col" class="px-4 py-3 text-right font-medium text-slate-400 bg-emerald-950/30 whitespace-nowrap">已领量</th>
                    <th scope="col" class="px-4 py-3 text-right font-medium text-slate-400 bg-emerald-950/30 whitespace-nowrap">未领量</th>
                    <!-- Receipt columns (sky tint) -->
                    <th scope="col" class="px-4 py-3 text-right font-medium text-slate-400 bg-sky-950/30 whitespace-nowrap">订单数量</th>
                    <th scope="col" class="px-4 py-3 text-right font-medium text-slate-400 bg-sky-950/30 whitespace-nowrap">入库量</th>
                    <th scope="col" class="px-4 py-3 text-right font-medium text-slate-400 bg-sky-950/30 whitespace-nowrap">未入库量</th>
                    <!-- Status columns (violet tint) -->
                    <th scope="col" class="px-4 py-3 text-right font-medium text-slate-400 bg-violet-950/30 whitespace-nowrap">销售出库</th>
                    <th scope="col" class="px-4 py-3 text-right font-medium text-slate-400 bg-violet-950/30 whitespace-nowrap">即时库存</th>
                </tr>
            </thead>
            <tbody role="rowgroup">
                <template x-for="(item, index) in childItems" :key="index">
                    <tr role="row" class="border-b border-slate-800 hover:bg-slate-800/50 transition"
                        :class="isOverPicked(item.unpicked_qty) ? 'row-overpick' : ''">
                        <td role="cell" class="px-4 py-3 text-slate-500" x-text="index + 1"></td>
                        <td role="cell" class="px-4 py-3 font-mono text-sm text-slate-300" x-text="item.material_code"></td>
                        <td role="cell" class="px-4 py-3 text-slate-200" x-text="item.material_name"></td>
                        <td role="cell" class="px-4 py-3 text-slate-400" x-text="item.specification || '-'"></td>
                        <td role="cell" class="px-4 py-3">
                            <span class="px-2 py-1 rounded text-xs font-medium"
                                  :class="getMaterialTypeBadge(item.material_type)"
                                  x-text="item.material_type"></span>
                        </td>
                        <!-- BOM columns -->
                        <td role="cell" class="px-4 py-3 text-right font-medium text-slate-200 bg-emerald-950/10" x-text="formatNumber(item.required_qty)"></td>
                        <td role="cell" class="px-4 py-3 text-right text-slate-300 bg-emerald-950/10" x-text="formatNumber(item.picked_qty)"></td>
                        <td role="cell" class="px-4 py-3 text-right font-medium bg-emerald-950/10"
                            :class="isOverPicked(item.unpicked_qty) ? 'text-rose-400 font-bold' : 'text-slate-200'">
                            <span x-text="formatNumber(item.unpicked_qty)"></span>
                            <span x-show="isOverPicked(item.unpicked_qty)" class="text-xs ml-1 text-rose-500">(超领)</span>
                        </td>
                        <!-- Receipt columns -->
                        <td role="cell" class="px-4 py-3 text-right text-slate-300 bg-sky-950/10" x-text="formatNumber(item.order_qty)"></td>
                        <td role="cell" class="px-4 py-3 text-right text-slate-300 bg-sky-950/10" x-text="formatNumber(item.received_qty)"></td>
                        <td role="cell" class="px-4 py-3 text-right font-medium bg-sky-950/10"
                            :class="item.unreceived_qty > 0 ? 'text-amber-400' : 'text-emerald-400'"
                            x-text="formatNumber(item.unreceived_qty)"></td>
                        <!-- Status columns -->
                        <td role="cell" class="px-4 py-3 text-right text-slate-300 bg-violet-950/10" x-text="formatNumber(item.sales_outbound_qty)"></td>
                        <td role="cell" class="px-4 py-3 text-right font-medium bg-violet-950/10"
                            :class="item.current_stock <= 0 ? 'text-rose-400' : 'text-slate-200'"
                            x-text="formatNumber(item.current_stock)"></td>
                    </tr>
                </template>
            </tbody>
        </table>
    </div>

    <!-- Table Footer -->
    <div class="bg-slate-800/50 px-6 py-4 border-t border-slate-700">
        <div class="flex items-center justify-between text-sm">
            <div class="text-slate-400">
                共 <span class="font-bold text-slate-200" x-text="childItems.length"></span> 条记录
            </div>
            <div class="flex items-center gap-6 text-xs">
                <div class="flex items-center gap-2">
                    <div class="w-3 h-3 bg-rose-500 rounded"></div>
                    <span class="text-slate-400">超领</span>
                </div>
                <div class="flex items-center gap-2">
                    <div class="w-3 h-3 bg-amber-500 rounded"></div>
                    <span class="text-slate-400">待入库</span>
                </div>
                <div class="flex items-center gap-2">
                    <div class="w-3 h-3 bg-emerald-500 rounded"></div>
                    <span class="text-slate-400">已完成</span>
                </div>
            </div>
        </div>
    </div>
</div>
```

- [x] Done

---

### T4-8: Add Mobile Card Layout (Responsive < 768px)

**File**: `src/frontend/static/css/main.css` (add mobile styles)

**Add to main.css**:
```css
/* Mobile card layout for BOM items */
@media (max-width: 767px) {
  .bom-table { display: none; }
  .bom-cards { display: block; }

  .bom-card {
    background: var(--slate-900);
    border: 1px solid var(--slate-800);
    border-radius: var(--radius-md);
    padding: 1rem;
    margin-bottom: 0.75rem;
  }

  .bom-card-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 0.75rem;
    padding-bottom: 0.75rem;
    border-bottom: 1px solid var(--slate-800);
  }

  .bom-card-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.5rem;
  }

  .bom-card-item {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .bom-card-label {
    font-size: 0.75rem;
    color: var(--slate-500);
  }

  .bom-card-value {
    font-size: 0.875rem;
    color: var(--slate-200);
    font-variant-numeric: tabular-nums;
  }

  .touch-target {
    min-height: 44px;
    min-width: 44px;
  }
}

@media (min-width: 768px) {
  .bom-table { display: block; }
  .bom-cards { display: none; }
}
```

**File**: `src/frontend/dashboard.html` (add mobile cards after table)

**Add mobile card view**:
```html
<!-- Mobile Card View -->
<div class="bom-cards md:hidden">
    <template x-for="(item, index) in childItems" :key="'card-'+index">
        <div class="bom-card" :class="isOverPicked(item.unpicked_qty) ? 'row-overpick' : ''">
            <div class="bom-card-header">
                <div>
                    <div class="font-mono text-sm text-slate-300" x-text="item.material_code"></div>
                    <div class="text-slate-200 mt-1" x-text="item.material_name"></div>
                </div>
                <span class="px-2 py-1 rounded text-xs font-medium"
                      :class="getMaterialTypeBadge(item.material_type)"
                      x-text="item.material_type"></span>
            </div>
            <div class="bom-card-grid">
                <div class="bom-card-item">
                    <span class="bom-card-label">需求量</span>
                    <span class="bom-card-value" x-text="formatNumber(item.required_qty)"></span>
                </div>
                <div class="bom-card-item">
                    <span class="bom-card-label">已领量</span>
                    <span class="bom-card-value" x-text="formatNumber(item.picked_qty)"></span>
                </div>
                <div class="bom-card-item">
                    <span class="bom-card-label">未领量</span>
                    <span class="bom-card-value" :class="isOverPicked(item.unpicked_qty) ? 'text-rose-400 font-bold' : ''"
                          x-text="formatNumber(item.unpicked_qty) + (isOverPicked(item.unpicked_qty) ? ' (超领)' : '')"></span>
                </div>
                <div class="bom-card-item">
                    <span class="bom-card-label">即时库存</span>
                    <span class="bom-card-value" :class="item.current_stock <= 0 ? 'text-rose-400' : ''"
                          x-text="formatNumber(item.current_stock)"></span>
                </div>
            </div>
        </div>
    </template>
</div>
```

- [x] Done

---

### T4-9: Create src/frontend/sync.html

**File**: `src/frontend/sync.html`

**Content**:
```html
<!DOCTYPE html>
<html lang="zh-CN" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QuickPulse V2 - 同步管理</title>

    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;600&display=swap" rel="stylesheet">

    <script src="https://cdn.tailwindcss.com"></script>
    <script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          colors: { slate: { 950: '#0a0a0b' } },
          fontFamily: { sans: ['Geist', 'Noto Sans SC', 'system-ui'] }
        }
      }
    }
    </script>

    <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
    <script src="https://unpkg.com/lucide@latest"></script>
    <link rel="stylesheet" href="/static/css/main.css">
</head>
<body class="bg-slate-950 min-h-screen" x-data="authGuard()">

    <div x-data="syncPanel()" x-init="init()">

        <!-- Header -->
        <header class="bg-slate-900 border-b border-slate-800 px-6 py-4">
            <div class="flex items-center justify-between max-w-4xl mx-auto">
                <div class="flex items-center gap-4">
                    <a href="/dashboard.html" class="text-slate-400 hover:text-slate-50 transition">
                        <i data-lucide="arrow-left" class="w-5 h-5"></i>
                    </a>
                    <h1 class="text-xl font-semibold text-slate-50">同步管理</h1>
                </div>
                <button @click="api.logout()" class="text-slate-400 hover:text-slate-50 text-sm transition">
                    退出登录
                </button>
            </div>
        </header>

        <!-- Main Content -->
        <main class="max-w-4xl mx-auto px-6 py-8">

            <!-- Status Card -->
            <div class="bg-slate-900 border border-slate-800 rounded p-6 mb-6">
                <div class="flex items-center justify-between mb-4">
                    <h2 class="text-lg font-semibold text-slate-50">同步状态</h2>
                    <div class="flex items-center gap-2">
                        <span class="w-3 h-3 rounded-full animate-pulse"
                              :class="status.is_running ? 'bg-amber-500' : 'bg-emerald-500'"></span>
                        <span class="text-sm" :class="status.is_running ? 'text-amber-400' : 'text-emerald-400'"
                              x-text="status.is_running ? '同步中...' : '空闲'"></span>
                    </div>
                </div>

                <!-- Progress Bar (when running) -->
                <div x-show="status.is_running" class="mb-4">
                    <div class="h-2 bg-slate-800 rounded overflow-hidden">
                        <div class="h-full bg-emerald-500 transition-all duration-300"
                             :style="`width: ${status.progress || 0}%`"></div>
                    </div>
                    <p class="text-sm text-slate-400 mt-2" x-text="status.current_task || '处理中...'"></p>
                </div>

                <!-- Last Sync Info -->
                <div class="grid grid-cols-2 gap-4 text-sm">
                    <div>
                        <span class="text-slate-500">上次同步</span>
                        <p class="text-slate-200 mt-1" x-text="status.last_sync || '从未同步'"></p>
                    </div>
                    <div>
                        <span class="text-slate-500">同步记录数</span>
                        <p class="text-slate-200 mt-1" x-text="status.records_synced || '-'"></p>
                    </div>
                </div>
            </div>

            <!-- Manual Trigger Form -->
            <div class="bg-slate-900 border border-slate-800 rounded p-6 mb-6">
                <h2 class="text-lg font-semibold text-slate-50 mb-4">手动同步</h2>
                <div class="flex gap-4 items-end">
                    <div class="flex-1">
                        <label class="block text-sm text-slate-400 mb-2">同步天数</label>
                        <input type="number" x-model="daysBack" min="1" max="90"
                               class="w-full bg-slate-800 border border-slate-700 text-slate-50 px-4 py-3 rounded focus:outline-none glow-emerald transition">
                    </div>
                    <div class="flex items-center gap-2">
                        <input type="checkbox" id="force-sync" x-model="forceSync"
                               class="w-4 h-4 bg-slate-800 border border-slate-700 rounded">
                        <label for="force-sync" class="text-sm text-slate-400">强制刷新</label>
                    </div>
                    <button @click="triggerSync()" :disabled="status.is_running || loading"
                            class="px-6 py-3 bg-emerald-500 hover:bg-emerald-400 disabled:bg-slate-700 disabled:cursor-not-allowed text-slate-950 font-medium rounded transition">
                        <span x-text="loading ? '触发中...' : '开始同步'"></span>
                    </button>
                </div>
            </div>

            <!-- Auto-Sync Schedule -->
            <div class="bg-slate-900 border border-slate-800 rounded p-6 mb-6">
                <h2 class="text-lg font-semibold text-slate-50 mb-4">自动同步计划</h2>
                <div class="text-slate-400 text-sm">
                    <p>每日自动同步时间: <span class="text-slate-200">07:00, 12:00, 16:00, 18:00</span></p>
                </div>
            </div>

            <!-- Error Message -->
            <div x-show="error" x-transition class="p-4 bg-rose-500/10 border border-rose-500/30 rounded text-rose-400 mb-6">
                <span x-text="error"></span>
            </div>

        </main>
    </div>

    <script src="/static/js/api.js"></script>
    <script src="/static/js/auth.js"></script>
    <script src="/static/js/sync.js"></script>
    <script>lucide.createIcons();</script>
</body>
</html>
```

- [x] Done

---

### T4-10: Create src/frontend/static/js/sync.js

**File**: `src/frontend/static/js/sync.js`

**Content**:
```javascript
/**
 * QuickPulse V2 - Sync Panel Alpine.js Component
 */
function syncPanel() {
    return {
        status: {
            is_running: false,
            progress: 0,
            current_task: null,
            last_sync: null,
            records_synced: null
        },
        daysBack: 7,
        forceSync: false,
        loading: false,
        error: null,
        pollInterval: null,

        async init() {
            console.log('Sync Panel initialized');
            await this.fetchStatus();
            this.startPolling();
        },

        async fetchStatus() {
            try {
                const data = await api.get('/sync/status');
                this.status = { ...this.status, ...data };
            } catch (err) {
                console.error('Failed to fetch sync status:', err);
            }
        },

        startPolling() {
            this.pollInterval = setInterval(() => this.fetchStatus(), 5000);
        },

        stopPolling() {
            if (this.pollInterval) {
                clearInterval(this.pollInterval);
            }
        },

        async triggerSync() {
            this.loading = true;
            this.error = null;

            try {
                await api.post('/sync/trigger', {
                    days_back: parseInt(this.daysBack),
                    force: this.forceSync
                });

                // Immediately refresh status
                await this.fetchStatus();

            } catch (err) {
                this.error = err.message;
            } finally {
                this.loading = false;
            }
        },

        // Cleanup on page leave
        destroy() {
            this.stopPolling();
        }
    };
}

window.syncPanel = syncPanel;
```

- [x] Done

---

### T4-11: Add Fullscreen Mode + Keyboard Shortcuts

**File**: `src/frontend/dashboard.html` (keyboard shortcut handling is in dashboard.js)

**Keyboard Shortcuts Implemented**:
- `F11` - Toggle fullscreen mode
- `ESC` - Exit fullscreen mode
- `/` - Focus search input

**Already implemented in T4-6 (dashboard.js) `setupKeyboardListeners()` method.**

**Add focus shortcut hint to search section**:
```html
<div class="text-xs text-slate-600 mt-2">
    提示: 按 <kbd class="px-1 bg-slate-800 rounded">/</kbd> 快速定位搜索框
</div>
```

- [x] Done

---

### T4-12: Implement Excel Export

**Already implemented in T4-6 (dashboard.js) `exportToExcel()` method.**

**Key features**:
- Uses auth-aware API wrapper
- Handles blob response from backend
- Generates timestamped filename
- Triggers browser download

**Verification**:
1. Search for an MTO number
2. Click "导出" button
3. Verify Excel file downloads with format `MTO_{number}_{timestamp}.xlsx`

- [x] Done

---

### T4-13: Add Loading Skeletons + ARIA Labels

**File**: `src/frontend/dashboard.html`

**Add loading skeleton for table**:
```html
<!-- Loading Skeleton (show while loading) -->
<div x-show="loading" class="bg-slate-900 border border-slate-800 rounded p-6">
    <div class="space-y-4">
        <template x-for="i in 5" :key="i">
            <div class="flex gap-4">
                <div class="skeleton h-4 w-12 rounded"></div>
                <div class="skeleton h-4 w-32 rounded"></div>
                <div class="skeleton h-4 flex-1 rounded"></div>
                <div class="skeleton h-4 w-20 rounded"></div>
            </div>
        </template>
    </div>
</div>
```

**ARIA labels already implemented in T4-5 and T4-7**:
- `role="table"`, `role="row"`, `role="cell"`, `role="columnheader"`
- `scope="col"` on table headers
- `aria-label` on search input and button
- `aria-describedby` linking input to help text
- `aria-live="polite"` region for status updates
- Skip link for keyboard navigation

- [x] Done

---

### T4-14: Create Docker Files

**File**: `docker/Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

COPY src/ ./src/
COPY conf.ini ./
COPY sync_config.json ./

RUN mkdir -p /app/data /app/reports

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**File**: `docker-compose.yml`

```yaml
version: '3.8'

services:
  quickpulse:
    build:
      context: .
      dockerfile: docker/Dockerfile
    container_name: quickpulse-v2
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - ./reports:/app/reports
      - ./sync_config.json:/app/sync_config.json
      - ./conf.ini:/app/conf.ini:ro
    environment:
      - TZ=Asia/Shanghai
      - PYTHONUNBUFFERED=1
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s

networks:
  default:
    name: quickpulse-network
```

**File**: `docker-compose.dev.yml`

```yaml
version: '3.8'

services:
  quickpulse-dev:
    build:
      context: .
      dockerfile: docker/Dockerfile.dev
    container_name: quickpulse-v2-dev
    ports:
      - "8000:8000"
    volumes:
      - ./src:/app/src
      - ./data:/app/data
      - ./reports:/app/reports
      - ./sync_config.json:/app/sync_config.json
      - ./conf.ini:/app/conf.ini
    environment:
      - TZ=Asia/Shanghai
      - PYTHONUNBUFFERED=1
      - DEBUG=1
    command: uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

networks:
  default:
    name: quickpulse-dev
```

- [x] Done

---

### T4 Completion Verification

**Test Frontend Flow**:
```bash
# Start server
uvicorn src.main:app --reload --port 8000

# Open browser
open http://localhost:8000/
```

**Manual Testing Checklist**:
1. **Login Page** (`/`)
   - [ ] Dark theme with dot pattern background
   - [ ] Emerald focus glow on inputs
   - [ ] Error message with shake animation
   - [ ] Redirect to dashboard on success

2. **Dashboard** (`/dashboard.html`)
   - [ ] Auth guard redirects if no token
   - [ ] Search with emerald glow focus
   - [ ] 13-column table with column group tinting
   - [ ] Over-picking rows highlighted (rose stripes)
   - [ ] Material type badges (emerald/sky/violet)
   - [ ] F11 toggles fullscreen, ESC exits
   - [ ] Export downloads Excel file

3. **Sync Panel** (`/sync.html`)
   - [ ] Status indicator (green pulse/amber spin)
   - [ ] Progress bar during sync
   - [ ] Manual trigger form
   - [ ] Auto-sync schedule display

4. **Mobile Responsiveness** (375px width)
   - [ ] Table converts to cards
   - [ ] Touch targets 44px minimum
   - [ ] Readable text sizes

**Docker Build Test**:
```bash
docker-compose build
docker-compose up -d
curl http://localhost:8000/health
```

---

## Final Integration Checklist

After all 4 terminals complete their tasks:

### Verification Steps

1. **Install dependencies**:
   ```bash
   pip install -e .
   ```

2. **Initialize database**:
   ```bash
   python -c "
   import asyncio
   from src.database.connection import Database
   from pathlib import Path
   async def main():
       db = Database(Path('data/quickpulse.db'))
       await db.connect()
       print('Database initialized')
       await db.close()
   asyncio.run(main())
   "
   ```

3. **Test Kingdee connection**:
   ```bash
   python -c "
   import asyncio
   from src.config import get_config
   from src.kingdee.client import KingdeeClient
   async def main():
       config = get_config()
       client = KingdeeClient(config.kingdee)
       result = await client.query('PRD_MO', ['FBillNo'], 'FBillNo like \"MO%\"', limit=1)
       print(f'Kingdee OK: {len(result)} records')
   asyncio.run(main())
   "
   ```

4. **Start server**:
   ```bash
   uvicorn src.main:app --reload
   ```

5. **Test authentication flow**:
   ```bash
   # Health check (no auth required)
   curl http://localhost:8000/health

   # Try without token (should return 401)
   curl http://localhost:8000/api/mto/AK2510034
   # Expected: {"detail":"Not authenticated"}

   # Get access token
   TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/token \
       -d "username=test&password=quickpulse" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
   echo "Token: $TOKEN"

   # Test with token (should work)
   curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/mto/AK2510034

   # Test sync endpoints
   curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/sync/status
   curl -H "Authorization: Bearer $TOKEN" -X POST http://localhost:8000/api/sync/trigger \
       -H "Content-Type: application/json" -d '{"days_back": 7}'
   ```

6. **Test mobile responsiveness**:
   - Open browser DevTools (F12)
   - Toggle device toolbar (Ctrl+Shift+M)
   - Select iPhone SE (375px width)
   - Verify:
     - [ ] BOM items display as cards (not table)
     - [ ] Touch targets are at least 44px
     - [ ] All content is readable without horizontal scroll
     - [ ] Accordion expands on tap

7. **Test accessibility**:
   ```bash
   # Install axe-cli for automated testing
   npm install -g @axe-core/cli

   # Run accessibility audit
   axe http://localhost:8000 --tags wcag2a,wcag2aa
   ```

   Manual checks:
   - [ ] Tab through entire page - all interactive elements focusable
   - [ ] Focus indicators visible
   - [ ] Screen reader announces content properly
   - [ ] Skip link works (Tab at page load)
   - [ ] Color contrast passes (use Chrome DevTools > Accessibility)

8. **Test Docker**:
   ```bash
   docker-compose up -d --build
   curl http://localhost:8000/health

   # Test auth in Docker
   TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/token \
       -d "username=test&password=quickpulse" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
   curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/sync/status
   ```

### Complete Verification Checklist

**Backend**:
- [ ] All imports work without errors
- [ ] Database initializes with WAL mode
- [ ] Kingdee client connects successfully
- [ ] JWT authentication works (login, protected routes)
- [ ] Rate limiting triggers after 30 requests/minute
- [ ] Sync service runs in background
- [ ] MTO query returns correct data

**Frontend**:
- [ ] Web UI loads at http://localhost:8000
- [ ] Search by MTO number works
- [ ] Parent item info displays correctly
- [ ] BOM table shows all child items
- [ ] Over-picked items highlighted in red
- [ ] syncControl panel visible and functional
- [ ] Manual sync can be triggered from UI
- [ ] Mobile card layout works (< 768px)
- [ ] Accessibility audit passes

**Docker**:
- [ ] Production build succeeds
- [ ] Container starts and passes health check
- [ ] Data persists via volumes
- [ ] Auto-sync scheduler runs on schedule

---

## Notes for AI Terminals

1. **Always reference** `IMPLEMENTATION_PLAN.md` for detailed code examples
2. **Run verification** after each task before marking done
3. **Communicate** completion to dependent terminals
4. **Ask questions** if requirements are unclear
5. **Don't skip** `__init__.py` files - they're needed for imports
